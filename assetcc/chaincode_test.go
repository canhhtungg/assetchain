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
	for _, actorID := range []string{"SYSTEM", "A001", "U001", "U100", "C001", "C002", "S001", "W001", "M001"} {
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

func seedTestUser(t *testing.T, context *contractapi.TransactionContext, user User) {
	t.Helper()
	data, err := json.Marshal(user)
	if err != nil {
		t.Fatal(err)
	}
	if err := context.GetStub().PutState("USER_"+user.ID, data); err != nil {
		t.Fatal(err)
	}
}

func createWorkflowTestUsers(t *testing.T, context *contractapi.TransactionContext, contract *SmartContract) {
	t.Helper()
	seedTestUser(t, context, User{ID: "A001", Username: "admin", FullName: "Admin", Role: "ADMIN"})
	users := []struct{ id, username, role, creator string }{
		{"M001", "manager", "MANAGER", "A001"},
		{"W001", "warehouse", "WAREHOUSE", "A001"},
		{"S001", "sales", "SALES", "A001"},
		{"C001", "customer1", "CUSTOMER", "A001"},
		{"C002", "customer2", "USER", "A001"},
	}
	for _, user := range users {
		if err := contract.CreateUser(context, user.id, user.username, user.username, user.role, "hash", "", user.creator); err != nil {
			t.Fatalf("failed to create %s: %v", user.id, err)
		}
	}
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
	seedTestUser(t, context, User{ID: "A001", Username: "admin", Role: "ADMIN"})

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
	seedTestUser(t, context, User{ID: "A001", Username: "admin", Role: "ADMIN"})
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
	seedTestUser(t, context, User{ID: "A001", Username: "admin", Role: "ADMIN"})
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
	seedTestUser(t, context, User{ID: "A001", Username: "admin", FullName: "Admin", Role: "ADMIN"})
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
	seedTestUser(t, context, User{ID: "A001", Username: "admin", FullName: "Admin", Role: "ADMIN"})
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
	seedTestUser(t, context, User{ID: "A001", Username: "admin", FullName: "Admin", Role: "ADMIN"})
	seedTestUser(t, context, User{ID: "S001", Username: "sales", FullName: "Sales", Role: "SALES"})
	if err := contract.CreateUser(context, "C001", "customer", "Customer", "CUSTOMER", "hash", "customer@example.com", "S001"); err != nil {
		t.Fatalf("failed to create customer: %v", err)
	}
	if err := contract.CreateAsset(context, "SKU-1", "Phone", "Phone", "STORE", 1000, "Active", "", "", 10, "A001"); err != nil {
		t.Fatalf("failed to create inventory: %v", err)
	}
	store, err := contract.GetUser(context, "STORE")
	if err != nil || store.Role != "STORE" {
		t.Fatalf("store owner was not created automatically: %#v, %v", store, err)
	}

	if err := contract.TransferAssetQuantity(context, "SKU-1", "C001", 3, "SALE-1", "A001"); err != nil {
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
	if sold.LastActorID != "A001" {
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
	if err := contract.DeleteAssetQuantity(context, "SALE-1", 2, "A001"); err != nil {
		t.Fatalf("DeleteAssetQuantity returned an error: %v", err)
	}
	remainingReturned, err := contract.ReadAsset(context, "SALE-1")
	if err != nil || remainingReturned.Quantity != 1 || remainingReturned.LastActorID != "A001" {
		t.Fatalf("unexpected quantity after partial delete: %#v, %v", remainingReturned, err)
	}
	if remainingReturned.LastOperation != "delete_quantity" {
		t.Fatalf("expected delete_quantity operation, got %q", remainingReturned.LastOperation)
	}
}

func TestAssetOperationsAndDeletionTombstone(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	seedTestUser(t, context, User{ID: "A001", Username: "admin", FullName: "Admin", Role: "ADMIN"})
	if err := contract.CreateUser(context, "C001", "customer", "Customer", "CUSTOMER", "hash", "", "A001"); err != nil {
		t.Fatalf("failed to create owner: %v", err)
	}
	if err := contract.CreateAsset(context, "A-OPS", "Laptop", "Computer", "C001", 100, "Active", "", "", 1, "A001"); err != nil {
		t.Fatalf("failed to create asset: %v", err)
	}
	created, err := contract.ReadAsset(context, "A-OPS")
	if err != nil || created.LastOperation != "create" {
		t.Fatalf("expected create operation: %#v, %v", created, err)
	}
	if err := contract.UpdateAsset(context, "A-OPS", "Laptop Pro", "Computer", "C001", 120, "Active", "", "", 1, "A001"); err != nil {
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
	seedTestUser(t, context, User{ID: "A001", Username: "admin", Role: "ADMIN"})
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

func TestUserManagementRejectsRoleEscalationAndPasswordTakeover(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	seedTestUser(t, context, User{ID: "A001", Username: "admin", FullName: "Admin", Role: "ADMIN"})
	if err := contract.CreateUser(context, "S001", "sales", "Sales", "SALES", "hash", "", "A001"); err != nil {
		t.Fatal(err)
	}
	if err := contract.CreateUser(context, "C001", "customer", "Customer", "CUSTOMER", "hash", "", "S001"); err != nil {
		t.Fatal(err)
	}
	if err := contract.CreateUser(context, "M999", "fake-manager", "Fake", "MANAGER", "hash", "", "S001"); err == nil {
		t.Fatal("sales user created a privileged account")
	}
	if err := contract.UpdateUser(context, "S001", "Sales", "MANAGER", "", "S001"); err == nil {
		t.Fatal("sales user escalated their own role")
	}
	if err := contract.SetUserPassword(context, "C001", "attacker-hash", "S001"); err == nil {
		t.Fatal("sales user changed another user's password")
	}
	if err := contract.SetUserPassword(context, "C001", "new-hash", "C001"); err != nil {
		t.Fatalf("customer could not change own password: %v", err)
	}
}

func TestAdminRegistersUniqueUserIdentity(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	seedTestUser(t, context, User{ID: "A001", Username: "admin", FullName: "Admin", Role: "ADMIN"})
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
	seedTestUser(t, context, User{ID: "U001", Username: "admin", FullName: "Admin", Role: "ADMIN"})
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
	seedTestUser(t, context, User{ID: "U001", Username: "admin", FullName: "Admin", Role: "ADMIN"})
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

func TestAssetCreationWorkflowApproveAndQueries(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	createWorkflowTestUsers(t, context, contract)

	requestItem, err := contract.SubmitAssetCreationRequest(
		context, "REQ-CREATE-1", "SKU-WF-1", "Phone", "Electronics", "STORE",
		1000, "Active", "SN-WF-1", "workflow asset", 5, "W001",
	)
	if err != nil || requestItem.Status != statusPendingApproval {
		t.Fatalf("unexpected creation request: %#v, %v", requestItem, err)
	}
	if _, err := contract.ReadAsset(context, "SKU-WF-1"); err == nil {
		t.Fatal("asset was created before checker approval")
	}
	if err := contract.CreateAsset(context, "WAREHOUSE-BYPASS", "Phone", "Electronics", "STORE", 1000, "Active", "", "", 1, "W001"); err == nil {
		t.Fatal("warehouse bypassed creation workflow through direct CreateAsset")
	}
	if err := contract.CreateAsset(context, "SKU-WF-1", "Phone", "Electronics", "STORE", 1000, "Active", "", "", 1, "A001"); err == nil {
		t.Fatal("admin direct create bypassed a pending asset ID lock")
	}
	assets, err := contract.GetAllAssets(context)
	if err != nil || len(assets) != 0 {
		t.Fatalf("workflow request leaked into asset scan: %#v, %v", assets, err)
	}
	requests, err := contract.ListWorkflowRequests(context)
	if err != nil || len(requests) != 1 || requests[0].ID != "REQ-CREATE-1" {
		t.Fatalf("workflow request query failed: %#v, %v", requests, err)
	}
	if _, err := contract.SubmitAssetCreationRequest(
		context, "REQ-CREATE-2", "SKU-WF-1", "Other", "Electronics", "STORE",
		1000, "Active", "", "", 1, "W001",
	); err == nil {
		t.Fatal("expected pending asset ID lock to reject duplicate asset ID")
	}
	approved, err := contract.ApproveWorkflowRequest(context, "REQ-CREATE-1", "stock verified", "M001")
	if err != nil || approved.Status != statusCompleted || approved.CheckerID != "M001" {
		t.Fatalf("creation approval failed: %#v, %v", approved, err)
	}
	asset, err := contract.ReadAsset(context, "SKU-WF-1")
	if err != nil || asset.Quantity != 5 || asset.ReservedQuantity != 0 || asset.LastActorID != "M001" {
		t.Fatalf("approved asset is incorrect: %#v, %v", asset, err)
	}
	if _, err := contract.ApproveWorkflowRequest(context, "REQ-CREATE-1", "again", "A001"); err == nil {
		t.Fatal("expected repeated approval to fail")
	}
}

func TestAssetCreationWorkflowRejectAndMakerRoleFailures(t *testing.T) {
	context, stub := newTestContext(t)
	contract := new(SmartContract)
	createWorkflowTestUsers(t, context, contract)
	if _, err := contract.SubmitAssetCreationRequest(
		context, "REQ-CREATE-R", "SKU-REJECT", "Phone", "Electronics", "STORE",
		1000, "Active", "", "", 2, "S001",
	); err == nil {
		t.Fatal("expected sales user to be rejected as creation maker")
	}
	if _, err := contract.SubmitAssetCreationRequest(
		context, "REQ-CREATE-R", "SKU-REJECT", "Phone", "Electronics", "STORE",
		1000, "Active", "", "", 2, "W001",
	); err != nil {
		t.Fatalf("creation submission failed: %v", err)
	}
	warehouse, _ := contract.GetUser(context, "W001")
	warehouse.Role = "MANAGER"
	data, _ := json.Marshal(warehouse)
	stub.State["USER_W001"] = data
	if _, err := contract.ApproveWorkflowRequest(context, "REQ-CREATE-R", "self", "W001"); err == nil {
		t.Fatal("expected maker self-approval to fail")
	}
	rejected, err := contract.RejectWorkflowRequest(context, "REQ-CREATE-R", "invalid serial", "M001")
	if err != nil || rejected.Status != statusRejected || rejected.Reason != "invalid serial" {
		t.Fatalf("creation rejection failed: %#v, %v", rejected, err)
	}
	if _, err := contract.SubmitAssetCreationRequest(
		context, "REQ-CREATE-R2", "SKU-REJECT", "Phone", "Electronics", "STORE",
		1000, "Active", "", "", 2, "W001",
	); err == nil {
		t.Fatal("role-changed maker should not be able to submit")
	}
}

func TestInventoryTransferWorkflowAcceptsOnlyAfterApproval(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	createWorkflowTestUsers(t, context, contract)
	if err := contract.CreateAsset(context, "SKU-T", "Phone", "Electronics", "STORE", 1000, "Active", "", "", 10, "A001"); err != nil {
		t.Fatalf("failed to create inventory: %v", err)
	}
	item, err := contract.SubmitInventoryTransferRequest(context, "REQ-T-1", "SKU-T", "C001", 3, "SALE-T-1", "S001")
	if err != nil || item.Status != statusPendingApproval {
		t.Fatalf("transfer submission failed: %#v, %v", item, err)
	}
	asset, _ := contract.ReadAsset(context, "SKU-T")
	if asset.Quantity != 10 || asset.OwnerID != "STORE" || asset.ReservedQuantity != 3 {
		t.Fatalf("submission mutated ownership/quantity instead of reservation: %#v", asset)
	}
	if err := contract.TransferAssetQuantity(context, "SKU-T", "C001", 1, "BYPASS", "S001"); err == nil {
		t.Fatal("sales bypassed workflow through direct transfer")
	}
	if err := contract.DeleteAssetQuantity(context, "SKU-T", 8, "A001"); err == nil {
		t.Fatal("delete consumed reserved inventory")
	}
	if err := contract.UpdateAsset(context, "SKU-T", "Changed", "Electronics", "STORE", 900, "Active", "", "", 10, "W001"); err == nil {
		t.Fatal("reserved asset metadata was updated while awaiting decisions")
	}
	approved, err := contract.ApproveWorkflowRequest(context, "REQ-T-1", "approved", "M001")
	if err != nil || approved.Status != statusAwaitingCustomer {
		t.Fatalf("transfer approval failed: %#v, %v", approved, err)
	}
	asset, _ = contract.ReadAsset(context, "SKU-T")
	if asset.Quantity != 10 || asset.ReservedQuantity != 3 {
		t.Fatalf("checker approval changed inventory: %#v", asset)
	}
	if _, err := contract.AcceptWorkflowRequest(context, "REQ-T-1", "wrong customer", "C002"); err == nil {
		t.Fatal("non-target customer accepted transfer")
	}
	completed, err := contract.AcceptWorkflowRequest(context, "REQ-T-1", "received", "C001")
	if err != nil || completed.Status != statusCompleted || completed.CustomerActorID != "C001" {
		t.Fatalf("customer acceptance failed: %#v, %v", completed, err)
	}
	remaining, _ := contract.ReadAsset(context, "SKU-T")
	sold, soldErr := contract.ReadAsset(context, "SALE-T-1")
	if remaining.Quantity != 7 || remaining.ReservedQuantity != 0 || soldErr != nil || sold.OwnerID != "C001" || sold.Quantity != 3 {
		t.Fatalf("unexpected accepted transfer assets: remaining=%#v sold=%#v err=%v", remaining, sold, soldErr)
	}
}

func TestInventoryTransferApprovalRequiresTargetFabricIdentity(t *testing.T) {
	context, stub := newTestContext(t)
	contract := new(SmartContract)
	createWorkflowTestUsers(t, context, contract)
	if err := contract.CreateAsset(context, "SKU-ID-GATE", "Phone", "Electronics", "STORE", 1000, "Active", "", "", 2, "A001"); err != nil {
		t.Fatalf("failed to create inventory: %v", err)
	}
	if _, err := contract.SubmitInventoryTransferRequest(context, "REQ-ID-GATE", "SKU-ID-GATE", "C001", 1, "SALE-ID-GATE", "S001"); err != nil {
		t.Fatalf("transfer submission failed: %v", err)
	}
	binding := stub.State[identityBindingKey("C001")]
	delete(stub.State, identityBindingKey("C001"))
	if _, err := contract.ApproveWorkflowRequest(context, "REQ-ID-GATE", "approve", "M001"); err == nil || !strings.Contains(err.Error(), "does not have a Fabric identity") {
		t.Fatalf("checker approved transfer without customer identity: %v", err)
	}
	pending, err := contract.ReadWorkflowRequest(context, "REQ-ID-GATE")
	if err != nil || pending.Status != statusPendingApproval {
		t.Fatalf("failed approval changed request state: %#v, %v", pending, err)
	}
	asset, err := contract.ReadAsset(context, "SKU-ID-GATE")
	if err != nil || asset.ReservedQuantity != 1 || asset.Quantity != 2 {
		t.Fatalf("failed approval changed reservation: %#v, %v", asset, err)
	}
	stub.State[identityBindingKey("C001")] = binding
	approved, err := contract.ApproveWorkflowRequest(context, "REQ-ID-GATE", "approve", "M001")
	if err != nil || approved.Status != statusAwaitingCustomer {
		t.Fatalf("approval failed after identity binding: %#v, %v", approved, err)
	}
}

func TestInventoryTransferRejectDeclineDuplicateAndUserReference(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	createWorkflowTestUsers(t, context, contract)
	if err := contract.CreateAsset(context, "SKU-R", "Phone", "Electronics", "STORE", 1000, "Active", "", "", 6, "A001"); err != nil {
		t.Fatalf("failed to create inventory: %v", err)
	}
	if _, err := contract.SubmitInventoryTransferRequest(context, "REQ-R-1", "SKU-R", "C001", 2, "SALE-R-1", "S001"); err != nil {
		t.Fatalf("first transfer submission failed: %v", err)
	}
	if _, err := contract.SubmitInventoryTransferRequest(context, "REQ-R-1", "SKU-R", "C001", 1, "SALE-R-2", "S001"); err == nil {
		t.Fatal("duplicate request ID was accepted")
	}
	if _, err := contract.SubmitInventoryTransferRequest(context, "REQ-R-2", "SKU-R", "C001", 1, "SALE-R-1", "S001"); err == nil {
		t.Fatal("duplicate pending new asset ID was accepted")
	}
	if err := contract.DeleteUser(context, "C001", "A001"); err == nil {
		t.Fatal("deleted customer referenced by nonterminal request")
	}
	if _, err := contract.RejectWorkflowRequest(context, "REQ-R-1", "not approved", "A001"); err != nil {
		t.Fatalf("transfer rejection failed: %v", err)
	}
	asset, _ := contract.ReadAsset(context, "SKU-R")
	if asset.ReservedQuantity != 0 || asset.Quantity != 6 {
		t.Fatalf("rejection did not release reservation: %#v", asset)
	}
	if _, err := contract.SubmitInventoryTransferRequest(context, "REQ-R-3", "SKU-R", "C002", 2, "SALE-R-1", "S001"); err != nil {
		t.Fatalf("legacy USER customer role or released asset ID was not accepted: %v", err)
	}
	if _, err := contract.ApproveWorkflowRequest(context, "REQ-R-3", "ok", "M001"); err != nil {
		t.Fatalf("approval before decline failed: %v", err)
	}
	declined, err := contract.DeclineWorkflowRequest(context, "REQ-R-3", "changed mind", "C002")
	if err != nil || declined.Status != statusDeclined {
		t.Fatalf("decline failed: %#v, %v", declined, err)
	}
	asset, _ = contract.ReadAsset(context, "SKU-R")
	if asset.ReservedQuantity != 0 || asset.Quantity != 6 {
		t.Fatalf("decline did not release reservation: %#v", asset)
	}
}

func TestTransferReservationsUseAvailableQuantityWithoutReducingTotal(t *testing.T) {
	context, _ := newTestContext(t)
	contract := new(SmartContract)
	createWorkflowTestUsers(t, context, contract)
	if err := contract.CreateAsset(context, "SKU-AVAILABLE", "Phone", "Electronics", "STORE", 1000, "Active", "", "", 5, "A001"); err != nil {
		t.Fatalf("failed to create inventory: %v", err)
	}
	if _, err := contract.SubmitInventoryTransferRequest(context, "REQ-A-1", "SKU-AVAILABLE", "C001", 3, "SALE-A-1", "S001"); err != nil {
		t.Fatalf("first reservation failed: %v", err)
	}
	if _, err := contract.SubmitInventoryTransferRequest(context, "REQ-A-2", "SKU-AVAILABLE", "C002", 3, "SALE-A-2", "S001"); err == nil {
		t.Fatal("reservation exceeded available quantity")
	}
	asset, err := contract.ReadAsset(context, "SKU-AVAILABLE")
	if err != nil || asset.Quantity != 5 || asset.ReservedQuantity != 3 || availableQuantity(asset) != 2 {
		t.Fatalf("reservation did not preserve total and track availability: %#v, %v", asset, err)
	}
	if _, err := contract.RejectWorkflowRequest(context, "REQ-A-1", "declined", "M001"); err != nil {
		t.Fatalf("rejection failed: %v", err)
	}
	asset, err = contract.ReadAsset(context, "SKU-AVAILABLE")
	if err != nil || asset.Quantity != 5 || asset.ReservedQuantity != 0 || availableQuantity(asset) != 5 {
		t.Fatalf("rejection did not restore availability: %#v, %v", asset, err)
	}
}

func TestLegacyAssetDefaultsReservedQuantityToZero(t *testing.T) {
	context, stub := newTestContext(t)
	contract := new(SmartContract)
	stub.State["LEGACY-RES"] = []byte(`{"id":"LEGACY-RES","quantity":4,"ownerID":"STORE"}`)
	asset, err := contract.ReadAsset(context, "LEGACY-RES")
	if err != nil || asset.ReservedQuantity != 0 {
		t.Fatalf("legacy reservation default failed: %#v, %v", asset, err)
	}
}

func TestWorkflowRequestJSONIncludesEmptySchemaFields(t *testing.T) {
	data, err := json.Marshal(&WorkflowRequest{ID: "REQ-SCHEMA", Type: requestTypeCreation, Status: statusPendingApproval})
	if err != nil {
		t.Fatalf("marshal workflow request: %v", err)
	}
	var payload map[string]interface{}
	if err := json.Unmarshal(data, &payload); err != nil {
		t.Fatalf("unmarshal workflow request: %v", err)
	}
	for _, field := range []string{
		"newAssetID", "targetCustomerID", "name", "assetType", "ownerID", "value",
		"assetStatus", "serialNumber", "description", "checkerID", "checkedAt",
		"customerActorID", "customerActedAt", "reason",
	} {
		if _, ok := payload[field]; !ok {
			t.Fatalf("workflow response omitted schema-required field %q: %s", field, data)
		}
	}
}
