package main

import (
	"crypto/x509"
	"fmt"
	"os"

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

func main() {
	fmt.Println("================================")
	fmt.Println("      FABRIC ASSET CLIENT")
	fmt.Println("================================")

	conn, err := newGrpcConnection()
	if err != nil {
		fmt.Printf("Connection ERROR: %v\n", err)
		return
	}
	defer conn.Close()

	id, err := newIdentity()
	if err != nil {
		fmt.Printf("Identity ERROR: %v\n", err)
		return
	}

	sign, err := newSign()
	if err != nil {
		fmt.Printf("Sign ERROR: %v\n", err)
		return
	}

	gateway, err := client.Connect(
		id,
		client.WithSign(sign),
		client.WithClientConnection(conn),
		client.WithHash(hash.SHA256),
	)
	if err != nil {
		fmt.Printf("Gateway ERROR: %v\n", err)
		return
	}
	defer gateway.Close()

	network := gateway.GetNetwork(channelName)
	contract := network.GetContract(chaincodeName)

	// ================================
	// 1. CREATE
	// ================================

	fmt.Println("\n[1] CreateAsset")

	_, err = contract.SubmitTransaction(
		"CreateAsset",
		"A001",
		"Laptop Dell",
		"CanhTung",
		"25000000",
	)

	if err != nil {
		fmt.Printf("CreateAsset ERROR: %v\n", err)
		return
	}

	fmt.Println("CreateAsset SUCCESS")

	// ================================
	// 2. READ
	// ================================

	fmt.Println("\n[2] ReadAsset")

	result, err := contract.EvaluateTransaction(
		"ReadAsset",
		"A001",
	)

	if err != nil {
		fmt.Printf("ReadAsset ERROR: %v\n", err)
		return
	}

	fmt.Printf("Asset: %s\n", string(result))

	// ================================
	// 3. UPDATE
	// ================================

	fmt.Println("\n[3] UpdateAsset")

	_, err = contract.SubmitTransaction(
		"UpdateAsset",
		"A001",
		"Laptop Dell XPS",
		"CanhTung",
		"30000000",
	)

	if err != nil {
		fmt.Printf("UpdateAsset ERROR: %v\n", err)
		return
	}

	fmt.Println("UpdateAsset SUCCESS")

	// ================================
	// 4. READ AFTER UPDATE
	// ================================

	fmt.Println("\n[4] ReadAsset after update")

	result, err = contract.EvaluateTransaction(
		"ReadAsset",
		"A001",
	)

	if err != nil {
		fmt.Printf("ReadAsset ERROR: %v\n", err)
		return
	}

	fmt.Printf("Asset: %s\n", string(result))

	// ================================
	// 5. DELETE
	// ================================

	fmt.Println("\n[5] DeleteAsset")

	_, err = contract.SubmitTransaction(
		"DeleteAsset",
		"A001",
	)

	if err != nil {
		fmt.Printf("DeleteAsset ERROR: %v\n", err)
		return
	}

	fmt.Println("DeleteAsset SUCCESS")

	// ================================
	// 6. READ AFTER DELETE
	// ================================

	fmt.Println("\n[6] ReadAsset after delete")

	result, err = contract.EvaluateTransaction(
		"ReadAsset",
		"A001",
	)

	if err != nil {
		fmt.Printf("ReadAsset: Asset A001 has been deleted\n")
	} else {
		fmt.Printf("Asset: %s\n", string(result))
	}

	fmt.Println("\n================================")
	fmt.Println("          HOAN THANH")
	fmt.Println("================================")
}

