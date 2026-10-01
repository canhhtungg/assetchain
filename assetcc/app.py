import os
import json
import logging
import requests
import hashlib
import hmac
import sqlite3
import ssl
from collections import defaultdict, deque
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock
from time import monotonic, time

from flask import Flask, g, has_request_context, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()


def runtime_secret(name):
    credentials_directory = os.getenv("CREDENTIALS_DIRECTORY")
    if credentials_directory:
        credential_path = Path(credentials_directory) / name
        try:
            return credential_path.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError:
            pass
    return os.getenv(name)


# ==========================================
# FLASK CONFIG
# ==========================================

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_REQUEST_BYTES", "65536"))

audit_logger = logging.getLogger("assetchain.audit")
audit_logger.setLevel(logging.INFO)
if not audit_logger.handlers:
    audit_handler = logging.StreamHandler()
    audit_handler.setFormatter(logging.Formatter("AUDIT %(message)s"))
    audit_logger.addHandler(audit_handler)
audit_logger.propagate = False

AUDIT_REDACTED_KEYS = {
    "authorization", "cookie", "password", "passwordhash", "secret", "token"
}


def audit_clean(value, key=""):
    normalized_key = str(key).replace("_", "").lower()
    if any(redacted in normalized_key for redacted in AUDIT_REDACTED_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): audit_clean(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [audit_clean(item) for item in value]
    if isinstance(value, str):
        return value[:256]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:256]


def request_client_ip():
    if not has_request_context():
        return ""
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    return forwarded_for or request.remote_addr or "unknown"


def audit_event(event, outcome, actor_id=None, actor_role=None, target_id=None, details=None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": str(event),
        "outcome": str(outcome),
        "actorID": str(actor_id or ""),
        "actorRole": normalize_role(actor_role) if actor_role else "",
        "targetID": str(target_id or ""),
    }
    if has_request_context():
        entry.update({
            "requestID": getattr(g, "request_id", ""),
            "clientIP": request_client_ip(),
            "method": request.method,
            "path": request.path,
        })
    if details:
        entry["details"] = audit_clean(details)
    audit_logger.info(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))


@app.before_request
def assign_request_id():
    supplied = request.headers.get("X-Request-ID", "").strip()
    if supplied and len(supplied) <= 64 and all(character.isalnum() or character in "-_." for character in supplied):
        g.request_id = supplied
    else:
        g.request_id = token_urlsafe(12)


@app.errorhandler(413)
def request_too_large(_error):
    audit_event("request.rejected", "rejected", details={"reason": "payload_too_large"})
    return jsonify({
        "status": "error",
        "message": "Dữ liệu gửi lên vượt quá giới hạn cho phép",
    }), 413

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,https://canhhtungg.github.io",
    ).split(",")
    if origin.strip()
]
CORS(
    app,
    resources={r"/api/*": {"origins": ALLOWED_ORIGINS}},
    supports_credentials=True,
)

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-Permitted-Cross-Domain-Policies": "none",
}


@app.after_request
def add_security_headers(response):
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Pragma", "no-cache")
    response.headers.setdefault("X-Request-ID", getattr(g, "request_id", ""))
    return response


# ==========================================
# CHAINLAUNCH CONFIG
# ==========================================

FABRIC_HOST = os.getenv(
    "FABRIC_HOST",
    "http://127.0.0.1:8100/api/v1"
)

FABRIC_USERNAME = runtime_secret("FABRIC_USERNAME")

FABRIC_PASSWORD = runtime_secret("FABRIC_PASSWORD")

APP_SECRET = runtime_secret("APP_SECRET")
AUTH_TOKEN_MAX_AGE = int(os.getenv("AUTH_TOKEN_MAX_AGE", "28800"))
AUTH_RETURN_BEARER_TOKEN = os.getenv("AUTH_RETURN_BEARER_TOKEN", "0") == "1"
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "assetchain_session")
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "1") != "0"
AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "None")
SECURITY_STATE_DB = os.getenv("SECURITY_STATE_DB", "").strip()
IDENTITY_REGISTRY_DB = os.getenv("IDENTITY_REGISTRY_DB", "").strip()
ENFORCE_FABRIC_IDENTITY_LOGIN = os.getenv("ENFORCE_FABRIC_IDENTITY_LOGIN", "0") == "1"
FABRIC_IDENTITY_ORGANIZATION_ID = os.getenv(
    "FABRIC_IDENTITY_ORGANIZATION_ID", "1"
).strip()
IDEMPOTENCY_TTL = int(os.getenv("IDEMPOTENCY_TTL", "86400"))
AUTH_CREDENTIALS_FILE = os.getenv("AUTH_CREDENTIALS_FILE")
ROLE_PERMISSIONS_FILE = os.getenv("ROLE_PERMISSIONS_FILE") or str(
    Path(__file__).with_name("role-permissions.local.json")
)
AUTH_STATE_FILE = os.getenv("AUTH_STATE_FILE") or str(
    Path(__file__).with_name("auth-state.local.json")
)
DEFAULT_INITIAL_PASSWORD = os.getenv("DEFAULT_INITIAL_PASSWORD", "12345678")

ROLE_ALIASES = {"user": "customer"}
ROLE_LABELS = {
    "admin": "Admin",
    "manager": "Quản lý",
    "sales": "Nhân viên bán hàng",
    "warehouse": "Nhân viên kho",
    "customer": "Khách hàng",
}
DEFAULT_ROLE_PERMISSIONS = {
    "manager": ["view_all_assets", "view_users", "create_staff", "update_asset", "update_user", "view_history"],
    "sales": ["view_inventory", "view_customers", "create_customer", "transfer_asset", "view_history"],
    "warehouse": ["view_inventory", "create_asset", "update_asset", "view_history"],
    "customer": ["view_own_assets", "update_own_contact", "delete_own_asset", "view_history"],
}
ALL_PERMISSIONS = [
    "view_all_assets", "view_inventory", "view_own_assets", "view_users",
    "view_customers", "create_staff", "create_customer", "create_asset",
    "update_asset", "delete_asset", "delete_own_asset", "transfer_asset",
    "sell_back", "view_history", "update_user", "update_own_contact",
    "manage_permissions",
]
STORE_USER_ID = "STORE"
ADMIN_OWNER_ID = os.getenv("ADMIN_OWNER_ID", "U001")
LOGIN_FAILURE_LIMIT = int(os.getenv("LOGIN_FAILURE_LIMIT", "8"))
LOGIN_FAILURE_WINDOW = int(os.getenv("LOGIN_FAILURE_WINDOW", "600"))
PASSWORD_RESET_REQUEST_LIMIT = int(os.getenv("PASSWORD_RESET_REQUEST_LIMIT", "5"))
PASSWORD_RESET_REQUEST_WINDOW = int(os.getenv("PASSWORD_RESET_REQUEST_WINDOW", "600"))
login_failures = defaultdict(deque)
login_failures_lock = Lock()
password_reset_attempts = defaultdict(deque)
password_reset_attempts_lock = Lock()
auth_state_lock = Lock()

FABRIC_CHAINCODE_ID = os.getenv(
    "FABRIC_CHAINCODE_ID",
    "1"
)

FABRIC_KEY_ID = os.getenv(
    "FABRIC_KEY_ID",
    "6"
)

# Actor position for every public chaincode mutation. Queries deliberately use
# the service identity; mutations must resolve a per-user key from the registry.
MUTATION_ACTOR_ARGUMENT_INDEX = {
    "CreateAsset": 9,
    "CreateUser": 6,
    "DeleteAsset": 1,
    "DeleteUser": 1,
    "SetUserPassword": 2,
    "MigrateUserCredential": 1,
    "TransferAsset": 2,
    "TransferAssetQuantity": 4,
    "UpdateAsset": 9,
    "UpdateUser": 4,
    "ReturnAssetToStore": 1,
    "DeleteAssetQuantity": 2,
    "EnsureStoreUser": 0,
    "RegisterUserIdentity": 3,
    "RotateUserIdentity": 3,
    "SubmitAssetCreationRequest": 10,
    "SubmitInventoryTransferRequest": 5,
    "ApproveWorkflowRequest": 2,
    "RejectWorkflowRequest": 2,
    "AcceptWorkflowRequest": 2,
    "DeclineWorkflowRequest": 2,
}


# ==========================================
# HTTP SESSION
# ==========================================

session = requests.Session()


# ==========================================
# CHAINLAUNCH LOGIN
# ==========================================

def login_chainlaunch():

    if not FABRIC_USERNAME or not FABRIC_PASSWORD:
        return None

    try:

        response = session.post(
            f"{FABRIC_HOST}/auth/login",
            json={
                "username": FABRIC_USERNAME,
                "password": FABRIC_PASSWORD
            },
            timeout=10
        )

        return response

    except requests.exceptions.RequestException:

        return None


# ==========================================
# GENERIC FABRIC REQUEST
# ==========================================

def fabric_request(method, endpoint, **kwargs):

    endpoint = endpoint.lstrip("/")

    url = f"{FABRIC_HOST}/{endpoint}"

    kwargs.setdefault("timeout", 30)

    try:

        login_response = login_chainlaunch()

        if login_response is None:

            return {
                "success": False,
                "error": "Không thể kết nối tới ChainLaunch"
            }

        if not login_response.ok:

            return {
                "success": False,
                "error": "Đăng nhập ChainLaunch thất bại",
                "status_code": login_response.status_code,
                "details": login_response.text
            }

        response = session.request(
            method,
            url,
            **kwargs
        )

        try:
            data = response.json()
        except ValueError:
            data = {
                "raw_response": response.text
            }

        return {
            "success": response.ok,
            "status_code": response.status_code,
            "data": data
        }

    except requests.exceptions.ConnectionError as error:

        return {
            "success": False,
            "error": "Không thể kết nối tới ChainLaunch",
            "details": str(error)
        }

    except requests.exceptions.Timeout:

        return {
            "success": False,
            "error": "Kết nối ChainLaunch bị timeout"
        }

    except Exception as error:

        return {
            "success": False,
            "error": str(error)
        }


# ==========================================
# FABRIC IDENTITY REGISTRY + CHAINCODE INVOKE
# ==========================================

def identity_registry_connection():
    """Open the local public-metadata registry; private keys never enter it."""
    if not IDENTITY_REGISTRY_DB:
        return None
    path = Path(IDENTITY_REGISTRY_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS fabric_identity_bindings (
            user_id TEXT PRIMARY KEY,
            key_id TEXT NOT NULL UNIQUE,
            organization_id TEXT NOT NULL,
            msp_id TEXT NOT NULL,
            certificate_fingerprint TEXT NOT NULL,
            key_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'active', 'failed', 'revoked')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_error TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS fabric_identity_requests (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            full_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT '',
            requested_by TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK(status IN (
                'pending', 'processing', 'approved', 'rejected', 'failed'
            )),
            requested_at TEXT NOT NULL,
            reviewed_at TEXT NOT NULL DEFAULT '',
            reviewed_by TEXT NOT NULL DEFAULT '',
            key_id TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_fabric_identity_requests_status
            ON fabric_identity_requests(status, requested_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fabric_identity_requests_actionable
            ON fabric_identity_requests(user_id)
            WHERE status IN ('pending', 'processing', 'failed');
    """)
    try:
        os.chmod(path, 0o600)
    except OSError:
        connection.close()
        raise
    return connection


def identity_binding(user_id, include_inactive=False):
    connection = identity_registry_connection()
    if connection is None:
        return None
    query = "SELECT * FROM fabric_identity_bindings WHERE user_id = ?"
    parameters = [str(user_id)]
    if not include_inactive:
        query += " AND status = 'active'"
    row = connection.execute(query, parameters).fetchone()
    connection.close()
    return dict(row) if row else None


def add_fabric_identity_request(user, requested_by):
    """Queue one durable, de-duplicated provisioning request for a ledger user."""
    user_id = str(user.get("id", "")).strip()
    if not user_id or normalize_role(user.get("role")) == "store":
        return None
    if identity_binding(user_id) is not None:
        return None
    connection = identity_registry_connection()
    if connection is None:
        raise RuntimeError("IDENTITY_REGISTRY_DB chưa được cấu hình")
    existing = connection.execute(
        """SELECT * FROM fabric_identity_requests
           WHERE user_id = ? AND status IN ('pending', 'processing', 'failed')
           ORDER BY requested_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()
    if existing:
        connection.close()
        return dict(existing)
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "id": token_urlsafe(12),
        "user_id": user_id,
        "username": str(user.get("username", "")),
        "full_name": str(user.get("fullName", "")),
        "role": normalize_role(user.get("role")).upper(),
        "requested_by": str(requested_by or ""),
        "status": "pending",
        "requested_at": now,
    }
    with connection:
        connection.execute(
            """INSERT INTO fabric_identity_requests
               (id, user_id, username, full_name, role, requested_by,
                status, requested_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(item[key] for key in (
                "id", "user_id", "username", "full_name", "role",
                "requested_by", "status", "requested_at",
            )),
        )
    connection.close()
    return item


def list_fabric_identity_requests():
    connection = identity_registry_connection()
    if connection is None:
        return None
    rows = connection.execute(
        """SELECT id, user_id AS userID, username, full_name AS fullName,
                  role, requested_by AS requestedBy, status,
                  requested_at AS requestedAt, reviewed_at AS reviewedAt,
                  reviewed_by AS reviewedBy, key_id AS keyID,
                  last_error AS lastError
           FROM fabric_identity_requests
           ORDER BY requested_at DESC"""
    ).fetchall()
    connection.close()
    return [dict(row) for row in rows]


def fabric_identity_request(request_id):
    connection = identity_registry_connection()
    if connection is None:
        return None
    row = connection.execute(
        "SELECT * FROM fabric_identity_requests WHERE id = ?", (str(request_id),)
    ).fetchone()
    connection.close()
    return dict(row) if row else None


def claim_fabric_identity_request(request_id, reviewer_id):
    """Atomically claim a request so two Admins cannot create duplicate keys."""
    connection = identity_registry_connection()
    if connection is None:
        return None
    now = datetime.now(timezone.utc).isoformat()
    with connection:
        cursor = connection.execute(
            """UPDATE fabric_identity_requests
               SET status = 'processing', reviewed_at = ?, reviewed_by = ?,
                   last_error = ''
               WHERE id = ? AND status IN ('pending', 'failed')""",
            (now, str(reviewer_id or ""), str(request_id)),
        )
    selected = connection.execute(
        "SELECT * FROM fabric_identity_requests WHERE id = ?", (str(request_id),)
    ).fetchone()
    connection.close()
    if cursor.rowcount != 1:
        return None
    return dict(selected)


def update_fabric_identity_request(request_id, status, reviewer_id, *, key_id="", error=""):
    connection = identity_registry_connection()
    if connection is None:
        return None
    now = datetime.now(timezone.utc).isoformat()
    with connection:
        connection.execute(
            """UPDATE fabric_identity_requests
               SET status = ?, reviewed_at = ?, reviewed_by = ?,
                   key_id = CASE WHEN ? != '' THEN ? ELSE key_id END,
                   last_error = ?
               WHERE id = ?""",
            (
                str(status), now, str(reviewer_id or ""), str(key_id or ""),
                str(key_id or ""), str(error or "")[:512], str(request_id),
            ),
        )
    connection.close()
    return next(
        (item for item in (list_fabric_identity_requests() or [])
         if item.get("id") == str(request_id)),
        None,
    )


def save_identity_binding(binding):
    connection = identity_registry_connection()
    if connection is None:
        raise RuntimeError("IDENTITY_REGISTRY_DB chưa được cấu hình")
    now = datetime.now(timezone.utc).isoformat()
    with connection:
        connection.execute(
            """INSERT INTO fabric_identity_bindings
               (user_id, key_id, organization_id, msp_id,
                certificate_fingerprint, key_name, status, created_at,
                updated_at, last_error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 key_id=excluded.key_id,
                 organization_id=excluded.organization_id,
                 msp_id=excluded.msp_id,
                 certificate_fingerprint=excluded.certificate_fingerprint,
                 key_name=excluded.key_name,
                 status=excluded.status,
                 updated_at=excluded.updated_at,
                 last_error=excluded.last_error""",
            (
                str(binding["user_id"]), str(binding["key_id"]),
                str(binding["organization_id"]), str(binding["msp_id"]),
                str(binding["certificate_fingerprint"]).lower(),
                str(binding["key_name"]), str(binding["status"]),
                str(binding.get("created_at") or now), now,
                str(binding.get("last_error") or "")[:512],
            ),
        )
    connection.close()


def mark_identity_binding(user_id, status, error=""):
    connection = identity_registry_connection()
    if connection is None:
        raise RuntimeError("IDENTITY_REGISTRY_DB chưa được cấu hình")
    with connection:
        connection.execute(
            """UPDATE fabric_identity_bindings
               SET status = ?, updated_at = ?, last_error = ?
               WHERE user_id = ?""",
            (status, datetime.now(timezone.utc).isoformat(), str(error)[:512], str(user_id)),
        )
    connection.close()


def delete_chainlaunch_identity(binding):
    """Delete the exact TLS/sign key pair created for one application user."""
    if not binding or not str(binding.get("key_id", "")).strip():
        return True, ""

    # Organization provisioning creates two keys while returning the signing
    # key ID. Resolve the TLS peer by its exact deterministic name; never assume
    # adjacent numeric IDs because concurrent provisioning can interleave them.
    key_name = str(binding.get("key_name", "")).strip()
    tls_name = f"{key_name}-tls-client" if key_name else ""
    inventory = fabric_request("GET", "keys/all")
    if not inventory.get("success"):
        return False, str(
            inventory.get("error")
            or response_object(inventory.get("data")).get("message")
            or "Không thể đối soát TLS key trong ChainLaunch"
        )
    inventory_data = inventory.get("data")
    for _ in range(4):
        if isinstance(inventory_data, dict) and isinstance(
            inventory_data.get("data"), (dict, list)
        ):
            inventory_data = inventory_data["data"]
        elif isinstance(inventory_data, dict) and isinstance(
            inventory_data.get("result"), (dict, list)
        ):
            inventory_data = inventory_data["result"]
        else:
            break
    items = inventory_data.get("items", []) if isinstance(inventory_data, dict) else inventory_data
    if not isinstance(items, list):
        return False, "ChainLaunch trả về danh sách key không hợp lệ"
    tls_id = next(
        (
            str(item.get("id")) for item in items
            if isinstance(item, dict) and tls_name
            and hmac.compare_digest(str(item.get("name", "")), tls_name)
        ),
        "",
    )

    key_ids = []
    if tls_id:
        key_ids.append(("TLS", tls_id))
    key_ids.append(("signing", str(binding["key_id"])))
    errors = []
    for key_type, key_id in key_ids:
        result = fabric_request("DELETE", f"keys/{key_id}")
        if not result.get("success") and result.get("status_code") != 404:
            message = str(
                result.get("error")
                or response_object(result.get("data")).get("message")
                or f"ChainLaunch không thể xóa {key_type} key"
            )
            errors.append(f"{key_type}: {message}")
    return not errors, "; ".join(errors)


def identity_request_is_processing(user_id):
    connection = identity_registry_connection()
    if connection is None:
        return False
    row = connection.execute(
        """SELECT 1 FROM fabric_identity_requests
           WHERE user_id = ? AND status = 'processing' LIMIT 1""",
        (str(user_id),),
    ).fetchone()
    connection.close()
    return row is not None


def cancel_fabric_identity_requests(user_id, reviewer_id):
    connection = identity_registry_connection()
    if connection is None:
        return
    now = datetime.now(timezone.utc).isoformat()
    with connection:
        connection.execute(
            """UPDATE fabric_identity_requests
               SET status = 'rejected', reviewed_at = ?, reviewed_by = ?,
                   last_error = 'ledger user deleted'
               WHERE user_id = ? AND status IN ('pending', 'failed')""",
            (now, str(reviewer_id or ""), str(user_id)),
        )
    connection.close()


def mutation_actor_id(function, args):
    index = MUTATION_ACTOR_ARGUMENT_INDEX.get(function)
    if index is None:
        return None
    if index >= len(args):
        return ""
    return str(args[index]).strip()


def invoke_chaincode(function, args=None, *, signing_key_id=None, allow_unbound=False):

    if args is None:
        args = []

    actor_id = mutation_actor_id(function, args)
    if function in MUTATING_CHAINCODE_FUNCTIONS or function in MUTATION_ACTOR_ARGUMENT_INDEX:
        authenticated_id = ""
        if has_request_context():
            authenticated_id = str(getattr(request, "auth_user", {}).get("id", "")).strip()
        if not actor_id:
            return {"success": False, "status_code": 403, "error": "Mutation thiếu actorID"}
        if authenticated_id and not hmac.compare_digest(authenticated_id, actor_id):
            return {"success": False, "status_code": 403, "error": "actorID không khớp phiên đăng nhập"}
        if signing_key_id is None:
            binding = identity_binding(actor_id)
            if binding is None:
                return {
                    "success": False,
                    "status_code": 409,
                    "error": "FABRIC_IDENTITY_REQUIRED",
                    "details": f"User {actor_id} chưa có Fabric identity đang hoạt động",
                }
            signing_key_id = binding["key_id"]
        elif not allow_unbound:
            binding = identity_binding(actor_id)
            if binding is None or not hmac.compare_digest(str(binding["key_id"]), str(signing_key_id)):
                return {"success": False, "status_code": 403, "error": "Signing key không thuộc actor"}

    scope = idempotency_scope(function, args)
    cached = idempotency_get(scope)
    if cached is not None:
        return cached

    endpoint = (
        f"sc/fabric/chaincodes/"
        f"{FABRIC_CHAINCODE_ID}/invoke"
    )

    payload = {
        "key_id": str(signing_key_id or FABRIC_KEY_ID),
        "function": function,
        "args": args
    }

    result = fabric_request(
        "POST",
        endpoint,
        json=payload
    )
    idempotency_put(scope, result)
    return result


# ==========================================
# PARSE CHAINCODE RESULT
# ==========================================

def parse_chaincode_result(result):

    try:

        chaincode_result = result["data"]

        for _ in range(3):
            if isinstance(chaincode_result, dict) and "result" in chaincode_result:
                chaincode_result = chaincode_result["result"]
                continue
            if isinstance(chaincode_result, str):
                try:
                    chaincode_result = json.loads(chaincode_result)
                    continue
                except (TypeError, ValueError):
                    pass
            break

        return chaincode_result

    except Exception:

        return None


def response_object(value):
    """Unwrap known ChainLaunch envelopes without recursively selecting nested IDs."""
    current = value
    for _ in range(4):
        if not isinstance(current, dict):
            return {}
        unwrapped = None
        for name in ("data", "result"):
            candidate = current.get(name)
            if isinstance(candidate, dict):
                unwrapped = candidate
                break
        if unwrapped is None:
            return current
        current = unwrapped
    return current if isinstance(current, dict) else {}


def certificate_fingerprint(pem_certificate):
    normalized = str(pem_certificate or "").strip()
    if "BEGIN CERTIFICATE" not in normalized:
        raise ValueError("ChainLaunch response không chứa certificate PEM")
    der = ssl.PEM_cert_to_DER_cert(normalized)
    return hashlib.sha256(der).hexdigest()


def provision_fabric_identity(user_id, body, bootstrap=False):
    organization_id = str(body.get("organizationID", "")).strip()
    requested_msp_id = str(body.get("mspID", "")).strip()
    key_name = str(body.get("name", f"assetchain-{user_id}")).strip()
    if not organization_id or not key_name:
        return None, "organizationID và name là bắt buộc", 400
    registry = identity_registry_connection()
    if registry is None:
        return None, "IDENTITY_REGISTRY_DB chưa được cấu hình", 503
    registry.close()
    if identity_binding(user_id, include_inactive=True):
        return None, "User đã có binding; dùng quy trình rotate có kiểm soát", 409

    actor_id = str(request.auth_user.get("id", ""))
    if not bootstrap and identity_binding(actor_id) is None:
        return None, "Admin chưa có Fabric identity active; chưa tạo key mới", 409

    user_result = invoke_chaincode("GetUser", [str(user_id)])
    user = parse_chaincode_result(user_result)
    if not user_result.get("success") or not isinstance(user, dict):
        return None, "User không tồn tại trên ledger", 404
    if bootstrap and (
        str(request.auth_user.get("id", "")) != str(user_id)
        or normalize_role(user.get("role")) != "admin"
    ):
        return None, "Bootstrap chỉ dành cho chính tài khoản Admin đầu tiên", 403

    organization_result = fabric_request(
        "GET", f"organizations/{organization_id}"
    )
    organization = response_object(organization_result.get("data"))
    msp_id = str(organization.get("mspId") or organization.get("mspID") or "").strip()
    if not organization_result.get("success") or not msp_id:
        return None, "Không thể xác minh MSP của organization trong ChainLaunch", 502
    if requested_msp_id and not hmac.compare_digest(requested_msp_id, msp_id):
        return None, "mspID không khớp organization trong ChainLaunch", 400

    payload = {"name": key_name, "role": "client"}
    for request_name, chainlaunch_name in (
        ("description", "description"),
        ("dnsNames", "dnsNames"),
        ("ipAddresses", "ipAddresses"),
    ):
        if body.get(request_name) not in (None, "", []):
            payload[chainlaunch_name] = body[request_name]

    created = fabric_request(
        "POST", f"organizations/{organization_id}/keys", json=payload
    )
    if not created.get("success"):
        return None, "ChainLaunch không thể tạo client signing key", 502
    response_data = response_object(created.get("data"))
    key_id = response_data.get("id") or response_data.get("keyId") or response_data.get("key_id")
    certificate = (
        response_data.get("certificate")
        or response_data.get("certificatePem")
        or response_data.get("certificate_pem")
        or response_data.get("cert")
    )
    if key_id in (None, ""):
        return None, "ChainLaunch đã trả response không có key ID; cần đối soát thủ công", 502
    try:
        fingerprint = certificate_fingerprint(certificate)
    except (TypeError, ValueError):
        # The key may now exist in ChainLaunch. Never delete it automatically and
        # never fabricate a fingerprint: an operator must reconcile it explicitly.
        audit_event(
            "fabric_identity.provision", "incomplete",
            request.auth_user.get("id"), request.auth_user.get("role"), user_id,
            {"reason": "certificate_missing", "keyID": str(key_id)},
        )
        return {
            "userID": str(user_id), "keyID": str(key_id), "status": "unbound"
        }, "Key đã tạo nhưng response thiếu certificate; chưa binding, không được dùng mutation", 502

    binding = {
        "user_id": str(user_id), "key_id": str(key_id),
        "organization_id": organization_id, "msp_id": msp_id,
        "certificate_fingerprint": fingerprint, "key_name": key_name,
        "status": "pending", "last_error": "",
    }
    try:
        save_identity_binding(binding)
    except (OSError, sqlite3.Error, RuntimeError) as error:
        return {
            "userID": str(user_id), "keyID": str(key_id), "status": "unbound"
        }, f"Key đã tạo nhưng registry local lỗi: {error}", 500

    if bootstrap:
        # Two-step by design: the operator must first learn the certificate
        # fingerprint, configure the chaincode allowlist identically on every
        # peer, and only then call the completion endpoint.
        return {
            "userID": str(user_id), "keyID": str(key_id),
            "organizationID": organization_id, "mspID": msp_id,
            "certificateFingerprint": fingerprint, "status": "pending",
        }, None, 202
    else:
        ledger_result = invoke_chaincode(
            "RegisterUserIdentity",
            [str(user_id), msp_id, fingerprint, actor_id],
        )
    if not ledger_result.get("success"):
        error = ledger_result.get("error") or "ledger binding thất bại"
        mark_identity_binding(user_id, "failed", error)
        return {
            "userID": str(user_id), "keyID": str(key_id), "mspID": msp_id,
            "certificateFingerprint": fingerprint, "status": "failed",
        }, "Key đã tạo nhưng chưa bind ledger; không được dùng mutation", 409

    mark_identity_binding(user_id, "active")
    result = {
        "userID": str(user_id), "keyID": str(key_id),
        "organizationID": organization_id, "mspID": msp_id,
        "certificateFingerprint": fingerprint, "status": "active",
    }
    audit_event(
        "fabric_identity.bootstrap" if bootstrap else "fabric_identity.provision",
        "success", actor_id, request.auth_user.get("role"), user_id,
        {"keyID": str(key_id), "mspID": msp_id},
    )
    return result, None, 201



MUTATING_CHAINCODE_FUNCTIONS = {
    "CreateAsset", "CreateUser", "DeleteAsset", "DeleteUser",
    "SetUserPassword", "MigrateUserCredential", "TransferAsset", "TransferAssetQuantity",
    "UpdateAsset", "UpdateUser", "ReturnAssetToStore", "DeleteAssetQuantity",
    "EnsureStoreUser", "RegisterUserIdentity", "RotateUserIdentity",
    "SubmitAssetCreationRequest", "SubmitInventoryTransferRequest",
    "ApproveWorkflowRequest", "RejectWorkflowRequest",
    "AcceptWorkflowRequest", "DeclineWorkflowRequest",
}


def security_db_connection():
    if not SECURITY_STATE_DB:
        return None
    path = Path(SECURITY_STATE_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS rate_limit_events (
            bucket TEXT NOT NULL,
            event_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rate_limit_bucket_time
            ON rate_limit_events(bucket, event_at);
        CREATE TABLE IF NOT EXISTS idempotency_results (
            actor_id TEXT NOT NULL,
            request_path TEXT NOT NULL,
            function_name TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY(actor_id, request_path, function_name, idempotency_key)
        );
    """)
    return connection


def shared_rate_limit_count(bucket, window):
    connection = security_db_connection()
    if connection is None:
        return None
    cutoff = time() - window
    with connection:
        connection.execute(
            "DELETE FROM rate_limit_events WHERE event_at < ?", (cutoff,)
        )
        row = connection.execute(
            "SELECT COUNT(*) FROM rate_limit_events WHERE bucket = ? AND event_at >= ?",
            (bucket, cutoff),
        ).fetchone()
    connection.close()
    return int(row[0])


def shared_rate_limit_add(bucket):
    connection = security_db_connection()
    if connection is None:
        return False
    with connection:
        connection.execute(
            "INSERT INTO rate_limit_events(bucket, event_at) VALUES (?, ?)",
            (bucket, time()),
        )
    connection.close()
    return True


def shared_rate_limit_clear(bucket):
    connection = security_db_connection()
    if connection is None:
        return False
    with connection:
        connection.execute("DELETE FROM rate_limit_events WHERE bucket = ?", (bucket,))
    connection.close()
    return True


def idempotency_scope(function, args):
    if not has_request_context() or request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if function not in MUTATING_CHAINCODE_FUNCTIONS:
        return None
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        return None
    if len(key) > 128 or not all(character.isalnum() or character in "-_.:" for character in key):
        return None
    actor_id = str(getattr(request, "auth_user", {}).get("id", "anonymous"))
    serialized = json.dumps(
        {"function": function, "args": args}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    )
    return actor_id, request.path, function, key, hashlib.sha256(serialized.encode()).hexdigest()


def idempotency_get(scope):
    if scope is None:
        return None
    connection = security_db_connection()
    if connection is None:
        return None
    actor_id, path, function, key, request_hash = scope
    cutoff = time() - IDEMPOTENCY_TTL
    with connection:
        connection.execute("DELETE FROM idempotency_results WHERE created_at < ?", (cutoff,))
        row = connection.execute(
            """SELECT request_hash, response_json FROM idempotency_results
               WHERE actor_id = ? AND request_path = ? AND function_name = ?
                 AND idempotency_key = ?""",
            (actor_id, path, function, key),
        ).fetchone()
    connection.close()
    if row is None:
        return None
    if not hmac.compare_digest(row[0], request_hash):
        return {
            "success": False,
            "error": "Idempotency-Key đã được dùng cho nội dung khác",
            "status_code": 409,
        }
    return json.loads(row[1])


def idempotency_put(scope, result):
    if scope is None or not result.get("success"):
        return
    connection = security_db_connection()
    if connection is None:
        return
    actor_id, path, function, key, request_hash = scope
    with connection:
        connection.execute(
            """INSERT OR IGNORE INTO idempotency_results
               (actor_id, request_path, function_name, idempotency_key,
                request_hash, response_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (actor_id, path, function, key, request_hash,
             json.dumps(result, ensure_ascii=False, separators=(",", ":")), time()),
        )
    connection.close()


def set_auth_cookie(response, token):
    response.set_cookie(
        AUTH_COOKIE_NAME, token, max_age=AUTH_TOKEN_MAX_AGE,
        secure=AUTH_COOKIE_SECURE, httponly=True,
        samesite=AUTH_COOKIE_SAMESITE, path="/api",
    )
    return response


def clear_auth_cookie(response):
    response.delete_cookie(
        AUTH_COOKIE_NAME, secure=AUTH_COOKIE_SECURE,
        httponly=True, samesite=AUTH_COOKIE_SAMESITE, path="/api",
    )
    return response


def auth_serializer():
    if not APP_SECRET:
        raise RuntimeError("APP_SECRET chưa được cấu hình")
    return URLSafeTimedSerializer(APP_SECRET, salt="assetchain-auth")


def login_attempt_key(username):
    return f"{request_client_ip()}:{username.strip().lower()}"


def login_is_rate_limited(key):
    shared_count = shared_rate_limit_count("login:" + key, LOGIN_FAILURE_WINDOW)
    if shared_count is not None:
        return shared_count >= LOGIN_FAILURE_LIMIT
    now = monotonic()
    cutoff = now - LOGIN_FAILURE_WINDOW
    with login_failures_lock:
        failures = login_failures[key]
        while failures and failures[0] < cutoff:
            failures.popleft()
        return len(failures) >= LOGIN_FAILURE_LIMIT


def record_login_failure(key):
    if shared_rate_limit_add("login:" + key):
        return
    with login_failures_lock:
        if len(login_failures) > 5000:
            login_failures.clear()
        login_failures[key].append(monotonic())


def clear_login_failures(key):
    if shared_rate_limit_clear("login:" + key):
        return
    with login_failures_lock:
        login_failures.pop(key, None)


def record_password_reset_attempt(key):
    bucket = "password-reset:" + key
    shared_count = shared_rate_limit_count(bucket, PASSWORD_RESET_REQUEST_WINDOW)
    if shared_count is not None:
        if shared_count >= PASSWORD_RESET_REQUEST_LIMIT:
            return False
        shared_rate_limit_add(bucket)
        return True
    now = monotonic()
    cutoff = now - PASSWORD_RESET_REQUEST_WINDOW
    with password_reset_attempts_lock:
        attempts = password_reset_attempts[key]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if len(attempts) >= PASSWORD_RESET_REQUEST_LIMIT:
            return False
        if len(password_reset_attempts) > 5000:
            password_reset_attempts.clear()
            attempts = password_reset_attempts[key]
        attempts.append(now)
        return True


COMMON_PASSWORDS = {
    "12345678", "123456789", "password", "password123", "qwerty123",
    "admin123", "letmein", "welcome123",
}


def password_policy_error(password, username=""):
    if len(password) < 12:
        return "Mật khẩu mới phải có ít nhất 12 ký tự"
    if len(password) > 128:
        return "Mật khẩu mới không được vượt quá 128 ký tự"
    normalized = password.casefold()
    if normalized in COMMON_PASSWORDS:
        return "Mật khẩu mới quá phổ biến"
    normalized_username = str(username or "").strip().casefold()
    if len(normalized_username) >= 4 and normalized_username in normalized:
        return "Mật khẩu mới không được chứa username"
    character_groups = sum((
        any(character.islower() for character in password),
        any(character.isupper() for character in password),
        any(character.isdigit() for character in password),
        any(not character.isalnum() for character in password),
    ))
    if character_groups < 3:
        return "Mật khẩu mới phải kết hợp ít nhất 3 nhóm: chữ thường, chữ hoa, số, ký tự đặc biệt"
    return ""


def configured_password_hash(username):
    if not AUTH_CREDENTIALS_FILE:
        return None
    try:
        with open(AUTH_CREDENTIALS_FILE, encoding="utf-8") as credentials_file:
            credentials = json.load(credentials_file)
        if not isinstance(credentials, dict):
            return None
        normalized_username = username.strip().lower()
        for configured_username, password_hash in credentials.items():
            if str(configured_username).strip().lower() == normalized_username:
                return password_hash if isinstance(password_hash, str) else None
    except (OSError, ValueError):
        return None
    return None


def normalize_role(role):
    normalized = str(role or "").strip().lower()
    return ROLE_ALIASES.get(normalized, normalized)


def load_role_permissions():
    permissions = {
        role: list(values) for role, values in DEFAULT_ROLE_PERMISSIONS.items()
    }
    try:
        configured = json.loads(Path(ROLE_PERMISSIONS_FILE).read_text(encoding="utf-8"))
        if isinstance(configured, dict):
            for role in DEFAULT_ROLE_PERMISSIONS:
                values = configured.get(role)
                if isinstance(values, list):
                    permissions[role] = [
                        value for value in values if value in ALL_PERMISSIONS
                    ]
    except (OSError, ValueError):
        pass
    return permissions


def has_permission(identity, permission):
    role = normalize_role(identity.get("role"))
    if role == "admin":
        return True
    return permission in load_role_permissions().get(role, [])


def save_role_permissions(permissions):
    normalized = {}
    for role in DEFAULT_ROLE_PERMISSIONS:
        values = permissions.get(role, [])
        if not isinstance(values, list):
            raise ValueError(f"Quyền của vai trò {role} phải là danh sách")
        normalized[role] = sorted({
            value for value in values if value in ALL_PERMISSIONS
        })
    path = Path(ROLE_PERMISSIONS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    return normalized


def empty_auth_state():
    return {
        "knownUserIDs": [],
        "mustChangeUserIDs": [],
        "sessionVersions": {},
        "passwordResetRequests": [],
    }


def load_auth_state_unlocked():
    state = empty_auth_state()
    try:
        configured = json.loads(Path(AUTH_STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return state
    if not isinstance(configured, dict):
        return state
    for key in ("knownUserIDs", "mustChangeUserIDs", "passwordResetRequests"):
        if isinstance(configured.get(key), list):
            state[key] = configured[key]
    if isinstance(configured.get("sessionVersions"), dict):
        state["sessionVersions"] = configured["sessionVersions"]
    return state


def save_auth_state_unlocked(state):
    path = Path(AUTH_STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def auth_state_snapshot():
    with auth_state_lock:
        return load_auth_state_unlocked()


def register_first_login(user_id):
    user_id = str(user_id or "").strip()
    if not user_id:
        return False
    with auth_state_lock:
        state = load_auth_state_unlocked()
        known = {str(value) for value in state["knownUserIDs"]}
        must_change = {str(value) for value in state["mustChangeUserIDs"]}
        if user_id not in known:
            known.add(user_id)
            must_change.add(user_id)
            state["knownUserIDs"] = sorted(known)
            state["mustChangeUserIDs"] = sorted(must_change)
            save_auth_state_unlocked(state)
        return user_id in must_change


def password_change_required(user_id):
    user_id = str(user_id or "").strip()
    if not user_id:
        return False
    state = auth_state_snapshot()
    return user_id in {str(value) for value in state["mustChangeUserIDs"]}


def session_version(user_id):
    state = auth_state_snapshot()
    try:
        return int(state["sessionVersions"].get(str(user_id), 0))
    except (TypeError, ValueError):
        return 0


def update_password_state(user_id, must_change):
    user_id = str(user_id or "").strip()
    with auth_state_lock:
        state = load_auth_state_unlocked()
        known = {str(value) for value in state["knownUserIDs"]}
        pending = {str(value) for value in state["mustChangeUserIDs"]}
        known.add(user_id)
        if must_change:
            pending.add(user_id)
        else:
            pending.discard(user_id)
        try:
            next_version = int(state["sessionVersions"].get(user_id, 0)) + 1
        except (TypeError, ValueError):
            next_version = 1
        state["knownUserIDs"] = sorted(known)
        state["mustChangeUserIDs"] = sorted(pending)
        state["sessionVersions"][user_id] = next_version
        save_auth_state_unlocked(state)
        return next_version


def add_password_reset_request(user):
    now = datetime.now(timezone.utc).isoformat()
    user_id = str(user.get("id", ""))
    with auth_state_lock:
        state = load_auth_state_unlocked()
        for item in state["passwordResetRequests"]:
            if str(item.get("userID")) == user_id and item.get("status") == "pending":
                return item
        item = {
            "id": token_urlsafe(12),
            "userID": user_id,
            "username": str(user.get("username", "")),
            "fullName": str(user.get("fullName", "")),
            "status": "pending",
            "requestedAt": now,
        }
        state["passwordResetRequests"].append(item)
        save_auth_state_unlocked(state)
        return item


def update_password_reset_request(request_id, status, reviewer_id):
    with auth_state_lock:
        state = load_auth_state_unlocked()
        selected = None
        for item in state["passwordResetRequests"]:
            if item.get("id") == request_id:
                selected = item
                break
        if selected is None:
            return None
        selected["status"] = status
        selected["reviewedAt"] = datetime.now(timezone.utc).isoformat()
        selected["reviewedBy"] = str(reviewer_id or "")
        save_auth_state_unlocked(state)
        return selected


def get_user_by_username(username):
    result = invoke_chaincode("GetUserByUsername", [str(username)])
    user = parse_chaincode_result(result)
    if result.get("success") and isinstance(user, dict):
        return user
    users_result = invoke_chaincode("GetAllUsers", [])
    users = parse_chaincode_result(users_result)
    if users_result.get("success") and isinstance(users, list):
        normalized = str(username).strip().lower()
        return next(
            (
                candidate for candidate in users
                if str(candidate.get("username", "")).strip().lower() == normalized
            ),
            None,
        )
    return None


def set_user_password_to_default(user_id):
    user_result = invoke_chaincode("GetUser", [str(user_id)])
    user = parse_chaincode_result(user_result)
    if not user_result.get("success") or not isinstance(user, dict):
        return None, "Người dùng không tồn tại"
    if normalize_role(user.get("role")) == "store":
        return None, "Không thể đặt mật khẩu cho tài khoản hệ thống"
    reset_result = invoke_chaincode(
        "SetUserPassword",
        [str(user_id), generate_password_hash(DEFAULT_INITIAL_PASSWORD),
         str(request.auth_user.get("id", ""))],
    )
    if not reset_result.get("success"):
        return None, "Không thể đặt lại mật khẩu trên Blockchain"
    update_password_state(user_id, must_change=True)
    return user, None


def can_view_asset(identity, asset):
    if has_permission(identity, "view_all_assets"):
        return True
    if has_permission(identity, "view_inventory"):
        return str(asset.get("ownerID")) in {STORE_USER_ID, ADMIN_OWNER_ID}
    if has_permission(identity, "view_own_assets"):
        return str(asset.get("ownerID")) == str(identity.get("id"))
    return False


def customer_ids_sold_by(identity):
    if normalize_role(identity.get("role")) != "sales":
        return set()
    result = invoke_chaincode("GetAllAssets", [])
    assets = parse_chaincode_result(result)
    if not result.get("success") or not isinstance(assets, list):
        return set()
    actor_id = str(identity.get("id"))
    return {
        str(asset.get("ownerID"))
        for asset in assets
        if str(asset.get("lastActorID")) == actor_id
        and str(asset.get("ownerID")) not in {"", STORE_USER_ID, ADMIN_OWNER_ID}
    }


def public_user_for_identity(identity, user, sold_customer_ids=None):
    role = normalize_role(identity.get("role"))
    target_role = normalize_role(user.get("role"))
    result = dict(user)
    if role == "sales":
        is_own_customer = str(user.get("createdBy")) == str(identity.get("id"))
        is_sold_customer = str(user.get("id")) in (sold_customer_ids or set())
        if (
            not has_permission(identity, "view_customers")
            or target_role != "customer"
            or not (is_own_customer or is_sold_customer)
        ):
            return None
        return {
            "id": user.get("id"),
            "fullName": user.get("fullName"),
            "role": "CUSTOMER",
        }
    if role == "manager":
        if not has_permission(identity, "view_users") or target_role in {"admin", "store"}:
            return None
    if role not in {"admin", "manager"} and str(user.get("id")) != str(identity.get("id")):
        return None
    result["role"] = target_role.upper()
    result["canEdit"] = (
        role == "admin"
        or role == "manager" and has_permission(identity, "update_user") and target_role not in {"admin", "store"}
        or role == "customer" and str(user.get("id")) == str(identity.get("id"))
    )
    return result


def read_chaincode_asset(asset_id):
    result = invoke_chaincode("ReadAsset", [str(asset_id)])
    if not result.get("success"):
        return None, result
    asset = parse_chaincode_result(result)
    return asset if isinstance(asset, dict) else None, result


def read_chaincode_asset_record(asset_id):
    result = invoke_chaincode("ReadAssetRecord", [str(asset_id)])
    if not result.get("success"):
        return None, result
    asset = parse_chaincode_result(result)
    return asset if isinstance(asset, dict) else None, result


def workflow_request_id(kind):
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    actor_id = str(request.auth_user.get("id", "")).strip()
    if idempotency_key:
        if len(idempotency_key) > 128 or not all(
            character.isalnum() or character in "-_.:" for character in idempotency_key
        ):
            return None
        digest = hashlib.sha256(
            f"{actor_id}\x00{kind}\x00{idempotency_key}".encode()
        ).hexdigest()[:24]
        return f"WF-{kind[:3].upper()}-{digest}"
    return f"WF-{kind[:3].upper()}-{token_urlsafe(18)}"


def workflow_error_response(result, fallback):
    raw_message = str(
        result.get("error")
        or response_object(result.get("data", {})).get("message", "")
        or fallback
    )
    lowered = raw_message.lower()
    status_code = int(result.get("status_code") or 0)
    if not status_code:
        if "does not exist" in lowered or "không tồn tại" in lowered:
            status_code = 404
        elif any(value in lowered for value in (
            "already exists", "locked", "not pending", "not awaiting",
            "reservation state", "nonterminal", "duplicate",
        )):
            status_code = 409
        elif any(value in lowered for value in (
            "not authorized", "only ", "cannot approve own", "cannot reject own",
            "does not match invoker", "identity",
        )):
            status_code = 403
        else:
            status_code = 400
    if status_code >= 500:
        status_code = 502
    return jsonify({
        "status": "error", "message": raw_message,
        "fabric_response": result,
    }), status_code


def visible_workflow_requests(identity, items):
    role = normalize_role(identity.get("role"))
    actor_id = str(identity.get("id", ""))
    if role in {"admin", "manager"}:
        return items
    if role in {"warehouse", "sales"}:
        return [item for item in items if str(item.get("makerID")) == actor_id]
    if role == "customer":
        return [
            item for item in items
            if str(item.get("targetCustomerID")) == actor_id
        ]
    return []


def list_visible_workflow_requests():
    result = invoke_chaincode("ListWorkflowRequests", [])
    items = parse_chaincode_result(result)
    if not result.get("success") or not isinstance(items, list):
        return None, result
    return visible_workflow_requests(request.auth_user, items), result


def submit_creation_workflow(body):
    required = ("id", "name", "type", "value", "quantity", "status")
    missing = next((field for field in required if body.get(field) in (None, "")), None)
    if missing:
        return None, jsonify({"status": "error", "message": f"Thiếu trường {missing}"}), 400
    try:
        value, quantity = int(body["value"]), int(body["quantity"])
    except (TypeError, ValueError):
        return None, jsonify({"status": "error", "message": "Giá và số lượng phải là số"}), 400
    if value < 1 or quantity < 1 or value > 9_000_000_000_000_000:
        return None, jsonify({"status": "error", "message": "Giá và số lượng không hợp lệ"}), 400
    request_id = workflow_request_id("creation")
    if request_id is None:
        return None, jsonify({"status": "error", "message": "Idempotency-Key không hợp lệ"}), 400
    owner_id = str(body.get("ownerID") or STORE_USER_ID)
    args = [
        request_id, str(body["id"]), str(body["name"]), str(body["type"]),
        owner_id, str(value), str(body["status"]),
        str(body.get("serialNumber", "")), str(body.get("description", "")),
        str(quantity), str(request.auth_user.get("id", "")),
    ]
    result = invoke_chaincode("SubmitAssetCreationRequest", args)
    if not result.get("success"):
        return None, workflow_error_response(result, "Không thể gửi yêu cầu tạo tài sản"), None
    item = parse_chaincode_result(result)
    return item if isinstance(item, dict) else {"id": request_id}, None, 201


def submit_transfer_workflow(body, asset_id=None, existing_asset=None):
    source_id = str(asset_id or body.get("assetID") or "").strip()
    target_id = str(body.get("newOwnerID") or body.get("targetCustomerID") or "").strip()
    if not source_id or not target_id or body.get("quantity") in (None, ""):
        return None, jsonify({
            "status": "error",
            "message": "assetID, targetCustomerID và quantity là bắt buộc",
        }), 400
    asset = existing_asset
    if asset is None:
        asset, _ = read_chaincode_asset(source_id)
    if not asset:
        return None, jsonify({"status": "error", "message": "Tài sản không tồn tại"}), 404
    if str(asset.get("ownerID")) not in {STORE_USER_ID, ADMIN_OWNER_ID}:
        return None, jsonify({"status": "error", "message": "Chỉ có thể bán hàng tồn kho STORE/U001"}), 400
    recipient_result = invoke_chaincode("GetUser", [target_id])
    recipient = parse_chaincode_result(recipient_result)
    if (
        not recipient_result.get("success") or not isinstance(recipient, dict)
        or normalize_role(recipient.get("role")) != "customer"
    ):
        return None, jsonify({"status": "error", "message": "Phải chọn khách hàng hiện có"}), 400
    try:
        quantity = int(body["quantity"])
    except (TypeError, ValueError):
        return None, jsonify({"status": "error", "message": "Số lượng bán không hợp lệ"}), 400
    if quantity < 1:
        return None, jsonify({"status": "error", "message": "Số lượng bán phải lớn hơn 0"}), 400
    new_asset_id = str(body.get("newAssetID") or "").strip()
    if quantity < int(asset.get("quantity") or 1) and not new_asset_id:
        return None, jsonify({"status": "error", "message": "Thiếu mã tài sản mới khi bán một phần"}), 400
    request_id = workflow_request_id("transfer")
    if request_id is None:
        return None, jsonify({"status": "error", "message": "Idempotency-Key không hợp lệ"}), 400
    result = invoke_chaincode("SubmitInventoryTransferRequest", [
        request_id, source_id, target_id, str(quantity), new_asset_id,
        str(request.auth_user.get("id", "")),
    ])
    if not result.get("success"):
        return None, workflow_error_response(result, "Không thể gửi yêu cầu chuyển kho"), None
    item = parse_chaincode_result(result)
    return item if isinstance(item, dict) else {"id": request_id}, None, 201


def user_reference(user_id, directory):
    user_id = str(user_id or "")
    if not user_id:
        return None
    if user_id == STORE_USER_ID:
        return {"id": STORE_USER_ID, "username": "store", "fullName": "Kho cửa hàng"}
    user = directory.get(user_id, {})
    return {
        "id": user_id,
        "username": str(user.get("username") or user_id),
        "fullName": str(user.get("fullName") or user.get("username") or user_id),
    }


def enrich_asset_history(history):
    users_result = invoke_chaincode("GetAllUsers", [])
    users = parse_chaincode_result(users_result)
    directory = {
        str(user.get("id")): user
        for user in (users if isinstance(users, list) else [])
        if isinstance(user, dict) and user.get("id")
    }
    enriched = []
    previous_owner_id = ""
    for index, original in enumerate(history):
        record = dict(original) if isinstance(original, dict) else {"value": original}
        value = record.get("value") or record.get("Value") or {}
        if not isinstance(value, dict):
            value = {}
        explicit_operation = str(
            value.get("lastOperation") or value.get("LastOperation") or ""
        ).strip().lower()
        is_delete = bool(
            record.get("isDelete")
            or record.get("IsDelete")
            or value.get("deleted")
            or value.get("Deleted")
            or explicit_operation.startswith("delete")
        )
        current_owner_id = str(value.get("ownerID") or value.get("OwnerID") or "")
        actor_id = str(value.get("lastActorID") or value.get("LastActorID") or "")
        from_owner_id = ""
        to_owner_id = current_owner_id
        if is_delete:
            from_owner_id = previous_owner_id
            to_owner_id = ""
        elif previous_owner_id and current_owner_id != previous_owner_id:
            from_owner_id = previous_owner_id
        elif (
            index == 0
            and str(value.get("status") or value.get("Status") or "").strip().lower() == "sold"
            and current_owner_id not in {"", STORE_USER_ID, ADMIN_OWNER_ID}
        ):
            # Tài sản tách ra khi bán một phần có lịch sử bắt đầu tại bản ghi đã bán.
            from_owner_id = STORE_USER_ID

        if is_delete:
            operation = explicit_operation or "delete"
        elif explicit_operation in {"create", "update", "transfer"}:
            operation = explicit_operation
        elif from_owner_id and to_owner_id and from_owner_id != to_owner_id:
            operation = "transfer"
        elif index == 0:
            operation = "create"
        else:
            operation = "update"

        record.update({
            "operation": operation,
            "isDelete": is_delete,
            "actorID": actor_id,
            "actor": user_reference(actor_id, directory),
            "fromOwnerID": from_owner_id,
            "fromOwner": user_reference(from_owner_id, directory),
            "toOwnerID": to_owner_id,
            "toOwner": user_reference(to_owner_id, directory),
        })
        enriched.append(record)
        if not is_delete and current_owner_id:
            previous_owner_id = current_owner_id
    return enriched


def history_visible_to_identity(history, identity):
    role = normalize_role(identity.get("role"))
    if role != "customer":
        return history

    user_id = str(identity.get("id", ""))
    ownership_start = None
    for index, record in enumerate(history):
        if (
            str(record.get("toOwnerID", "")) == user_id
            and str(record.get("operation", "")) in {"create", "transfer"}
        ):
            ownership_start = index
    if ownership_start is None:
        return []
    return history[ownership_start:]


def require_auth(admin_only=False, permission=None, allow_password_change=False):
    def decorator(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            cookie_token = request.cookies.get(AUTH_COOKIE_NAME, "")
            token = cookie_token or (header[7:] if header.startswith("Bearer ") else "")
            if not token:
                audit_event("authorization.denied", "denied", details={"reason": "missing_token"})
                return jsonify({"status": "error", "message": "Chưa đăng nhập"}), 401
            try:
                identity = auth_serializer().loads(
                    token, max_age=AUTH_TOKEN_MAX_AGE
                )
            except (BadSignature, SignatureExpired, RuntimeError):
                audit_event("authorization.denied", "denied", details={"reason": "invalid_or_expired_token"})
                return jsonify({
                    "status": "error",
                    "message": "Phiên đăng nhập không hợp lệ hoặc đã hết hạn"
                }), 401
            user_id = str(identity.get("id", ""))
            if cookie_token and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                csrf_token = request.headers.get("X-CSRF-Token", "")
                if not csrf_token or not hmac.compare_digest(
                    str(identity.get("csrf", "")), csrf_token
                ):
                    audit_event(
                        "authorization.denied", "denied", user_id, identity.get("role"),
                        details={"reason": "csrf_check_failed"},
                    )
                    return jsonify({
                        "status": "error", "code": "CSRF_FAILED",
                        "message": "Yêu cầu thiếu mã chống CSRF hợp lệ"
                    }), 403
            try:
                token_version = int(identity.get("version", 0))
            except (TypeError, ValueError):
                token_version = -1
            if token_version != session_version(user_id):
                audit_event(
                    "authorization.denied", "denied", user_id, identity.get("role"),
                    details={"reason": "session_revoked"},
                )
                return jsonify({
                    "status": "error",
                    "code": "SESSION_REVOKED",
                    "message": "Phiên đăng nhập đã hết hiệu lực. Vui lòng đăng nhập lại"
                }), 401
            if password_change_required(user_id) and not allow_password_change:
                audit_event(
                    "authorization.denied", "denied", user_id, identity.get("role"),
                    details={"reason": "password_change_required"},
                )
                return jsonify({
                    "status": "error",
                    "code": "PASSWORD_CHANGE_REQUIRED",
                    "message": "Bạn phải đổi mật khẩu trước khi tiếp tục"
                }), 428
            if admin_only and normalize_role(identity.get("role")) != "admin":
                audit_event(
                    "authorization.denied", "denied", user_id, identity.get("role"),
                    details={"reason": "admin_required"},
                )
                return jsonify({
                    "status": "error",
                    "message": "Chỉ Admin mới có quyền thực hiện thao tác này"
                }), 403
            if permission and not has_permission(identity, permission):
                audit_event(
                    "authorization.denied", "denied", user_id, identity.get("role"),
                    details={"reason": "missing_permission", "permission": permission},
                )
                return jsonify({
                    "status": "error",
                    "message": "Vai trò hiện tại không có quyền thực hiện thao tác này"
                }), 403
            request.auth_user = identity
            return handler(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/api/auth/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        audit_event("authentication.login", "rejected", details={"reason": "missing_credentials"})
        return jsonify({
            "status": "error",
            "message": "Username và password là bắt buộc"
        }), 400

    attempt_key = login_attempt_key(username)
    if login_is_rate_limited(attempt_key):
        audit_event(
            "authentication.login", "rate_limited",
            details={"username": username.lower()},
        )
        return jsonify({
            "status": "error",
            "message": "Đăng nhập tạm thời bị giới hạn. Vui lòng thử lại sau"
        }), 429

    credential_result = invoke_chaincode("GetPasswordHash", [username])
    password_hash = parse_chaincode_result(credential_result)
    if not credential_result.get("success") or not isinstance(password_hash, str):
        password_hash = configured_password_hash(username)
    if (
        not isinstance(password_hash, str)
        or not check_password_hash(password_hash, password)
    ):
        record_login_failure(attempt_key)
        audit_event(
            "authentication.login", "failure",
            details={"username": username.lower(), "reason": "invalid_credentials"},
        )
        return jsonify({
            "status": "error",
            "message": "Username hoặc password không đúng"
        }), 401

    user = get_user_by_username(username)
    if not isinstance(user, dict):
        record_login_failure(attempt_key)
        audit_event(
            "authentication.login", "failure",
            details={"username": username.lower(), "reason": "user_not_found"},
        )
        return jsonify({
            "status": "error",
            "message": "Username hoặc password không đúng"
        }), 401

    user_role = normalize_role(user.get("role"))
    clear_login_failures(attempt_key)
    user["role"] = user_role.upper()
    user_id = str(user.get("id", ""))
    if ENFORCE_FABRIC_IDENTITY_LOGIN and identity_binding(user_id) is None:
        audit_event(
            "authentication.login", "denied", target_id=user_id,
            details={"reason": "fabric_identity_required"},
        )
        return jsonify({
            "status": "error", "code": "FABRIC_IDENTITY_REQUIRED",
            "message": "Tài khoản chưa được cấp Fabric identity đang hoạt động"
        }), 403
    must_change_password = register_first_login(user_id)
    user["mustChangePassword"] = must_change_password

    try:
        csrf_token = token_urlsafe(24)
        token = auth_serializer().dumps({
            "id": user_id,
            "role": user.get("role"),
            "version": session_version(user_id),
            "csrf": csrf_token,
        })
    except RuntimeError as error:
        audit_event(
            "authentication.login", "error", user_id, user.get("role"),
            details={"reason": "token_signing_unavailable"},
        )
        return jsonify({"status": "error", "message": str(error)}), 503

    audit_event(
        "authentication.login", "success", user_id, user.get("role"),
        details={"mustChangePassword": must_change_password},
    )

    response_data = {"user": user, "csrfToken": csrf_token}
    if AUTH_RETURN_BEARER_TOKEN:
        response_data["token"] = token
    response = jsonify({
        "status": "success",
        "data": response_data
    })
    return set_auth_cookie(response, token)


@app.route("/api/auth/logout", methods=["POST"])
@require_auth(allow_password_change=True)
def logout():
    audit_event(
        "authentication.logout", "success",
        request.auth_user.get("id"), request.auth_user.get("role"),
    )
    return clear_auth_cookie(jsonify({"status": "success"}))


@app.route("/api/auth/password-reset-requests", methods=["POST"])
def request_password_reset():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    if not username:
        return jsonify({
            "status": "error",
            "message": "Vui lòng nhập username trước khi gửi yêu cầu"
        }), 400

    if not record_password_reset_attempt(login_attempt_key(username)):
        audit_event(
            "password_reset.request", "rate_limited",
            details={"username": username.lower()},
        )
        return jsonify({
            "status": "error",
            "message": "Đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau",
        }), 429

    user = get_user_by_username(username)
    if isinstance(user, dict) and normalize_role(user.get("role")) != "store":
        add_password_reset_request(user)
        audit_event(
            "password_reset.request", "accepted", target_id=user.get("id"),
            details={"username": user.get("username")},
        )
    else:
        audit_event(
            "password_reset.request", "ignored",
            details={"username": username.lower(), "reason": "unknown_account"},
        )

    # Luôn trả cùng một thông báo để không làm lộ username có tồn tại hay không.
    return jsonify({
        "status": "success",
        "message": "Nếu username tồn tại, yêu cầu đã được gửi đến Admin"
    })


@app.route("/api/auth/change-password", methods=["POST"])
@require_auth(allow_password_change=True)
def change_password():
    body = request.get_json(silent=True) or {}
    current_password = str(body.get("currentPassword", ""))
    new_password = str(body.get("newPassword", ""))
    if not current_password or not new_password:
        return jsonify({
            "status": "error",
            "message": "Mật khẩu hiện tại và mật khẩu mới là bắt buộc"
        }), 400
    if new_password == DEFAULT_INITIAL_PASSWORD:
        return jsonify({
            "status": "error",
            "message": "Mật khẩu mới không được trùng mật khẩu mặc định"
        }), 400
    if new_password == current_password:
        return jsonify({
            "status": "error",
            "message": "Mật khẩu mới phải khác mật khẩu hiện tại"
        }), 400

    user_id = str(request.auth_user.get("id", ""))
    user_result = invoke_chaincode("GetUser", [user_id])
    user = parse_chaincode_result(user_result)
    if not user_result.get("success") or not isinstance(user, dict):
        return jsonify({"status": "error", "message": "Người dùng không tồn tại"}), 404

    username = str(user.get("username", ""))
    policy_error = password_policy_error(new_password, username)
    if policy_error:
        audit_event(
            "password.change", "rejected", user_id, request.auth_user.get("role"),
            target_id=user_id, details={"reason": "password_policy"},
        )
        return jsonify({"status": "error", "message": policy_error}), 400
    credential_result = invoke_chaincode("GetPasswordHash", [username])
    password_hash = parse_chaincode_result(credential_result)
    if not credential_result.get("success") or not isinstance(password_hash, str):
        password_hash = configured_password_hash(username)
    if not isinstance(password_hash, str) or not check_password_hash(password_hash, current_password):
        audit_event(
            "password.change", "failure", user_id, request.auth_user.get("role"),
            target_id=user_id, details={"reason": "invalid_current_password"},
        )
        return jsonify({
            "status": "error",
            "message": "Mật khẩu hiện tại không đúng"
        }), 401

    updated = invoke_chaincode(
        "SetUserPassword", [user_id, generate_password_hash(new_password), user_id]
    )
    if not updated.get("success"):
        return jsonify({
            "status": "error",
            "message": "Không thể cập nhật mật khẩu trên Blockchain",
            "fabric_response": updated,
        }), 500

    version = update_password_state(user_id, must_change=False)
    csrf_token = token_urlsafe(24)
    token = auth_serializer().dumps({
        "id": user_id,
        "role": request.auth_user.get("role"),
        "version": version,
        "csrf": csrf_token,
    })
    user["role"] = normalize_role(user.get("role")).upper()
    user["mustChangePassword"] = False
    audit_event(
        "password.change", "success", user_id, user.get("role"), target_id=user_id,
    )
    response_data = {"user": user, "csrfToken": csrf_token}
    if AUTH_RETURN_BEARER_TOKEN:
        response_data["token"] = token
    response = jsonify({
        "status": "success",
        "message": "Đổi mật khẩu thành công",
        "data": response_data,
    })
    return set_auth_cookie(response, token)


@app.route("/api/password-reset-requests", methods=["GET"])
@require_auth(admin_only=True)
def get_password_reset_requests():
    items = list(auth_state_snapshot()["passwordResetRequests"])
    items.sort(key=lambda item: str(item.get("requestedAt", "")), reverse=True)
    return jsonify({"status": "success", "data": items})


@app.route("/api/password-reset-requests/<request_id>/<decision>", methods=["POST"])
@require_auth(admin_only=True)
def review_password_reset_request(request_id, decision):
    if decision not in {"approve", "reject"}:
        return jsonify({"status": "error", "message": "Quyết định không hợp lệ"}), 400
    state = auth_state_snapshot()
    selected = next(
        (item for item in state["passwordResetRequests"] if item.get("id") == request_id),
        None,
    )
    if selected is None:
        return jsonify({"status": "error", "message": "Yêu cầu không tồn tại"}), 404
    if selected.get("status") != "pending":
        return jsonify({"status": "error", "message": "Yêu cầu này đã được xử lý"}), 409

    status = "rejected"
    if decision == "approve":
        _, error = set_user_password_to_default(selected.get("userID"))
        if error:
            return jsonify({"status": "error", "message": error}), 500
        status = "approved"
    updated = update_password_reset_request(
        request_id, status, request.auth_user.get("id")
    )
    audit_event(
        "password_reset.review", status,
        request.auth_user.get("id"), request.auth_user.get("role"),
        selected.get("userID"), {"requestID": request_id},
    )
    return jsonify({
        "status": "success",
        "message": "Đã chấp nhận yêu cầu và đặt mật khẩu về mặc định"
        if status == "approved" else "Đã từ chối yêu cầu",
        "data": updated,
    })


@app.route("/api/users/<user_id>/reset-password", methods=["POST"])
@require_auth(admin_only=True)
def admin_reset_user_password(user_id):
    if str(user_id) == str(request.auth_user.get("id")):
        return jsonify({
            "status": "error",
            "message": "Admin không thể tự đặt lại mật khẩu bằng chức năng quản trị"
        }), 400
    user, error = set_user_password_to_default(user_id)
    if error:
        return jsonify({"status": "error", "message": error}), 500
    audit_event(
        "password_reset.admin", "success",
        request.auth_user.get("id"), request.auth_user.get("role"), user_id,
    )
    return jsonify({
        "status": "success",
        "message": "Đã đặt mật khẩu về mặc định; người dùng phải đổi mật khẩu khi đăng nhập",
        "data": {"id": user.get("id"), "username": user.get("username")},
    })


@app.route("/api/permissions", methods=["GET"])
@require_auth(admin_only=True)
def get_permissions():
    return jsonify({
        "status": "success",
        "data": {
            "roles": ROLE_LABELS,
            "permissions": load_role_permissions(),
            "availablePermissions": ALL_PERMISSIONS,
        }
    })


@app.route("/api/permissions", methods=["PUT"])
@require_auth(admin_only=True)
def update_permissions():
    body = request.get_json(silent=True) or {}
    try:
        permissions = save_role_permissions(body.get("permissions", {}))
    except ValueError as error:
        return jsonify({"status": "error", "message": str(error)}), 400
    audit_event(
        "authorization.permissions_update", "success",
        request.auth_user.get("id"), request.auth_user.get("role"),
        details={"roles": sorted(permissions)},
    )
    return jsonify({"status": "success", "data": permissions})


@app.route("/api/permissions/me", methods=["GET"])
@require_auth()
def my_permissions():
    role = normalize_role(request.auth_user.get("role"))
    permissions = ALL_PERMISSIONS if role == "admin" else load_role_permissions().get(role, [])
    return jsonify({
        "status": "success",
        "data": {"role": role, "permissions": permissions}
    })


@app.route("/api/fabric-identity-requests", methods=["GET"])
@require_auth(admin_only=True)
def get_fabric_identity_requests():
    items = list_fabric_identity_requests()
    if items is None:
        return jsonify({
            "status": "error", "message": "IDENTITY_REGISTRY_DB chưa được cấu hình"
        }), 503
    return jsonify({"status": "success", "data": items})


@app.route("/api/fabric-identity-requests/<request_id>/<decision>", methods=["POST"])
@require_auth(admin_only=True)
def review_fabric_identity_request(request_id, decision):
    if decision not in {"approve", "reject"}:
        return jsonify({"status": "error", "message": "Quyết định không hợp lệ"}), 400
    selected = fabric_identity_request(request_id)
    if selected is None:
        return jsonify({"status": "error", "message": "Yêu cầu không tồn tại"}), 404
    reviewer_id = str(request.auth_user.get("id", ""))
    claimed = claim_fabric_identity_request(request_id, reviewer_id)
    if claimed is None:
        return jsonify({
            "status": "error", "message": "Yêu cầu này đang được xử lý hoặc đã hoàn tất"
        }), 409

    user_id = str(claimed["user_id"])
    if decision == "reject":
        updated = update_fabric_identity_request(
            request_id, "rejected", reviewer_id
        )
        audit_event(
            "fabric_identity.request_review", "rejected", reviewer_id,
            request.auth_user.get("role"), user_id, {"requestID": request_id},
        )
        return jsonify({
            "status": "success", "message": "Đã từ chối yêu cầu cấp Fabric identity",
            "data": updated,
        })

    binding = identity_binding(user_id, include_inactive=True)
    if binding is None and str(claimed.get("key_id", "")):
        message = (
            "Yêu cầu đã ghi nhận key nhưng chưa có binding; cần đối soát "
            "ChainLaunch, không tự động tạo thêm key"
        )
        updated = update_fabric_identity_request(
            request_id, "failed", reviewer_id,
            key_id=claimed.get("key_id", ""), error=message,
        )
        return jsonify({"status": "error", "message": message, "data": updated}), 409

    if binding is not None:
        result, error, response_status = complete_fabric_identity_binding(
            user_id, reviewer_id
        )
    else:
        safe_user_id = "".join(
            character if character.isalnum() or character in "_.-" else "-"
            for character in user_id
        )[:64]
        result, error, response_status = provision_fabric_identity(
            user_id,
            {
                "organizationID": FABRIC_IDENTITY_ORGANIZATION_ID,
                "name": f"assetchain-{safe_user_id}-v1",
                "description": f"AssetChain per-user signing identity for {user_id}",
            },
            bootstrap=False,
        )

    key_id = str((result or {}).get("keyID", ""))
    if error:
        updated = update_fabric_identity_request(
            request_id, "failed", reviewer_id, key_id=key_id, error=error
        )
        audit_event(
            "fabric_identity.request_review", "failed", reviewer_id,
            request.auth_user.get("role"), user_id,
            {"requestID": request_id, "keyID": key_id, "reason": error},
        )
        return jsonify({
            "status": "error", "message": error, "data": updated,
        }), response_status

    updated = update_fabric_identity_request(
        request_id, "approved", reviewer_id, key_id=key_id
    )
    audit_event(
        "fabric_identity.request_review", "approved", reviewer_id,
        request.auth_user.get("role"), user_id,
        {"requestID": request_id, "keyID": key_id},
    )
    return jsonify({
        "status": "success",
        "message": "Đã tự động cấp và kích hoạt Fabric identity",
        "data": updated,
        "identity": result,
    })


@app.route("/api/admin/fabric-identities", methods=["GET"])
@require_auth(admin_only=True)
def list_fabric_identities():
    connection = identity_registry_connection()
    if connection is None:
        return jsonify({
            "status": "error", "message": "IDENTITY_REGISTRY_DB chưa được cấu hình"
        }), 503
    rows = connection.execute(
        """SELECT user_id, key_id, organization_id, msp_id,
                  certificate_fingerprint, key_name, status, created_at, updated_at
           FROM fabric_identity_bindings ORDER BY user_id"""
    ).fetchall()
    connection.close()
    return jsonify({"status": "success", "data": [dict(row) for row in rows]})


@app.route("/api/admin/fabric-identities/<user_id>", methods=["POST"])
@require_auth(admin_only=True)
def create_fabric_identity(user_id):
    result, error, status = provision_fabric_identity(
        user_id, request.get_json(silent=True) or {}, bootstrap=False
    )
    if error:
        return jsonify({"status": "error", "message": error, "data": result}), status
    return jsonify({"status": "success", "data": result}), status


def complete_fabric_identity_binding(user_id, actor_id):
    binding = identity_binding(user_id, include_inactive=True)
    if not binding:
        return None, "Không có user binding đang chờ", 409
    if binding.get("status") == "active":
        return {
            "userID": str(user_id), "keyID": str(binding["key_id"]),
            "mspID": binding["msp_id"],
            "certificateFingerprint": binding["certificate_fingerprint"],
            "status": "active",
        }, None, 200
    if binding.get("status") not in {"pending", "failed"}:
        return None, "Binding không ở trạng thái có thể hoàn tất", 409
    if identity_binding(actor_id) is None:
        return None, "Admin chưa có Fabric identity active", 409

    # Reconcile a response-loss case before submitting another ledger mutation.
    current_result = invoke_chaincode("GetUserIdentity", [str(user_id)])
    current = parse_chaincode_result(current_result)
    already_bound = (
        current_result.get("success") and isinstance(current, dict)
        and hmac.compare_digest(str(current.get("mspID", "")), str(binding["msp_id"]))
        and hmac.compare_digest(
            str(current.get("certificateFingerprint", "")).lower(),
            str(binding["certificate_fingerprint"]).lower(),
        )
    )
    if not already_bound:
        ledger_result = invoke_chaincode(
            "RegisterUserIdentity",
            [
                str(user_id), binding["msp_id"],
                binding["certificate_fingerprint"], str(actor_id),
            ],
        )
        if not ledger_result.get("success"):
            error = ledger_result.get("error") or "ledger binding thất bại"
            mark_identity_binding(user_id, "failed", error)
            return {
                "userID": str(user_id), "keyID": str(binding["key_id"]),
                "status": "failed",
            }, "Binding ledger vẫn thất bại", 409
    mark_identity_binding(user_id, "active")
    return {
        "userID": str(user_id), "keyID": str(binding["key_id"]),
        "mspID": binding["msp_id"],
        "certificateFingerprint": binding["certificate_fingerprint"],
        "status": "active",
    }, None, 200


@app.route("/api/admin/fabric-identities/<user_id>/complete", methods=["POST"])
@require_auth(admin_only=True)
def complete_fabric_identity(user_id):
    result, error, status = complete_fabric_identity_binding(
        user_id, str(request.auth_user.get("id", ""))
    )
    if error:
        return jsonify({"status": "error", "message": error, "data": result}), status
    return jsonify({"status": "success", "data": result}), status


@app.route("/api/admin/fabric-identities/<user_id>/bootstrap", methods=["POST"])
@require_auth(admin_only=True)
def bootstrap_fabric_identity(user_id):
    result, error, status = provision_fabric_identity(
        user_id, request.get_json(silent=True) or {}, bootstrap=True
    )
    if error:
        return jsonify({"status": "error", "message": error, "data": result}), status
    return jsonify({"status": "success", "data": result}), status


@app.route("/api/admin/fabric-identities/<user_id>/bootstrap/complete", methods=["POST"])
@require_auth(admin_only=True)
def complete_fabric_identity_bootstrap(user_id):
    actor_id = str(request.auth_user.get("id", ""))
    if actor_id != str(user_id):
        return jsonify({
            "status": "error",
            "message": "Bootstrap chỉ dành cho chính tài khoản Admin đầu tiên",
        }), 403
    binding = identity_binding(user_id, include_inactive=True)
    if not binding or binding.get("status") not in {"pending", "failed"}:
        return jsonify({
            "status": "error", "message": "Không có bootstrap binding đang chờ"
        }), 409
    ledger_result = invoke_chaincode(
        "BootstrapAdminIdentity", [str(user_id)],
        signing_key_id=str(binding["key_id"]), allow_unbound=True,
    )
    if not ledger_result.get("success"):
        error = ledger_result.get("error") or "ledger bootstrap thất bại"
        mark_identity_binding(user_id, "failed", error)
        return jsonify({
            "status": "error",
            "message": "Bootstrap ledger thất bại; binding vẫn fail-closed",
            "data": {"userID": str(user_id), "status": "failed"},
        }), 409
    mark_identity_binding(user_id, "active")
    audit_event(
        "fabric_identity.bootstrap", "success", actor_id,
        request.auth_user.get("role"), user_id,
        {"keyID": str(binding["key_id"]), "mspID": binding["msp_id"]},
    )
    return jsonify({
        "status": "success",
        "data": {
            "userID": str(user_id), "keyID": str(binding["key_id"]),
            "mspID": binding["msp_id"],
            "certificateFingerprint": binding["certificate_fingerprint"],
            "status": "active",
        },
    })


@app.route("/api/workflow/asset-creation-requests", methods=["POST"])
@require_auth(permission="create_asset")
def create_asset_creation_request():
    if normalize_role(request.auth_user.get("role")) != "warehouse":
        return jsonify({"status": "error", "message": "Chỉ nhân viên kho được gửi yêu cầu tạo tài sản"}), 403
    item, error_response, status_code = submit_creation_workflow(
        request.get_json(silent=True) or {}
    )
    if item is None:
        return error_response if status_code is None else (error_response, status_code)
    return jsonify({
        "status": "success", "message": "Đã gửi yêu cầu tạo tài sản",
        "data": item,
    }), status_code


@app.route("/api/workflow/transfer-requests", methods=["POST"])
@require_auth(permission="transfer_asset")
def create_transfer_request():
    if normalize_role(request.auth_user.get("role")) != "sales":
        return jsonify({"status": "error", "message": "Chỉ nhân viên bán hàng được gửi yêu cầu chuyển kho"}), 403
    item, error_response, status_code = submit_transfer_workflow(
        request.get_json(silent=True) or {}
    )
    if item is None:
        return error_response if status_code is None else (error_response, status_code)
    return jsonify({
        "status": "success", "message": "Đã gửi yêu cầu chuyển tài sản",
        "data": item,
    }), status_code


@app.route("/api/workflow/requests", methods=["GET"])
@require_auth()
def get_workflow_requests():
    if normalize_role(request.auth_user.get("role")) not in {
        "admin", "manager", "warehouse", "sales", "customer"
    }:
        return jsonify({"status": "error", "message": "Vai trò không được xem workflow"}), 403
    items, result = list_visible_workflow_requests()
    if items is None:
        return workflow_error_response(result, "Không thể lấy danh sách yêu cầu")
    return jsonify({"status": "success", "data": items})


@app.route("/api/workflow/pending-counts", methods=["GET"])
@require_auth()
def get_workflow_pending_counts():
    items, result = list_visible_workflow_requests()
    if items is None:
        return workflow_error_response(result, "Không thể lấy số yêu cầu chờ xử lý")
    pending_approval = sum(item.get("status") == "PENDING_APPROVAL" for item in items)
    awaiting_customer = sum(item.get("status") == "AWAITING_CUSTOMER" for item in items)
    role = normalize_role(request.auth_user.get("role"))
    if role in {"admin", "manager"}:
        total = pending_approval
    elif role == "customer":
        total = awaiting_customer
    else:
        # Makers track all of their own nonterminal requests.
        total = pending_approval + awaiting_customer
    return jsonify({"status": "success", "data": {
        "pendingApproval": pending_approval,
        "awaitingCustomer": awaiting_customer,
        "total": total,
    }})


@app.route("/api/workflow/requests/<request_id>/<decision>", methods=["POST"])
@require_auth()
def decide_workflow_request(request_id, decision):
    decision = str(decision).lower()
    role = normalize_role(request.auth_user.get("role"))
    if decision in {"approve", "reject"}:
        if role not in {"manager", "admin"}:
            return jsonify({"status": "error", "message": "Chỉ Manager/Admin được phê duyệt hoặc từ chối"}), 403
        function = "ApproveWorkflowRequest" if decision == "approve" else "RejectWorkflowRequest"
    elif decision in {"accept", "decline"}:
        if role != "customer":
            return jsonify({"status": "error", "message": "Chỉ khách hàng đích được chấp nhận hoặc từ chối"}), 403
        function = "AcceptWorkflowRequest" if decision == "accept" else "DeclineWorkflowRequest"
    else:
        return jsonify({"status": "error", "message": "Quyết định không hợp lệ"}), 404
    body = request.get_json(silent=True) or {}
    result = invoke_chaincode(function, [
        str(request_id), str(body.get("reason", "")),
        str(request.auth_user.get("id", "")),
    ])
    if not result.get("success"):
        return workflow_error_response(result, "Không thể cập nhật yêu cầu")
    item = parse_chaincode_result(result)
    return jsonify({
        "status": "success", "message": "Đã cập nhật yêu cầu",
        "data": item if isinstance(item, dict) else {},
    })


@app.route("/api/chaincode/invoke", methods=["POST"])
@require_auth()
def authenticated_chaincode_invoke():
    body = request.get_json(silent=True) or {}
    function = str(body.get("function", "")).strip()
    args = body.get("args", [])
    blocked_functions = {
        "CreateAsset", "CreateUser", "DeleteAsset", "DeleteUser",
        "EnsureStoreUser", "GetAllAssets", "GetAllUsers", "GetAssetHistory",
        "GetPasswordHash", "SetUserPassword", "MigrateUserCredential", "TransferAsset",
        "TransferAssetQuantity", "UpdateAsset", "UpdateUser", "UsernameExists",
        "ReturnAssetToStore", "DeleteAssetQuantity", "RegisterUserIdentity",
        "RotateUserIdentity", "BootstrapAdminIdentity", "GetUserIdentity",
        "SubmitAssetCreationRequest", "SubmitInventoryTransferRequest",
        "ApproveWorkflowRequest", "RejectWorkflowRequest",
        "AcceptWorkflowRequest", "DeclineWorkflowRequest", "ReadWorkflowRequest",
        "ListWorkflowRequests"
    }
    if not function or not isinstance(args, list):
        return jsonify({
            "status": "error",
            "message": "Function và args hợp lệ là bắt buộc"
        }), 400
    if function in blocked_functions:
        audit_event(
            "chaincode.direct_invoke", "denied",
            request.auth_user.get("id"), request.auth_user.get("role"),
            details={"function": function},
        )
        return jsonify({
            "status": "error",
            "message": "Hàm chaincode này không được phép gọi trực tiếp"
        }), 403

    result = invoke_chaincode(function, [str(arg) for arg in args])
    if not result.get("success"):
        return jsonify({
            "status": "error",
            "message": "Gọi chaincode thất bại",
            "fabric_response": result
        }), 502
    return jsonify(result["data"])


# ==========================================
# HOME
# ==========================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "status": "success",
        "message": "Asset Management Backend API is running"
    })


# ==========================================
# HEALTH CHECK
# ==========================================

@app.route("/api/health", methods=["GET"])
def health():

    return jsonify({
        "status": "success",
        "message": "Backend is running"
    })


# ==========================================
# GET ALL ASSETS
# ==========================================

@app.route("/api/assets", methods=["GET"])
@require_auth()
def get_assets():

    result = invoke_chaincode(
        "GetAllAssets",
        []
    )

    if not result.get("success"):

        return jsonify({
            "status": "error",
            "message": "Không thể lấy danh sách tài sản",
            "fabric_response": result
        }), 500

    assets = parse_chaincode_result(result)
    if not isinstance(assets, list):
        assets = []
    assets = [asset for asset in assets if can_view_asset(request.auth_user, asset)]

    return jsonify({
        "status": "success",
        "data": assets
    })


# ==========================================
# GET ONE ASSET
# ==========================================

@app.route("/api/assets/<asset_id>", methods=["GET"])
@require_auth()
def get_asset(asset_id):

    result = invoke_chaincode(
        "ReadAsset",
        [asset_id]
    )

    if not result.get("success"):

        return jsonify({
            "status": "error",
            "message": "Không thể lấy tài sản",
            "fabric_response": result
        }), 500

    asset = parse_chaincode_result(result)
    if not isinstance(asset, dict) or not can_view_asset(request.auth_user, asset):
        return jsonify({"status": "error", "message": "Không có quyền xem tài sản này"}), 403

    return jsonify({
        "status": "success",
        "data": asset
    })


# ==========================================
# CREATE ASSET
# ==========================================

@app.route("/api/assets", methods=["POST"])
@require_auth(permission="create_asset")
def create_asset():

    body = request.get_json(silent=True) or {}

    role = normalize_role(request.auth_user.get("role"))
    if role == "warehouse":
        item, error_response, status_code = submit_creation_workflow(body)
        if item is None:
            return error_response if status_code is None else (error_response, status_code)
        return jsonify({
            "status": "success",
            "message": "Đã gửi yêu cầu tạo tài sản; tài sản chỉ xuất hiện sau khi được duyệt",
            "data": item,
        }), status_code
    if role != "admin":
        return jsonify({"status": "error", "message": "Tạo trực tiếp chỉ dành cho Admin"}), 403

    required_fields = [
        "id",
        "name",
        "type",
        "value",
        "quantity",
        "status"
    ]

    for field in required_fields:

        if body.get(field) in [None, ""]:

            return jsonify({
                "status": "error",
                "message": f"Thiếu trường {field}"
            }), 400

    owner_id = str(body.get("ownerID") or STORE_USER_ID)

    try:
        quantity = int(body["quantity"])
        value = int(body["value"])
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Giá và số lượng phải là số"}), 400
    if quantity < 1 or value < 1:
        return jsonify({"status": "error", "message": "Giá và số lượng phải lớn hơn 0"}), 400
    if value > 9_000_000_000_000_000:
        return jsonify({"status": "error", "message": "Giá trị tài sản vượt quá giới hạn"}), 400

    args = [
        str(body["id"]),
        str(body["name"]),
        str(body["type"]),
        owner_id,
        str(value),
        str(body["status"]),
        str(body.get("serialNumber", "")),
        str(body.get("description", "")),
        str(quantity),
        str(request.auth_user.get("id", ""))
    ]

    result = invoke_chaincode(
        "CreateAsset",
        args
    )

    if not result.get("success"):

        return jsonify({
            "status": "error",
            "message": "Không thể tạo tài sản",
            "fabric_response": result
        }), 500

    return jsonify({
        "status": "success",
        "message": "Tạo tài sản thành công",
        "fabric_response": result["data"]
    })


# ==========================================
# UPDATE ASSET
# ==========================================

@app.route("/api/assets/<asset_id>", methods=["PUT"])
@require_auth(permission="update_asset")
def update_asset(asset_id):

    body = request.get_json(silent=True) or {}

    required_fields = [
        "name",
        "type",
        "ownerID",
        "value",
        "quantity",
        "status"
    ]

    for field in required_fields:

        if body.get(field) in [None, ""]:

            return jsonify({
                "status": "error",
                "message": f"Thiếu trường {field}"
            }), 400

    existing_asset, read_result = read_chaincode_asset(asset_id)
    if not existing_asset:
        return jsonify({"status": "error", "message": "Tài sản không tồn tại"}), 404
    if not can_view_asset(request.auth_user, existing_asset):
        return jsonify({"status": "error", "message": "Không có quyền cập nhật tài sản này"}), 403

    try:
        value = int(body["value"])
        quantity = int(body["quantity"])
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Giá và số lượng phải là số nguyên"}), 400
    if value < 1 or quantity < 1:
        return jsonify({"status": "error", "message": "Giá và số lượng phải lớn hơn 0"}), 400
    if value > 9_000_000_000_000_000:
        return jsonify({"status": "error", "message": "Giá trị tài sản vượt quá giới hạn"}), 400

    role = normalize_role(request.auth_user.get("role"))
    owner_id = str(body["ownerID"]) if role == "admin" else str(existing_asset.get("ownerID"))

    args = [
        str(asset_id),
        str(body["name"]),
        str(body["type"]),
        owner_id,
        str(value),
        str(body["status"]),
        str(body.get("serialNumber", "")),
        str(body.get("description", "")),
        str(quantity),
        str(request.auth_user.get("id", ""))
    ]

    result = invoke_chaincode(
        "UpdateAsset",
        args
    )

    if not result.get("success"):

        return jsonify({
            "status": "error",
            "message": "Không thể cập nhật tài sản",
            "fabric_response": result
        }), 500

    return jsonify({
        "status": "success",
        "message": "Cập nhật tài sản thành công",
        "fabric_response": result["data"]
    })


# ==========================================
# DELETE ASSET
# ==========================================

@app.route("/api/assets/<asset_id>", methods=["DELETE"])
@require_auth()
def delete_asset(asset_id):

    asset, read_result = read_chaincode_asset(asset_id)
    if not asset:
        return jsonify({"status": "error", "message": "Tài sản không tồn tại"}), 404
    owns_asset = str(asset.get("ownerID")) == str(request.auth_user.get("id"))
    allowed = has_permission(request.auth_user, "delete_asset") or (
        owns_asset and has_permission(request.auth_user, "delete_own_asset")
    )
    if not allowed:
        return jsonify({"status": "error", "message": "Không có quyền xóa tài sản này"}), 403

    body = request.get_json(silent=True) or {}
    try:
        quantity = int(body.get("quantity") or asset.get("quantity") or 1)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Số lượng xóa không hợp lệ"}), 400
    available_quantity = int(asset.get("quantity") or 1)
    if quantity < 1 or quantity > available_quantity:
        return jsonify({
            "status": "error",
            "message": f"Số lượng xóa phải từ 1 đến {available_quantity}"
        }), 400

    result = invoke_chaincode(
        "DeleteAssetQuantity",
        [asset_id, str(quantity), str(request.auth_user.get("id", ""))]
    )

    if not result.get("success"):

        return jsonify({
            "status": "error",
            "message": "Không thể xóa tài sản",
            "fabric_response": result
        }), 500

    return jsonify({
        "status": "success",
        "message": "Xóa tài sản thành công",
        "fabric_response": result["data"]
    })


# ==========================================
# TRANSFER ASSET
# ==========================================

@app.route(
    "/api/assets/<asset_id>/transfer",
    methods=["POST"]
)
@require_auth()
def transfer_asset(asset_id):

    body = request.get_json(silent=True) or {}

    new_owner_id = (
        body.get("newOwnerID")
        or body.get("ownerID")
    )

    if not new_owner_id:

        return jsonify({
            "status": "error",
            "message": "Thiếu newOwnerID"
        }), 400

    asset, read_result = read_chaincode_asset(asset_id)
    if not asset:
        return jsonify({"status": "error", "message": "Tài sản không tồn tại"}), 404

    role = normalize_role(request.auth_user.get("role"))
    owns_asset = str(asset.get("ownerID")) == str(request.auth_user.get("id"))
    if role != "admin" and not can_view_asset(request.auth_user, asset):
        return jsonify({"status": "error", "message": "Không có quyền chuyển tài sản này"}), 403
    if role == "customer":
        if not has_permission(request.auth_user, "sell_back") or not owns_asset:
            return jsonify({"status": "error", "message": "Chỉ có thể bán lại tài sản của chính mình"}), 403
        if str(new_owner_id) != STORE_USER_ID:
            return jsonify({"status": "error", "message": "Khách hàng chỉ có thể bán lại cho cửa hàng"}), 403
        result = invoke_chaincode(
            "ReturnAssetToStore",
            [str(asset_id), str(request.auth_user.get("id", ""))]
        )
    elif role == "sales":
        if not has_permission(request.auth_user, "transfer_asset"):
            return jsonify({"status": "error", "message": "Không có quyền bán tài sản"}), 403
        item, error_response, status_code = submit_transfer_workflow(body, asset_id, asset)
        if item is None:
            return error_response if status_code is None else (error_response, status_code)
        return jsonify({
            "status": "success",
            "message": "Đã gửi yêu cầu chuyển tài sản; hàng đã được giữ chỗ",
            "data": item,
        }), status_code
    elif not has_permission(request.auth_user, "transfer_asset"):
        return jsonify({"status": "error", "message": "Không có quyền chuyển tài sản"}), 403

    quantity = body.get("quantity")
    new_asset_id = str(body.get("newAssetID") or "")
    if role == "customer":
        pass
    elif quantity not in [None, ""]:
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Số lượng bán không hợp lệ"}), 400
        if quantity < 1:
            return jsonify({"status": "error", "message": "Số lượng bán phải lớn hơn 0"}), 400
        if quantity < int(asset.get("quantity") or 1) and not new_asset_id:
            return jsonify({"status": "error", "message": "Thiếu mã tài sản mới khi bán một phần"}), 400
        result = invoke_chaincode(
            "TransferAssetQuantity",
            [str(asset_id), str(new_owner_id), str(quantity), new_asset_id,
             str(request.auth_user.get("id", ""))]
        )
    else:
        result = invoke_chaincode(
            "TransferAsset",
            [str(asset_id), str(new_owner_id), str(request.auth_user.get("id", ""))]
        )

    if not result.get("success"):

        return jsonify({
            "status": "error",
            "message": "Không thể chuyển quyền sở hữu",
            "fabric_response": result
        }), 500

    return jsonify({
        "status": "success",
        "message": "Chuyển quyền sở hữu thành công",
        "fabric_response": result["data"]
    })


# ==========================================
# ASSET HISTORY
# ==========================================

@app.route("/api/assets/history-index", methods=["GET"])
@require_auth(permission="view_history")
def asset_history_index():
    result = invoke_chaincode("GetAllAssetRecords", [])
    records = parse_chaincode_result(result)
    if not result.get("success") or not isinstance(records, list):
        return jsonify({
            "status": "error",
            "message": "Không thể lấy danh mục lịch sử tài sản",
            "fabric_response": result,
        }), 500

    visible = [
        {
            "id": str(asset.get("id", "")),
            "name": str(asset.get("name", "") or "Tài sản"),
            "ownerID": str(asset.get("ownerID", "")),
            "deleted": bool(asset.get("deleted", False)),
        }
        for asset in records
        if isinstance(asset, dict)
        and asset.get("id")
        and can_view_asset(request.auth_user, asset)
    ]
    return jsonify({"status": "success", "data": visible})

@app.route(
    "/api/assets/<asset_id>/history",
    methods=["GET"]
)
@require_auth()
def asset_history(asset_id):

    asset, read_result = read_chaincode_asset_record(asset_id)
    if not asset:
        return jsonify({"status": "error", "message": "Tài sản không tồn tại"}), 404
    if not has_permission(request.auth_user, "view_history") or not can_view_asset(request.auth_user, asset):
        return jsonify({"status": "error", "message": "Không có quyền xem lịch sử tài sản này"}), 403

    result = invoke_chaincode(
        "GetAssetHistory",
        [asset_id]
    )

    if not result.get("success"):

        return jsonify({
            "status": "error",
            "message": "Không thể lấy lịch sử tài sản",
            "fabric_response": result
        }), 500

    history = parse_chaincode_result(result)
    if not isinstance(history, list):
        history = []
    history = enrich_asset_history(history)
    history = history_visible_to_identity(history, request.auth_user)
    if normalize_role(request.auth_user.get("role")) == "warehouse":
        actor_id = str(request.auth_user.get("id"))
        history = [
            record for record in history
            if str(record.get("actorID")) == actor_id
        ]

    return jsonify({
        "status": "success",
        "data": history
    })


# ==========================================
# GET USER
# ==========================================

@app.route("/api/users", methods=["GET"])
@require_auth()
def get_users():
    result = invoke_chaincode("GetAllUsers", [])
    if not result.get("success"):
        return jsonify({"status": "error", "message": "Không thể lấy người dùng"}), 500
    users = parse_chaincode_result(result)
    if not isinstance(users, list):
        users = []
    sold_customer_ids = customer_ids_sold_by(request.auth_user)
    visible = []
    for user in users:
        if normalize_role(user.get("role")) == "store":
            continue
        public_user = public_user_for_identity(
            request.auth_user, user, sold_customer_ids
        )
        if public_user:
            visible.append(public_user)
    return jsonify({"status": "success", "data": visible})

@app.route("/api/users/<user_id>", methods=["GET"])
@require_auth()
def get_user(user_id):

    result = invoke_chaincode(
        "GetUser",
        [user_id]
    )

    if not result.get("success"):

        return jsonify({
            "status": "error",
            "message": "Không thể lấy thông tin người dùng",
            "fabric_response": result
        }), 500

    user = parse_chaincode_result(result)
    if not isinstance(user, dict):
        return jsonify({"status": "error", "message": "Người dùng không tồn tại"}), 404
    user = public_user_for_identity(
        request.auth_user, user, customer_ids_sold_by(request.auth_user)
    )
    if not user:
        return jsonify({"status": "error", "message": "Không có quyền xem người dùng này"}), 403

    return jsonify({
        "status": "success",
        "data": user
    })


# ==========================================
# CREATE USER
# ==========================================

@app.route("/api/users", methods=["POST"])
@require_auth()
def create_user():

    body = request.get_json(silent=True) or {}

    required_fields = [
        "username",
        "fullName",
        "role"
    ]

    for field in required_fields:

        if not body.get(field):

            return jsonify({
                "status": "error",
                "message": f"Thiếu trường {field}"
            }), 400

    creator_role = normalize_role(request.auth_user.get("role"))
    requested_role = normalize_role(body.get("role"))
    allowed_roles = {
        "admin": {"admin", "manager", "sales", "warehouse", "customer"},
        "manager": {"sales", "warehouse"} if has_permission(request.auth_user, "create_staff") else set(),
        "sales": {"customer"} if has_permission(request.auth_user, "create_customer") else set(),
    }.get(creator_role, set())
    if requested_role not in allowed_roles:
        return jsonify({
            "status": "error",
            "message": "Không có quyền tạo vai trò đã chọn"
        }), 403

    user_id = str(body.get("id", "")).strip()
    if not user_id:
        users_result = invoke_chaincode("GetAllUsers", [])
        users = parse_chaincode_result(users_result)
        if not users_result.get("success") or not isinstance(users, list):
            return jsonify({"status": "error", "message": "Không thể tạo mã người dùng tự động"}), 500
        users = [user for user in users if normalize_role(user.get("role")) != "store"]
        existing_ids = {str(user.get("id")) for user in users}
        sequence = len(users) + 1
        user_id = f"user_{sequence}"
        while user_id in existing_ids:
            sequence += 1
            user_id = f"user_{sequence}"
    contact = str(body.get("contact", "")).strip() or user_id

    result = invoke_chaincode(
        "CreateUser",
        [
            user_id,
            str(body["username"]),
            str(body["fullName"]),
            requested_role.upper(),
            generate_password_hash(DEFAULT_INITIAL_PASSWORD),
            contact,
            str(request.auth_user.get("id", ""))
        ]
    )

    if not result.get("success"):

        return jsonify({
            "status": "error",
            "message": "Không thể tạo người dùng",
            "fabric_response": result
        }), 500

    created_user = {
        "id": user_id,
        "username": str(body["username"]),
        "fullName": str(body["fullName"]),
        "role": requested_role.upper(),
        "contact": contact,
        "createdBy": str(request.auth_user.get("id", "")),
    }
    update_password_state(user_id, must_change=True)
    identity_request = None
    identity_request_error = ""
    try:
        identity_request = add_fabric_identity_request(
            created_user, request.auth_user.get("id")
        )
    except (OSError, sqlite3.Error, RuntimeError) as error:
        identity_request_error = str(error)
        audit_event(
            "fabric_identity.request_create", "failed",
            request.auth_user.get("id"), request.auth_user.get("role"), user_id,
            {"reason": identity_request_error},
        )
    audit_event(
        "user.create", "success",
        request.auth_user.get("id"), request.auth_user.get("role"), user_id,
        {
            "targetRole": requested_role,
            "identityRequestID": (identity_request or {}).get("id", ""),
        },
    )
    response_user = public_user_for_identity(request.auth_user, created_user)
    if creator_role == "sales":
        response_user = {
            "id": user_id,
            "fullName": str(body["fullName"]),
            "role": "CUSTOMER",
        }
    response = {
        "status": "success",
        "message": (
            "Tạo người dùng thành công; yêu cầu cấp Fabric identity đã gửi tới Admin"
            if identity_request else
            "Tạo người dùng thành công nhưng chưa thể gửi yêu cầu cấp Fabric identity"
        ),
        "data": response_user or created_user,
        "identityRequest": identity_request,
        "fabric_response": result["data"],
    }
    if identity_request_error:
        response["warning"] = identity_request_error
    return jsonify(response)


@app.route("/api/users/<user_id>", methods=["PUT"])
@require_auth()
def update_user(user_id):
    body = request.get_json(silent=True) or {}
    result = invoke_chaincode("GetUser", [str(user_id)])
    user = parse_chaincode_result(result)
    if not result.get("success") or not isinstance(user, dict):
        return jsonify({"status": "error", "message": "Người dùng không tồn tại"}), 404

    actor_role = normalize_role(request.auth_user.get("role"))
    target_role = normalize_role(user.get("role"))
    is_self = str(user_id) == str(request.auth_user.get("id"))
    is_contact_only = bool(body) and set(body) <= {"contact"}
    if is_self and is_contact_only:
        allowed = True
    elif actor_role == "admin":
        allowed = True
    elif actor_role == "manager":
        allowed = has_permission(request.auth_user, "update_user") and target_role not in {"admin", "store"}
    elif actor_role == "sales":
        allowed = False
    else:
        allowed = is_self and has_permission(request.auth_user, "update_own_contact")
    if not allowed:
        audit_event(
            "user.update", "denied", request.auth_user.get("id"),
            request.auth_user.get("role"), user_id,
        )
        return jsonify({"status": "error", "message": "Không có quyền sửa người dùng này"}), 403

    if actor_role != "admin" and is_self:
        unexpected = set(body) - {"contact"}
        if unexpected:
            return jsonify({"status": "error", "message": "Bạn chỉ được sửa SĐT/email của chính mình"}), 403

    full_name = str(body.get("fullName", user.get("fullName", ""))).strip()
    contact = str(body.get("contact", user.get("contact", ""))).strip()
    role = target_role
    if actor_role == "admin" and body.get("role"):
        requested_role = normalize_role(body.get("role"))
        if requested_role not in ROLE_LABELS:
            return jsonify({"status": "error", "message": "Vai trò không hợp lệ"}), 400
        if is_self and requested_role != "admin":
            return jsonify({"status": "error", "message": "Admin không thể tự hạ quyền tài khoản đang đăng nhập"}), 400
        if target_role == "admin" and requested_role != "admin":
            users_result = invoke_chaincode("GetAllUsers", [])
            users = parse_chaincode_result(users_result)
            admin_count = sum(
                1 for candidate in users or []
                if normalize_role(candidate.get("role")) == "admin"
            )
            if not users_result.get("success") or admin_count <= 1:
                return jsonify({"status": "error", "message": "Không thể hạ quyền Admin cuối cùng"}), 400
        role = requested_role
    if not full_name:
        return jsonify({"status": "error", "message": "Họ và tên không được để trống"}), 400

    updated = invoke_chaincode(
        "UpdateUser",
        [str(user_id), full_name, role.upper(), contact,
         str(request.auth_user.get("id", ""))]
    )
    if not updated.get("success"):
        return jsonify({"status": "error", "message": "Không thể cập nhật người dùng", "fabric_response": updated}), 500
    user.update({"fullName": full_name, "role": role.upper(), "contact": contact})
    audit_event(
        "user.update", "success", request.auth_user.get("id"),
        request.auth_user.get("role"), user_id,
        {"roleChanged": role != target_role, "contactOnly": is_contact_only},
    )
    return jsonify({"status": "success", "message": "Cập nhật người dùng thành công", "data": user})


@app.route("/api/users/<user_id>", methods=["DELETE"])
@require_auth(admin_only=True)
def delete_user(user_id):
    actor_id = str(request.auth_user.get("id", ""))
    if actor_id == str(user_id):
        return jsonify({
            "status": "error",
            "message": "Admin không thể tự xóa tài khoản đang đăng nhập"
        }), 400
    if identity_request_is_processing(user_id):
        return jsonify({
            "status": "error",
            "message": "Fabric identity của user đang được cấp; hãy chờ thao tác hoàn tất"
        }), 409

    binding = identity_binding(user_id, include_inactive=True)
    result = invoke_chaincode("DeleteUser", [str(user_id), actor_id])
    if not result.get("success"):
        return jsonify({
            "status": "error",
            "message": "Không thể xóa người dùng; hãy chuyển hoặc xóa tài sản của họ trước",
            "fabric_response": result
        }), 409

    # DeleteUser atomically removes the current ledger identity binding. The
    # ChainLaunch TLS/sign key pair is deleted only after that transaction
    # commits, avoiding an unusable user if ledger validation rejects deletion.
    cancel_fabric_identity_requests(user_id, actor_id)
    key_deleted, cleanup_error = delete_chainlaunch_identity(binding)
    if binding:
        mark_identity_binding(
            user_id, "revoked",
            "ledger user and ChainLaunch TLS/sign keys deleted" if key_deleted
            else f"ledger user deleted; key cleanup pending: {cleanup_error}",
        )
    audit_event(
        "user.delete", "success" if key_deleted else "partial",
        actor_id, request.auth_user.get("role"), user_id,
        {
            "fabricIdentityDeleted": key_deleted,
            "keyID": str((binding or {}).get("key_id", "")),
            "cleanupError": cleanup_error,
        },
    )
    response = {
        "status": "success",
        "message": (
            "Xóa người dùng và Fabric identity thành công" if key_deleted
            else "Đã xóa user và thu hồi identity trên ledger; "
                 "client key pair ChainLaunch cần được dọn lại"
        ),
        "identityDeleted": key_deleted,
    }
    if cleanup_error:
        response["warning"] = cleanup_error
    return jsonify(response)


# ==========================================
# FABRIC NETWORK
# ==========================================

@app.route("/api/fabric/networks", methods=["GET"])
@require_auth(admin_only=True)
def fabric_networks():

    result = fabric_request(
        "GET",
        "sc/fabric/chaincodes"
    )

    if not result.get("success"):

        return jsonify({
            "status": "error",
            "fabric_response": result
        }), 500

    return jsonify({
        "status": "success",
        "data": result["data"]
    })


# ==========================================
# RUN
# ==========================================

if __name__ == "__main__":

    app.run(
        host=os.getenv("BACKEND_HOST", "127.0.0.1"),
        port=5000,
        debug=os.getenv("FLASK_DEBUG", "0") == "1"
    )
