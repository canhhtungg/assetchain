import os
import json
import requests
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()


# ==========================================
# FLASK CONFIG
# ==========================================

app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    }
)


# ==========================================
# CHAINLAUNCH CONFIG
# ==========================================

FABRIC_HOST = os.getenv(
    "FABRIC_HOST",
    "http://127.0.0.1:8100/api/v1"
)

FABRIC_USERNAME = os.getenv("FABRIC_USERNAME")

FABRIC_PASSWORD = os.getenv("FABRIC_PASSWORD")

APP_SECRET = os.getenv("APP_SECRET")
AUTH_TOKEN_MAX_AGE = int(os.getenv("AUTH_TOKEN_MAX_AGE", "28800"))
AUTH_CREDENTIALS_FILE = os.getenv("AUTH_CREDENTIALS_FILE")
ROLE_PERMISSIONS_FILE = os.getenv("ROLE_PERMISSIONS_FILE") or str(
    Path(__file__).with_name("role-permissions.local.json")
)

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

FABRIC_CHAINCODE_ID = os.getenv(
    "FABRIC_CHAINCODE_ID",
    "1"
)

FABRIC_KEY_ID = os.getenv(
    "FABRIC_KEY_ID",
    "6"
)


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
# CHAINCODE INVOKE
# ==========================================

def invoke_chaincode(function, args=None):

    if args is None:
        args = []

    endpoint = (
        f"sc/fabric/chaincodes/"
        f"{FABRIC_CHAINCODE_ID}/invoke"
    )

    payload = {
        "key_id": str(FABRIC_KEY_ID),
        "function": function,
        "args": args
    }

    return fabric_request(
        "POST",
        endpoint,
        json=payload
    )


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


def auth_serializer():
    if not APP_SECRET:
        raise RuntimeError("APP_SECRET chưa được cấu hình")
    return URLSafeTimedSerializer(APP_SECRET, salt="assetchain-auth")


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


def can_view_asset(identity, asset):
    if has_permission(identity, "view_all_assets"):
        return True
    if has_permission(identity, "view_inventory"):
        return str(asset.get("ownerID")) in {STORE_USER_ID, ADMIN_OWNER_ID}
    if has_permission(identity, "view_own_assets"):
        return str(asset.get("ownerID")) == str(identity.get("id"))
    return False


def created_within_minutes(user, creator_id, minutes=10):
    if str(user.get("createdBy")) != str(creator_id):
        return False
    try:
        created_at = datetime.fromisoformat(str(user.get("createdAt", "")).replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)
        return 0 <= age.total_seconds() <= minutes * 60
    except (TypeError, ValueError):
        return False


def public_user_for_identity(identity, user):
    role = normalize_role(identity.get("role"))
    target_role = normalize_role(user.get("role"))
    result = dict(user)
    if role == "sales":
        if (
            not has_permission(identity, "view_customers")
            or target_role != "customer"
            or not created_within_minutes(user, identity.get("id"))
        ):
            return None
        return {
            "id": user.get("id"),
            "fullName": user.get("fullName"),
            "role": "CUSTOMER",
            "canEdit": True,
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


def require_auth(admin_only=False, permission=None):
    def decorator(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify({"status": "error", "message": "Chưa đăng nhập"}), 401
            try:
                identity = auth_serializer().loads(
                    header[7:], max_age=AUTH_TOKEN_MAX_AGE
                )
            except (BadSignature, SignatureExpired, RuntimeError):
                return jsonify({
                    "status": "error",
                    "message": "Phiên đăng nhập không hợp lệ hoặc đã hết hạn"
                }), 401
            if admin_only and normalize_role(identity.get("role")) != "admin":
                return jsonify({
                    "status": "error",
                    "message": "Chỉ Admin mới có quyền thực hiện thao tác này"
                }), 403
            if permission and not has_permission(identity, permission):
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
        return jsonify({
            "status": "error",
            "message": "Username và password là bắt buộc"
        }), 400

    credential_result = invoke_chaincode("GetPasswordHash", [username])
    password_hash = parse_chaincode_result(credential_result)
    if not credential_result.get("success") or not isinstance(password_hash, str):
        password_hash = configured_password_hash(username)
    if (
        not isinstance(password_hash, str)
        or not check_password_hash(password_hash, password)
    ):
        return jsonify({
            "status": "error",
            "message": "Username hoặc password không đúng"
        }), 401

    user_result = invoke_chaincode("GetUserByUsername", [username])
    user = parse_chaincode_result(user_result)
    if not user_result.get("success") or not isinstance(user, dict):
        users_result = invoke_chaincode("GetAllUsers", [])
        users = parse_chaincode_result(users_result)
        if users_result.get("success") and isinstance(users, list):
            normalized_username = username.lower()
            user = next(
                (
                    candidate for candidate in users
                    if str(candidate.get("username", "")).strip().lower()
                    == normalized_username
                ),
                None,
            )
    if not isinstance(user, dict):
        return jsonify({
            "status": "error",
            "message": "Username hoặc password không đúng"
        }), 401

    user["role"] = normalize_role(user.get("role")).upper()

    try:
        token = auth_serializer().dumps({
            "id": user.get("id"),
            "role": user.get("role")
        })
    except RuntimeError as error:
        return jsonify({"status": "error", "message": str(error)}), 503

    return jsonify({
        "status": "success",
        "data": {"user": user, "token": token}
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


@app.route("/api/chaincode/invoke", methods=["POST"])
@require_auth()
def authenticated_chaincode_invoke():
    body = request.get_json(silent=True) or {}
    function = str(body.get("function", "")).strip()
    args = body.get("args", [])
    blocked_functions = {
        "CreateAsset", "CreateUser", "DeleteAsset", "DeleteUser",
        "EnsureStoreUser", "GetAllAssets", "GetAllUsers", "GetAssetHistory",
        "GetPasswordHash", "SetUserPassword", "TransferAsset",
        "TransferAssetQuantity", "UpdateAsset", "UpdateUser", "UsernameExists",
        "ReturnAssetToStore", "DeleteAssetQuantity"
    }
    if not function or not isinstance(args, list):
        return jsonify({
            "status": "error",
            "message": "Function và args hợp lệ là bắt buộc"
        }), 400
    if function in blocked_functions:
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
    if normalize_role(request.auth_user.get("role")) == "warehouse":
        owner_id = ADMIN_OWNER_ID

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
        if str(asset.get("ownerID")) not in {STORE_USER_ID, ADMIN_OWNER_ID}:
            return jsonify({"status": "error", "message": "Chỉ có thể bán tài sản chưa thuộc khách hàng"}), 403
        recipient_result = invoke_chaincode("GetUser", [str(new_owner_id)])
        recipient = parse_chaincode_result(recipient_result)
        if (
            not recipient_result.get("success")
            or not isinstance(recipient, dict)
            or normalize_role(recipient.get("role")) != "customer"
        ):
            return jsonify({"status": "error", "message": "Nhân viên bán hàng chỉ có thể bán cho khách hàng"}), 400
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

@app.route(
    "/api/assets/<asset_id>/history",
    methods=["GET"]
)
@require_auth()
def asset_history(asset_id):

    asset, read_result = read_chaincode_asset(asset_id)
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
    if normalize_role(request.auth_user.get("role")) == "warehouse":
        actor_id = str(request.auth_user.get("id"))
        history = [
            record for record in history
            if str((record.get("value") or {}).get("lastActorID")) == actor_id
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
    visible = []
    for user in users:
        if normalize_role(user.get("role")) == "store":
            continue
        public_user = public_user_for_identity(request.auth_user, user)
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
    user = public_user_for_identity(request.auth_user, user)
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
        "password",
        "fullName",
        "role"
    ]

    for field in required_fields:

        if not body.get(field):

            return jsonify({
                "status": "error",
                "message": f"Thiếu trường {field}"
            }), 400

    if len(str(body["password"])) < 8:
        return jsonify({
            "status": "error",
            "message": "Password phải có ít nhất 8 ký tự"
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
            generate_password_hash(str(body["password"])),
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

    return jsonify({
        "status": "success",
        "message": "Tạo người dùng thành công",
        "data": {
            "id": user_id,
            "username": str(body["username"]),
            "fullName": str(body["fullName"]),
            "role": requested_role.upper(),
            "contact": contact,
            "createdBy": str(request.auth_user.get("id", "")),
        },
        "fabric_response": result["data"]
    })


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
    if actor_role == "admin":
        allowed = True
    elif actor_role == "manager":
        allowed = has_permission(request.auth_user, "update_user") and target_role not in {"admin", "store"}
    elif actor_role == "sales":
        allowed = (
            has_permission(request.auth_user, "create_customer")
            and target_role == "customer"
            and created_within_minutes(user, request.auth_user.get("id"))
        )
    else:
        allowed = is_self and has_permission(request.auth_user, "update_own_contact")
    if not allowed:
        return jsonify({"status": "error", "message": "Không có quyền sửa người dùng này"}), 403

    if actor_role == "customer":
        unexpected = set(body) - {"contact"}
        if unexpected:
            return jsonify({"status": "error", "message": "Khách hàng chỉ được sửa SĐT/email"}), 403

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
        [str(user_id), full_name, role.upper(), contact]
    )
    if not updated.get("success"):
        return jsonify({"status": "error", "message": "Không thể cập nhật người dùng", "fabric_response": updated}), 500
    user.update({"fullName": full_name, "role": role.upper(), "contact": contact})
    return jsonify({"status": "success", "message": "Cập nhật người dùng thành công", "data": user})


@app.route("/api/users/<user_id>", methods=["DELETE"])
@require_auth(admin_only=True)
def delete_user(user_id):
    if str(request.auth_user.get("id")) == str(user_id):
        return jsonify({
            "status": "error",
            "message": "Admin không thể tự xóa tài khoản đang đăng nhập"
        }), 400

    result = invoke_chaincode("DeleteUser", [str(user_id)])
    if not result.get("success"):
        return jsonify({
            "status": "error",
            "message": "Không thể xóa người dùng; hãy chuyển hoặc xóa tài sản của họ trước",
            "fabric_response": result
        }), 409

    return jsonify({
        "status": "success",
        "message": "Xóa người dùng thành công"
    })


# ==========================================
# FABRIC NETWORK
# ==========================================

@app.route("/api/fabric/networks", methods=["GET"])
@require_auth()
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
        host="0.0.0.0",
        port=5000,
        debug=os.getenv("FLASK_DEBUG", "0") == "1"
    )
