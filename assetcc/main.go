package main

import (
	"log"
	"os"

	"github.com/hyperledger/fabric-chaincode-go/shim"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

func main() {
	cc, err := contractapi.NewChaincode(new(SmartContract))
	if err != nil {
		log.Panic(err)
	}

	ccID := os.Getenv("CHAINCODE_ID")
	address := os.Getenv("CHAINCODE_SERVER_ADDRESS")

	if ccID == "" {
		log.Panic("CHAINCODE_ID is not set")
	}

	if address == "" {
		log.Panic("CHAINCODE_SERVER_ADDRESS is not set")
	}

	server := shim.ChaincodeServer{
		CCID:    ccID,
		Address: address,
		CC:      cc,
	}

	if err := server.Start(); err != nil {
		log.Panic(err)
	}
}
