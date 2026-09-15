package main

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type SmartContract struct {
	contractapi.Contract
}

// ================================
// USER
// ================================

type User struct {
	ID       string `json:"id"`
	Username string `json:"username"`
	FullName string `json:"fullName"`
	Role     string `json:"role"`
}

// UserCredential is stored separately so user-list queries never expose password hashes.
type UserCredential struct {
	Username     string `json:"username"`
	PasswordHash string `json:"passwordHash"`
}

// ================================
// ASSET
// ================================

type Asset struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	Type         string `json:"type"`
	OwnerID      string `json:"ownerID"`
	Value        int    `json:"value"`
	Status       string `json:"status"`
	SerialNumber string `json:"serialNumber"`
	Description  string `json:"description"`
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

// CreateUser creates a new user.
func (s *SmartContract) CreateUser(
	ctx contractapi.TransactionContextInterface,
	id string,
	username string,
	fullName string,
	role string,
	passwordHash string,
) error {
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

	user := User{
		ID:       id,
		Username: username,
		FullName: fullName,
		Role:     role,
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

	return ctx.GetStub().PutState("AUTH_"+strings.ToLower(username), credentialData)
}

// UsernameExists checks whether a login name already has credentials.
func (s *SmartContract) UsernameExists(ctx contractapi.TransactionContextInterface, username string) (bool, error) {
	normalizedUsername := strings.TrimSpace(username)
	data, err := ctx.GetStub().GetState("AUTH_" + strings.ToLower(normalizedUsername))
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
	data, err := ctx.GetStub().GetState("AUTH_" + strings.ToLower(strings.TrimSpace(username)))
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
func (s *SmartContract) SetUserPassword(ctx contractapi.TransactionContextInterface, userID string, passwordHash string) error {
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
	return ctx.GetStub().PutState("AUTH_"+strings.ToLower(strings.TrimSpace(user.Username)), data)
}

// DeleteUser removes a user and their credentials when no assets depend on them.
func (s *SmartContract) DeleteUser(ctx contractapi.TransactionContextInterface, id string) error {
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

	if err := ctx.GetStub().DelState("AUTH_" + strings.ToLower(strings.TrimSpace(user.Username))); err != nil {
		return err
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
) error {

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
		ID:           id,
		Name:         name,
		Type:         assetType,
		OwnerID:      ownerID,
		Value:        value,
		Status:       status,
		SerialNumber: serialNumber,
		Description:  description,
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
) error {

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
		ID:           id,
		Name:         name,
		Type:         assetType,
		OwnerID:      ownerID,
		Value:        value,
		Status:       status,
		SerialNumber: serialNumber,
		Description:  description,
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
) error {

	exists, err := s.AssetExists(ctx, id)
	if err != nil {
		return err
	}

	if !exists {
		return fmt.Errorf("asset %s does not exist", id)
	}

	return ctx.GetStub().DelState(id)
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
) error {

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

	data, err := json.Marshal(asset)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState(id, data)
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

		assets = append(
			assets,
			&asset,
		)
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
) error {

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
			Role:     "USER",
		},
		{
			ID:       "U003",
			Username: "nguyenvana",
			FullName: "Nguyen Van A",
			Role:     "USER",
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
