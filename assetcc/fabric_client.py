import os
import requests
from dotenv import load_dotenv

load_dotenv()

FABRIC_HOST = os.getenv(
    "FABRIC_HOST",
    "https://localhost:8100/api/v1"
)

FABRIC_USERNAME = os.getenv(
    "FABRIC_USERNAME",
    "admin"
)

FABRIC_PASSWORD = os.getenv(
    "FABRIC_PASSWORD"
)

FABRIC_CHANNEL_NAME = os.getenv(
    "FABRIC_CHANNEL_NAME",
    "assetchannel"
)

FABRIC_CHAINCODE_ID = os.getenv(
    "FABRIC_CHAINCODE_ID",
    "1"
)

FABRIC_KEY_ID = os.getenv(
    "FABRIC_KEY_ID",
    "6"
)


class FabricClient:

    def __init__(self):
        self.base_url = FABRIC_HOST

        self.session = requests.Session()

        self.session.auth = (
            FABRIC_USERNAME,
            FABRIC_PASSWORD
        )

        self.session.verify = False


    def request(
        self,
        method,
        endpoint,
        data=None,
        params=None
    ):

        url = f"{self.base_url}{endpoint}"

        response = self.session.request(
            method=method,
            url=url,
            json=data,
            params=params,
            timeout=30
        )

        try:
            result = response.json()
        except Exception:
            result = {
                "message": response.text
            }

        if not response.ok:
            raise Exception({
                "status": response.status_code,
                "response": result
            })

        return result


fabric = FabricClient()
