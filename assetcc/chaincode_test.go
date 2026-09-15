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
		context, "U100", "Alice", "Alice Nguyen", "USER", "test-password-hash",
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
		context, "U100", "Alice", "Alice Nguyen", "USER", "first-hash",
	); err != nil {
		t.Fatalf("first CreateUser returned an error: %v", err)
	}
	if err := contract.CreateUser(
		context, "U101", " alice ", "Other Alice", "USER", "second-hash",
	); err == nil {
		t.Fatal("expected duplicate username to be rejected")
	}
}

func TestDeleteUserRemovesProfileAndCredential(t *testing.T) {
	context, stub := newTestContext(t)
	contract := new(SmartContract)
	if err := contract.CreateUser(context, "A001", "admin", "Admin", "ADMIN", "admin-hash"); err != nil {
		t.Fatalf("failed to create admin: %v", err)
	}
	if err := contract.CreateUser(context, "U100", "alice", "Alice", "USER", "alice-hash"); err != nil {
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
	if err := contract.CreateUser(context, "A001", "admin", "Admin", "ADMIN", "admin-hash"); err != nil {
		t.Fatalf("failed to create admin: %v", err)
	}
	if err := contract.CreateUser(context, "U100", "alice", "Alice", "USER", "alice-hash"); err != nil {
		t.Fatalf("failed to create user: %v", err)
	}
	if err := contract.CreateAsset(context, "ASSET-1", "Laptop", "Computer", "U100", 100, "ACTIVE", "SN-1", ""); err != nil {
		t.Fatalf("failed to create asset: %v", err)
	}

	if err := contract.DeleteUser(context, "U100"); err == nil {
		t.Fatal("expected user with assets to be rejected")
	}
	if err := contract.DeleteUser(context, "A001"); err == nil {
		t.Fatal("expected last admin deletion to be rejected")
	}
}
