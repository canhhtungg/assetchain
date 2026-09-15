import os
import json
import requests
from functools import wraps

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


def require_auth(admin_only=False):
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
            if admin_only and str(identity.get("role", "")).lower() != "admin":
                return jsonify({
                    "status": "error",
                    "message": "Chỉ Admin mới có quyền thực hiện thao tác này"
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


@app.route("/api/chaincode/invoke", methods=["POST"])
@require_auth()
def authenticated_chaincode_invoke():
    body = request.get_json(silent=True) or {}
    function = str(body.get("function", "")).strip()
    args = body.get("args", [])
    blocked_functions = {
        "CreateUser", "DeleteUser", "GetPasswordHash", "SetUserPassword",
        "UsernameExists"
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

    return jsonify({
        "status": "success",
        "data": assets or []
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

    return jsonify({
        "status": "success",
        "data": asset
    })


# ==========================================
# CREATE ASSET
# ==========================================

@app.route("/api/assets", methods=["POST"])
@require_auth()
def create_asset():

    body = request.get_json(silent=True) or {}

    required_fields = [
        "id",
        "name",
        "type",
        "ownerID",
        "value",
        "status"
    ]

    for field in required_fields:

        if body.get(field) in [None, ""]:

            return jsonify({
                "status": "error",
                "message": f"Thiếu trường {field}"
            }), 400

    args = [
        str(body["id"]),
        str(body["name"]),
        str(body["type"]),
        str(body["ownerID"]),
        str(int(body["value"])),
        str(body["status"]),
        str(body.get("serialNumber", "")),
        str(body.get("description", ""))
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
@require_auth()
def update_asset(asset_id):

    body = request.get_json(silent=True) or {}

    required_fields = [
        "name",
        "type",
        "ownerID",
        "value",
        "status"
    ]

    for field in required_fields:

        if body.get(field) in [None, ""]:

            return jsonify({
                "status": "error",
                "message": f"Thiếu trường {field}"
            }), 400

    args = [
        str(asset_id),
        str(body["name"]),
        str(body["type"]),
        str(body["ownerID"]),
        str(int(body["value"])),
        str(body["status"]),
        str(body.get("serialNumber", "")),
        str(body.get("description", ""))
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

    result = invoke_chaincode(
        "DeleteAsset",
        [asset_id]
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

    result = invoke_chaincode(
        "TransferAsset",
        [
            str(asset_id),
            str(new_owner_id)
        ]
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

    return jsonify({
        "status": "success",
        "data": history or []
    })


# ==========================================
# GET USER
# ==========================================

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

    return jsonify({
        "status": "success",
        "data": user
    })


# ==========================================
# CREATE USER
# ==========================================

@app.route("/api/users", methods=["POST"])
@require_auth(admin_only=True)
def create_user():

    body = request.get_json(silent=True) or {}

    required_fields = [
        "id",
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

    result = invoke_chaincode(
        "CreateUser",
        [
            str(body["id"]),
            str(body["username"]),
            str(body["fullName"]),
            str(body["role"]),
            generate_password_hash(str(body["password"]))
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
        "fabric_response": result["data"]
    })


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
