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
        self.previous_permissions_file = backend.ROLE_PERMISSIONS_FILE
        self.permissions_directory = tempfile.TemporaryDirectory()
        backend.APP_SECRET = "test-only-secret"
        backend.AUTH_CREDENTIALS_FILE = None
        backend.ROLE_PERMISSIONS_FILE = os.path.join(
            self.permissions_directory.name, "permissions.json"
        )
        backend.app.config.update(TESTING=True)
        self.client = backend.app.test_client()

    def tearDown(self):
        backend.APP_SECRET = self.previous_secret
        backend.AUTH_CREDENTIALS_FILE = self.previous_credentials_file
        backend.ROLE_PERMISSIONS_FILE = self.previous_permissions_file
        self.permissions_directory.cleanup()

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
            json={"function": "AssetExists", "args": ["A001"]},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        invoke.assert_called_once_with("AssetExists", ["A001"])

        blocked = self.client.post(
            "/api/chaincode/invoke",
            json={"function": "DeleteUser", "args": ["U002"]},
            headers=headers,
        )
        self.assertEqual(blocked.status_code, 403)

    @patch("app.invoke_chaincode")
    def test_update_asset_rejects_invalid_numeric_fields(self, invoke):
        token = backend.auth_serializer().dumps({"id": "U001", "role": "ADMIN"})
        invoke.return_value = {
            "success": True,
            "data": {"result": {"id": "A001", "ownerID": "STORE"}},
        }
        response = self.client.put(
            "/api/assets/A001",
            json={
                "name": "Laptop",
                "type": "Computer",
                "ownerID": "STORE",
                "value": "invalid",
                "quantity": 1,
                "status": "Active",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(invoke.call_count, 1)

    @patch("app.load_role_permissions")
    @patch("app.invoke_chaincode")
    def test_non_admin_update_preserves_current_owner(self, invoke, load_permissions):
        load_permissions.return_value = {
            "manager": ["view_all_assets", "update_asset"],
            "sales": [],
            "warehouse": [],
            "customer": [],
        }
        token = backend.auth_serializer().dumps({"id": "M001", "role": "MANAGER"})
        invoke.side_effect = [
            {
                "success": True,
                "data": {"result": {"id": "A001", "ownerID": "STORE"}},
            },
            {"success": True, "data": {"result": {}}},
        ]
        response = self.client.put(
            "/api/assets/A001",
            json={
                "name": "Laptop",
                "type": "Computer",
                "ownerID": "C001",
                "value": 100,
                "quantity": 2,
                "status": "Active",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(invoke.call_args_list[1].args[1][3], "STORE")

    @patch("app.invoke_chaincode")
    def test_sales_can_only_transfer_inventory_to_customer(self, invoke):
        token = backend.auth_serializer().dumps({"id": "S001", "role": "SALES"})
        invoke.side_effect = [
            {
                "success": True,
                "data": {
                    "result": {
                        "id": "SKU-1",
                        "ownerID": "STORE",
                        "quantity": 2,
                    }
                },
            },
            {
                "success": True,
                "data": {"result": {"id": "M001", "role": "MANAGER"}},
            },
        ]
        response = self.client.post(
            "/api/assets/SKU-1/transfer",
            json={"newOwnerID": "M001", "quantity": 1, "newAssetID": "SALE-1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(invoke.call_count, 2)

    @patch("app.invoke_chaincode")
    def test_create_user_generates_id_and_contact_fallback(self, invoke):
        token = backend.auth_serializer().dumps(dict(id="U001", role="ADMIN"))
        invoke.side_effect = [
            {
                "success": True,
                "data": {"result": [{"id": "U001"}, {"id": "U002"}, {"id": "U003"}]},
            },
            {"success": True, "data": {"result": {}}},
        ]
        response = self.client.post(
            "/api/users",
            json={
                "username": "newcustomer",
                "password": "password-123",
                "fullName": "New Customer",
                "role": "customer",
                "contact": "",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["id"], "user_4")
        create_args = invoke.call_args_list[1].args[1]
        self.assertEqual(create_args[0], "user_4")
        self.assertEqual(create_args[5], "user_4")
        self.assertEqual(create_args[6], "U001")

    @patch("app.invoke_chaincode")
    def test_customer_can_only_update_own_contact(self, invoke):
        token = backend.auth_serializer().dumps(dict(id="C001", role="CUSTOMER"))
        invoke.side_effect = [
            {
                "success": True,
                "data": {
                    "result": {
                        "id": "C001",
                        "fullName": "Customer",
                        "role": "CUSTOMER",
                        "contact": "old@example.com",
                    }
                },
            },
            {"success": True, "data": {"result": {}}},
        ]
        response = self.client.put(
            "/api/users/C001",
            json={"contact": "new@example.com"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        invoke.assert_called_with(
            "UpdateUser", ["C001", "Customer", "CUSTOMER", "new@example.com"]
        )

    def test_sales_cannot_view_customer_after_ten_minutes(self):
        user = {
            "id": "C001",
            "fullName": "Old Customer",
            "role": "CUSTOMER",
            "createdBy": "S001",
            "createdAt": "2026-09-15T00:00:00Z",
        }
        self.assertIsNone(
            backend.public_user_for_identity({"id": "S001", "role": "SALES"}, user)
        )


if __name__ == "__main__":
    unittest.main()
