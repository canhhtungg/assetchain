package main

import (
	"crypto/sha256"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"github.com/hyperledger/fabric-chaincode-go/shimtest"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type privateDataMockStub struct {
	*shimtest.MockStub
}

type testClientIdentity struct {
	mspID string
	cert  *x509.Certificate
}

func (identity *testClientIdentity) GetID() (string, error)    { return "test-id", nil }
func (identity *testClientIdentity) GetMSPID() (string, error) { return identity.mspID, nil }
func (identity *testClientIdentity) GetAttributeValue(string) (string, bool, error) {
	return "", false, nil
}
func (identity *testClientIdentity) AssertAttributeValue(string, string) error {
	return fmt.Errorf("attribute unavailable")
}
func (identity *testClientIdentity) GetX509Certificate() (*x509.Certificate, error) {
	return identity.cert, nil
}

func (stub *privateDataMockStub) DelPrivateData(collection string, key string) error {
	if values := stub.PvtState[collection]; values != nil {
		delete(values, key)
	}
	return nil
}

func newTestContext(t *testing.T) (*contractapi.TransactionContext, *privateDataMockStub) {
	t.Helper()
	t.Setenv("USER_CREDENTIAL_PDC_ENABLED", "true")
	stub := &privateDataMockStub{shimtest.NewMockStub("assetcc", nil)}
	stub.MockTransactionStart("tx-1")
	context := new(contractapi.TransactionContext)
	context.SetStub(stub)
	certificate := &x509.Certificate{Raw: []byte("assetchain-test-certificate")}
	context.SetClientIdentity(&testClientIdentity{mspID: "Org1MSP", cert: certificate})
	fingerprint := fmt.Sprintf("%x", sha256.Sum256(certificate.Raw))
	for _, actorID := range []string{"SYSTEM", "A001", "U001", "U100", "C001", "S001", "W001", "M001"} {
		binding, err := json.Marshal(FabricIdentityBinding{
			UserID: actorID, MSPID: "Org1MSP", CertificateFingerprint: fingerprint,
		})
		if err != nil {
			t.Fatalf("failed to create test binding: %v", err)
		}
		stub.State[identityBindingKey(actorID)] = binding
	}
	t.Cleanup(func() { stub.MockTransactionEnd("tx-1") })
	return context, stub
}

func TestCredentialCompatibilityModeUsesWorldState(t *testing.T) {
	context, stub := newTestContext(t)
	t.Setenv("USER_CREDENTIAL_PDC_ENABLED", "false")
	credential := UserCredential{Username: "legacy-mode", PasswordHash: "hash"}
	data, err := json.Marshal(credential)
	if err != nil {
		t.Fatal(err)
	}
	if err := putCredentialState(context, "AUTH_legacy-mode", data); err != nil {
		t.Fatalf("putCredentialState returned an error: %v", err)
	}
	if stub.State["AUTH_legacy-mode"] == nil {
		t.Fatal("compatibility mode did not use world state")
	}
	if stub.PvtState[credentialCollection]["AUTH_legacy-mode"] != nil {
		t.Fatal("compatibility mode unexpectedly wrote private data")
	}
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
	if stub.State["AUTH_alice"] != nil {
		t.Fatal("credential hash was written to public world state")
	}
	if stub.PvtState[credentialCollection]["AUTH_alice"] == nil {
		t.Fatal("credential hash was not written to the private collection")
	}
	if user["contact"] != "alice@example.com" || user["createdBy"] != "A001" {
		t.Fatalf("unexpected public profile metadata: %#v", user)
	}
	if err := contract.UpdateUser(context, "U100", "Alice Updated", "CUSTOMER", "0900000000", "A001"); err != nil {
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

func TestMigrateLegacyCredentialToPrivateData(t *testing.T) {
	context, stub := newTestContext(t)
	contract := new(SmartContract)
	stub.State["AUTH_legacy"] = []byte(`{"username":"legacy","passwordHash":"hash"}`)

	if err := contract.MigrateUserCredential(context, "legacy", "A001"); err != nil {
		t.Fatalf("MigrateUserCredential returned an error: %v", err)
	}
	if stub.State["AUTH_legacy"] != nil {
		t.Fatal("legacy credential remains in public world state")
	}
	if string(stub.PvtState[credentialCollection]["AUTH_legacy"]) == "" {
		t.Fatal("credential was not copied to private data")
	}
	passwordHash, err := contract.GetPasswordHash(context, "legacy")
	if err != nil || passwordHash != "hash" {
		t.Fatalf("private credential unavailable after migration: %q, %v", passwordHash, err)
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

	if err := contract.DeleteUser(context, "U100", "A001"); err != nil {
		t.Fatalf("DeleteUser returned an error: %v", err)
	}
	if stub.State["USER_U100"] != nil || stub.State["AUTH_alice"] != nil ||
		stub.PvtState[credentialCollection]["AUTH_alice"] != nil {
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

	if err := contract.DeleteUser(context, "U100", "A001"); err == nil {
		t.Fatal("expected user with assets to be rejected")
	}
	if err := contract.DeleteUser(context, "A001", "A001"); err == nil {
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
	if sold.LastOperation != "transfer" || remaining.LastOperation != "update" {
		t.Fatalf("unexpected sale operations: sold=%q remaining=%q", sold.LastOperation, remaining.LastOperation)
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
	if remainingReturned.LastOperation != "delete_quantity" {
		t.Fatalf("expected delete_quantity operation, got %q", remainingReturned.LastOperation)
	}
}

func TestAssetOperationsAndDeletionTombstone(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	if err := contract.CreateUser(context, "C001", "customer", "Customer", "CUSTOMER", "hash", "", "A001"); err != nil {
		t.Fatalf("failed to create owner: %v", err)
	}
	if err := contract.CreateAsset(context, "A-OPS", "Laptop", "Computer", "C001", 100, "Active", "", "", 1, "W001"); err != nil {
		t.Fatalf("failed to create asset: %v", err)
	}
	created, err := contract.ReadAsset(context, "A-OPS")
	if err != nil || created.LastOperation != "create" {
		t.Fatalf("expected create operation: %#v, %v", created, err)
	}
	if err := contract.UpdateAsset(context, "A-OPS", "Laptop Pro", "Computer", "C001", 120, "Active", "", "", 1, "W001"); err != nil {
		t.Fatalf("failed to update asset: %v", err)
	}
	updated, err := contract.ReadAsset(context, "A-OPS")
	if err != nil || updated.LastOperation != "update" {
		t.Fatalf("expected update operation: %#v, %v", updated, err)
	}
	if err := contract.DeleteAssetQuantity(context, "A-OPS", 1, "C001"); err != nil {
		t.Fatalf("failed to delete asset: %v", err)
	}
	if _, err := contract.ReadAsset(context, "A-OPS"); err == nil {
		t.Fatal("deleted asset should not be readable as active")
	}
	tombstone, err := contract.ReadAssetRecord(context, "A-OPS")
	if err != nil || !tombstone.Deleted || tombstone.LastOperation != "delete" || tombstone.LastActorID != "C001" {
		t.Fatalf("unexpected deletion tombstone: %#v, %v", tombstone, err)
	}
	active, err := contract.GetAllAssets(context)
	if err != nil || len(active) != 0 {
		t.Fatalf("deleted asset leaked into active list: %#v, %v", active, err)
	}
	records, err := contract.GetAllAssetRecords(context)
	if err != nil || len(records) != 1 || !records[0].Deleted {
		t.Fatalf("deletion tombstone missing from history index: %#v, %v", records, err)
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

func TestMutationRejectsActorWhoseCertificateDoesNotMatch(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	if err := contract.CreateUser(context, "U200", "user200", "User 200", "CUSTOMER", "hash", "", "A001"); err != nil {
		t.Fatalf("failed to create test user: %v", err)
	}
	context.SetClientIdentity(&testClientIdentity{
		mspID: "Org1MSP", cert: &x509.Certificate{Raw: []byte("different-certificate")},
	})
	if err := contract.UpdateUser(context, "U200", "Changed", "CUSTOMER", "", "A001"); err == nil {
		t.Fatal("expected mismatched invoker certificate to be rejected")
	}
	user, err := contract.GetUser(context, "U200")
	if err != nil || user.FullName != "User 200" {
		t.Fatalf("rejected mutation changed state: %#v, %v", user, err)
	}
}

func TestAdminRegistersUniqueUserIdentity(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	if err := contract.CreateUser(context, "A001", "admin", "Admin", "ADMIN", "hash", "", "A001"); err != nil {
		t.Fatalf("failed to create admin: %v", err)
	}
	if err := contract.CreateUser(context, "C200", "customer200", "Customer", "CUSTOMER", "hash", "", "A001"); err != nil {
		t.Fatalf("failed to create customer: %v", err)
	}
	if err := contract.CreateUser(context, "C201", "customer201", "Customer 2", "CUSTOMER", "hash", "", "A001"); err != nil {
		t.Fatalf("failed to create second customer: %v", err)
	}
	fingerprint := strings.Repeat("b", 64)
	if err := contract.RegisterUserIdentity(context, "C200", "Org1MSP", fingerprint, "A001"); err != nil {
		t.Fatalf("RegisterUserIdentity returned an error: %v", err)
	}
	binding, err := contract.GetUserIdentity(context, "C200")
	if err != nil || binding.CertificateFingerprint != fingerprint || binding.BoundBy != "A001" {
		t.Fatalf("unexpected identity binding: %#v, %v", binding, err)
	}
	if err := contract.RegisterUserIdentity(context, "C201", "Org1MSP", fingerprint, "A001"); err == nil {
		t.Fatal("expected duplicate certificate binding to be rejected")
	}
}

func TestBootstrapIsDisabledWithoutExplicitAllowlist(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	if err := contract.CreateUser(context, "U001", "admin", "Admin", "ADMIN", "hash", "", "A001"); err != nil {
		t.Fatalf("failed to create admin: %v", err)
	}
	t.Setenv("IDENTITY_BOOTSTRAP_USER_ID", "")
	t.Setenv("IDENTITY_BOOTSTRAP_MSP_ID", "")
	t.Setenv("IDENTITY_BOOTSTRAP_CERT_FINGERPRINT", "")
	if err := contract.BootstrapAdminIdentity(context, "U001"); err == nil {
		t.Fatal("expected bootstrap to be disabled by default")
	}
}

func TestBootstrapBindsAllowlistedAdminExactlyOnce(t *testing.T) {
	context, stub := newTestContext(t)
	contract := new(SmartContract)
	if err := contract.CreateUser(context, "U001", "admin", "Admin", "ADMIN", "hash", "", "A001"); err != nil {
		t.Fatalf("failed to create admin: %v", err)
	}
	delete(stub.State, identityBindingKey("U001"))
	certificate, err := context.GetClientIdentity().GetX509Certificate()
	if err != nil {
		t.Fatalf("failed to read test certificate: %v", err)
	}
	fingerprint := fmt.Sprintf("%x", sha256.Sum256(certificate.Raw))
	t.Setenv("IDENTITY_BOOTSTRAP_USER_ID", "U001")
	t.Setenv("IDENTITY_BOOTSTRAP_MSP_ID", "Org1MSP")
	t.Setenv("IDENTITY_BOOTSTRAP_CERT_FINGERPRINT", fingerprint)
	if err := contract.BootstrapAdminIdentity(context, "U001"); err != nil {
		t.Fatalf("BootstrapAdminIdentity returned an error: %v", err)
	}
	if _, err := contract.GetUserIdentity(context, "U001"); err != nil {
		t.Fatalf("bootstrap binding was not stored: %v", err)
	}
	if err := contract.BootstrapAdminIdentity(context, "U001"); err == nil {
		t.Fatal("expected second bootstrap to be rejected")
	}
}
