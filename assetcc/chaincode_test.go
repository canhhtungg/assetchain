package main

import (
	"encoding/json"
	"testing"

	"github.com/hyperledger/fabric-chaincode-go/shimtest"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

func newTestContext(t *testing.T) (*contractapi.TransactionContext, *shimtest.MockStub) {
	t.Helper()
	stub := shimtest.NewMockStub("assetcc", nil)
	stub.MockTransactionStart("tx-1")
	context := new(contractapi.TransactionContext)
	context.SetStub(stub)
	t.Cleanup(func() { stub.MockTransactionEnd("tx-1") })
	return context, stub
}

func TestCreateUserStoresCredentialSeparately(t *testing.T) {
	context, stub := newTestContext(t)
	contract := new(SmartContract)

	if err := contract.CreateUser(
		context, "U100", "Alice", "Alice Nguyen", "USER", "test-password-hash", "alice@example.com", "A001",
	); err != nil {
		t.Fatalf("CreateUser returned an error: %v", err)
	}

	var user map[string]any
	if err := json.Unmarshal(stub.State["USER_U100"], &user); err != nil {
		t.Fatalf("failed to decode stored user: %v", err)
	}
	if _, exposed := user["passwordHash"]; exposed {
		t.Fatal("public user record exposed passwordHash")
	}
	if user["contact"] != "alice@example.com" || user["createdBy"] != "A001" {
		t.Fatalf("unexpected public profile metadata: %#v", user)
	}
	if err := contract.UpdateUser(context, "U100", "Alice Updated", "CUSTOMER", "0900000000"); err != nil {
		t.Fatalf("UpdateUser returned an error: %v", err)
	}
	updated, err := contract.GetUser(context, "U100")
	if err != nil || updated.FullName != "Alice Updated" || updated.Contact != "0900000000" {
		t.Fatalf("unexpected updated user: %#v, %v", updated, err)
	}

	passwordHash, err := contract.GetPasswordHash(context, "alice")
	if err != nil {
		t.Fatalf("GetPasswordHash returned an error: %v", err)
	}
	if passwordHash != "test-password-hash" {
		t.Fatalf("unexpected password hash: %q", passwordHash)
	}
}

func TestCreateUserRejectsDuplicateUsernameIgnoringCase(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	if err := contract.CreateUser(
		context, "U100", "Alice", "Alice Nguyen", "USER", "first-hash", "", "A001",
	); err != nil {
		t.Fatalf("first CreateUser returned an error: %v", err)
	}
	if err := contract.CreateUser(
		context, "U101", " alice ", "Other Alice", "USER", "second-hash", "", "A001",
	); err == nil {
		t.Fatal("expected duplicate username to be rejected")
	}
}

func TestDeleteUserRemovesProfileAndCredential(t *testing.T) {
	context, stub := newTestContext(t)
	contract := new(SmartContract)
	if err := contract.CreateUser(context, "A001", "admin", "Admin", "ADMIN", "admin-hash", "", "SYSTEM"); err != nil {
		t.Fatalf("failed to create admin: %v", err)
	}
	if err := contract.CreateUser(context, "U100", "alice", "Alice", "USER", "alice-hash", "", "A001"); err != nil {
		t.Fatalf("failed to create user: %v", err)
	}

	if err := contract.DeleteUser(context, "U100"); err != nil {
		t.Fatalf("DeleteUser returned an error: %v", err)
	}
	if stub.State["USER_U100"] != nil || stub.State["AUTH_alice"] != nil {
		t.Fatal("user profile or credential remains after deletion")
	}
}

func TestDeleteUserRejectsOwnedAssetsAndLastAdmin(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	if err := contract.CreateUser(context, "A001", "admin", "Admin", "ADMIN", "admin-hash", "", "SYSTEM"); err != nil {
		t.Fatalf("failed to create admin: %v", err)
	}
	if err := contract.CreateUser(context, "U100", "alice", "Alice", "USER", "alice-hash", "", "A001"); err != nil {
		t.Fatalf("failed to create user: %v", err)
	}
	if err := contract.CreateAsset(context, "ASSET-1", "Laptop", "Computer", "U100", 100, "ACTIVE", "SN-1", "", 1, "A001"); err != nil {
		t.Fatalf("failed to create asset: %v", err)
	}

	if err := contract.DeleteUser(context, "U100"); err == nil {
		t.Fatal("expected user with assets to be rejected")
	}
	if err := contract.DeleteUser(context, "A001"); err == nil {
		t.Fatal("expected last admin deletion to be rejected")
	}
}

func TestStoreInventoryQuantityAndPartialSale(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	if err := contract.CreateUser(context, "C001", "customer", "Customer", "CUSTOMER", "hash", "customer@example.com", "S001"); err != nil {
		t.Fatalf("failed to create customer: %v", err)
	}
	if err := contract.CreateAsset(context, "SKU-1", "Phone", "Phone", "STORE", 1000, "Active", "", "", 10, "W001"); err != nil {
		t.Fatalf("failed to create inventory: %v", err)
	}
	store, err := contract.GetUser(context, "STORE")
	if err != nil || store.Role != "STORE" {
		t.Fatalf("store owner was not created automatically: %#v, %v", store, err)
	}

	if err := contract.TransferAssetQuantity(context, "SKU-1", "C001", 3, "SALE-1", "S001"); err != nil {
		t.Fatalf("TransferAssetQuantity returned an error: %v", err)
	}
	remaining, err := contract.ReadAsset(context, "SKU-1")
	if err != nil || remaining.Quantity != 7 || remaining.OwnerID != "STORE" {
		t.Fatalf("unexpected remaining inventory: %#v, %v", remaining, err)
	}
	sold, err := contract.ReadAsset(context, "SALE-1")
	if err != nil || sold.Quantity != 3 || sold.OwnerID != "C001" {
		t.Fatalf("unexpected sold asset: %#v, %v", sold, err)
	}
	if sold.LastActorID != "S001" {
		t.Fatalf("expected sales actor, got %q", sold.LastActorID)
	}
	if err := contract.ReturnAssetToStore(context, "SALE-1", "C001"); err != nil {
		t.Fatalf("ReturnAssetToStore returned an error: %v", err)
	}
	returned, err := contract.ReadAsset(context, "SALE-1")
	if err != nil || returned.OwnerID != "STORE" || returned.Status != "Active" {
		t.Fatalf("unexpected returned asset: %#v, %v", returned, err)
	}
	if err := contract.DeleteAssetQuantity(context, "SALE-1", 2, "C001"); err != nil {
		t.Fatalf("DeleteAssetQuantity returned an error: %v", err)
	}
	remainingReturned, err := contract.ReadAsset(context, "SALE-1")
	if err != nil || remainingReturned.Quantity != 1 || remainingReturned.LastActorID != "C001" {
		t.Fatalf("unexpected quantity after partial delete: %#v, %v", remainingReturned, err)
	}
}

func TestLegacyAssetDefaultsToQuantityOne(t *testing.T) {
	context, stub := newTestContext(t)
	contract := new(SmartContract)
	stub.State["LEGACY-1"] = []byte(`{"id":"LEGACY-1","name":"Legacy","ownerID":"STORE"}`)
	asset, err := contract.ReadAsset(context, "LEGACY-1")
	if err != nil {
		t.Fatalf("ReadAsset returned an error: %v", err)
	}
	if asset.Quantity != 1 {
		t.Fatalf("expected legacy quantity 1, got %d", asset.Quantity)
	}
}
