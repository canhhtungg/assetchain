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
        self.previous_auth_state_file = backend.AUTH_STATE_FILE
        self.permissions_directory = tempfile.TemporaryDirectory()
        backend.APP_SECRET = "test-only-secret"
        backend.AUTH_CREDENTIALS_FILE = None
        backend.ROLE_PERMISSIONS_FILE = os.path.join(
            self.permissions_directory.name, "permissions.json"
        )
        backend.AUTH_STATE_FILE = os.path.join(
            self.permissions_directory.name, "auth-state.json"
        )
        backend.login_failures.clear()
        backend.app.config.update(TESTING=True)
        self.client = backend.app.test_client()

    def tearDown(self):
        backend.APP_SECRET = self.previous_secret
        backend.AUTH_CREDENTIALS_FILE = self.previous_credentials_file
        backend.ROLE_PERMISSIONS_FILE = self.previous_permissions_file
        backend.AUTH_STATE_FILE = self.previous_auth_state_file
        backend.login_failures.clear()
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
        self.assertNotIn("passwordHash", payload["user"])
        self.assertNotIn("password", payload["user"])
        self.assertTrue(payload["user"]["mustChangePassword"])

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
    def test_login_rate_limits_repeated_failures(self, invoke):
        invoke.return_value = {
            "success": True,
            "data": {"result": generate_password_hash("correct-password")},
        }
        for _ in range(backend.LOGIN_FAILURE_LIMIT):
            response = self.client.post(
                "/api/auth/login",
                json={"username": "rate-limited-user", "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 401)
        blocked = self.client.post(
            "/api/auth/login",
            json={"username": "rate-limited-user", "password": "wrong-password"},
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(invoke.call_count, backend.LOGIN_FAILURE_LIMIT)

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

    @patch("app.invoke_chaincode")
    def test_forgot_password_creates_pending_request_without_exposing_lookup(self, invoke):
        invoke.return_value = {
            "success": True,
            "data": {
                "result": {
                    "id": "C001",
                    "username": "customer1",
                    "fullName": "Customer One",
                    "role": "CUSTOMER",
                }
            },
        }
        response = self.client.post(
            "/api/auth/password-reset-requests",
            json={"username": "customer1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Nếu username tồn tại", response.get_json()["message"])
        requests = backend.auth_state_snapshot()["passwordResetRequests"]
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["userID"], "C001")
        self.assertEqual(requests[0]["status"], "pending")

    @patch("app.invoke_chaincode")
    def test_admin_approves_password_reset_to_default_and_requires_change(self, invoke):
        request_item = backend.add_password_reset_request({
            "id": "C001",
            "username": "customer1",
            "fullName": "Customer One",
        })
        invoke.side_effect = [
            {
                "success": True,
                "data": {"result": {"id": "C001", "username": "customer1", "role": "CUSTOMER"}},
            },
            {"success": True, "data": {"result": {}}},
        ]
        token = backend.auth_serializer().dumps({"id": "U001", "role": "ADMIN", "version": 0})
        response = self.client.post(
            f"/api/password-reset-requests/{request_item['id']}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        password_hash = invoke.call_args_list[1].args[1][1]
        self.assertTrue(backend.check_password_hash(password_hash, "12345678"))
        self.assertTrue(backend.password_change_required("C001"))
        self.assertEqual(response.get_json()["data"]["status"], "approved")

    @patch("app.invoke_chaincode")
    def test_required_user_can_change_password_and_receives_new_session(self, invoke):
        version = backend.update_password_state("C001", must_change=True)
        token = backend.auth_serializer().dumps({
            "id": "C001", "role": "CUSTOMER", "version": version
        })
        invoke.side_effect = [
            {
                "success": True,
                "data": {"result": {"id": "C001", "username": "customer1", "role": "CUSTOMER"}},
            },
            {
                "success": True,
                "data": {"result": generate_password_hash("12345678")},
            },
            {"success": True, "data": {"result": {}}},
        ]
        response = self.client.post(
            "/api/auth/change-password",
            json={"currentPassword": "12345678", "newPassword": "new-password-123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(backend.password_change_required("C001"))
        self.assertFalse(response.get_json()["data"]["user"]["mustChangePassword"])
        self.assertTrue(response.get_json()["data"]["token"])

    def test_required_user_is_blocked_from_other_protected_endpoints(self):
        version = backend.update_password_state("C001", must_change=True)
        token = backend.auth_serializer().dumps({
            "id": "C001", "role": "CUSTOMER", "version": version
        })
        response = self.client.get(
            "/api/permissions/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 428)
        self.assertEqual(response.get_json()["code"], "PASSWORD_CHANGE_REQUIRED")

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
    def test_sales_create_customer_response_hides_private_fields(self, invoke):
        invoke.side_effect = [
            {
                "success": True,
                "data": {"result": [{"id": "S001"}, {"id": "C001"}]},
            },
            {"success": True, "data": {"result": {}}},
        ]
        token = backend.auth_serializer().dumps({"id": "S001", "role": "SALES"})
        response = self.client.post(
            "/api/users",
            json={
                "username": "hidden-login",
                "password": "password-123",
                "fullName": "New Customer",
                "role": "customer",
                "contact": "hidden@example.com",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["data"],
            {"id": "user_3", "fullName": "New Customer", "role": "CUSTOMER"},
        )

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

    def test_sales_can_view_created_customer_without_private_fields(self):
        user = {
            "id": "C001",
            "username": "private-login",
            "fullName": "Old Customer",
            "role": "CUSTOMER",
            "contact": "private@example.com",
            "createdBy": "S001",
            "createdAt": "2026-09-15T00:00:00Z",
        }
        visible = backend.public_user_for_identity(
            {"id": "S001", "role": "SALES"}, user
        )
        self.assertEqual(
            visible,
            {"id": "C001", "fullName": "Old Customer", "role": "CUSTOMER"},
        )

    def test_sales_cannot_view_unrelated_customer(self):
        user = {
            "id": "C001",
            "fullName": "Other Customer",
            "role": "CUSTOMER",
            "createdBy": "S002",
        }
        self.assertIsNone(
            backend.public_user_for_identity({"id": "S001", "role": "SALES"}, user)
        )

    @patch("app.invoke_chaincode")
    def test_sales_can_view_customer_they_sold_to_without_private_fields(self, invoke):
        invoke.side_effect = [
            {
                "success": True,
                "data": {
                    "result": [
                        {
                            "id": "C001",
                            "username": "hidden-login",
                            "fullName": "Sold Customer",
                            "role": "CUSTOMER",
                            "contact": "hidden@example.com",
                            "createdBy": "S002",
                        },
                        {
                            "id": "C002",
                            "fullName": "Unrelated Customer",
                            "role": "CUSTOMER",
                            "createdBy": "S002",
                        },
                    ]
                },
            },
            {
                "success": True,
                "data": {
                    "result": [
                        {
                            "id": "SALE-1",
                            "ownerID": "C001",
                            "lastActorID": "S001",
                        }
                    ]
                },
            },
        ]
        token = backend.auth_serializer().dumps({"id": "S001", "role": "SALES"})
        response = self.client.get(
            "/api/users", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["data"],
            [{"id": "C001", "fullName": "Sold Customer", "role": "CUSTOMER"}],
        )

    @patch("app.invoke_chaincode")
    def test_sales_cannot_update_customer(self, invoke):
        invoke.return_value = {
            "success": True,
            "data": {
                "result": {
                    "id": "C001",
                    "fullName": "Customer",
                    "role": "CUSTOMER",
                    "createdBy": "S001",
                }
            },
        }
        token = backend.auth_serializer().dumps({"id": "S001", "role": "SALES"})
        response = self.client.put(
            "/api/users/C001",
            json={"fullName": "Changed"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(invoke.call_count, 1)


if __name__ == "__main__":
    unittest.main()
