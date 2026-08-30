package main

import (
	"crypto/x509"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/hyperledger/fabric-gateway/pkg/client"
	"github.com/hyperledger/fabric-gateway/pkg/hash"
	"github.com/hyperledger/fabric-gateway/pkg/identity"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
)

const (
	mspID         = "Org1MSP"
	peerEndpoint  = "127.0.0.1:7000"
	gatewayHost   = "127.0.0.1"
	channelName   = "assetchannel"
	chaincodeName = "assetcc"

	certPath = "/home/canhtung/.chainlaunch/data/peers/peer0-org1msp/config/signcerts/cert.pem"
	keyPath  = "/home/canhtung/.chainlaunch/data/peers/peer0-org1msp/config/keystore/key.pem"
	tlsPath  = "/home/canhtung/.chainlaunch/data/peers/peer0-org1msp/config/tlscacerts/cacert.pem"
)

// ================================
// MODELS
// ================================

type User struct {
	ID       string `json:"id"`
	Username string `json:"username"`
	FullName string `json:"fullName"`
	Role     string `json:"role"`
}

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

type AssetHistory struct {
	TxID      string `json:"txID"`
	Timestamp string `json:"timestamp"`
	IsDelete  bool   `json:"isDelete"`
	Value     *Asset `json:"value,omitempty"`
}

// ================================
// FABRIC CONNECTION
// ================================

func newIdentity() (*identity.X509Identity, error) {
	certPEM, err := os.ReadFile(certPath)
	if err != nil {
		return nil, err
	}

	cert, err := identity.CertificateFromPEM(certPEM)
	if err != nil {
		return nil, err
	}

	return identity.NewX509Identity(mspID, cert)
}

func newSign() (identity.Sign, error) {
	keyPEM, err := os.ReadFile(keyPath)
	if err != nil {
		return nil, err
	}

	key, err := identity.PrivateKeyFromPEM(keyPEM)
	if err != nil {
		return nil, err
	}

	return identity.NewPrivateKeySign(key)
}

func newGrpcConnection() (*grpc.ClientConn, error) {
	tlsPEM, err := os.ReadFile(tlsPath)
	if err != nil {
		return nil, err
	}

	certPool := x509.NewCertPool()

	if !certPool.AppendCertsFromPEM(tlsPEM) {
		return nil, fmt.Errorf("failed to parse TLS certificate")
	}

	transportCredentials := credentials.NewClientTLSFromCert(
		certPool,
		gatewayHost,
	)

	return grpc.NewClient(
		peerEndpoint,
		grpc.WithTransportCredentials(transportCredentials),
	)
}

func connectFabric() (*client.Contract, func(), error) {
	conn, err := newGrpcConnection()
	if err != nil {
		return nil, nil, fmt.Errorf("grpc connection: %w", err)
	}

	id, err := newIdentity()
	if err != nil {
		conn.Close()
		return nil, nil, fmt.Errorf("identity: %w", err)
	}

	sign, err := newSign()
	if err != nil {
		conn.Close()
		return nil, nil, fmt.Errorf("sign: %w", err)
	}

	gateway, err := client.Connect(
		id,
		client.WithSign(sign),
		client.WithClientConnection(conn),
		client.WithHash(hash.SHA256),
	)
	if err != nil {
		conn.Close()
		return nil, nil, fmt.Errorf("gateway: %w", err)
	}

	network := gateway.GetNetwork(channelName)
	contract := network.GetContract(chaincodeName)

	closeFunc := func() {
		gateway.Close()
		conn.Close()
	}

	return contract, closeFunc, nil
}

// ================================
// JSON
// ================================

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]interface{}{
		"success": false,
		"error":   message,
	})
}

// ================================
// HEALTH
// ================================

func healthHandler(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":   true,
		"message":   "Fabric Asset Backend is running",
		"network":   channelName,
		"chaincode": chaincodeName,
		"time":      time.Now(),
	})
}

// ================================
// USER API
// ================================

// POST /api/users
func createUserHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	var user User

	if err := json.NewDecoder(r.Body).Decode(&user); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON")
		return
	}

	if user.ID == "" ||
		user.Username == "" ||
		user.FullName == "" ||
		user.Role == "" {
		writeError(
			w,
			http.StatusBadRequest,
			"id, username, fullName and role are required",
		)
		return
	}

	contract, closeFabric, err := connectFabric()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer closeFabric()

	tx, err := contract.SubmitTransaction(
		"CreateUser",
		user.ID,
		user.Username,
		user.FullName,
		user.Role,
	)

	if err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("CreateUser failed: %v", err),
		)
		return
	}

	writeJSON(w, http.StatusCreated, map[string]interface{}{
		"success":     true,
		"message":     "User created successfully",
		"user":        user,
		"transaction": string(tx),
	})
}

// GET /api/users/{id}
func getUserHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	id := strings.TrimPrefix(r.URL.Path, "/api/users/")

	if id == "" {
		writeError(w, http.StatusBadRequest, "user ID is required")
		return
	}

	contract, closeFabric, err := connectFabric()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer closeFabric()

	result, err := contract.EvaluateTransaction(
		"GetUser",
		id,
	)

	if err != nil {
		writeError(
			w,
			http.StatusNotFound,
			fmt.Sprintf("user %s not found: %v", id, err),
		)
		return
	}

	var user User

	if err := json.Unmarshal(result, &user); err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("invalid user data: %v", err),
		)
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"user":    user,
	})
}

// ================================
// ASSET API
// ================================

// POST /api/assets
func createAssetHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	var asset Asset

	if err := json.NewDecoder(r.Body).Decode(&asset); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON")
		return
	}

	if asset.ID == "" ||
		asset.Name == "" ||
		asset.Type == "" ||
		asset.OwnerID == "" ||
		asset.Status == "" {
		writeError(
			w,
			http.StatusBadRequest,
			"id, name, type, ownerID and status are required",
		)
		return
	}

	contract, closeFabric, err := connectFabric()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer closeFabric()

	tx, err := contract.SubmitTransaction(
		"CreateAsset",
		asset.ID,
		asset.Name,
		asset.Type,
		asset.OwnerID,
		fmt.Sprintf("%d", asset.Value),
		asset.Status,
		asset.SerialNumber,
		asset.Description,
	)

	if err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("CreateAsset failed: %v", err),
		)
		return
	}

	writeJSON(w, http.StatusCreated, map[string]interface{}{
		"success":     true,
		"message":     "Asset created successfully",
		"asset":       asset,
		"transaction": string(tx),
	})
}

// GET /api/assets/{id}
func readAssetHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	id := strings.TrimPrefix(r.URL.Path, "/api/assets/")

	if id == "" {
		writeError(w, http.StatusBadRequest, "asset ID is required")
		return
	}

	contract, closeFabric, err := connectFabric()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer closeFabric()

	result, err := contract.EvaluateTransaction(
		"ReadAsset",
		id,
	)

	if err != nil {
		writeError(
			w,
			http.StatusNotFound,
			fmt.Sprintf("asset %s not found: %v", id, err),
		)
		return
	}

	var asset Asset

	if err := json.Unmarshal(result, &asset); err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("invalid asset data: %v", err),
		)
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"asset":   asset,
	})
}

// GET /api/assets
func getAllAssetsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	contract, closeFabric, err := connectFabric()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer closeFabric()

	result, err := contract.EvaluateTransaction(
		"GetAllAssets",
	)

	if err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("GetAllAssets failed: %v", err),
		)
		return
	}

	var assets []Asset

	if err := json.Unmarshal(result, &assets); err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("invalid asset list: %v", err),
		)
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"assets":  assets,
		"total":   len(assets),
	})
}

// PUT /api/assets/{id}
func updateAssetHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	id := strings.TrimPrefix(r.URL.Path, "/api/assets/")

	if id == "" {
		writeError(w, http.StatusBadRequest, "asset ID is required")
		return
	}

	var asset Asset

	if err := json.NewDecoder(r.Body).Decode(&asset); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON")
		return
	}

	contract, closeFabric, err := connectFabric()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer closeFabric()

	tx, err := contract.SubmitTransaction(
		"UpdateAsset",
		id,
		asset.Name,
		asset.Type,
		asset.OwnerID,
		fmt.Sprintf("%d", asset.Value),
		asset.Status,
		asset.SerialNumber,
		asset.Description,
	)

	if err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("UpdateAsset failed: %v", err),
		)
		return
	}

	asset.ID = id

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":     true,
		"message":     "Asset updated successfully",
		"asset":       asset,
		"transaction": string(tx),
	})
}

// DELETE /api/assets/{id}
func deleteAssetHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	id := strings.TrimPrefix(r.URL.Path, "/api/assets/")

	if id == "" {
		writeError(w, http.StatusBadRequest, "asset ID is required")
		return
	}

	contract, closeFabric, err := connectFabric()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer closeFabric()

	tx, err := contract.SubmitTransaction(
		"DeleteAsset",
		id,
	)

	if err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("DeleteAsset failed: %v", err),
		)
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":     true,
		"message":     "Asset deleted successfully",
		"id":          id,
		"transaction": string(tx),
	})
}

// ================================
// GET ASSETS BY OWNER
// ================================

// GET /api/users/{id}/assets
func getAssetsByOwnerHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	path := strings.TrimPrefix(r.URL.Path, "/api/users/")
	id := strings.TrimSuffix(path, "/assets")

	if id == "" {
		writeError(w, http.StatusBadRequest, "user ID is required")
		return
	}

	contract, closeFabric, err := connectFabric()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer closeFabric()

	result, err := contract.EvaluateTransaction(
		"GetAssetsByOwner",
		id,
	)

	if err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("GetAssetsByOwner failed: %v", err),
		)
		return
	}

	var assets []Asset

	if err := json.Unmarshal(result, &assets); err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("invalid asset list: %v", err),
		)
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"ownerID": id,
		"assets":  assets,
	})
}

// ================================
// TRANSFER ASSET
// ================================

// PUT /api/assets/{id}/transfer
func transferAssetHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPut {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	path := strings.TrimPrefix(r.URL.Path, "/api/assets/")
	id := strings.TrimSuffix(path, "/transfer")

	if id == "" {
		writeError(w, http.StatusBadRequest, "asset ID is required")
		return
	}

	var request struct {
		NewOwnerID string `json:"newOwnerID"`
	}

	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON")
		return
	}

	if request.NewOwnerID == "" {
		writeError(w, http.StatusBadRequest, "newOwnerID is required")
		return
	}

	contract, closeFabric, err := connectFabric()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer closeFabric()

	tx, err := contract.SubmitTransaction(
		"TransferAsset",
		id,
		request.NewOwnerID,
	)

	if err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("TransferAsset failed: %v", err),
		)
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":     true,
		"message":     "Asset transferred successfully",
		"id":          id,
		"newOwnerID":  request.NewOwnerID,
		"transaction": string(tx),
	})
}

// ================================
// ASSET HISTORY
// ================================

// GET /api/assets/{id}/history
func getAssetHistoryHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	path := strings.TrimPrefix(r.URL.Path, "/api/assets/")
	id := strings.TrimSuffix(path, "/history")

	if id == "" {
		writeError(w, http.StatusBadRequest, "asset ID is required")
		return
	}

	contract, closeFabric, err := connectFabric()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	defer closeFabric()

	result, err := contract.EvaluateTransaction(
		"GetAssetHistory",
		id,
	)

	if err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("GetAssetHistory failed: %v", err),
		)
		return
	}

	var history []AssetHistory

	if err := json.Unmarshal(result, &history); err != nil {
		writeError(
			w,
			http.StatusInternalServerError,
			fmt.Sprintf("invalid history data: %v", err),
		)
		return
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success": true,
		"assetID": id,
		"history": history,
	})
}

// ================================
// ROUTER
// ================================

func router() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("/api/health", healthHandler)

	mux.HandleFunc("/api/users/", func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/assets") {
			getAssetsByOwnerHandler(w, r)
			return
		}

		getUserHandler(w, r)
	})

	mux.HandleFunc("/api/users", func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			createUserHandler(w, r)
			return
		}

		writeError(
			w,
			http.StatusMethodNotAllowed,
			"method not allowed",
		)
	})

	mux.HandleFunc("/api/assets/", func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/transfer") {
			transferAssetHandler(w, r)
			return
		}

		if strings.HasSuffix(r.URL.Path, "/history") {
			getAssetHistoryHandler(w, r)
			return
		}

		switch r.Method {
		case http.MethodGet:
			readAssetHandler(w, r)

		case http.MethodPut:
			updateAssetHandler(w, r)

		case http.MethodDelete:
			deleteAssetHandler(w, r)

		default:
			writeError(
				w,
				http.StatusMethodNotAllowed,
				"method not allowed",
			)
		}
	})

	mux.HandleFunc("/api/assets", func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			createAssetHandler(w, r)
			return
		}

		writeError(
			w,
			http.StatusMethodNotAllowed,
			"method not allowed",
		)
	})

	return corsMiddleware(mux)
}

// ================================
// CORS
// ================================

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {

		w.Header().Set(
			"Access-Control-Allow-Origin",
			"*",
		)

		w.Header().Set(
			"Access-Control-Allow-Methods",
			"GET, POST, PUT, DELETE, OPTIONS",
		)

		w.Header().Set(
			"Access-Control-Allow-Headers",
			"Content-Type, Authorization",
		)

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next.ServeHTTP(w, r)
	})
}

// ================================
// MAIN
// ================================

func main() {

	fmt.Println("================================")
	fmt.Println("     FABRIC ASSET BACKEND V2")
	fmt.Println("================================")
	fmt.Println()
	fmt.Println("Network :", channelName)
	fmt.Println("Chaincode:", chaincodeName)
	fmt.Println("Peer    :", peerEndpoint)
	fmt.Println()
	fmt.Println("Server:")
	fmt.Println("http://localhost:8080")
	fmt.Println()
	fmt.Println("API:")
	fmt.Println("POST   /api/users")
	fmt.Println("GET    /api/users/{id}")
	fmt.Println("GET    /api/users/{id}/assets")
	fmt.Println()
	fmt.Println("POST   /api/assets")
	fmt.Println("GET    /api/assets/{id}")
	fmt.Println("PUT    /api/assets/{id}")
	fmt.Println("DELETE /api/assets/{id}")
	fmt.Println("PUT    /api/assets/{id}/transfer")
	fmt.Println("GET    /api/assets/{id}/history")
	fmt.Println()

	server := &http.Server{
		Addr:         ":8080",
		Handler:      router(),
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
	}

	log.Fatal(server.ListenAndServe())
}
