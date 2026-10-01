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
        self.previous_security_state_db = backend.SECURITY_STATE_DB
        self.previous_identity_registry_db = backend.IDENTITY_REGISTRY_DB
        self.previous_cookie_secure = backend.AUTH_COOKIE_SECURE
        self.previous_return_bearer = backend.AUTH_RETURN_BEARER_TOKEN
        self.previous_enforce_identity_login = backend.ENFORCE_FABRIC_IDENTITY_LOGIN
        self.permissions_directory = tempfile.TemporaryDirectory()
        backend.APP_SECRET = "test-only-secret"
        backend.AUTH_CREDENTIALS_FILE = None
        backend.ROLE_PERMISSIONS_FILE = os.path.join(
            self.permissions_directory.name, "permissions.json"
        )
        backend.AUTH_STATE_FILE = os.path.join(
            self.permissions_directory.name, "auth-state.json"
        )
        backend.SECURITY_STATE_DB = os.path.join(
            self.permissions_directory.name, "security-state.sqlite3"
        )
        backend.IDENTITY_REGISTRY_DB = os.path.join(
            self.permissions_directory.name, "identity-registry.sqlite3"
        )
        backend.AUTH_COOKIE_SECURE = False
        backend.AUTH_RETURN_BEARER_TOKEN = False
        backend.ENFORCE_FABRIC_IDENTITY_LOGIN = False
        backend.login_failures.clear()
        backend.password_reset_attempts.clear()
        backend.app.config.update(TESTING=True)
        self.client = backend.app.test_client()

    def tearDown(self):
        backend.APP_SECRET = self.previous_secret
        backend.AUTH_CREDENTIALS_FILE = self.previous_credentials_file
        backend.ROLE_PERMISSIONS_FILE = self.previous_permissions_file
        backend.AUTH_STATE_FILE = self.previous_auth_state_file
        backend.SECURITY_STATE_DB = self.previous_security_state_db
        backend.IDENTITY_REGISTRY_DB = self.previous_identity_registry_db
        backend.AUTH_COOKIE_SECURE = self.previous_cookie_secure
        backend.AUTH_RETURN_BEARER_TOKEN = self.previous_return_bearer
        backend.ENFORCE_FABRIC_IDENTITY_LOGIN = self.previous_enforce_identity_login
        backend.login_failures.clear()
        backend.password_reset_attempts.clear()
        self.permissions_directory.cleanup()

    def test_login_requires_username_and_password(self):
        response = self.client.post("/api/auth/login", json={"username": "admin"})
        self.assertEqual(response.status_code, 400)

    def test_api_responses_include_security_headers(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertTrue(response.headers["X-Request-ID"])

    def test_audit_log_is_structured_and_redacts_secrets(self):
        with self.assertLogs("assetchain.audit", level="INFO") as captured:
            backend.audit_event(
                "security.test", "success", "U001", "ADMIN", "U002",
                {"password": "do-not-log", "token": "do-not-log-either", "field": "safe"},
            )
        rendered = "\n".join(captured.output)
        self.assertIn('"event":"security.test"', rendered)
        self.assertIn('"field":"safe"', rendered)
        self.assertIn("[REDACTED]", rendered)
        self.assertNotIn("do-not-log", rendered)

    def test_client_request_id_is_validated_and_returned(self):
        accepted = self.client.get("/api/health", headers={"X-Request-ID": "report-123"})
        self.assertEqual(accepted.headers["X-Request-ID"], "report-123")
        replaced = self.client.get("/api/health", headers={"X-Request-ID": "invalid request id"})
        self.assertNotEqual(replaced.headers["X-Request-ID"], "invalid request id")

    def test_oversized_request_is_rejected(self):
        response = self.client.post(
            "/api/auth/login",
            data="x" * (backend.app.config["MAX_CONTENT_LENGTH"] + 1),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 413)

    def test_runtime_secret_prefers_systemd_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            credential_path = os.path.join(directory, "APP_SECRET")
            with open(credential_path, "w", encoding="utf-8") as output:
                output.write("credential-store-value\n")
            with patch.dict(
                os.environ,
                {"CREDENTIALS_DIRECTORY": directory, "APP_SECRET": "environment-value"},
            ):
                self.assertEqual(
                    backend.runtime_secret("APP_SECRET"), "credential-store-value"
                )

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
    def test_history_uses_explicit_operations_and_keeps_delete_metadata(self, invoke):
        invoke.return_value = {"success": True, "data": {"result": []}}
        history = backend.enrich_asset_history([
            {"value": {"id": "A1", "ownerID": "STORE", "lastOperation": "create"}},
            {"value": {"id": "A1", "ownerID": "STORE", "lastOperation": "update", "lastActorID": "W1"}},
            {"value": {"id": "A1", "ownerID": "STORE", "lastOperation": "delete", "deleted": True, "lastActorID": "W1"}},
        ])
        self.assertEqual([item["operation"] for item in history], ["create", "update", "delete"])
        self.assertEqual(history[-1]["fromOwnerID"], "STORE")
        self.assertEqual(history[-1]["toOwnerID"], "")

    def test_customer_history_starts_at_latest_ownership_acquisition(self):
        history = [
            {"operation": "create", "toOwnerID": "STORE"},
            {"operation": "update", "toOwnerID": "STORE"},
            {"operation": "transfer", "fromOwnerID": "STORE", "toOwnerID": "C001"},
            {"operation": "update", "toOwnerID": "C001"},
            {"operation": "delete", "fromOwnerID": "C001", "toOwnerID": ""},
        ]
        visible = backend.history_visible_to_identity(
            history, {"id": "C001", "role": "CUSTOMER"}
        )
        self.assertEqual(visible, history[2:])

    @patch("app.invoke_chaincode")
    def test_history_index_includes_owned_deleted_assets(self, invoke):
        invoke.return_value = {
            "success": True,
            "data": {"result": [
                {"id": "ACTIVE-1", "name": "Phone", "ownerID": "C001"},
                {"id": "DELETED-1", "name": "Laptop", "ownerID": "C001", "deleted": True},
                {"id": "OTHER-1", "name": "Other", "ownerID": "C002"},
            ]},
        }
        token = backend.auth_serializer().dumps({"id": "C001", "role": "CUSTOMER"})
        response = self.client.get(
            "/api/assets/history-index",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.get_json()["data"]],
            ["ACTIVE-1", "DELETED-1"],
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
        self.assertTrue(payload["csrfToken"])
        self.assertNotIn("token", payload)
        self.assertIn(f"{backend.AUTH_COOKIE_NAME}=", response.headers["Set-Cookie"])
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertNotIn("passwordHash", payload["user"])
        self.assertNotIn("password", payload["user"])
        self.assertTrue(payload["user"]["mustChangePassword"])

    @patch("app.invoke_chaincode")
    def test_login_requires_active_fabric_identity_when_enforced(self, invoke):
        backend.ENFORCE_FABRIC_IDENTITY_LOGIN = True
        invoke.side_effect = [
            {"success": True, "data": {"result": generate_password_hash("correct-password")}},
            {"success": True, "data": {"result": {
                "id": "C900", "username": "pending", "role": "CUSTOMER"
            }}},
        ]
        response = self.client.post(
            "/api/auth/login",
            json={"username": "pending", "password": "correct-password"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "FABRIC_IDENTITY_REQUIRED")

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
    def test_forgot_password_is_rate_limited(self, invoke):
        invoke.return_value = {"success": False}
        for _ in range(backend.PASSWORD_RESET_REQUEST_LIMIT):
            response = self.client.post(
                "/api/auth/password-reset-requests", json={"username": "unknown"}
            )
            self.assertEqual(response.status_code, 200)
        blocked = self.client.post(
            "/api/auth/password-reset-requests", json={"username": "unknown"}
        )
        self.assertEqual(blocked.status_code, 429)

    def test_password_policy_requires_length_variety_and_excludes_username(self):
        self.assertIn("12 ký tự", backend.password_policy_error("Short1!"))
        self.assertIn("3 nhóm", backend.password_policy_error("alllowercase12"))
        self.assertIn("username", backend.password_policy_error("Admin-Strong-123", "admin"))
        self.assertEqual(backend.password_policy_error("Strong-Access-2026!", "customer"), "")

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
        self.assertTrue(response.get_json()["data"]["csrfToken"])
        self.assertNotIn("token", response.get_json()["data"])

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


    def test_cookie_session_requires_csrf_for_mutation(self):
        csrf = "test-csrf-token"
        token = backend.auth_serializer().dumps({
            "id": "U001", "role": "ADMIN", "version": 0, "csrf": csrf
        })
        self.client.set_cookie(backend.AUTH_COOKIE_NAME, token)
        denied = self.client.put("/api/permissions", json={"permissions": {}})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.get_json()["code"], "CSRF_FAILED")

        accepted = self.client.put(
            "/api/permissions", json={"permissions": {}},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(accepted.status_code, 200)

    def test_shared_rate_limit_survives_in_memory_reset(self):
        key = "127.0.0.1:shared-user"
        for _ in range(backend.LOGIN_FAILURE_LIMIT):
            backend.record_login_failure(key)
        backend.login_failures.clear()
        self.assertTrue(backend.login_is_rate_limited(key))

    def test_idempotency_cache_replays_successful_mutation(self):
        scope = ("U001", "/api/assets", "CreateAsset", "request-1", "hash-1")
        expected = {"success": True, "data": {"tx": "abc"}}
        backend.idempotency_put(scope, expected)
        self.assertEqual(backend.idempotency_get(scope), expected)
        conflict = ("U001", "/api/assets", "CreateAsset", "request-1", "hash-2")
        self.assertEqual(backend.idempotency_get(conflict)["status_code"], 409)

    @patch("app.fabric_request")
    def test_mutation_uses_authenticated_users_registered_key(self, fabric_request):
        backend.save_identity_binding({
            "user_id": "U001", "key_id": "user-key-91",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "a" * 64,
            "key_name": "assetchain-U001", "status": "active",
        })
        fabric_request.return_value = {"success": True, "data": {"result": {}}}
        with backend.app.test_request_context("/api/assets", method="POST"):
            backend.request.auth_user = {"id": "U001", "role": "ADMIN"}
            result = backend.invoke_chaincode(
                "CreateAsset",
                ["A1", "Laptop", "Computer", "STORE", "100", "Active", "", "", "1", "U001"],
            )
        self.assertTrue(result["success"])
        self.assertEqual(fabric_request.call_args.kwargs["json"]["key_id"], "user-key-91")

    @patch("app.fabric_request")
    def test_mutation_without_identity_fails_closed(self, fabric_request):
        with backend.app.test_request_context("/api/assets", method="POST"):
            backend.request.auth_user = {"id": "U404", "role": "CUSTOMER"}
            result = backend.invoke_chaincode(
                "DeleteAssetQuantity", ["A1", "1", "U404"]
            )
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "FABRIC_IDENTITY_REQUIRED")
        fabric_request.assert_not_called()

    @patch("app.fabric_request")
    @patch("app.invoke_chaincode")
    def test_admin_provisions_client_key_without_returning_private_key(self, invoke, fabric_request):
        backend.save_identity_binding({
            "user_id": "U001", "key_id": "admin-key-7",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "d" * 64,
            "key_name": "assetchain-U001", "status": "active",
        })
        invoke.side_effect = [
            {"success": True, "data": {"result": {"id": "C001", "role": "CUSTOMER"}}},
            {"success": True, "data": {"result": {}}},
        ]
        certificate = "-----BEGIN CERTIFICATE-----\nYWJj\n-----END CERTIFICATE-----"
        fabric_request.side_effect = [
            {"success": True, "data": {"id": 12, "mspId": "Org1MSP"}},
            {
                "success": True,
                "data": {"id": 91, "certificate": certificate, "privateKey": "must-not-leak"},
            },
        ]
        token = backend.auth_serializer().dumps({"id": "U001", "role": "ADMIN"})
        response = self.client.post(
            "/api/admin/fabric-identities/C001",
            json={
                "organizationID": "12", "mspID": "Org1MSP",
                "name": "assetchain-C001", "description": "AssetChain user C001",
                "dnsNames": ["client.example"], "ipAddresses": ["127.0.0.1"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()["data"]
        self.assertEqual(payload["keyID"], "91")
        self.assertEqual(payload["status"], "active")
        self.assertNotIn("private", json.dumps(response.get_json()).lower())
        self.assertEqual(fabric_request.call_args_list[0].args, (
            "GET", "organizations/12"
        ))
        self.assertEqual(fabric_request.call_args_list[1].args, (
            "POST", "organizations/12/keys"
        ))
        self.assertEqual(fabric_request.call_args_list[1].kwargs["json"], {
            "name": "assetchain-C001", "role": "client",
            "description": "AssetChain user C001",
            "dnsNames": ["client.example"], "ipAddresses": ["127.0.0.1"],
        })
        invoke.assert_any_call(
            "RegisterUserIdentity",
            ["C001", "Org1MSP", backend.certificate_fingerprint(certificate), "U001"],
        )
        self.assertEqual(backend.identity_binding("C001")["key_id"], "91")

    @patch("app.fabric_request")
    @patch("app.invoke_chaincode")
    def test_identity_provision_rejects_msp_not_owned_by_organization(self, invoke, fabric_request):
        backend.save_identity_binding({
            "user_id": "U001", "key_id": "admin-key-7",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "d" * 64,
            "key_name": "assetchain-U001", "status": "active",
        })
        invoke.return_value = {
            "success": True, "data": {"result": {"id": "C001", "role": "CUSTOMER"}}
        }
        fabric_request.return_value = {
            "success": True, "data": {"id": 12, "mspId": "Org1MSP"}
        }
        token = backend.auth_serializer().dumps({"id": "U001", "role": "ADMIN"})
        response = self.client.post(
            "/api/admin/fabric-identities/C001",
            json={"organizationID": "12", "mspID": "OtherMSP"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("không khớp", response.get_json()["message"])
        fabric_request.assert_called_once_with("GET", "organizations/12")
        self.assertIsNone(backend.identity_binding("C001", include_inactive=True))

    @patch("app.provision_fabric_identity")
    def test_admin_approves_identity_request_and_activates_binding(self, provision):
        request_item = backend.add_fabric_identity_request({
            "id": "C009", "username": "customer9",
            "fullName": "Customer Nine", "role": "CUSTOMER",
        }, "S001")
        provision.return_value = ({
            "userID": "C009", "keyID": "customer-key-9",
            "organizationID": "1", "mspID": "Org1MSP",
            "certificateFingerprint": "a" * 64, "status": "active",
        }, None, 201)
        token = backend.auth_serializer().dumps({"id": "U001", "role": "ADMIN"})
        response = self.client.post(
            f"/api/fabric-identity-requests/{request_item['id']}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["status"], "approved")
        provision.assert_called_once_with(
            "C009",
            {
                "organizationID": "1",
                "name": "assetchain-C009-v1",
                "description": "AssetChain per-user signing identity for C009",
            },
            bootstrap=False,
        )

    def test_identity_request_with_orphan_key_never_creates_duplicate(self):
        request_item = backend.add_fabric_identity_request({
            "id": "C010", "username": "customer10",
            "fullName": "Customer Ten", "role": "CUSTOMER",
        }, "S001")
        backend.update_fabric_identity_request(
            request_item["id"], "failed", "U001",
            key_id="orphan-key-10", error="certificate missing",
        )
        token = backend.auth_serializer().dumps({"id": "U001", "role": "ADMIN"})
        with patch("app.provision_fabric_identity") as provision:
            response = self.client.post(
                f"/api/fabric-identity-requests/{request_item['id']}/approve",
                headers={"Authorization": f"Bearer {token}"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertIn("không tự động tạo thêm key", response.get_json()["message"])
        provision.assert_not_called()

    @patch("app.invoke_chaincode")
    def test_admin_completes_pending_bootstrap_with_pending_key(self, invoke):
        backend.save_identity_binding({
            "user_id": "U001", "key_id": "admin-key-7",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "c" * 64,
            "key_name": "assetchain-U001", "status": "pending",
        })
        invoke.return_value = {"success": True, "data": {"result": {}}}
        token = backend.auth_serializer().dumps({"id": "U001", "role": "ADMIN"})
        response = self.client.post(
            "/api/admin/fabric-identities/U001/bootstrap/complete",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        invoke.assert_called_once_with(
            "BootstrapAdminIdentity", ["U001"],
            signing_key_id="admin-key-7", allow_unbound=True,
        )
        self.assertEqual(backend.identity_binding("U001")["status"], "active")

    @patch("app.invoke_chaincode")
    def test_admin_reconciles_completed_ledger_binding_without_duplicate_register(self, invoke):
        backend.save_identity_binding({
            "user_id": "U001", "key_id": "admin-key-7",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "d" * 64,
            "key_name": "assetchain-U001", "status": "active",
        })
        backend.save_identity_binding({
            "user_id": "C001", "key_id": "customer-key-8",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "e" * 64,
            "key_name": "assetchain-C001", "status": "failed",
        })
        invoke.return_value = {
            "success": True,
            "data": {"result": {
                "userID": "C001", "mspID": "Org1MSP",
                "certificateFingerprint": "e" * 64,
            }},
        }
        token = backend.auth_serializer().dumps({"id": "U001", "role": "ADMIN"})
        response = self.client.post(
            "/api/admin/fabric-identities/C001/complete",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        invoke.assert_called_once_with("GetUserIdentity", ["C001"])
        self.assertEqual(backend.identity_binding("C001")["status"], "active")

    def test_chaincode_proxy_requires_a_session(self):
        response = self.client.post(
            "/api/chaincode/invoke",
            json={"function": "GetAllUsers", "args": []},
        )
        self.assertEqual(response.status_code, 401)

    @patch("app.fabric_request")
    @patch("app.invoke_chaincode")
    def test_admin_can_delete_another_user_and_chainlaunch_key(self, invoke, fabric_request):
        backend.save_identity_binding({
            "user_id": "U002", "key_id": "user-key-2",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "f" * 64,
            "key_name": "assetchain-U002", "status": "active",
        })
        token = backend.auth_serializer().dumps(dict(id="U001", role="ADMIN"))
        invoke.return_value = {"success": True, "data": {"status": "success"}}
        fabric_request.side_effect = [
            {
                "success": True, "status_code": 200,
                "data": {"items": [
                    {"id": 31, "name": "assetchain-U002-tls-client"},
                    {"id": "user-key-2", "name": "assetchain-U002-sign-client"},
                ]},
            },
            {"success": True, "status_code": 204, "data": {}},
            {"success": True, "status_code": 204, "data": {}},
        ]
        response = self.client.delete(
            "/api/users/U002",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        invoke.assert_called_once_with("DeleteUser", ["U002", "U001"])
        self.assertEqual(
            [call.args for call in fabric_request.call_args_list],
            [("GET", "keys/all"), ("DELETE", "keys/31"),
             ("DELETE", "keys/user-key-2")],
        )
        self.assertTrue(response.get_json()["identityDeleted"])
        binding = backend.identity_binding("U002", include_inactive=True)
        self.assertEqual(binding["status"], "revoked")
        self.assertIn("TLS/sign keys deleted", binding["last_error"])

    @patch("app.fabric_request")
    @patch("app.invoke_chaincode")
    def test_user_delete_stays_revoked_when_chainlaunch_cleanup_fails(
        self, invoke, fabric_request
    ):
        backend.save_identity_binding({
            "user_id": "U003", "key_id": "user-key-3",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "e" * 64,
            "key_name": "assetchain-U003", "status": "active",
        })
        invoke.return_value = {"success": True, "data": {"status": "success"}}
        fabric_request.side_effect = [
            {
                "success": True, "status_code": 200,
                "data": {"items": [
                    {"id": 33, "name": "assetchain-U003-tls-client"},
                ]},
            },
            {
                "success": False, "status_code": 500,
                "error": "temporary TLS cleanup failure",
            },
            {"success": True, "status_code": 204, "data": {}},
        ]
        token = backend.auth_serializer().dumps(dict(id="U001", role="ADMIN"))
        response = self.client.delete(
            "/api/users/U003", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["identityDeleted"])
        self.assertIn("dọn lại", response.get_json()["message"])
        binding = backend.identity_binding("U003", include_inactive=True)
        self.assertEqual(binding["status"], "revoked")
        self.assertIn("cleanup pending", binding["last_error"])

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
        identity_request = response.get_json()["identityRequest"]
        self.assertEqual(identity_request["user_id"], "user_4")
        self.assertEqual(identity_request["status"], "pending")
        queued = backend.list_fabric_identity_requests()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["userID"], "user_4")

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
        identity_request = response.get_json()["identityRequest"]
        self.assertEqual(identity_request["user_id"], "user_3")
        self.assertEqual(identity_request["requested_by"], "S001")
        self.assertEqual(identity_request["status"], "pending")

    @patch("app.invoke_chaincode")
    def test_auto_user_id_never_reuses_revoked_identity_history(self, invoke):
        backend.save_identity_binding({
            "user_id": "user_9", "key_id": "revoked-key-9",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "9" * 64,
            "key_name": "assetchain-user_9", "status": "revoked",
        })
        invoke.side_effect = [
            {"success": True, "data": {"result": [{"id": "S001"}, {"id": "C001"}]}},
            {"success": True, "data": {"result": {}}},
        ]
        token = backend.auth_serializer().dumps({"id": "S001", "role": "SALES"})
        response = self.client.post(
            "/api/users",
            json={
                "username": "fresh-customer", "fullName": "Fresh Customer",
                "role": "customer", "contact": "fresh@example.com",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["id"], "user_10")
        self.assertEqual(invoke.call_args_list[1].args[1][0], "user_10")

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
            "UpdateUser", ["C001", "Customer", "CUSTOMER", "new@example.com", "C001"]
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

    def test_workflow_mutations_have_actor_indexes_and_classification(self):
        expected = {
            "SubmitAssetCreationRequest": 10,
            "SubmitInventoryTransferRequest": 5,
            "ApproveWorkflowRequest": 2,
            "RejectWorkflowRequest": 2,
            "AcceptWorkflowRequest": 2,
            "DeclineWorkflowRequest": 2,
        }
        for function, index in expected.items():
            self.assertEqual(backend.MUTATION_ACTOR_ARGUMENT_INDEX[function], index)
            self.assertIn(function, backend.MUTATING_CHAINCODE_FUNCTIONS)

    @patch("app.invoke_chaincode")
    def test_warehouse_asset_route_submits_request_without_direct_creation(self, invoke):
        invoke.return_value = {
            "success": True,
            "data": {"result": {
                "id": "WF-CRE-stable", "type": "ASSET_CREATION",
                "status": "PENDING_APPROVAL", "assetID": "SKU-W1",
            }},
        }
        token = backend.auth_serializer().dumps({"id": "W001", "role": "WAREHOUSE"})
        response = self.client.post(
            "/api/assets",
            json={
                "id": "SKU-W1", "name": "Phone", "type": "Electronics",
                "ownerID": "U001", "value": 1000, "quantity": 5, "status": "Active",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "warehouse-create-1",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("sau khi được duyệt", response.get_json()["message"])
        function, args = invoke.call_args.args
        self.assertEqual(function, "SubmitAssetCreationRequest")
        self.assertEqual(args[1], "SKU-W1")
        self.assertEqual(args[4], "STORE")
        self.assertEqual(args[-1], "W001")
        self.assertNotIn("CreateAsset", [call.args[0] for call in invoke.call_args_list])
        self.assertNotIn("password", json.dumps(args).lower())

    @patch("app.invoke_chaincode")
    def test_workflow_request_id_is_stable_for_idempotency_key(self, invoke):
        invoke.return_value = {
            "success": True,
            "data": {"result": {"status": "PENDING_APPROVAL"}},
        }
        token = backend.auth_serializer().dumps({"id": "W001", "role": "WAREHOUSE"})
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "same-create-key",
        }
        body = {
            "id": "SKU-STABLE", "name": "Phone", "type": "Electronics",
            "value": 1000, "quantity": 1, "status": "Active",
        }
        first = self.client.post("/api/workflow/asset-creation-requests", json=body, headers=headers)
        second = self.client.post("/api/workflow/asset-creation-requests", json=body, headers=headers)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(invoke.call_args_list[0].args[1][0], invoke.call_args_list[1].args[1][0])

    @patch("app.invoke_chaincode")
    def test_sales_transfer_route_reserves_via_workflow_without_direct_transfer(self, invoke):
        invoke.side_effect = [
            {"success": True, "data": {"result": {
                "id": "SKU-S1", "ownerID": "STORE", "quantity": 5,
                "reservedQuantity": 0,
            }}},
            {"success": True, "data": {"result": {
                "id": "C001", "role": "CUSTOMER",
            }}},
            {"success": True, "data": {"result": {
                "id": "WF-TRA-1", "type": "INVENTORY_TRANSFER",
                "status": "PENDING_APPROVAL", "assetID": "SKU-S1",
                "targetCustomerID": "C001", "quantity": 2,
            }}},
        ]
        token = backend.auth_serializer().dumps({"id": "S001", "role": "SALES"})
        response = self.client.post(
            "/api/assets/SKU-S1/transfer",
            json={"newOwnerID": "C001", "quantity": 2, "newAssetID": "SALE-S1"},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "sale-1"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("giữ chỗ", response.get_json()["message"])
        functions = [call.args[0] for call in invoke.call_args_list]
        self.assertEqual(functions, ["ReadAsset", "GetUser", "SubmitInventoryTransferRequest"])
        self.assertNotIn("TransferAsset", functions)
        self.assertNotIn("TransferAssetQuantity", functions)

    @patch("app.invoke_chaincode")
    def test_asset_response_derives_available_quantity(self, invoke):
        invoke.return_value = {"success": True, "data": {"result": [{
            "id": "SKU-RSV", "ownerID": "STORE", "quantity": 7,
            "reservedQuantity": 3,
        }]}}
        token = backend.auth_serializer().dumps({"id": "M001", "role": "MANAGER"})
        response = self.client.get(
            "/api/assets", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 200)
        asset = response.get_json()["data"][0]
        self.assertEqual(asset["quantity"], 7)
        self.assertEqual(asset["reservedQuantity"], 3)
        self.assertEqual(asset["availableQuantity"], 4)

    @patch("app.invoke_chaincode")
    def test_sales_transfer_rejects_quantity_that_is_fully_reserved(self, invoke):
        invoke.side_effect = [
            {"success": True, "data": {"result": {
                "id": "SKU-FULL", "ownerID": "STORE", "quantity": 5,
                "reservedQuantity": 5,
            }}},
            {"success": True, "data": {"result": {
                "id": "C001", "role": "CUSTOMER",
            }}},
        ]
        token = backend.auth_serializer().dumps({"id": "S001", "role": "SALES"})
        response = self.client.post(
            "/api/assets/SKU-FULL/transfer",
            json={"newOwnerID": "C001", "quantity": 1, "newAssetID": "SALE-FULL"},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("0 sản phẩm khả dụng", response.get_json()["message"])
        self.assertEqual(
            [call.args[0] for call in invoke.call_args_list],
            ["ReadAsset", "GetUser"],
        )

    @patch("app.invoke_chaincode")
    def test_transfer_approval_requires_active_customer_identity_binding(self, invoke):
        backend.save_identity_binding({
            "user_id": "C-NO-ID", "key_id": "pending-key",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "b" * 64,
            "key_name": "assetchain-C-NO-ID", "status": "pending",
        })
        invoke.return_value = {"success": True, "data": {"result": {
            "id": "T-NO-ID", "type": "INVENTORY_TRANSFER",
            "targetCustomerID": "C-NO-ID", "status": "PENDING_APPROVAL",
        }}}
        token = backend.auth_serializer().dumps({"id": "M001", "role": "MANAGER"})
        response = self.client.post(
            "/api/workflow/requests/T-NO-ID/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("chưa có Fabric identity đang hoạt động", response.get_json()["message"])
        invoke.assert_called_once_with("ReadWorkflowRequest", ["T-NO-ID"])

    @patch("app.invoke_chaincode")
    def test_workflow_request_list_has_strict_role_filtering(self, invoke):
        items = [
            {"id": "C1", "makerID": "W001", "type": "ASSET_CREATION", "status": "PENDING_APPROVAL"},
            {"id": "T1", "makerID": "S001", "targetCustomerID": "C001", "type": "INVENTORY_TRANSFER", "status": "AWAITING_CUSTOMER"},
            {"id": "T2", "makerID": "S002", "targetCustomerID": "C002", "type": "INVENTORY_TRANSFER", "status": "COMPLETED"},
        ]
        invoke.return_value = {"success": True, "data": {"result": items}}
        cases = [
            ({"id": "U001", "role": "ADMIN"}, ["C1", "T1", "T2"]),
            ({"id": "M001", "role": "MANAGER"}, ["C1", "T1", "T2"]),
            ({"id": "W001", "role": "WAREHOUSE"}, ["C1"]),
            ({"id": "S001", "role": "SALES"}, ["T1"]),
            ({"id": "C001", "role": "CUSTOMER"}, ["T1"]),
        ]
        for identity, expected_ids in cases:
            with self.subTest(role=identity["role"]):
                token = backend.auth_serializer().dumps(identity)
                response = self.client.get(
                    "/api/workflow/requests",
                    headers={"Authorization": f"Bearer {token}"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    [item["id"] for item in response.get_json()["data"]],
                    expected_ids,
                )

    @patch("app.invoke_chaincode")
    def test_workflow_decisions_enforce_route_roles_and_actor(self, invoke):
        backend.save_identity_binding({
            "user_id": "C001", "key_id": "customer-key-1",
            "organization_id": "12", "msp_id": "Org1MSP",
            "certificate_fingerprint": "a" * 64,
            "key_name": "assetchain-C001", "status": "active",
        })
        invoke.side_effect = [
            {
                "success": True,
                "data": {"result": {
                    "id": "T1", "type": "INVENTORY_TRANSFER",
                    "targetCustomerID": "C001", "status": "PENDING_APPROVAL",
                }},
            },
            {
                "success": True,
                "data": {"result": {"id": "T1", "status": "AWAITING_CUSTOMER"}},
            },
        ]
        sales_token = backend.auth_serializer().dumps({"id": "S001", "role": "SALES"})
        denied = self.client.post(
            "/api/workflow/requests/T1/approve",
            headers={"Authorization": f"Bearer {sales_token}"},
        )
        self.assertEqual(denied.status_code, 403)
        invoke.assert_not_called()

        manager_token = backend.auth_serializer().dumps({"id": "M001", "role": "MANAGER"})
        approved = self.client.post(
            "/api/workflow/requests/T1/approve",
            json={"reason": "verified"},
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(invoke.call_args_list[0].args, ("ReadWorkflowRequest", ["T1"]))
        self.assertEqual(
            invoke.call_args_list[1].args,
            ("ApproveWorkflowRequest", ["T1", "verified", "M001"]),
        )

        invoke.reset_mock()
        invoke.side_effect = None
        invoke.return_value = {
            "success": True,
            "data": {"result": {"id": "T1", "status": "COMPLETED"}},
        }
        customer_token = backend.auth_serializer().dumps({"id": "C001", "role": "CUSTOMER"})
        accepted = self.client.post(
            "/api/workflow/requests/T1/accept",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        self.assertEqual(accepted.status_code, 200)
        invoke.assert_called_once_with(
            "AcceptWorkflowRequest", ["T1", "", "C001"]
        )

    @patch("app.invoke_chaincode")
    def test_manager_pending_count_excludes_customer_only_stage(self, invoke):
        invoke.return_value = {"success": True, "data": {"result": [
            {"id": "C1", "status": "PENDING_APPROVAL"},
            {"id": "T1", "status": "AWAITING_CUSTOMER"},
            {"id": "T2", "status": "COMPLETED"},
        ]}}
        token = backend.auth_serializer().dumps({"id": "M001", "role": "MANAGER"})
        response = self.client.get(
            "/api/workflow/pending-counts",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"], {
            "pendingApproval": 1, "awaitingCustomer": 1, "total": 1,
        })

    @patch("app.invoke_chaincode")
    def test_customer_pending_count_only_includes_target_requests(self, invoke):
        invoke.return_value = {"success": True, "data": {"result": [
            {"id": "T1", "targetCustomerID": "C001", "status": "AWAITING_CUSTOMER"},
            {"id": "T2", "targetCustomerID": "C002", "status": "AWAITING_CUSTOMER"},
            {"id": "T3", "targetCustomerID": "C001", "status": "COMPLETED"},
        ]}}
        token = backend.auth_serializer().dumps({"id": "C001", "role": "CUSTOMER"})
        response = self.client.get(
            "/api/workflow/pending-counts",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"], {
            "pendingApproval": 0, "awaitingCustomer": 1, "total": 1,
        })


if __name__ == "__main__":
    unittest.main()
