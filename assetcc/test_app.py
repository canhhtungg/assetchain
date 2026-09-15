import json
import os
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as backend


class AuthenticationApiTest(unittest.TestCase):
    def setUp(self):
        self.previous_secret = backend.APP_SECRET
        self.previous_credentials_file = backend.AUTH_CREDENTIALS_FILE
        backend.APP_SECRET = "test-only-secret"
        backend.AUTH_CREDENTIALS_FILE = None
        backend.app.config.update(TESTING=True)
        self.client = backend.app.test_client()

    def tearDown(self):
        backend.APP_SECRET = self.previous_secret
        backend.AUTH_CREDENTIALS_FILE = self.previous_credentials_file

    def test_login_requires_username_and_password(self):
        response = self.client.post("/api/auth/login", json={"username": "admin"})
        self.assertEqual(response.status_code, 400)

    def test_parse_chaincode_result_handles_chainlaunch_envelope(self):
        result = {
            "data": {
                "result": {
                    "code": 200,
                    "result": '[{"id":"U001","username":"admin"}]',
                }
            }
        }
        self.assertEqual(
            backend.parse_chaincode_result(result),
            [{"id": "U001", "username": "admin"}],
        )

    @patch("app.invoke_chaincode")
    def test_login_returns_user_and_signed_token(self, invoke):
        password_hash = generate_password_hash("correct-password")
        invoke.side_effect = [
            {"success": True, "data": {"result": password_hash}},
            {
                "success": True,
                "data": {
                    "result": {
                        "id": "U001",
                        "username": "admin",
                        "fullName": "Administrator",
                        "role": "ADMIN",
                    }
                },
            },
        ]

        response = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "correct-password"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()["data"]
        self.assertEqual(payload["user"]["username"], "admin")
        self.assertTrue(payload["token"])
        self.assertNotIn("password", json.dumps(payload["user"]).lower())

    @patch("app.invoke_chaincode")
    def test_login_rejects_wrong_password_without_user_enumeration(self, invoke):
        invoke.return_value = {
            "success": True,
            "data": {"result": generate_password_hash("correct-password")},
        }
        response = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["message"], "Username hoặc password không đúng")
        self.assertEqual(invoke.call_count, 1)

    @patch("app.invoke_chaincode")
    def test_legacy_user_can_use_hashed_credentials_file(self, invoke):
        with tempfile.TemporaryDirectory() as directory:
            credentials_path = os.path.join(directory, "credentials.json")
            with open(credentials_path, "w", encoding="utf-8") as output:
                json.dump({"Admin": generate_password_hash("legacy-password")}, output)
            backend.AUTH_CREDENTIALS_FILE = credentials_path
            invoke.side_effect = [
                {"success": False},
                {
                    "success": True,
                    "data": {"result": {"id": "U001", "username": "admin", "role": "ADMIN"}},
                },
            ]
            response = self.client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "legacy-password"},
            )
        self.assertEqual(response.status_code, 200)

    @patch("app.invoke_chaincode")
    def test_login_falls_back_to_user_list_for_older_chaincode(self, invoke):
        password_hash = generate_password_hash("legacy-password")
        invoke.side_effect = [
            {"success": True, "data": {"result": password_hash}},
            {"success": False, "data": {"message": "function unavailable"}},
            {
                "success": True,
                "data": {
                    "result": [
                        {"id": "U001", "username": "admin", "role": "ADMIN"}
                    ]
                },
            },
        ]

        login_password = "legacy-" + "password"
        response = self.client.post(
            "/api/auth/login",
            json={"username": "ADMIN", "password": login_password},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["user"]["id"], "U001")

    def test_chaincode_proxy_requires_a_session(self):
        response = self.client.post(
            "/api/chaincode/invoke",
            json={"function": "GetAllUsers", "args": []},
        )
        self.assertEqual(response.status_code, 401)

    @patch("app.invoke_chaincode")
    def test_admin_can_delete_another_user(self, invoke):
        token = backend.auth_serializer().dumps(dict(id="U001", role="ADMIN"))
        invoke.return_value = {"success": True, "data": {"status": "success"}}
        response = self.client.delete(
            "/api/users/U002",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        invoke.assert_called_once_with("DeleteUser", ["U002"])

    @patch("app.invoke_chaincode")
    def test_admin_cannot_delete_current_account(self, invoke):
        token = backend.auth_serializer().dumps(dict(id="U001", role="ADMIN"))
        response = self.client.delete(
            "/api/users/U001",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 400)
        invoke.assert_not_called()

    @patch("app.invoke_chaincode")
    def test_chaincode_proxy_accepts_signed_session_and_blocks_auth_functions(self, invoke):
        token = backend.auth_serializer().dumps({"id": "U001", "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}
        invoke.return_value = {
            "success": True,
            "data": {"status": "success", "result": []},
        }

        response = self.client.post(
            "/api/chaincode/invoke",
            json={"function": "GetAllUsers", "args": []},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        invoke.assert_called_once_with("GetAllUsers", [])

        blocked = self.client.post(
            "/api/chaincode/invoke",
            json={"function": "DeleteUser", "args": ["U002"]},
            headers=headers,
        )
        self.assertEqual(blocked.status_code, 403)


if __name__ == "__main__":
    unittest.main()
