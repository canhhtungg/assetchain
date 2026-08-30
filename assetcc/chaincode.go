package main

import (
	"encoding/json"
	"fmt"

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
) error {

	exists, err := s.UserExists(ctx, id)
	if err != nil {
		return err
	}

	if exists {
		return fmt.Errorf("user %s already exists", id)
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

	return ctx.GetStub().PutState("USER_"+id, data)
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

		// Ignore User records.
		if len(queryResponse.Key) >= 5 &&
			queryResponse.Key[:5] == "USER_" {
			continue
		}

		var asset Asset

		err = json.Unmarshal(queryResponse.Value, &asset)
		if err != nil {
			continue
		}

		if asset.OwnerID == ownerID {
			assets = append(assets, &asset)
		}
	}

	return assets, nil
}

// ================================
// GET ALL ASSETS
// ================================

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

		// Ignore User records.
		if len(queryResponse.Key) >= 5 &&
			queryResponse.Key[:5] == "USER_" {
			continue
		}

		var asset Asset

		err = json.Unmarshal(queryResponse.Value, &asset)
		if err != nil {
			continue
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
