package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type SmartContract struct {
	contractapi.Contract
}

const credentialCollection = "userCredentials"

func credentialPrivateDataEnabled() bool {
	return strings.EqualFold(strings.TrimSpace(os.Getenv("USER_CREDENTIAL_PDC_ENABLED")), "true")
}

func getCredentialState(ctx contractapi.TransactionContextInterface, key string) ([]byte, error) {
	if credentialPrivateDataEnabled() {
		data, err := ctx.GetStub().GetPrivateData(credentialCollection, key)
		if err != nil || data != nil {
			return data, err
		}
	}
	return ctx.GetStub().GetState(key)
}

func putCredentialState(ctx contractapi.TransactionContextInterface, key string, data []byte) error {
	if credentialPrivateDataEnabled() {
		if err := ctx.GetStub().PutPrivateData(credentialCollection, key, data); err != nil {
			return err
		}
		return ctx.GetStub().DelState(key)
	}
	return ctx.GetStub().PutState(key, data)
}

func deleteCredentialState(ctx contractapi.TransactionContextInterface, key string) error {
	if credentialPrivateDataEnabled() {
		if err := ctx.GetStub().DelPrivateData(credentialCollection, key); err != nil {
			return err
		}
	}
	return ctx.GetStub().DelState(key)
}

// ================================
// USER
// ================================

type User struct {
	ID        string `json:"id"`
	Username  string `json:"username"`
	FullName  string `json:"fullName"`
	Role      string `json:"role"`
	Contact   string `json:"contact"`
	CreatedBy string `json:"createdBy"`
	CreatedAt string `json:"createdAt"`
}

// UserCredential is stored separately so user-list queries never expose password hashes.
type UserCredential struct {
	Username     string `json:"username"`
	PasswordHash string `json:"passwordHash"`
}

// FabricIdentityBinding binds an application user to the certificate that must
// sign their mutations. Only public certificate metadata is stored on-ledger.
type FabricIdentityBinding struct {
	UserID                 string `json:"userID"`
	MSPID                  string `json:"mspID"`
	CertificateFingerprint string `json:"certificateFingerprint"`
	BoundBy                string `json:"boundBy"`
	BoundAt                string `json:"boundAt"`
}

const identityBootstrapMarker = "IDENTITY_BOOTSTRAP_COMPLETE"

func identityBindingKey(userID string) string {
	return "IDENTITY_BINDING_" + strings.TrimSpace(userID)
}

func identityFingerprintKey(mspID string, fingerprint string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(mspID) + "\x00" + strings.ToLower(strings.TrimSpace(fingerprint))))
	return fmt.Sprintf("IDENTITY_FINGERPRINT_%x", digest[:])
}

func invokerIdentity(ctx contractapi.TransactionContextInterface) (string, string, error) {
	identity := ctx.GetClientIdentity()
	if identity == nil {
		return "", "", fmt.Errorf("invoker Fabric identity is unavailable")
	}
	mspID, err := identity.GetMSPID()
	if err != nil || strings.TrimSpace(mspID) == "" {
		return "", "", fmt.Errorf("cannot determine invoker MSPID")
	}
	certificate, err := identity.GetX509Certificate()
	if err != nil || certificate == nil || len(certificate.Raw) == 0 {
		return "", "", fmt.Errorf("invoker must use an X.509 certificate")
	}
	fingerprint := sha256.Sum256(certificate.Raw)
	return strings.TrimSpace(mspID), fmt.Sprintf("%x", fingerprint[:]), nil
}

func (s *SmartContract) verifyMutationActor(ctx contractapi.TransactionContextInterface, actorID string) error {
	actorID = strings.TrimSpace(actorID)
	if actorID == "" {
		return fmt.Errorf("actorID is required")
	}
	data, err := ctx.GetStub().GetState(identityBindingKey(actorID))
	if err != nil {
		return err
	}
	if data == nil {
		return fmt.Errorf("Fabric identity is not bound for actor %s", actorID)
	}
	var binding FabricIdentityBinding
	if err := json.Unmarshal(data, &binding); err != nil {
		return err
	}
	mspID, fingerprint, err := invokerIdentity(ctx)
	if err != nil {
		return err
	}
	if !strings.EqualFold(binding.MSPID, mspID) ||
		!strings.EqualFold(binding.CertificateFingerprint, fingerprint) {
		return fmt.Errorf("actor %s does not match invoker Fabric identity", actorID)
	}
	return nil
}

func transactionTime(ctx contractapi.TransactionContextInterface) string {
	if timestamp, err := ctx.GetStub().GetTxTimestamp(); err == nil && timestamp != nil {
		return timestamp.AsTime().UTC().Format(time.RFC3339)
	}
	return ""
}

func (s *SmartContract) putIdentityBinding(
	ctx contractapi.TransactionContextInterface,
	userID string,
	mspID string,
	fingerprint string,
	boundBy string,
	replace bool,
) error {
	userID = strings.TrimSpace(userID)
	mspID = strings.TrimSpace(mspID)
	fingerprint = strings.ToLower(strings.TrimSpace(fingerprint))
	if userID == "" || mspID == "" || len(fingerprint) != 64 {
		return fmt.Errorf("userID, MSPID and SHA-256 certificate fingerprint are required")
	}
	for _, character := range fingerprint {
		if !strings.ContainsRune("0123456789abcdef", character) {
			return fmt.Errorf("certificate fingerprint must be lowercase hexadecimal SHA-256")
		}
	}
	userExists, err := s.UserExists(ctx, userID)
	if err != nil {
		return err
	}
	if !userExists {
		return fmt.Errorf("user %s does not exist", userID)
	}
	key := identityBindingKey(userID)
	existing, err := ctx.GetStub().GetState(key)
	if err != nil {
		return err
	}
	if existing != nil && !replace {
		return fmt.Errorf("Fabric identity already exists for user %s", userID)
	}
	reverseKey := identityFingerprintKey(mspID, fingerprint)
	assignedUser, err := ctx.GetStub().GetState(reverseKey)
	if err != nil {
		return err
	}
	if assignedUser != nil && string(assignedUser) != userID {
		return fmt.Errorf("Fabric identity is already bound to another user")
	}
	if existing != nil && replace {
		var old FabricIdentityBinding
		if err := json.Unmarshal(existing, &old); err != nil {
			return err
		}
		if err := ctx.GetStub().DelState(identityFingerprintKey(old.MSPID, old.CertificateFingerprint)); err != nil {
			return err
		}
	}
	binding := FabricIdentityBinding{
		UserID: userID, MSPID: mspID, CertificateFingerprint: fingerprint,
		BoundBy: strings.TrimSpace(boundBy), BoundAt: transactionTime(ctx),
	}
	data, err := json.Marshal(binding)
	if err != nil {
		return err
	}
	if err := ctx.GetStub().PutState(key, data); err != nil {
		return err
	}
	return ctx.GetStub().PutState(reverseKey, []byte(userID))
}

// ================================
// ASSET
// ================================

type Asset struct {
	ID            string `json:"id"`
	Name          string `json:"name"`
	Type          string `json:"type"`
	OwnerID       string `json:"ownerID"`
	Value         int    `json:"value"`
	Quantity      int    `json:"quantity"`
	Status        string `json:"status"`
	SerialNumber  string `json:"serialNumber"`
	Description   string `json:"description"`
	LastActorID   string `json:"lastActorID"`
	LastOperation string `json:"lastOperation"`
	Deleted       bool   `json:"deleted"`
}

// ================================
// HISTORY
// ================================

type AssetHistory struct {
	TxID      string `json:"txID"`
	Timestamp string `json:"timestamp"`
	IsDelete  bool   `json:"isDelete"`
	Value     *Asset `json:"value,omitempty"`
}

// ================================
// USER FUNCTIONS
// ================================

// BootstrapAdminIdentity performs the one-time transition from a legacy
// ledger. It is disabled unless all three allowlist environment variables are
// configured on every chaincode peer and the invoking certificate matches.
func (s *SmartContract) BootstrapAdminIdentity(
	ctx contractapi.TransactionContextInterface,
	userID string,
) error {
	expectedUser := strings.TrimSpace(os.Getenv("IDENTITY_BOOTSTRAP_USER_ID"))
	expectedMSP := strings.TrimSpace(os.Getenv("IDENTITY_BOOTSTRAP_MSP_ID"))
	expectedFingerprint := strings.ToLower(strings.TrimSpace(os.Getenv("IDENTITY_BOOTSTRAP_CERT_FINGERPRINT")))
	if expectedUser == "" || expectedMSP == "" || expectedFingerprint == "" {
		return fmt.Errorf("identity bootstrap is disabled")
	}
	if strings.TrimSpace(userID) != expectedUser {
		return fmt.Errorf("bootstrap user is not allowlisted")
	}
	marker, err := ctx.GetStub().GetState(identityBootstrapMarker)
	if err != nil {
		return err
	}
	if marker != nil {
		return fmt.Errorf("identity bootstrap is already complete")
	}
	user, err := s.GetUser(ctx, userID)
	if err != nil {
		return err
	}
	if !strings.EqualFold(user.Role, "admin") {
		return fmt.Errorf("bootstrap user must have the admin role")
	}
	mspID, fingerprint, err := invokerIdentity(ctx)
	if err != nil {
		return err
	}
	if !strings.EqualFold(mspID, expectedMSP) ||
		!strings.EqualFold(fingerprint, expectedFingerprint) {
		return fmt.Errorf("invoker Fabric identity is not bootstrap-allowlisted")
	}
	if err := s.putIdentityBinding(ctx, userID, mspID, fingerprint, userID, false); err != nil {
		return err
	}
	return ctx.GetStub().PutState(identityBootstrapMarker, []byte(userID))
}

// RegisterUserIdentity lets an already-bound admin bind a user certificate.
func (s *SmartContract) RegisterUserIdentity(
	ctx contractapi.TransactionContextInterface,
	userID string,
	mspID string,
	certificateFingerprint string,
	actorID string,
) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	actor, err := s.GetUser(ctx, actorID)
	if err != nil {
		return err
	}
	if !strings.EqualFold(actor.Role, "admin") {
		return fmt.Errorf("only an admin may register Fabric identities")
	}
	return s.putIdentityBinding(ctx, userID, mspID, certificateFingerprint, actorID, false)
}

// RotateUserIdentity replaces a binding; no compatibility bypass is retained.
func (s *SmartContract) RotateUserIdentity(
	ctx contractapi.TransactionContextInterface,
	userID string,
	mspID string,
	certificateFingerprint string,
	actorID string,
) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	actor, err := s.GetUser(ctx, actorID)
	if err != nil {
		return err
	}
	if !strings.EqualFold(actor.Role, "admin") {
		return fmt.Errorf("only an admin may rotate Fabric identities")
	}
	existing, err := ctx.GetStub().GetState(identityBindingKey(userID))
	if err != nil {
		return err
	}
	if existing == nil {
		return fmt.Errorf("Fabric identity does not exist for user %s", userID)
	}
	return s.putIdentityBinding(ctx, userID, mspID, certificateFingerprint, actorID, true)
}

// GetUserIdentity returns public binding metadata for reconciliation.
func (s *SmartContract) GetUserIdentity(
	ctx contractapi.TransactionContextInterface,
	userID string,
) (*FabricIdentityBinding, error) {
	data, err := ctx.GetStub().GetState(identityBindingKey(userID))
	if err != nil {
		return nil, err
	}
	if data == nil {
		return nil, fmt.Errorf("Fabric identity does not exist for user %s", userID)
	}
	var binding FabricIdentityBinding
	if err := json.Unmarshal(data, &binding); err != nil {
		return nil, err
	}
	return &binding, nil
}

// CreateUser creates a new user.
func (s *SmartContract) CreateUser(
	ctx contractapi.TransactionContextInterface,
	id string,
	username string,
	fullName string,
	role string,
	passwordHash string,
	contact string,
	createdBy string,
) error {
	if err := s.verifyMutationActor(ctx, createdBy); err != nil {
		return err
	}
	username = strings.TrimSpace(username)
	passwordHash = strings.TrimSpace(passwordHash)
	if username == "" || passwordHash == "" {
		return fmt.Errorf("username and password hash are required")
	}

	exists, err := s.UserExists(ctx, id)
	if err != nil {
		return err
	}

	if exists {
		return fmt.Errorf("user %s already exists", id)
	}

	usernameExists, err := s.UsernameExists(ctx, username)
	if err != nil {
		return err
	}
	if usernameExists {
		return fmt.Errorf("username %s already exists", username)
	}

	createdAt := ""
	if timestamp, timestampErr := ctx.GetStub().GetTxTimestamp(); timestampErr == nil && timestamp != nil {
		createdAt = timestamp.AsTime().UTC().Format(time.RFC3339)
	}
	user := User{
		ID:        id,
		Username:  username,
		FullName:  fullName,
		Role:      role,
		Contact:   strings.TrimSpace(contact),
		CreatedBy: strings.TrimSpace(createdBy),
		CreatedAt: createdAt,
	}

	data, err := json.Marshal(user)
	if err != nil {
		return err
	}

	if err := ctx.GetStub().PutState("USER_"+id, data); err != nil {
		return err
	}

	credential := UserCredential{Username: username, PasswordHash: passwordHash}
	credentialData, err := json.Marshal(credential)
	if err != nil {
		return err
	}

	return putCredentialState(ctx, "AUTH_"+strings.ToLower(username), credentialData)
}

// UpdateUser changes public profile fields while preserving credentials and provenance.
func (s *SmartContract) UpdateUser(
	ctx contractapi.TransactionContextInterface,
	id string,
	fullName string,
	role string,
	contact string,
	actorID string,
) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	user, err := s.GetUser(ctx, id)
	if err != nil {
		return err
	}
	user.FullName = strings.TrimSpace(fullName)
	user.Role = strings.TrimSpace(role)
	user.Contact = strings.TrimSpace(contact)
	data, err := json.Marshal(user)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState("USER_"+id, data)
}

func (s *SmartContract) ensureStoreUser(ctx contractapi.TransactionContextInterface) error {
	exists, err := s.UserExists(ctx, "STORE")
	if err != nil {
		return err
	}
	if exists {
		return nil
	}
	data, err := json.Marshal(User{
		ID: "STORE", Username: "store", FullName: "Kho cửa hàng", Role: "STORE",
	})
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState("USER_STORE", data)
}

// EnsureStoreUser creates the non-login owner used for store inventory and buybacks.
func (s *SmartContract) EnsureStoreUser(ctx contractapi.TransactionContextInterface, actorID string) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	return s.ensureStoreUser(ctx)
}

// UsernameExists checks whether a login name already has credentials.
func (s *SmartContract) UsernameExists(ctx contractapi.TransactionContextInterface, username string) (bool, error) {
	normalizedUsername := strings.TrimSpace(username)
	key := "AUTH_" + strings.ToLower(normalizedUsername)
	data, err := getCredentialState(ctx, key)
	if err != nil {
		return false, err
	}
	if data != nil {
		return true, nil
	}

	users, err := s.GetAllUsers(ctx)
	if err != nil {
		return false, err
	}
	for _, user := range users {
		if strings.EqualFold(strings.TrimSpace(user.Username), normalizedUsername) {
			return true, nil
		}
	}
	return false, nil
}

// GetUserByUsername returns the public user profile matching a login name.
func (s *SmartContract) GetUserByUsername(ctx contractapi.TransactionContextInterface, username string) (*User, error) {
	users, err := s.GetAllUsers(ctx)
	if err != nil {
		return nil, err
	}
	for _, user := range users {
		if strings.EqualFold(strings.TrimSpace(user.Username), strings.TrimSpace(username)) {
			return user, nil
		}
	}
	return nil, fmt.Errorf("username does not exist")
}

// GetPasswordHash returns the stored one-way hash for backend verification.
func (s *SmartContract) GetPasswordHash(ctx contractapi.TransactionContextInterface, username string) (string, error) {
	key := "AUTH_" + strings.ToLower(strings.TrimSpace(username))
	data, err := getCredentialState(ctx, key)
	if err != nil {
		return "", err
	}
	if data == nil {
		return "", fmt.Errorf("credentials do not exist")
	}

	var credential UserCredential
	if err := json.Unmarshal(data, &credential); err != nil {
		return "", err
	}
	return credential.PasswordHash, nil
}

// SetUserPassword creates or replaces credentials for an existing user.
func (s *SmartContract) SetUserPassword(ctx contractapi.TransactionContextInterface, userID string, passwordHash string, actorID string) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	user, err := s.GetUser(ctx, userID)
	if err != nil {
		return err
	}
	if strings.TrimSpace(passwordHash) == "" {
		return fmt.Errorf("password hash is required")
	}

	credential := UserCredential{Username: user.Username, PasswordHash: strings.TrimSpace(passwordHash)}
	data, err := json.Marshal(credential)
	if err != nil {
		return err
	}
	key := "AUTH_" + strings.ToLower(strings.TrimSpace(user.Username))
	return putCredentialState(ctx, key, data)
}

// MigrateUserCredential moves one legacy credential from world state to private data.
func (s *SmartContract) MigrateUserCredential(ctx contractapi.TransactionContextInterface, username string, actorID string) error {
	if !credentialPrivateDataEnabled() {
		return fmt.Errorf("userCredentials private-data collection is not enabled")
	}
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	key := "AUTH_" + strings.ToLower(strings.TrimSpace(username))
	legacy, err := ctx.GetStub().GetState(key)
	if err != nil {
		return err
	}
	if legacy == nil {
		return nil
	}
	if err := ctx.GetStub().PutPrivateData(credentialCollection, key, legacy); err != nil {
		return err
	}
	return ctx.GetStub().DelState(key)
}

// DeleteUser removes a user and their credentials when no assets depend on them.
func (s *SmartContract) DeleteUser(ctx contractapi.TransactionContextInterface, id string, actorID string) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	user, err := s.GetUser(ctx, id)
	if err != nil {
		return err
	}

	assets, err := s.GetAssetsByOwner(ctx, id)
	if err != nil {
		return err
	}
	if len(assets) > 0 {
		return fmt.Errorf("user %s still owns %d asset(s)", id, len(assets))
	}

	if strings.EqualFold(user.Role, "admin") {
		users, err := s.GetAllUsers(ctx)
		if err != nil {
			return err
		}
		adminCount := 0
		for _, candidate := range users {
			if strings.EqualFold(candidate.Role, "admin") {
				adminCount++
			}
		}
		if adminCount <= 1 {
			return fmt.Errorf("cannot delete the last admin user")
		}
	}

	credentialKey := "AUTH_" + strings.ToLower(strings.TrimSpace(user.Username))
	if err := deleteCredentialState(ctx, credentialKey); err != nil {
		return err
	}
	identityKey := identityBindingKey(id)
	identityData, err := ctx.GetStub().GetState(identityKey)
	if err != nil {
		return err
	}
	if identityData != nil {
		var binding FabricIdentityBinding
		if err := json.Unmarshal(identityData, &binding); err != nil {
			return err
		}
		if err := ctx.GetStub().DelState(identityFingerprintKey(binding.MSPID, binding.CertificateFingerprint)); err != nil {
			return err
		}
		if err := ctx.GetStub().DelState(identityKey); err != nil {
			return err
		}
	}
	return ctx.GetStub().DelState("USER_" + id)
}

// GetUser returns a user by ID.
func (s *SmartContract) GetUser(
	ctx contractapi.TransactionContextInterface,
	id string,
) (*User, error) {

	data, err := ctx.GetStub().GetState("USER_" + id)
	if err != nil {
		return nil, err
	}

	if data == nil {
		return nil, fmt.Errorf("user %s does not exist", id)
	}

	var user User

	err = json.Unmarshal(data, &user)
	if err != nil {
		return nil, err
	}

	return &user, nil
}

// UserExists checks whether a user exists.
func (s *SmartContract) UserExists(
	ctx contractapi.TransactionContextInterface,
	id string,
) (bool, error) {

	data, err := ctx.GetStub().GetState("USER_" + id)
	if err != nil {
		return false, err
	}

	return data != nil, nil
}

// ================================
// ASSET FUNCTIONS
// ================================

// CreateAsset creates a new asset.
func (s *SmartContract) CreateAsset(
	ctx contractapi.TransactionContextInterface,
	id string,
	name string,
	assetType string,
	ownerID string,
	value int,
	status string,
	serialNumber string,
	description string,
	quantity int,
	actorID string,
) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	if quantity < 1 {
		return fmt.Errorf("quantity must be at least 1")
	}
	if ownerID == "STORE" {
		if err := s.ensureStoreUser(ctx); err != nil {
			return err
		}
	}

	exists, err := s.AssetExists(ctx, id)
	if err != nil {
		return err
	}

	if exists {
		return fmt.Errorf("asset %s already exists", id)
	}

	// Check owner
	ownerExists, err := s.UserExists(ctx, ownerID)
	if err != nil {
		return err
	}

	if !ownerExists {
		return fmt.Errorf("owner %s does not exist", ownerID)
	}

	asset := Asset{
		ID:            id,
		Name:          name,
		Type:          assetType,
		OwnerID:       ownerID,
		Value:         value,
		Quantity:      quantity,
		Status:        status,
		SerialNumber:  serialNumber,
		Description:   description,
		LastActorID:   strings.TrimSpace(actorID),
		LastOperation: "create",
	}

	data, err := json.Marshal(asset)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState(id, data)
}

// ReadAsset returns an asset by ID.
func (s *SmartContract) ReadAsset(
	ctx contractapi.TransactionContextInterface,
	id string,
) (*Asset, error) {
	asset, err := s.ReadAssetRecord(ctx, id)
	if err != nil {
		return nil, err
	}
	if asset.Deleted {
		return nil, fmt.Errorf("asset %s does not exist", id)
	}
	return asset, nil
}

// ReadAssetRecord returns an asset record, including a deletion tombstone.
func (s *SmartContract) ReadAssetRecord(
	ctx contractapi.TransactionContextInterface,
	id string,
) (*Asset, error) {

	data, err := ctx.GetStub().GetState(id)
	if err != nil {
		return nil, err
	}

	if data == nil {
		return nil, fmt.Errorf("asset %s does not exist", id)
	}

	var asset Asset

	err = json.Unmarshal(data, &asset)
	if err != nil {
		return nil, err
	}
	if asset.Quantity < 1 {
		asset.Quantity = 1
	}

	return &asset, nil
}

// UpdateAsset updates an existing asset.
func (s *SmartContract) UpdateAsset(
	ctx contractapi.TransactionContextInterface,
	id string,
	name string,
	assetType string,
	ownerID string,
	value int,
	status string,
	serialNumber string,
	description string,
	quantity int,
	actorID string,
) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	if quantity < 1 {
		return fmt.Errorf("quantity must be at least 1")
	}
	if ownerID == "STORE" {
		if err := s.ensureStoreUser(ctx); err != nil {
			return err
		}
	}

	exists, err := s.AssetExists(ctx, id)
	if err != nil {
		return err
	}

	if !exists {
		return fmt.Errorf("asset %s does not exist", id)
	}

	ownerExists, err := s.UserExists(ctx, ownerID)
	if err != nil {
		return err
	}

	if !ownerExists {
		return fmt.Errorf("owner %s does not exist", ownerID)
	}

	asset := Asset{
		ID:            id,
		Name:          name,
		Type:          assetType,
		OwnerID:       ownerID,
		Value:         value,
		Quantity:      quantity,
		Status:        status,
		SerialNumber:  serialNumber,
		Description:   description,
		LastActorID:   strings.TrimSpace(actorID),
		LastOperation: "update",
	}

	data, err := json.Marshal(asset)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState(id, data)
}

// DeleteAsset deletes an asset.
func (s *SmartContract) DeleteAsset(
	ctx contractapi.TransactionContextInterface,
	id string,
	actorID string,
) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}

	exists, err := s.AssetExists(ctx, id)
	if err != nil {
		return err
	}

	if !exists {
		return fmt.Errorf("asset %s does not exist", id)
	}

	asset, err := s.ReadAsset(ctx, id)
	if err != nil {
		return err
	}
	asset.Deleted = true
	asset.LastActorID = strings.TrimSpace(actorID)
	asset.LastOperation = "delete"
	data, err := json.Marshal(asset)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(id, data)
}

// DeleteAssetQuantity removes all or part of an asset quantity.
func (s *SmartContract) DeleteAssetQuantity(
	ctx contractapi.TransactionContextInterface,
	id string,
	quantity int,
	actorID string,
) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	asset, err := s.ReadAsset(ctx, id)
	if err != nil {
		return err
	}
	if quantity < 1 || quantity > asset.Quantity {
		return fmt.Errorf("quantity must be between 1 and %d", asset.Quantity)
	}
	if quantity == asset.Quantity {
		asset.Deleted = true
		asset.LastActorID = strings.TrimSpace(actorID)
		asset.LastOperation = "delete"
		data, err := json.Marshal(asset)
		if err != nil {
			return err
		}
		return ctx.GetStub().PutState(id, data)
	}
	asset.Quantity -= quantity
	asset.LastActorID = strings.TrimSpace(actorID)
	asset.LastOperation = "delete_quantity"
	data, err := json.Marshal(asset)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(id, data)
}

// AssetExists checks whether an asset exists.
func (s *SmartContract) AssetExists(
	ctx contractapi.TransactionContextInterface,
	id string,
) (bool, error) {

	data, err := ctx.GetStub().GetState(id)
	if err != nil {
		return false, err
	}

	return data != nil, nil
}

// ================================
// TRANSFER ASSET
// ================================

// TransferAsset changes the owner of an asset.
func (s *SmartContract) TransferAsset(
	ctx contractapi.TransactionContextInterface,
	id string,
	newOwnerID string,
	actorID string,
) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	if newOwnerID == "STORE" {
		if err := s.ensureStoreUser(ctx); err != nil {
			return err
		}
	}

	asset, err := s.ReadAsset(ctx, id)
	if err != nil {
		return err
	}

	ownerExists, err := s.UserExists(ctx, newOwnerID)
	if err != nil {
		return err
	}

	if !ownerExists {
		return fmt.Errorf("new owner %s does not exist", newOwnerID)
	}

	asset.OwnerID = newOwnerID
	asset.LastActorID = strings.TrimSpace(actorID)
	asset.LastOperation = "transfer"

	data, err := json.Marshal(asset)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState(id, data)
}

// ReturnAssetToStore transfers a customer asset back into store inventory.
func (s *SmartContract) ReturnAssetToStore(ctx contractapi.TransactionContextInterface, id string, actorID string) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	asset, err := s.ReadAsset(ctx, id)
	if err != nil {
		return err
	}
	if err := s.ensureStoreUser(ctx); err != nil {
		return err
	}
	asset.OwnerID = "STORE"
	asset.Status = "Active"
	asset.LastActorID = strings.TrimSpace(actorID)
	asset.LastOperation = "transfer"
	data, err := json.Marshal(asset)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(id, data)
}

// TransferAssetQuantity transfers all or part of a store inventory record.
func (s *SmartContract) TransferAssetQuantity(
	ctx contractapi.TransactionContextInterface,
	id string,
	newOwnerID string,
	quantity int,
	newAssetID string,
	actorID string,
) error {
	if err := s.verifyMutationActor(ctx, actorID); err != nil {
		return err
	}
	if newOwnerID == "STORE" {
		if err := s.ensureStoreUser(ctx); err != nil {
			return err
		}
	}
	asset, err := s.ReadAsset(ctx, id)
	if err != nil {
		return err
	}
	if quantity < 1 || quantity > asset.Quantity {
		return fmt.Errorf("quantity must be between 1 and %d", asset.Quantity)
	}
	ownerExists, err := s.UserExists(ctx, newOwnerID)
	if err != nil {
		return err
	}
	if !ownerExists {
		return fmt.Errorf("new owner %s does not exist", newOwnerID)
	}

	if quantity == asset.Quantity {
		asset.OwnerID = newOwnerID
		asset.LastActorID = strings.TrimSpace(actorID)
		asset.LastOperation = "transfer"
		data, err := json.Marshal(asset)
		if err != nil {
			return err
		}
		return ctx.GetStub().PutState(id, data)
	}

	newAssetID = strings.TrimSpace(newAssetID)
	if newAssetID == "" {
		return fmt.Errorf("new asset ID is required for a partial transfer")
	}
	exists, err := s.AssetExists(ctx, newAssetID)
	if err != nil {
		return err
	}
	if exists {
		return fmt.Errorf("asset %s already exists", newAssetID)
	}

	soldAsset := *asset
	soldAsset.ID = newAssetID
	soldAsset.OwnerID = newOwnerID
	soldAsset.Quantity = quantity
	soldAsset.Status = "Sold"
	soldAsset.LastActorID = strings.TrimSpace(actorID)
	soldAsset.LastOperation = "transfer"
	asset.Quantity -= quantity
	asset.LastActorID = strings.TrimSpace(actorID)
	asset.LastOperation = "update"

	remainingData, err := json.Marshal(asset)
	if err != nil {
		return err
	}
	soldData, err := json.Marshal(soldAsset)
	if err != nil {
		return err
	}
	if err := ctx.GetStub().PutState(id, remainingData); err != nil {
		return err
	}
	return ctx.GetStub().PutState(newAssetID, soldData)
}

// ================================
// GET ASSETS BY OWNER
// ================================

// GetAssetsByOwner returns all assets owned by a user.
func (s *SmartContract) GetAssetsByOwner(
	ctx contractapi.TransactionContextInterface,
	ownerID string,
) ([]*Asset, error) {

	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}

	defer resultsIterator.Close()

	var assets []*Asset

	for resultsIterator.HasNext() {

		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		// Bỏ qua User
		if len(queryResponse.Key) >= 5 &&
			queryResponse.Key[:5] == "USER_" {
			continue
		}

		var asset Asset

		err = json.Unmarshal(
			queryResponse.Value,
			&asset,
		)

		if err != nil {
			continue
		}

		// Bỏ qua dữ liệu không phải Asset
		if asset.ID == "" {
			continue
		}
		if asset.Quantity < 1 {
			asset.Quantity = 1
		}
		if asset.Deleted {
			continue
		}

		if asset.OwnerID == ownerID {
			assets = append(
				assets,
				&asset,
			)
		}
	}

	return assets, nil
}

// ================================
// GET ALL ASSETS
// ================================

// GetAllAssets returns all assets.
func (s *SmartContract) GetAllAssets(
	ctx contractapi.TransactionContextInterface,
) ([]*Asset, error) {

	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}

	defer resultsIterator.Close()

	var assets []*Asset

	for resultsIterator.HasNext() {

		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		// Bỏ qua dữ liệu User
		if len(queryResponse.Key) >= 5 &&
			queryResponse.Key[:5] == "USER_" {
			continue
		}

		var asset Asset

		err = json.Unmarshal(
			queryResponse.Value,
			&asset,
		)

		// Nếu dữ liệu không đúng định dạng Asset thì bỏ qua
		if err != nil {
			continue
		}

		// Chỉ nhận dữ liệu thực sự là Asset
		if asset.ID == "" {
			continue
		}
		if asset.Quantity < 1 {
			asset.Quantity = 1
		}
		if asset.Deleted {
			continue
		}

		assets = append(
			assets,
			&asset,
		)
	}

	return assets, nil
}

// GetAllAssetRecords returns active assets and deletion tombstones for history discovery.
func (s *SmartContract) GetAllAssetRecords(
	ctx contractapi.TransactionContextInterface,
) ([]*Asset, error) {
	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}
	defer resultsIterator.Close()

	var assets []*Asset
	for resultsIterator.HasNext() {
		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}
		if strings.HasPrefix(queryResponse.Key, "USER_") ||
			strings.HasPrefix(queryResponse.Key, "USER_CREDENTIAL_") {
			continue
		}
		var asset Asset
		if err := json.Unmarshal(queryResponse.Value, &asset); err != nil || asset.ID == "" {
			continue
		}
		if asset.Quantity < 1 {
			asset.Quantity = 1
		}
		assets = append(assets, &asset)
	}
	return assets, nil
}

// ================================
// GET ASSET HISTORY
// ================================

func (s *SmartContract) GetAssetHistory(
	ctx contractapi.TransactionContextInterface,
	id string,
) ([]*AssetHistory, error) {

	resultsIterator, err := ctx.GetStub().GetHistoryForKey(id)
	if err != nil {
		return nil, err
	}

	defer resultsIterator.Close()

	var history []*AssetHistory

	for resultsIterator.HasNext() {

		modification, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		record := &AssetHistory{
			TxID:     modification.TxId,
			IsDelete: modification.IsDelete,
		}

		if modification.Timestamp != nil {
			record.Timestamp = modification.Timestamp.String()
		}

		if !modification.IsDelete &&
			len(modification.Value) > 0 {

			var asset Asset

			err := json.Unmarshal(
				modification.Value,
				&asset,
			)

			if err == nil {
				record.Value = &asset
			}
		}

		history = append(history, record)
	}

	return history, nil
}

// ================================
// GET ALL USERS
// ================================
// GetAllUsers returns all users.
func (s *SmartContract) GetAllUsers(
	ctx contractapi.TransactionContextInterface,
) ([]*User, error) {

	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}

	defer resultsIterator.Close()

	var users []*User

	for resultsIterator.HasNext() {

		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		// Chỉ lấy các key bắt đầu bằng USER_
		if len(queryResponse.Key) < 5 ||
			queryResponse.Key[:5] != "USER_" {
			continue
		}

		var user User

		err = json.Unmarshal(
			queryResponse.Value,
			&user,
		)

		if err != nil {
			continue
		}

		// Chỉ thêm User hợp lệ
		if user.ID == "" {
			continue
		}

		users = append(
			users,
			&user,
		)
	}

	return users, nil
}

// ================================
// INIT LEDGER
// ================================

func (s *SmartContract) InitLedger(
	ctx contractapi.TransactionContextInterface,
	actorID string,
) error {
	expectedUser := strings.TrimSpace(os.Getenv("IDENTITY_BOOTSTRAP_USER_ID"))
	expectedMSP := strings.TrimSpace(os.Getenv("IDENTITY_BOOTSTRAP_MSP_ID"))
	expectedFingerprint := strings.ToLower(strings.TrimSpace(os.Getenv("IDENTITY_BOOTSTRAP_CERT_FINGERPRINT")))
	if expectedUser == "" || expectedMSP == "" || expectedFingerprint == "" {
		return fmt.Errorf("ledger initialization is disabled")
	}
	if strings.TrimSpace(actorID) != expectedUser {
		return fmt.Errorf("initialization actor is not allowlisted")
	}
	mspID, fingerprint, err := invokerIdentity(ctx)
	if err != nil {
		return err
	}
	if !strings.EqualFold(mspID, expectedMSP) || !strings.EqualFold(fingerprint, expectedFingerprint) {
		return fmt.Errorf("invoker Fabric identity is not initialization-allowlisted")
	}
	initialized, err := s.UserExists(ctx, expectedUser)
	if err != nil {
		return err
	}
	if initialized {
		return fmt.Errorf("ledger is already initialized")
	}

	users := []User{
		{
			ID:       "U001",
			Username: "admin",
			FullName: "System Administrator",
			Role:     "ADMIN",
		},
		{
			ID:       "U002",
			Username: "canhtung",
			FullName: "Canh Tung",
			Role:     "CUSTOMER",
		},
		{
			ID:       "U003",
			Username: "nguyenvana",
			FullName: "Nguyen Van A",
			Role:     "CUSTOMER",
		},
	}

	for _, user := range users {

		userJSON, err := json.Marshal(user)
		if err != nil {
			return err
		}

		err = ctx.GetStub().PutState(
			"USER_"+user.ID,
			userJSON,
		)

		if err != nil {
			return err
		}
	}

	return nil
}
