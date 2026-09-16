import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_URL =
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:5000";
const ADMIN_OWNER_ID = "U001";

const ROLE_LABELS = {
  admin: "Admin",
  manager: "Quản lý",
  sales: "Nhân viên bán hàng",
  warehouse: "Nhân viên kho",
  customer: "Khách hàng",
};

const PERMISSION_LABELS = {
  view_all_assets: "Xem toàn bộ tài sản",
  view_inventory: "Xem hàng trong kho",
  view_own_assets: "Xem tài sản cá nhân",
  view_users: "Xem nhân viên và khách hàng",
  view_customers: "Xem khách hàng",
  create_staff: "Thêm nhân viên",
  create_customer: "Thêm khách hàng",
  create_asset: "Thêm sản phẩm/tài sản",
  update_asset: "Cập nhật tài sản",
  delete_asset: "Xóa mọi tài sản",
  delete_own_asset: "Xóa tài sản cá nhân",
  transfer_asset: "Bán/chuyển quyền tài sản",
  sell_back: "Bán lại cho cửa hàng",
  view_history: "Xem lịch sử giao dịch",
  update_user: "Sửa thông tin nhân viên và khách hàng",
  update_own_contact: "Sửa SĐT/email của chính mình",
};

const normalizeRole = (role) => {
  const normalized = String(role || "").toLowerCase();
  return normalized === "user" ? "customer" : normalized;
};

const iconFor = (type) =>
  (
    {
      Computer: "💻",
      Phone: "📱",
      Vehicle: "🚗",
      Other: "📦",
      car: "🚗",
      laptop: "💻",
      phone: "📱",
    }[type] || "📦"
  );


const money = (value) =>
  Number(value || 0).toLocaleString("vi-VN") +
  " ₫";


function parseChaincodeResult(data, fallback = []) {
  let result =
    data?.result?.result ??
    fallback;

  if (typeof result === "string") {
    if (!result.trim()) {
      return fallback;
    }

    try {
      return JSON.parse(result);
    } catch {
      return result;
    }
  }

  return result;
}



const THEME_STYLES = `
  html, body, #root { min-height: 100%; }

  body { transition: background-color .25s ease, color .25s ease; }

  [data-assetchain-theme="light"] body {
    background: #f5f7fb !important;
    color: #172033 !important;
  }

  [data-assetchain-theme="dark"] body {
    background: #0b1220 !important;
    color: #e5e7eb !important;
  }

  [data-assetchain-theme="dark"] .app,
  [data-assetchain-theme="dark"] .main,
  [data-assetchain-theme="dark"] .content,
  [data-assetchain-theme="dark"] .header {
    background: #0b1220 !important;
    color: #e5e7eb !important;
  }

  [data-assetchain-theme="dark"] .header {
    border-bottom-color: #263247 !important;
  }

  [data-assetchain-theme="dark"] .sidebar {
    background: #0f172a !important;
    border-right-color: #1f2937 !important;
  }

  [data-assetchain-theme="dark"] .menu-item { color: #cbd5e1 !important; }
  [data-assetchain-theme="dark"] .menu-item:hover {
    background: #1e293b !important;
    color: #fff !important;
  }
  [data-assetchain-theme="dark"] .menu-item.active {
    background: #2563eb !important;
    color: #fff !important;
  }

  [data-assetchain-theme="dark"] .menu-title,
  [data-assetchain-theme="dark"] .network-name,
  [data-assetchain-theme="dark"] .user-role,
  [data-assetchain-theme="dark"] .logo-subtitle,
  [data-assetchain-theme="dark"] .muted,
  [data-assetchain-theme="dark"] .percentage {
    color: #94a3b8 !important;
  }

  [data-assetchain-theme="dark"] .logo-title,
  [data-assetchain-theme="dark"] .header h1,
  [data-assetchain-theme="dark"] .content h1,
  [data-assetchain-theme="dark"] .content h2,
  [data-assetchain-theme="dark"] .content h3,
  [data-assetchain-theme="dark"] .user-name,
  [data-assetchain-theme="dark"] .asset-name {
    color: #f8fafc !important;
  }

  [data-assetchain-theme="dark"] .stat-card,
  [data-assetchain-theme="dark"] .asset-type-card,
  [data-assetchain-theme="dark"] .table-card,
  [data-assetchain-theme="dark"] .settings-card,
  [data-assetchain-theme="dark"] .modal,
  [data-assetchain-theme="dark"] .drawer {
    background: #111827 !important;
    color: #e5e7eb !important;
    border-color: #263247 !important;
    box-shadow: 0 10px 30px rgba(0,0,0,.28) !important;
  }

  [data-assetchain-theme="dark"] .stat-info h3,
  [data-assetchain-theme="dark"] .stat-info p,
  [data-assetchain-theme="dark"] .section-header p,
  [data-assetchain-theme="dark"] .page-toolbar p {
    color: #94a3b8 !important;
  }

  [data-assetchain-theme="dark"] table,
  [data-assetchain-theme="dark"] th,
  [data-assetchain-theme="dark"] td {
    border-color: #263247 !important;
  }

  [data-assetchain-theme="dark"] th {
    background: #0f172a !important;
    color: #94a3b8 !important;
  }

  [data-assetchain-theme="dark"] td { color: #dbe4f0 !important; }

  [data-assetchain-theme="dark"] tr:hover td {
    background: #172033 !important;
  }

  [data-assetchain-theme="dark"] input,
  [data-assetchain-theme="dark"] textarea,
  [data-assetchain-theme="dark"] select,
  [data-assetchain-theme="dark"] .search-box {
    background: #0f172a !important;
    color: #f8fafc !important;
    border-color: #334155 !important;
  }

  [data-assetchain-theme="dark"] input::placeholder,
  [data-assetchain-theme="dark"] textarea::placeholder {
    color: #64748b !important;
  }

  [data-assetchain-theme="dark"] .detail-list > div,
  [data-assetchain-theme="dark"] .setting-row {
    border-color: #263247 !important;
  }

  [data-assetchain-theme="dark"] .user-card {
    background: #0f172a !important;
    border-color: #334155 !important;
  }

  [data-assetchain-theme="dark"] .drawer-backdrop,
  [data-assetchain-theme="dark"] .modal-backdrop {
    background: rgba(2,6,23,.72) !important;
  }

  [data-assetchain-theme="dark"] pre {
    background: #0b1220 !important;
    color: #cbd5e1 !important;
    border-color: #263247 !important;
  }

  [data-assetchain-theme="dark"] .secondary-button {
    background: #1e293b !important;
    color: #e2e8f0 !important;
    border-color: #334155 !important;
  }

  [data-assetchain-theme="dark"] .secondary-button:hover {
    background: #334155 !important;
  }

  [data-assetchain-theme="dark"] .assetchain-login-page {
    background: #0b1220 !important;
  }

  [data-assetchain-theme="dark"] .assetchain-login-card {
    background: #111827 !important;
    color: #e5e7eb !important;
    border-color: #263247 !important;
  }

  [data-assetchain-theme="dark"] .assetchain-login-card .login-title,
  [data-assetchain-theme="dark"] .assetchain-login-card label {
    color: #f8fafc !important;
  }

  [data-assetchain-theme="dark"] .assetchain-login-card .login-subtitle {
    color: #94a3b8 !important;
  }

  [data-assetchain-theme="dark"] .assetchain-login-card input {
    background: #0f172a !important;
    color: #f8fafc !important;
    border-color: #334155 !important;
  }

  [data-assetchain-theme="light"] .app,
  [data-assetchain-theme="light"] .main,
  [data-assetchain-theme="light"] .content,
  [data-assetchain-theme="light"] .header {
    background: #f5f7fb !important;
    color: #172033 !important;
  }

  [data-assetchain-theme="light"] .sidebar {
    background: #0f172a !important;
  }

  [data-assetchain-theme="light"] .stat-card,
  [data-assetchain-theme="light"] .asset-type-card,
  [data-assetchain-theme="light"] .table-card,
  [data-assetchain-theme="light"] .settings-card,
  [data-assetchain-theme="light"] .modal,
  [data-assetchain-theme="light"] .drawer {
    background: #fff !important;
    color: #172033 !important;
    border-color: #e5e7eb !important;
  }
`;


function formatAssetValue(value) {
  const digits = String(value ?? "").replace(/\D/g, "");
  if (!digits) return "";
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function parseAssetValue(value) {
  const digits = String(value ?? "").replace(/\D/g, "");
  return digits ? Number(digits) : 0;
}

function App() {
  const [page, setPage] =
    useState("dashboard");

  const [assets, setAssets] =
    useState([]);

  const [users, setUsers] =
    useState([]);

  const [network, setNetwork] =
    useState(null);

  const [backend, setBackend] =
    useState("checking");

  const [query, setQuery] =
    useState("");

  const [modal, setModal] =
    useState(null);

  const [editing, setEditing] =
    useState(null);

  const [selected, setSelected] =
    useState(null);

  const [notice, setNotice] =
    useState("");

  const [loading, setLoading] =
    useState(false);

  const [confirmDialog, setConfirmDialog] = useState(null);

  const [blockchainHistory, setBlockchainHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  const [currentUser, setCurrentUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("assetchain-session"))?.user || null;
    } catch {
      return null;
    }
  });

  const [authToken, setAuthToken] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("assetchain-session"))?.token || "";
    } catch {
      return "";
    }
  });

  const [loginUsername, setLoginUsername] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const [permissions, setPermissions] = useState([]);
  const [permissionConfig, setPermissionConfig] = useState(null);
  const [userTab, setUserTab] = useState("employees");
  const [editingUser, setEditingUser] = useState(null);
  const [transactionQuery, setTransactionQuery] = useState("");

  const [themeMode, setThemeMode] = useState(() => {
    try {
      return localStorage.getItem("assetchain-theme") || "system";
    } catch {
      return "system";
    }
  });

  const [systemTheme, setSystemTheme] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return "light";
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  const effectiveTheme =
    themeMode === "system" ? systemTheme : themeMode;

  const currentRole = normalizeRole(currentUser?.role);
  const isAdmin = currentRole === "admin";
  const isManager = currentRole === "manager";
  const isSales = currentRole === "sales";
  const isWarehouse = currentRole === "warehouse";
  const isCustomer = currentRole === "customer";
  const can = (permission) => isAdmin || permissions.includes(permission);

  useEffect(() => {
    try {
      localStorage.setItem("assetchain-theme", themeMode);
    } catch {}
  }, [themeMode]);

  useEffect(() => {
    document.documentElement.setAttribute(
      "data-assetchain-theme",
      effectiveTheme
    );
  }, [effectiveTheme]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;

    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const updateSystemTheme = (event) => {
      setSystemTheme(event.matches ? "dark" : "light");
    };

    media.addEventListener?.("change", updateSystemTheme);
    return () => media.removeEventListener?.("change", updateSystemTheme);
  }, []);

useEffect(() => {
  if (!notice) return;

  const timer = setTimeout(() => {
    setNotice("");
  }, 5000);

  return () => clearTimeout(timer);
}, [notice]);


  /*
   * =====================================================
   * CHAINLAUNCH
   * =====================================================
   */

  const invokeChaincode = async (
    functionName,
    args = []
  ) => {
    const response = await fetch(
      `${API_URL}/api/chaincode/invoke`,
      {
        method: "POST",

        headers: {
          "Content-Type":
            "application/json",

          Authorization: `Bearer ${authToken}`,
        },

        body: JSON.stringify({
          function: functionName,

          args: args.map((arg) =>
            String(arg)
          ),
        }),
      }
    );


    const text =
      await response.text();


    let data;

    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(
        text ||
          "ChainLaunch trả về dữ liệu không hợp lệ"
      );
    }


    if (
      !response.ok ||
      data.status !== "success"
    ) {
      throw new Error(
        data.message ||
          data?.data?.detail ||
          "Không thể gọi Chaincode"
      );
    }

    return data;
  };

  const apiRequest = async (path, options = {}) => {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        Authorization: "Bearer " + authToken,
        ...(options.headers || {}),
      },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.message || "Yêu cầu không thành công");
    }
    return data;
  };


  /*
   * =====================================================
   * LOAD ASSETS
   * =====================================================
   */

  const loadAssets = async () => {
    try {
      const data = await apiRequest("/api/assets");
      const blockchainAssets = Array.isArray(data.data) ? data.data : [];


      const formattedAssets =
        blockchainAssets.map(
          (asset) => ({
            ...asset,

            value: Number(
              asset.value || 0
            ),

            quantity: Number(asset.quantity || 1),

            updatedAt:
              asset.updatedAt ||
              new Date()
                .toISOString()
                .slice(0, 10),
          })
        );


      setAssets(
        formattedAssets
      );

      setBackend("online");

      return formattedAssets;
    } catch (error) {
      console.error(
        "Load assets error:",
        error
      );

      setBackend("offline");

      throw error;
    }
  };


  /*
   * =====================================================
   * LOAD USERS
   * =====================================================
   */

  const loadUsers = async () => {
    try {
      const data = await apiRequest("/api/users");
      const blockchainUsers = Array.isArray(data.data) ? data.data : [];

      setUsers(
        blockchainUsers
      );

      return blockchainUsers;
    } catch (error) {
      console.error(
        "Load users error:",
        error
      );

      throw error;
    }
  };

  const loadPermissions = async () => {
    const data = await apiRequest("/api/permissions/me");
    setPermissions(data.data?.permissions || []);
    if (normalizeRole(currentUser?.role) === "admin") {
      const config = await apiRequest("/api/permissions");
      setPermissionConfig(config.data);
    }
  };


  /*
   * =====================================================
   * NETWORK
   * =====================================================
   */

  const loadNetworks = async () => {
    try {
      const response =
        await fetch(
          `${API_URL}/api/fabric/networks`,
          { headers: { Authorization: `Bearer ${authToken}` } }
        );

      const data =
        await response.json();

      if (
        response.ok &&
        data.status === "success"
      ) {
        setNetwork(
          data.data
        );
      }
    } catch {
      // Backend endpoint có thể không tồn tại
    }
  };


  /*
   * =====================================================
   * INITIAL LOAD
   * =====================================================
   */

  const loadAll = async () => {
    setLoading(true);

    try {
      await Promise.all([
        loadAssets(),
        loadUsers(),
        loadNetworks(),
        loadPermissions(),
      ]);
    } catch (error) {
      console.error(error);

      setNotice(
        "Không thể tải đầy đủ dữ liệu từ Blockchain: " +
          error.message
      );
    } finally {
      setLoading(false);
    }
  };


  useEffect(() => {
    if (currentUser) loadAll();
  }, [currentUser]);


  /*
   * =====================================================
   * FILTER ASSETS
   * =====================================================
   */

  const visibleAssets = useMemo(() => {
    if (
      isAdmin ||
      permissions.includes("view_all_assets") ||
      permissions.includes("view_inventory")
    ) {
      return assets;
    }
    return assets.filter((asset) => asset.ownerID === currentUser?.id);
  }, [assets, currentUser, isAdmin, permissions]);

  const filteredAssets = useMemo(() => {
    return visibleAssets.filter((asset) =>
      [asset.id, asset.name, asset.type, asset.ownerID, asset.status]
        .join(" ")
        .toLowerCase()
        .includes(query.toLowerCase())
    );
  }, [visibleAssets, query]);


  /*
   * =====================================================
   * STATISTICS
   * =====================================================
   */

  const typeStats =
    useMemo(() => {
      const counts = {
        Computer: 0,
        Phone: 0,
        Vehicle: 0,
        Other: 0,
      };

      visibleAssets.forEach(
        (asset) => {
          if (
            counts[
              asset.type
            ] !== undefined
          ) {
            counts[
              asset.type
            ]++;
          } else {
            counts.Other++;
          }
        }
      );

      return counts;
    }, [visibleAssets]);


  const activeCount =
    visibleAssets.filter(
      (asset) =>
        asset.status
          ?.toLowerCase() ===
        "active"
    ).length;

  const inventoryAssets = assets.filter((asset) =>
    ["STORE", ADMIN_OWNER_ID].includes(asset.ownerID)
  );
  const inventoryQuantity = inventoryAssets.reduce(
    (total, asset) => total + Number(asset.quantity || 1),
    0
  );
  const employees = users.filter((user) => {
    const role = normalizeRole(user.role);
    return ["manager", "sales", "warehouse"].includes(role) || (isAdmin && role === "admin");
  });
  const customers = users.filter((user) => normalizeRole(user.role) === "customer");
  const canManageUsers = can("view_users") || can("view_customers") || can("create_staff") || can("create_customer");
  const creatableRoles = isAdmin
    ? ["manager", "sales", "warehouse", "customer", "admin"]
    : isManager
    ? ["sales", "warehouse"]
    : isSales
    ? ["customer"]
    : [];


  /*
   * =====================================================
   * BLOCKCHAIN HISTORY
   * =====================================================
   * Lịch sử hiển thị trực tiếp từ GetAssetHistory trên Fabric.
   * Không còn sử dụng localStorage làm nguồn dữ liệu giao dịch.
   */

  const formatBlockchainTimestamp = (timestamp) => {
    if (timestamp === null || timestamp === undefined || timestamp === "") {
      return { display: "Không có timestamp", value: 0 };
    }

    let seconds = 0;
    let nanos = 0;

    if (typeof timestamp === "object") {
      seconds = Number(timestamp.seconds ?? timestamp.Seconds ?? 0);
      nanos = Number(timestamp.nanos ?? timestamp.Nanos ?? 0);
    } else if (typeof timestamp === "number") {
      seconds = timestamp;
    } else if (typeof timestamp === "string") {
      const trimmed = timestamp.trim();

      // GetAssetHistory của chaincode có thể trả timestamp dưới dạng
      // chuỗi protobuf, ví dụ: "seconds:1789237977 nanos:683848285".
      // Trường hợp này không thể dùng Date.parse(), nên phải tách
      // seconds/nanos thủ công trước khi chuyển sang Date.
      const protobufMatch = trimmed.match(
        /seconds\s*:\s*(-?\d+(?:\.\d+)?)\s+nanos\s*:\s*(-?\d+(?:\.\d+)?)/i
      );

      if (protobufMatch) {
        seconds = Number(protobufMatch[1]);
        nanos = Number(protobufMatch[2]);
      } else if (/^-?\d+(?:\.\d+)?$/.test(trimmed)) {
        seconds = Number(trimmed);
      } else {
        const parsed = Date.parse(trimmed);
        if (!Number.isNaN(parsed)) {
          return {
            display: new Date(parsed).toLocaleString("vi-VN", {
              timeZone: "Asia/Ho_Chi_Minh",
              day: "2-digit",
              month: "2-digit",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            }),
            value: parsed,
          };
        }

        try {
          const parsedObject = JSON.parse(trimmed);
          return formatBlockchainTimestamp(parsedObject);
        } catch {
          return { display: "Không có timestamp", value: 0 };
        }
      }
    }

    if (!Number.isFinite(seconds) || seconds === 0) {
      return { display: "Không có timestamp", value: 0 };
    }

    // Fabric timestamp dùng Unix seconds + nanos.
    const milliseconds = seconds * 1000 + Math.floor(nanos / 1000000);
    const date = new Date(milliseconds);

    if (Number.isNaN(date.getTime())) {
      return { display: "Không có timestamp", value: 0 };
    }

    return {
      display: date.toLocaleString("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
      value: milliseconds,
    };
  };

  const shortenTxId = (txId) => {
    if (!txId) return "-";
    if (txId.length <= 22) return txId;
    return `${txId.slice(0, 10)}...${txId.slice(-8)}`;
  };

  const normalizeHistoryRecord = (record, index, previousAsset = null) => {
    let value =
      record?.value ??
      record?.Value ??
      record?.asset ??
      record?.Asset ??
      {};

    if (typeof value === "string") {
      try {
        value = JSON.parse(value);
      } catch {
        value = {};
      }
    }

    const txId =
      record?.txId ??
      record?.TxId ??
      record?.txID ??
      record?.TxID ??
      record?.transactionId ??
      record?.TransactionID ??
      `HISTORY-${index + 1}`;

    const timestamp =
      record?.timestamp ??
      record?.Timestamp ??
      record?.time ??
      record?.Time ??
      "";

    const isDelete = Boolean(
      record?.isDelete ??
      record?.IsDelete ??
      record?.deleted ??
      record?.Deleted
    );

    const currentOwner = value?.ownerID || value?.OwnerID || "";
    const previousOwner = previousAsset?.ownerID || "";

    let action = "Cập nhật";
    if (isDelete) {
      action = "Xóa tài sản";
    } else if (index === 0) {
      action = "Tạo tài sản";
    } else if (currentOwner && previousOwner && currentOwner !== previousOwner) {
      action = "Cập nhật sở hữu";
    }

    const formattedTimestamp = formatBlockchainTimestamp(timestamp);

    return {
      id: txId,
      txId,
      action,
      assetID: value?.id || value?.ID || record?.assetID || "",
      assetName: value?.name || value?.Name || "Tài sản",
      ownerID: currentOwner,
      previousOwnerID: previousOwner,
      actorID: value?.lastActorID || value?.LastActorID || "",
      value: Number(value?.value || value?.Value || 0),
      status: value?.status || value?.Status || "",
      serialNumber: value?.serialNumber || value?.SerialNumber || "",
      detail: isDelete
        ? "Tài sản đã được xóa trên Blockchain"
        : currentOwner && previousOwner && currentOwner !== previousOwner
        ? `${previousOwner} -> ${currentOwner}`
        : "Dữ liệu tài sản được ghi nhận trên Blockchain",
      time: formattedTimestamp.display,
      timeValue: formattedTimestamp.value,
      raw: record,
    };
  };

  const loadBlockchainHistory = async () => {
    if (!currentUser) return;

    const historyAssets = visibleAssets;

    if (!historyAssets.length) {
      setBlockchainHistory([]);
      setHistoryError("");
      return;
    }

    try {
      setHistoryLoading(true);
      setHistoryError("");

      const results = await Promise.all(
        historyAssets.map(async (asset) => {
          try {
            const data = await apiRequest(`/api/assets/${encodeURIComponent(asset.id)}/history`);
            const records = Array.isArray(data.data) ? data.data : [];
            const chronologicalRecords = [...records].sort((left, right) => {
              const timestampOf = (record) =>
                record?.timestamp ??
                record?.Timestamp ??
                record?.time ??
                record?.Time ??
                "";

              return (
                formatBlockchainTimestamp(timestampOf(left)).value -
                formatBlockchainTimestamp(timestampOf(right)).value
              );
            });

            let previous = null;

            const normalized = chronologicalRecords.map((record, index) => {
              const item = normalizeHistoryRecord(record, index, previous);
              if (!record?.isDelete && !record?.IsDelete) {
                previous = {
                  ownerID: item.ownerID,
                };
              }
              return {
                ...item,
                assetID: item.assetID || asset.id,
                assetName: item.assetName || asset.name,
              };
            });

            return normalized;
          } catch (error) {
            console.error(`GetAssetHistory ${asset.id}:`, error);
            return [];
          }
        })
      );

      const flattened = results.flat();

      flattened.sort((a, b) => b.timeValue - a.timeValue);

      setBlockchainHistory(flattened);
    } catch (error) {
      console.error("Load blockchain history error:", error);
      setHistoryError(error.message || "Không thể tải lịch sử Blockchain");
      setBlockchainHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (page === "transactions" && currentUser) {
      loadBlockchainHistory();
    }
  }, [page, currentUser, visibleAssets]);

  /*
   * =====================================================
   * CREATE USER
   * =====================================================
   */

  const createUserRecord = async (form) => {
    const response = await apiRequest("/api/users", {
      method: "POST",
      body: JSON.stringify({
        id: form.id?.trim() || "",
        username: form.username.trim(),
        password: form.password,
        fullName: form.fullName.trim(),
        role: form.role,
        contact: form.contact?.trim() || "",
      }),
    });
    return response.data;
  };

  const createUser = async (form) => {
    const mayCreate = isAdmin || can("create_staff") || can("create_customer");
    if (!mayCreate) {
      setNotice("Vai trò hiện tại không có quyền tạo người dùng");
      return;
    }

    try {
      setLoading(true);
      const created = await createUserRecord(form);
      await loadUsers();
      setNotice(`Đã tạo người dùng ${created?.id || form.username} trên Blockchain`);
      setModal(null);
    } catch (error) {
      console.error(error);
      setNotice(`Lỗi Blockchain: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const updateUser = async (form) => {
    if (!editingUser) return;
    const body = {};
    if (!form.contactOnly) body.fullName = form.fullName.trim();
    if (form.contact !== "" || Object.hasOwn(editingUser, "contact")) {
      body.contact = form.contact.trim();
    }
    if (isAdmin) body.role = form.role;
    try {
      setLoading(true);
      const response = await apiRequest(`/api/users/${encodeURIComponent(editingUser.id)}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      if (editingUser.id === currentUser?.id) {
        const updatedUser = { ...currentUser, ...response.data };
        setCurrentUser(updatedUser);
        localStorage.setItem("assetchain-session", JSON.stringify({ user: updatedUser, token: authToken }));
      }
      await loadUsers();
      setEditingUser(null);
      setModal(null);
      setNotice("Đã cập nhật thông tin người dùng");
    } catch (error) {
      setNotice(`Không thể cập nhật người dùng: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  /*
   * =====================================================
   * DELETE USER
   * =====================================================
   */

  const executeDeleteUser = async (user) => {
    try {
      setLoading(true);
      const response = await fetch(`${API_URL}/api/users/${encodeURIComponent(user.id)}`, {
        method: "DELETE",
        headers: { Authorization: "Bearer " + authToken },
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.message || "Không thể xóa người dùng");
      }
      await Promise.all([loadUsers(), loadAssets()]);
      setConfirmDialog(null);
      setNotice(`Đã xóa người dùng ${user.username || user.id}`);
    } catch (error) {
      console.error(error);
      setNotice(error.message || "Không thể xóa người dùng");
    } finally {
      setLoading(false);
    }
  };

  const deleteUser = (user) => {
    if (!isAdmin) {
      setNotice("Chỉ Admin mới có quyền xóa người dùng");
      return;
    }
    if (user.id === currentUser?.id) {
      setNotice("Bạn không thể tự xóa tài khoản đang đăng nhập");
      return;
    }
    const ownedAssetCount = assets.filter((asset) => asset.ownerID === user.id).length;
    setConfirmDialog({
      title: "Xác nhận xóa người dùng",
      message: `Bạn có chắc chắn muốn xóa “${user.fullName || user.username || user.id}”?\n\nID: ${user.id}\nUsername: ${user.username}\nTài sản đang sở hữu: ${ownedAssetCount}\n\nChỉ có thể xóa khi người dùng không còn sở hữu tài sản.`,
      confirmText: "Xóa người dùng",
      danger: true,
      onConfirm: () => executeDeleteUser(user),
    });
  };


  /*
   * =====================================================
   * CHECK ASSET ID
   * =====================================================
   */

  const checkAssetIdExists = async (assetID) => {
    const id = assetID?.trim();
    if (!id) return null;

    const data = await invokeChaincode("AssetExists", [id]);
    const result = parseChaincodeResult(data, false);

    if (typeof result === "boolean") return result;

    if (typeof result === "string") {
      const normalized = result.trim().toLowerCase();
      if (normalized === "true") return true;
      if (normalized === "false") return false;
    }

    if (result && typeof result === "object") {
      if (typeof result.exists === "boolean") return result.exists;
      if (typeof result.value === "boolean") return result.value;
    }

    return Boolean(result);
  };


  /*
   * =====================================================
   * INPUT VALIDATION
   * =====================================================
   */

  const validateAssetForm = (form, isEdit) => {
    const id = form.id?.trim() || "";
    const name = form.name?.trim() || "";
    const type = form.type || "";
    const ownerID = isAdmin
      ? form.ownerID?.trim() || ""
      : isEdit
      ? form.ownerID?.trim() || ""
      : isWarehouse
      ? ADMIN_OWNER_ID
      : currentUser?.id || "";
    const value = parseAssetValue(form.value);
    const quantity = Number(form.quantity);
    const serialNumber = form.serialNumber?.trim() || "";
    const description = form.description?.trim() || "";

    if (!id) return "Mã tài sản không được để trống";
    if (id.length < 4 || id.length > 40) {
      return "Mã tài sản phải có từ 4 đến 40 ký tự";
    }
    if (!/^[A-Za-z0-9_-]+$/.test(id)) {
      return "Mã tài sản chỉ được chứa chữ cái, số, dấu gạch ngang hoặc gạch dưới";
    }

    if (!name) return "Tên tài sản không được để trống";
    if (name.length < 2 || name.length > 100) {
      return "Tên tài sản phải có từ 2 đến 100 ký tự";
    }

    const allowedTypes = ["Computer", "Phone", "Vehicle", "Other"];
    if (!allowedTypes.includes(type)) {
      return "Loại tài sản không hợp lệ";
    }

    if (!ownerID) return "Chủ sở hữu không được để trống";
    if (!["STORE", ADMIN_OWNER_ID].includes(ownerID) && !users.some((user) => user.id === ownerID)) {
      return `User ${ownerID} chưa tồn tại trên Blockchain`;
    }

    if (!Number.isSafeInteger(value) || value <= 0) {
      return "Giá trị tài sản phải là số nguyên lớn hơn 0";
    }
    if (value > 9000000000000000) {
      return "Giá trị tài sản vượt quá giới hạn cho phép";
    }
    if (!Number.isSafeInteger(quantity) || quantity < 1) {
      return "Số lượng sản phẩm phải là số nguyên lớn hơn 0";
    }

    if (serialNumber.length > 100) {
      return "Serial Number không được vượt quá 100 ký tự";
    }

    if (description.length > 500) {
      return "Mô tả không được vượt quá 500 ký tự";
    }

    if (!isEdit && id.length < 4) {
      return "Mã tài sản không hợp lệ";
    }

    return "";
  };


  /*
   * =====================================================
   * CREATE / UPDATE ASSET
   * =====================================================
   */

  const saveAsset = async (form) => {
    const isEdit = Boolean(editing);

    const validationError = validateAssetForm(form, isEdit);
    if (validationError) {
      setNotice(validationError);
      return;
    }

    if (isEdit && !can("update_asset")) {
      setNotice("Bạn không có quyền chỉnh sửa tài sản");
      return;
    }

    const ownerID = isAdmin
      ? form.ownerID?.trim()
      : isEdit
      ? form.ownerID?.trim()
      : isWarehouse
      ? ADMIN_OWNER_ID
      : currentUser?.id;

    const asset = {
      ...form,
      id: form.id?.trim() || `A${String(assets.length + 1).padStart(3, "0")}`,
      name: form.name.trim(),
      type: form.type,
      ownerID,
      value: parseAssetValue(form.value),
      quantity: Number(form.quantity),
      status: form.status,
      serialNumber: form.serialNumber || "",
      description: form.description || "",
    };

    if (!asset.ownerID) {
      setNotice("Vui lòng chọn chủ sở hữu");
      return;
    }

    if (!["STORE", ADMIN_OWNER_ID].includes(asset.ownerID) && !users.some((user) => user.id === asset.ownerID)) {
      setNotice(`User ${asset.ownerID} chưa tồn tại trên Blockchain`);
      return;
    }

    try {
      setLoading(true);

      // Khi tạo mới, kiểm tra trực tiếp trên Blockchain lần cuối.
      // Điều này chống trường hợp hai người cùng dùng một mã tài sản.
      if (!isEdit) {
        const exists = await checkAssetIdExists(asset.id);
        if (exists === true) {
          setNotice(`Mã tài sản ${asset.id} đã tồn tại. Vui lòng sử dụng mã khác.`);
          return;
        }
      }

      if (isEdit) {
        await apiRequest(`/api/assets/${encodeURIComponent(asset.id)}`, {
          method: "PUT",
          body: JSON.stringify(asset),
        });
      } else {
        await apiRequest("/api/assets", {
          method: "POST",
          body: JSON.stringify(asset),
        });
      }

      await loadAssets();

      setNotice(
        isEdit
          ? "Đã cập nhật tài sản trên Blockchain"
          : "Đã thêm tài sản vào Blockchain"
      );
      if (page === "transactions") {
        await loadBlockchainHistory();
      }
      setModal(null);
      setEditing(null);
    } catch (error) {
      console.error(error);
      setNotice(`Lỗi Blockchain: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };


  /*
   * =====================================================
   * DELETE ASSET
   * =====================================================
   */

  const executeDeleteAsset = async (asset, quantity) => {
    try {
      setLoading(true);

      await apiRequest(`/api/assets/${encodeURIComponent(asset.id)}`, {
        method: "DELETE",
        body: JSON.stringify({ quantity }),
      });
      await loadAssets();

      setNotice("Đã xóa tài sản khỏi Blockchain");
      setSelected(null);
      setConfirmDialog(null);
    } catch (error) {
      console.error(error);
      setNotice(`Lỗi Blockchain: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const deleteAsset = async (asset) => {
    const isOwner = asset?.ownerID === currentUser?.id;

    if (!can("delete_asset") && !(isOwner && can("delete_own_asset"))) {
      setNotice("Bạn không có quyền xóa tài sản này");
      return;
    }

    const availableQuantity = Number(asset?.quantity || 1);
    let quantity = availableQuantity;
    if (availableQuantity > 1) {
      const answer = window.prompt(
        `Nhập số lượng muốn xóa (1-${availableQuantity})`,
        String(availableQuantity)
      );
      if (answer === null) return;
      quantity = Number(answer);
      if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > availableQuantity) {
        setNotice(`Số lượng xóa phải từ 1 đến ${availableQuantity}`);
        return;
      }
    }

    setConfirmDialog({
      title: "Xác nhận xóa tài sản",
      message: `Bạn có chắc chắn muốn xóa ${quantity}/${availableQuantity} sản phẩm “${asset?.name || asset?.id}”?\n\nMã tài sản: ${asset?.id}\nGiá trị: ${money(asset?.value)}\n\nSố lượng được ghi trực tiếp lên Blockchain.`,
      confirmText: "Xóa tài sản",
      danger: true,
      onConfirm: () => executeDeleteAsset(asset, quantity),
    });
  };

  /*
   * =====================================================
   * TRANSFER ASSET
   * =====================================================
   */

  const executeTransferAsset = async (transfer) => {
    if (!selected) return;

    try {
      setLoading(true);
      let ownerID = transfer.ownerID;
      if (transfer.newCustomer) {
        const customer = await createUserRecord({
          ...transfer.newCustomer,
          role: "customer",
        });
        ownerID = customer.id;
        await loadUsers();
      }
      await apiRequest(`/api/assets/${encodeURIComponent(selected.id)}/transfer`, {
        method: "POST",
        body: JSON.stringify({
          newOwnerID: ownerID,
          quantity: transfer.quantity,
          newAssetID: transfer.newAssetID,
        }),
      });
      await loadAssets();

      setNotice("Đã chuyển quyền sở hữu trên Blockchain");
      setModal(null);
      setSelected(null);
      setConfirmDialog(null);
    } catch (error) {
      console.error(error);
      setNotice(`Lỗi Blockchain: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const transferAsset = async (transfer) => {
    if (!selected) return;

    const ownerID = transfer?.ownerID;

    if (isCustomer && selected.ownerID !== currentUser?.id) {
      setNotice("Bạn chỉ có thể chuyển tài sản của chính mình");
      return;
    }

    if (!ownerID || ownerID === selected.ownerID) {
      setNotice("Vui lòng chọn User ID mới khác chủ sở hữu hiện tại");
      return;
    }

    if (ownerID !== "STORE" && !transfer?.newCustomer && !users.some((user) => user.id === ownerID)) {
      setNotice(`User ${ownerID} chưa tồn tại trên Blockchain`);
      return;
    }

    const recipient = transfer?.recipient || users.find((user) => user.id === ownerID);
    const recipientLabel = ownerID === "STORE"
      ? "Kho cửa hàng (STORE)"
      : `${recipient?.fullName || recipient?.username || recipient?.id} (${recipient?.id})`;

    setConfirmDialog({
      title: isCustomer ? "Xác nhận bán lại cho cửa hàng" : "Xác nhận chuyển quyền",
      message: `Bạn có chắc chắn muốn chuyển tài sản “${selected.name}”?\n\nMã tài sản: ${selected.id}\nSố lượng: ${transfer.quantity || selected.quantity || 1}\n\nChủ sở hữu hiện tại:\n${selected.ownerID}\n\nChủ sở hữu mới:\n${recipientLabel}\n\nSau khi xác nhận, quyền sở hữu sẽ được ghi lên Blockchain.`,
      confirmText: "Xác nhận chuyển",
      danger: false,
      onConfirm: () => executeTransferAsset(transfer),
    });
  };

  const login = async () => {
    const username = loginUsername.trim();
    if (!username || !loginPassword) {
      setNotice("Vui lòng nhập username và password");
      return;
    }

    try {
      setLoginLoading(true);
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password: loginPassword }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.message || "Đăng nhập thất bại");
      }
      const { user, token } = payload.data;

      setCurrentUser(user);
      setAuthToken(token);
      localStorage.setItem("assetchain-session", JSON.stringify({ user, token }));
      setLoginUsername("");
      setLoginPassword("");
      setPage("dashboard");
    } catch (error) {
      console.error(error);
      setNotice(`Không thể đăng nhập: ${error.message}`);
    } finally {
      setLoginLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem("assetchain-session");
    setCurrentUser(null);
    setAuthToken("");
    setAssets([]);
    setUsers([]);
    setNetwork(null);
    setSelected(null);
    setEditing(null);
    setModal(null);
    setQuery("");
    setPage("dashboard");
  };


  /*
   * =====================================================
   * DASHBOARD
   * =====================================================
   */

  const renderDashboard =
    () => (
      <>
        <div className="welcome">
          <div>
            <h2>
              Xin chào, {currentUser?.fullName || currentUser?.username || "User"} 👋
            </h2>

            <p>
              Theo dõi và quản lý tài sản
              trên Blockchain
            </p>
          </div>

          {can("create_asset") && (
            <button
              className="primary-button"
              onClick={() => {
                setEditing(null);
                setModal("asset");
              }}
            >
              ＋ Thêm sản phẩm
            </button>
          )}
        </div>


        <div className="stats">
          <Stat
            icon="📦"
            tone="blue"
            label={isManager || isWarehouse ? "Tồn kho" : "Tổng tài sản"}
            value={isManager || isWarehouse ? inventoryQuantity : visibleAssets.length}
            small={isManager || isWarehouse ? `${inventoryAssets.length} mã sản phẩm` : `${activeCount} đang hoạt động`}
          />

          <Stat
            icon="👥"
            tone="green"
            label={isManager ? "Nhân viên" : isAdmin ? "Người dùng" : "Tài khoản"}
            value={isManager ? employees.length : isAdmin ? users.length : 1}
            small={isManager ? "Bán hàng và kho" : isAdmin ? "Quản lý trên Blockchain" : ROLE_LABELS[currentRole]}
          />

          {isManager && (
            <Stat
              icon="🛍"
              tone="orange"
              label="Khách hàng"
              value={customers.length}
              small="Tài khoản khách hàng"
            />
          )}

          <Stat
            icon="↗"
            tone="purple"
            label="Giao dịch"
            value={visibleTransactions.length}
            small="Lịch sử thao tác"
          />

          <Stat
            icon="🛡"
            tone="orange"
            label="Blockchain"
            value={
              backend === "online"
                ? "Online"
                : backend === "offline"
                ? "Offline"
                : "..."
            }
            small="Hyperledger Fabric"
          />
        </div>


        <SectionTitle
          title="Phân loại tài sản"
          subtitle="Thống kê theo loại tài sản"
          action={() =>
            setPage("assets")
          }
          actionText="Xem tất cả →"
        />


        <div className="asset-types">
          {[
            "Computer",
            "Phone",
            "Vehicle",
          ].map(
            (type) => (
              <div
                className="asset-type-card"
                key={type}
              >
                <div className="asset-type-icon">
                  {iconFor(type)}
                </div>

                <div>
                  <span>
                    {type === "Computer"
                      ? "Máy tính"
                      : type === "Phone"
                      ? "Điện thoại"
                      : "Phương tiện"}
                  </span>

                  <strong>
                    {typeStats[type]}
                  </strong>
                </div>

                <div className="percentage">
                  {assets.length
                    ? Math.round(
                        (typeStats[type] /
                          assets.length) *
                          100
                      )
                    : 0}
                  %
                </div>
              </div>
            )
          )}
        </div>


        <SectionTitle
          title="Tài sản gần đây"
          subtitle="Dữ liệu trực tiếp từ Blockchain"
        />


        <AssetTable
          assets={visibleAssets.slice(0, 6)}
          onSelect={(asset) => {
            setSelected(asset);

            setPage("assets");
          }}
        />
      </>
    );


  /*
   * =====================================================
   * ASSETS PAGE
   * =====================================================
   */

  const renderAssets =
    () => (
      <>
        <div className="page-toolbar">
          <div>
            <h2>
              Quản lý tài sản
            </h2>

            <p>
              Dữ liệu được lưu trên
              Hyperledger Fabric Blockchain
            </p>
          </div>

          <div
            style={{
              display: "flex",
              gap: "10px",
            }}
          >
            <button
              className="secondary-button"
              onClick={loadAll}
            >
              ↻ Làm mới
            </button>

            {can("create_asset") && (
              <button
                className="primary-button"
                onClick={() => {
                  setEditing(null);
                  setModal("asset");
                }}
              >
                ＋ Thêm sản phẩm
              </button>
            )}
          </div>
        </div>


        <div className="search-box large">
          <span>
            🔍
          </span>

          <input
            value={query}
            onChange={(event) =>
              setQuery(
                event.target.value
              )
            }
            placeholder="Tìm theo mã, tên, loại, chủ sở hữu..."
          />
        </div>


        <AssetTable
          assets={filteredAssets}
          onSelect={setSelected}
        />
      </>
    );


  /*
   * =====================================================
   * USERS PAGE
   * =====================================================
   */

  const renderUsers =
    () => {
      if (!canManageUsers) return null;
      const effectiveUserTab = can("view_users") ? userTab : "customers";
      const displayedUsers = effectiveUserTab === "employees" ? employees : customers;
      return (
        <>
        <div className="page-toolbar">
          <div>
            <h2>
              Người dùng
            </h2>

            <p>
              Danh sách người dùng
              được lưu trên Blockchain
            </p>
          </div>

          {creatableRoles.length > 0 && (
            <button
              className="primary-button"
              onClick={() => {
                setEditingUser(null);
                setModal("user");
              }}
            >
              ＋ {isSales ? "Thêm khách hàng" : "Thêm người dùng"}
            </button>
          )}
        </div>

        <div style={{ display: "flex", gap: "12px", marginBottom: "18px" }}>
          {can("view_users") && (
            <button
              className={effectiveUserTab === "employees" ? "primary-button" : "secondary-button"}
              onClick={() => setUserTab("employees")}
              style={{ background: effectiveUserTab === "employees" ? "#2563eb" : undefined }}
            >
              Nhân viên ({employees.length})
            </button>
          )}
          <button
            className={effectiveUserTab === "customers" ? "primary-button" : "secondary-button"}
            onClick={() => setUserTab("customers")}
            style={{ background: effectiveUserTab === "customers" ? "#16a34a" : undefined }}
          >
            Khách hàng ({customers.length})
          </button>
        </div>

        <div className="simple-grid">
          {displayedUsers.length ? (
            displayedUsers.map(
              (user) => (
                <div
                  className="user-card"
                  key={user.id}
                  style={{ borderLeft: `4px solid ${effectiveUserTab === "employees" ? "#2563eb" : "#16a34a"}` }}
                >
                  <div className="avatar">
                    {(user.fullName ||
                      user.id)
                      .slice(0, 2)
                      .toUpperCase()}
                  </div>

                  <div>
                    <strong>
                      {user.fullName ||
                        user.id}
                    </strong>

                    {!isSales && (
                      <span>
                        ID: {user.id}
                      </span>
                    )}

                    {!isSales && user.username && <span>Username: {user.username}</span>}

                    {!isSales && user.contact && <span>SĐT/email: {user.contact}</span>}

                    <span>
                      Vai trò: {ROLE_LABELS[normalizeRole(user.role)] || user.role}
                    </span>

                    {!isSales && (
                      <span>
                        {
                          assets.filter(
                            (asset) =>
                              asset.ownerID ===
                              user.id
                          ).length
                        }{" "}
                        tài sản
                      </span>
                    )}

                    {user.canEdit && (
                      <button
                        className="secondary-button"
                        type="button"
                        disabled={loading}
                        onClick={() => {
                          setEditingUser(user);
                          setModal("user");
                        }}
                        style={{ marginTop: "12px", marginRight: "8px" }}
                      >
                        Sửa thông tin
                      </button>
                    )}

                    {isAdmin && user.id !== currentUser?.id && (
                      <button
                        className="danger-button"
                        type="button"
                        disabled={loading}
                        onClick={() => deleteUser(user)}
                        style={{ marginTop: "12px" }}
                      >
                        Xóa người dùng
                      </button>
                    )}
                  </div>
                </div>
              )
            )
          ) : (
            <div className="empty">
              Chưa có người dùng
            </div>
          )}
        </div>
        </>
      );
    };


  const visibleTransactions = (() => {
    const normalizedQuery = transactionQuery.trim().toLowerCase();
    if (!normalizedQuery) return blockchainHistory;
    const userText = (id) => {
      const user = users.find((candidate) => candidate.id === id);
      return user
        ? [user.id, user.contact, user.username, user.fullName].filter(Boolean).join(" ")
        : id || "";
    };
    return blockchainHistory.filter((transaction) =>
      [
        transaction.txId,
        transaction.assetID,
        transaction.assetName,
        transaction.action,
        transaction.detail,
        userText(transaction.ownerID),
        userText(transaction.previousOwnerID),
        userText(transaction.actorID),
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery)
    );
  })();

  /*
   * =====================================================
   * TRANSACTIONS PAGE
   * =====================================================
   */

  const renderTransactions = () => (
    <>
      <div className="page-toolbar">
        <div>
          <h2>Lịch sử giao dịch</h2>
          <p>
            Lịch sử được truy xuất trực tiếp từ Blockchain thông qua GetAssetHistory
          </p>
        </div>

        <button
          className="secondary-button"
          onClick={loadBlockchainHistory}
          disabled={historyLoading}
        >
          {historyLoading ? "Đang tải..." : "↻ Làm mới lịch sử"}
        </button>
      </div>

      <div className="search-box large" style={{ marginBottom: "18px" }}>
        <span>🔍</span>
        <input
          value={transactionQuery}
          onChange={(event) => setTransactionQuery(event.target.value)}
          placeholder="Tìm theo SĐT/email, khách hàng, nhân viên, mã tài sản hoặc giao dịch..."
        />
      </div>

      {historyError && (
        <div className="notice">
          ⚠ {historyError}
        </div>
      )}

      <div className="table-card">
        <table>
          <thead>
            <tr>
              <th>TRANSACTION ID</th>
              <th>THAO TÁC</th>
              <th>TÀI SẢN</th>
              <th>CHỦ SỞ HỮU</th>
              <th>CHI TIẾT</th>
              <th>THỜI GIAN</th>
            </tr>
          </thead>

          <tbody>
            {historyLoading ? (
              <tr>
                <td colSpan="6" className="empty">
                  ⏳ Đang truy xuất lịch sử từ Blockchain...
                </td>
              </tr>
            ) : visibleTransactions.length ? (
              visibleTransactions.map((transaction, index) => (
                <tr key={`${transaction.txId}-${index}`}>
                  <td
                    title={transaction.txId || ""}
                    style={{
                      maxWidth: "190px",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    <small>{shortenTxId(transaction.txId)}</small>
                  </td>
                  <td>
                    <strong>{transaction.action}</strong>
                  </td>
                  <td>
                    {transaction.assetName} <small>({transaction.assetID})</small>
                  </td>
                  <td>{transaction.ownerID || "-"}</td>
                  <td>{transaction.detail || "-"}</td>
                  <td>{transaction.time}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="6" className="empty">
                  Chưa có lịch sử giao dịch trên Blockchain
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );

  /*
   * =====================================================
   * SETTINGS
   * =====================================================
   */

  const toggleRolePermission = (role, permission) => {
    setPermissionConfig((current) => {
      if (!current) return current;
      const selected = current.permissions?.[role] || [];
      const next = selected.includes(permission)
        ? selected.filter((item) => item !== permission)
        : [...selected, permission];
      return {
        ...current,
        permissions: { ...current.permissions, [role]: next },
      };
    });
  };

  const savePermissions = async () => {
    try {
      setLoading(true);
      await apiRequest("/api/permissions", {
        method: "PUT",
        body: JSON.stringify({ permissions: permissionConfig.permissions }),
      });
      await loadPermissions();
      setNotice("Đã cập nhật quyền theo vai trò");
    } catch (error) {
      setNotice(error.message);
    } finally {
      setLoading(false);
    }
  };

  const renderSettings =
    () => (
      <>
        <div className="page-toolbar">
          <div>
            <h2>
              Hệ thống
            </h2>

            <p>
              Thông tin kết nối Hyperledger
              Fabric và ChainLaunch
            </p>
          </div>
        </div>


        <div className="settings-card">
          <Setting
            label="Blockchain"
            value="Hyperledger Fabric"
            status={backend}
          />

          <Setting
            label="Kết nối ChainLaunch"
            value="Thông qua Backend API"
          />

          <Setting
            label="Backend API"
            value={API_URL}
          />

          <Setting
            label="Tài khoản hiện tại"
            value={currentUser?.username || "-"}
          />

          {isCustomer && can("update_own_contact") && (
            <div className="setting-row">
              <div>
                <strong>SĐT/email</strong>
                <div className="muted" style={{ marginTop: "4px" }}>
                  {currentUser?.contact || "Chưa cập nhật"}
                </div>
              </div>
              <button
                className="secondary-button"
                onClick={() => {
                  setEditingUser({ ...currentUser, canEdit: true });
                  setModal("user");
                }}
              >
                Sửa SĐT/email
              </button>
            </div>
          )}

          <div className="setting-row">
            <div>
              <strong>Giao diện</strong>
              <div className="muted" style={{ marginTop: "4px" }}>
                Chọn sáng, tối hoặc tự động theo hệ thống
              </div>
            </div>

            <select
              value={themeMode}
              onChange={(event) => setThemeMode(event.target.value)}
              style={{
                minWidth: "180px",
                padding: "10px 12px",
                borderRadius: "8px",
              }}
            >
              <option value="system">Theo hệ thống</option>
              <option value="light">Sáng</option>
              <option value="dark">Tối</option>
            </select>
          </div>


          <button
            className="secondary-button"
            onClick={loadAll}
          >
            ↻ Làm mới kết nối
          </button>


          <pre>
            {network
              ? JSON.stringify(
                  network,
                  null,
                  2
                )
              : "Chưa có dữ liệu Network từ Backend"}
          </pre>
        </div>

        {isAdmin && permissionConfig && (
          <div className="settings-card" style={{ marginTop: "20px" }}>
            <h3>Phân quyền theo vai trò</h3>
            <p className="muted">Admin luôn có toàn quyền. Thay đổi dưới đây áp dụng ngay cho các vai trò khác.</p>
            <div className="simple-grid">
              {Object.entries(permissionConfig.permissions || {}).map(([role, selected]) => (
                <div className="user-card" key={role}>
                  <strong>{ROLE_LABELS[role] || role}</strong>
                  {Object.entries(PERMISSION_LABELS).map(([permission, label]) => (
                    <label key={permission} style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <input
                        type="checkbox"
                        checked={selected.includes(permission)}
                        onChange={() => toggleRolePermission(role, permission)}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              ))}
            </div>
            <button className="primary-button" onClick={savePermissions} disabled={loading}>
              Lưu phân quyền
            </button>
          </div>
        )}
      </>
    );


  /*
   * =====================================================
   * MAIN UI
   * =====================================================
   */

  if (!currentUser) {
    return (
      <>
        <style>{THEME_STYLES}</style>
      <div
        className="assetchain-login-page"
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#f5f7fb",
          padding: "24px",
        }}
      >
        <form
          className="assetchain-login-card"
          onSubmit={(event) => {
            event.preventDefault();
            login();
          }}
          style={{
            width: "100%",
            maxWidth: "430px",
            background: "#fff",
            borderRadius: "18px",
            padding: "36px",
            boxShadow: "0 18px 50px rgba(15, 23, 42, 0.12)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "14px", marginBottom: "28px" }}>
            <div className="logo-icon">🛡</div>
            <div>
              <div className="logo-title" style={{ color: "#111827" }}>AssetChain</div>
              <div className="logo-subtitle" style={{ color: "#6b7280" }}>Blockchain Management</div>
            </div>
          </div>

          <h1
            className="login-title"
            style={{
              marginBottom: "8px",
              textAlign: "center",
              width: "100%",
            }}
          >
            Đăng nhập
          </h1>
          <p className="login-subtitle muted" style={{ marginBottom: "24px" }}>
            Đăng nhập bằng username và password
          </p>

          <div
            style={{
              width: "100%",
              marginTop: "8px",
            }}
          >
            <input
              autoFocus
              required
              value={loginUsername}
              onChange={(event) => setLoginUsername(event.target.value)}
              placeholder="Nhập username"
              aria-label="Username"
              style={{
                display: "block",
                width: "100%",
                height: "52px",
                boxSizing: "border-box",
                padding: "0 16px",
                border: "1px solid #d1d5db",
                borderRadius: "10px",
                background: "#f9fafb",
                color: "#111827",
                fontSize: "16px",
                outline: "none",
                transition: "all .2s ease",
              }}
            />
          </div>

          <div style={{ width: "100%", marginTop: "14px" }}>
            <input
              required
              type="password"
              autoComplete="current-password"
              value={loginPassword}
              onChange={(event) => setLoginPassword(event.target.value)}
              placeholder="Nhập password"
              aria-label="Password"
              style={{
                display: "block",
                width: "100%",
                height: "52px",
                boxSizing: "border-box",
                padding: "0 16px",
                border: "1px solid #d1d5db",
                borderRadius: "10px",
                background: "#f9fafb",
                color: "#111827",
                fontSize: "16px",
              }}
            />
          </div>

          <button
            className="primary-button"
            type="submit"
            disabled={loginLoading}
            style={{ width: "100%", marginTop: "20px" }}
          >
            {loginLoading ? "Đang xác thực..." : "Đăng nhập"}
          </button>

        </form>

        <NoticeModal
          message={notice}
          onClose={() => setNotice("")}
        />
      </div>
      </>
    );
  }

  return (
    <>
      <style>{THEME_STYLES}</style>
    <div className="app">

      <NoticeModal
        message={notice}
        onClose={() => setNotice("")}
      />

      <aside className="sidebar">

        <div className="logo">

          <div className="logo-icon">
            🛡
          </div>

          <div>

            <div className="logo-title">
              AssetChain
            </div>

            <div className="logo-subtitle">
              Blockchain Management
            </div>

          </div>

        </div>


        <div className="menu-title">
          QUẢN LÝ
        </div>


        <nav>
          {[
            ["dashboard", "▣", "Dashboard"],
            ["assets", "▤", isWarehouse ? "Sản phẩm trong kho" : "Tài sản"],
            ...(canManageUsers ? [["users", "♙", "Nhân sự & khách hàng"]] : []),
            ...(can("view_history") ? [["transactions", "◷", "Lịch sử giao dịch"]] : []),
          ].map(
            ([
              key,
              icon,
              label,
            ]) => (
              <button
                className={`menu-item ${
                  page === key
                    ? "active"
                    : ""
                }`}
                key={key}
                onClick={() =>
                  setPage(key)
                }
              >
                <span className="menu-icon">
                  {icon}
                </span>

                <span>
                  {label}
                </span>
              </button>
            )
          )}
        </nav>


        <div className="menu-title system-title">
          HỆ THỐNG
        </div>


        <button
          className={`menu-item ${
            page === "settings"
              ? "active"
              : ""
          }`}
          onClick={() =>
            setPage("settings")
          }
        >
          <span className="menu-icon">
            ⚙
          </span>

          <span>
            Cài đặt
          </span>
        </button>


        <div className="sidebar-bottom">

          <div className="network-status">

            <div
              className={`status-dot ${
                backend === "offline"
                  ? "offline"
                  : ""
              }`}
            />

            <div>

              <div className="network-name">
                Fabric Network
              </div>

              <div className="network-online">
                {backend === "online"
                  ? "● Online"
                  : backend === "offline"
                  ? "● Offline"
                  : "● Checking"}
              </div>

            </div>

          </div>

          <button
            className="secondary-button"
            style={{ width: "100%", marginTop: "14px" }}
            onClick={logout}
          >
            ↪ Đăng xuất
          </button>
        </div>

      </aside>


      <main className="main">

        <header className="header">

          <div>

            <h1>
              {
                {
                  dashboard:
                    "Dashboard",

                  assets:
                    "Tài sản",

                  users:
                    "Người dùng",

                  transactions:
                    "Lịch sử giao dịch",

                  settings:
                    "Cài đặt",
                }[page]
              }
            </h1>

            <p>
              Hyperledger Fabric Asset
              Management System
            </p>

          </div>


          <div className="user-profile">

            <div className="avatar">
              {(currentUser?.fullName || currentUser?.username || "U")
                .slice(0, 2)
                .toUpperCase()}
            </div>

            <div>

              <div className="user-name">
                {currentUser?.fullName || currentUser?.username}
              </div>

              <div className="user-role">
                {ROLE_LABELS[currentRole] || currentUser?.role}
              </div>

            </div>

          </div>

        </header>


        <section className="content">

          {loading && (
            <div className="notice">
              ⏳ Đang xử lý Blockchain...
            </div>
          )}


          {page === "dashboard" &&
            renderDashboard()}

          {page === "assets" &&
            renderAssets()}

          {page === "users" &&
            (canManageUsers ? renderUsers() : null)}

          {page === "transactions" &&
            renderTransactions()}

          {page === "settings" &&
            renderSettings()}

        </section>

      </main>


      <ConfirmModal
        dialog={confirmDialog}
        onClose={() => setConfirmDialog(null)}
      />

      {modal === "asset" && (
        <AssetModal
          initial={editing}
          users={users}
          currentUser={currentUser}
          isAdmin={isAdmin}
          isWarehouse={isWarehouse}
          onCheckAssetId={checkAssetIdExists}
          onClose={() => {
            setModal(null);
            setEditing(null);
          }}
          onSave={saveAsset}
        />
      )}


      {modal === "user" && (
        <UserModal
          roles={creatableRoles}
          initial={editingUser}
          contactOnly={isCustomer && editingUser?.id === currentUser?.id}
          allowRoleEdit={isAdmin}
          onClose={() => {
            setEditingUser(null);
            setModal(null);
          }}
          onSave={editingUser ? updateUser : createUser}
        />
      )}


      {modal === "transfer" && (
        <TransferModal
          asset={selected}
          users={users}
          currentRole={currentRole}
          onClose={() =>
            setModal(null)
          }
          onSave={transferAsset}
        />
      )}


      {selected &&
	  page === "assets" &&
	  modal !== "transfer" && (
          <div
            className="drawer-backdrop"
            onClick={() =>
              setSelected(null)
            }
          >

            <aside
              className="drawer"
              onClick={(event) =>
                event.stopPropagation()
              }
            >

              <button
                className="close-button"
                onClick={() =>
                  setSelected(null)
                }
              >
                ×
              </button>


              <div className="drawer-icon">
                {iconFor(
                  selected.type
                )}
              </div>


              <h2>
                {selected.name}
              </h2>

              <p className="muted">
                {selected.id}
              </p>


              <div className="detail-list">

                <div>
                  <span>
                    Loại
                  </span>

                  <strong>
                    {selected.type}
                  </strong>
                </div>


                <div>
                  <span>
                    Chủ sở hữu
                  </span>

                  <strong>
                    {selected.ownerID}
                  </strong>
                </div>


                <div>
                  <span>
                    Giá trị
                  </span>

                  <strong>
                    {money(
                      selected.value
                    )}
                  </strong>
                </div>

                <div>
                  <span>Số lượng</span>
                  <strong>{Number(selected.quantity || 1)}</strong>
                </div>


                <div>
                  <span>
                    Serial Number
                  </span>

                  <strong>
                    {
                      selected.serialNumber ||
                      "-"
                    }
                  </strong>
                </div>


                <div>
                  <span>
                    Mô tả
                  </span>

                  <strong>
                    {
                      selected.description ||
                      "-"
                    }
                  </strong>
                </div>


                <div>
                  <span>
                    Trạng thái
                  </span>

                  <strong>
                    <span
                      className={`status ${
                        selected.status
                          ?.toLowerCase() ||
                        ""
                      }`}
                    >
                      {
                        selected.status
                      }
                    </span>
                  </strong>
                </div>

              </div>


              <div className="drawer-actions">

                {(isAdmin ||
                  (can("transfer_asset") && ["STORE", ADMIN_OWNER_ID].includes(selected.ownerID)) ||
                  (can("sell_back") && selected.ownerID === currentUser?.id)) && (
                  <button
                    className="primary-button"
                    onClick={() => setModal("transfer")}
                  >
                    {isCustomer ? "Bán lại cho cửa hàng" : isSales ? "Bán sản phẩm" : "Chuyển quyền"}
                  </button>
                )}

                {can("update_asset") && (
                  <button
                    className="secondary-button"
                    onClick={() => {
                      setEditing(selected);
                      setSelected(null);
                      setModal("asset");
                    }}
                  >
                    Chỉnh sửa
                  </button>
                )}

                {(can("delete_asset") ||
                  (can("delete_own_asset") && selected.ownerID === currentUser?.id)) && (
                  <button
                    className="danger-button"
                    onClick={() => deleteAsset(selected)}
                  >
                    Xóa
                  </button>
                )}

              </div>

            </aside>

          </div>
        )}

    </div>
    </>
  );
}


/*
 * =====================================================
 * NOTIFICATION POPUP
 * =====================================================
 */

function ConfirmModal({ dialog, onClose }) {
  if (!dialog) return null;

  const handleConfirm = async () => {
    if (!dialog.onConfirm) {
      onClose();
      return;
    }
    await dialog.onConfirm();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={dialog.title}
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        background: "rgba(0,0,0,.52)",
        backdropFilter: "blur(3px)",
      }}
    >
      <div
        onClick={(event) => event.stopPropagation()}
        style={{
          width: "min(560px, 100%)",
          background: "#fff",
          borderRadius: "18px",
          padding: "30px",
          boxShadow: "0 25px 80px rgba(0,0,0,.28)",
        }}
      >
        <div
          style={{
            width: "58px",
            height: "58px",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "18px",
            background: dialog.danger ? "#fee2e2" : "#dbeafe",
            color: dialog.danger ? "#dc2626" : "#2563eb",
            fontSize: "28px",
            fontWeight: 700,
          }}
        >
          {dialog.danger ? "!" : "?"}
        </div>

        <h2 style={{ margin: "0 0 14px" }}>{dialog.title}</h2>

        <p
          style={{
            margin: 0,
            whiteSpace: "pre-line",
            lineHeight: 1.65,
            color: "#64748b",
          }}
        >
          {dialog.message}
        </p>

        <div
          className="modal-actions"
          style={{ marginTop: "28px" }}
        >
          <button
            type="button"
            className="secondary-button"
            onClick={onClose}
          >
            Hủy
          </button>

          <button
            type="button"
            className={dialog.danger ? "danger-button" : "primary-button"}
            onClick={handleConfirm}
          >
            {dialog.confirmText || "Xác nhận"}
          </button>
        </div>
      </div>
    </div>
  );
}


function NoticeModal({ message, onClose }) {
  if (!message) return null;

  const lower = message.toLowerCase();

  const isSuccess =
    lower.includes("đã ") ||
    lower.includes("thành công") ||
    lower.includes("online");

  const isError =
    lower.includes("lỗi") ||
    lower.includes("không thể") ||
    lower.includes("không tìm") ||
    lower.includes("chưa tồn tại") ||
    lower.includes("không có quyền") ||
    lower.includes("vui lòng");

  const title = isSuccess ? "Thành công!" : isError ? "Thông báo" : "Thông báo";
  const icon = isSuccess ? "✓" : "!";
  const iconColor = isSuccess ? "#8bdc68" : "#f0a84f";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 99999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        background: "rgba(0, 0, 0, 0.48)",
        backdropFilter: "blur(2px)",
      }}
    >
      <div
        onClick={(event) => event.stopPropagation()}
        style={{
          position: "relative",
          width: "min(620px, 100%)",
          minHeight: "390px",
          background: "#fff",
          borderRadius: "16px",
          boxShadow: "0 24px 70px rgba(0,0,0,.25)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "42px 42px 36px",
          textAlign: "center",
          boxSizing: "border-box",
        }}
      >
        <button
          type="button"
          aria-label="Đóng"
          onClick={onClose}
          style={{
            position: "absolute",
            top: "16px",
            right: "18px",
            width: "38px",
            height: "38px",
            border: "none",
            borderRadius: "50%",
            background: "#f3f4f6",
            color: "#6b7280",
            fontSize: "25px",
            lineHeight: 1,
            cursor: "pointer",
          }}
        >
          ×
        </button>

        <div
          style={{
            width: "132px",
            height: "132px",
            borderRadius: "50%",
            border: `7px solid ${isSuccess ? "#dff3d7" : "#fde6c7"}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "34px",
            boxSizing: "border-box",
          }}
        >
          <div
            style={{
              width: "82px",
              height: "82px",
              borderRadius: "50%",
              border: `5px solid ${iconColor}`,
              color: iconColor,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: isSuccess ? "58px" : "48px",
              fontWeight: 700,
              fontFamily: "Arial, sans-serif",
            }}
          >
            {icon}
          </div>
        </div>

        <h2
          style={{
            margin: "0 0 14px",
            fontSize: "34px",
            lineHeight: 1.2,
            color: "#4b4b4b",
            fontWeight: 600,
          }}
        >
          {title}
        </h2>

        <p
          style={{
            margin: 0,
            maxWidth: "520px",
            fontSize: "20px",
            lineHeight: 1.55,
            color: "#666",
          }}
        >
          {message}
        </p>

        <button
          type="button"
          onClick={onClose}
          style={{
            marginTop: "30px",
            minWidth: "150px",
            padding: "13px 34px",
            border: "none",
            borderRadius: "8px",
            background: "#3186d8",
            color: "#fff",
            fontSize: "19px",
            fontWeight: 500,
            cursor: "pointer",
            boxShadow: "0 2px 6px rgba(49,134,216,.3)",
          }}
        >
          OK
        </button>
      </div>
    </div>
  );
}


/*
 * =====================================================
 * COMPONENTS
 * =====================================================
 */


function Stat({
  icon,
  tone,
  label,
  value,
  small,
}) {
  return (
    <div className="stat-card">

      <div
        className={`stat-icon ${tone}`}
      >
        {icon}
      </div>

      <div className="stat-info">

        <span>
          {label}
        </span>

        <strong
          className={
            label === "Blockchain"
              ? "online-text"
              : ""
          }
        >
          {value}
        </strong>

        <small>
          {small}
        </small>

      </div>

    </div>
  );
}


function SectionTitle({
  title,
  subtitle,
  action,
  actionText,
}) {
  return (
    <div className="section-header">

      <div>

        <h2>
          {title}
        </h2>

        <p>
          {subtitle}
        </p>

      </div>


      {action && (
        <button
          className="view-all"
          onClick={action}
        >
          {actionText}
        </button>
      )}

    </div>
  );
}


function Setting({
  label,
  value,
  status,
}) {
  return (
    <div className="setting-row">

      <span>
        {label}
      </span>

      <strong>
        {value}
      </strong>

      {status && (
        <em
          className={status}
        >
          {status}
        </em>
      )}

    </div>
  );
}


function AssetTable({
  assets,
  onSelect,
}) {
  return (
    <div className="table-card">

      <table>

        <thead>

          <tr>

            <th>
              TÀI SẢN
            </th>

            <th>
              LOẠI
            </th>

            <th>
              NGƯỜI SỞ HỮU
            </th>

            <th>
              GIÁ TRỊ
            </th>

            <th>
              SỐ LƯỢNG
            </th>

            <th>
              TRẠNG THÁI
            </th>

            <th />

          </tr>

        </thead>


        <tbody>

          {assets.length ? (
            assets.map(
              (asset) => (
                <tr
                  key={asset.id}
                  className="clickable"
                  onClick={() =>
                    onSelect(asset)
                  }
                >

                  <td>

                    <div className="asset-name">

                      <div className="table-icon">
                        {iconFor(
                          asset.type
                        )}
                      </div>

                      <div>

                        <strong>
                          {
                            asset.name
                          }
                        </strong>

                        <span>
                          {
                            asset.id
                          }
                        </span>

                      </div>

                    </div>

                  </td>


                  <td>

                    <span className="type-badge">
                      {
                        asset.type
                      }
                    </span>

                  </td>


                  <td>
                    {
                      asset.ownerID
                    }
                  </td>


                  <td>
                    {money(
                      asset.value
                    )}
                  </td>

                  <td>{Number(asset.quantity || 1)}</td>


                  <td>

                    <span
                      className={`status ${
                        asset.status
                          ?.toLowerCase() ||
                        ""
                      }`}
                    >
                      {
                        asset.status
                      }
                    </span>

                  </td>


                  <td>
                    →
                  </td>

                </tr>
              )
            )
          ) : (
            <tr>

              <td
                colSpan="7"
                className="empty"
              >
                Không tìm thấy tài sản
              </td>

            </tr>
          )}

        </tbody>

      </table>

    </div>
  );
}


/*
 * =====================================================
 * ASSET MODAL
 * =====================================================
 */

function AssetModal({
  initial,
  users,
  currentUser,
  isAdmin,
  isWarehouse,
  onCheckAssetId,
  onClose,
  onSave,
}) {
  const generateAssetId = () => {
    const timestamp = Date.now().toString(36).toUpperCase();
    const random = Math.random().toString(36).slice(2, 6).toUpperCase();
    return `AST-${timestamp}-${random}`;
  };

  const [form, setForm] = useState(() =>
    initial ? { ...initial, quantity: Number(initial.quantity || 1) } : {
      id: generateAssetId(),
      name: "",
      type: "Computer",
      ownerID: currentUser?.id || "",
      value: "",
      quantity: 1,
      status: "Active",
      serialNumber: "",
      description: "",
    }
  );

  useEffect(() => {
    if (initial) {
      setForm((previous) => ({
        ...previous,
        value: formatAssetValue(initial.value),
      }));
    }
  }, [initial]);

  const [assetIdStatus, setAssetIdStatus] = useState(
    initial ? "valid" : "idle"
  );
  const [assetIdChecking, setAssetIdChecking] = useState(false);

  useEffect(() => {
    if (initial) return;

    const id = form.id.trim();
    if (!id) {
      setAssetIdStatus("idle");
      return;
    }

    let cancelled = false;
    setAssetIdStatus("checking");

    const timer = setTimeout(async () => {
      try {
        setAssetIdChecking(true);
        const exists = await onCheckAssetId(id);
        if (cancelled) return;
        setAssetIdStatus(exists ? "taken" : "available");
      } catch (error) {
        console.error("Check asset ID error:", error);
        if (!cancelled) setAssetIdStatus("error");
      } finally {
        if (!cancelled) setAssetIdChecking(false);
      }
    }, 450);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [form.id, initial]);

  const regenerateId = () => {
    setForm((previous) => ({
      ...previous,
      id: generateAssetId(),
    }));
  };

  const idMessage =
    assetIdStatus === "taken"
      ? "Mã này đã tồn tại trên Blockchain"
      : assetIdStatus === "available"
      ? "Mã tài sản chưa được sử dụng"
      : assetIdStatus === "checking"
      ? "Đang kiểm tra trên Blockchain..."
      : assetIdStatus === "error"
      ? "Không thể kiểm tra mã tài sản"
      : "Mã được tạo tự động; bạn có thể thay đổi nếu muốn";

  return (
    <div className="modal-backdrop">

      <form
        className="modal"
        onSubmit={(event) => {
          event.preventDefault();

          if (!initial && assetIdStatus !== "available") {
            return;
          }

          onSave(form);
        }}
      >

        <h2>
          {initial
            ? "Chỉnh sửa tài sản"
            : "Thêm tài sản mới"}
        </h2>


        <label>
          Mã tài sản

          <div style={{ position: "relative" }}>
            <input
              required
              value={form.id}
              disabled={Boolean(initial)}
              onChange={(event) =>
                setForm({
                  ...form,
                  id: event.target.value.trimStart(),
                })
              }
              placeholder="AST-..."
              style={{
                paddingRight: initial ? "14px" : "48px",
                borderColor:
                  !initial && assetIdStatus === "taken"
                    ? "#ef4444"
                    : !initial && assetIdStatus === "available"
                    ? "#22c55e"
                    : undefined,
              }}
            />

            {!initial && form.id && assetIdStatus !== "checking" && (
              <span
                aria-label={assetIdStatus === "available" ? "Mã hợp lệ" : "Mã đã tồn tại"}
                title={idMessage}
                style={{
                  position: "absolute",
                  right: "14px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  fontSize: "22px",
                  fontWeight: 700,
                  color:
                    assetIdStatus === "available"
                      ? "#22c55e"
                      : assetIdStatus === "taken"
                      ? "#ef4444"
                      : "#f59e0b",
                }}
              >
                {assetIdStatus === "available" ? "✓" : "!"}
              </span>
            )}
          </div>

          {!initial && (
            <>
              <small
                style={{
                  display: "block",
                  marginTop: "6px",
                  color:
                    assetIdStatus === "taken"
                      ? "#ef4444"
                      : assetIdStatus === "available"
                      ? "#16a34a"
                      : "#6b7280",
                }}
              >
                {assetIdChecking ? "Đang kiểm tra trên Blockchain..." : idMessage}
              </small>

              <button
                type="button"
                className="secondary-button"
                onClick={regenerateId}
                style={{ marginTop: "8px" }}
              >
                ↻ Tạo mã tự động khác
              </button>
            </>
          )}

          {initial && (
            <small
              style={{ display: "block", marginTop: "6px", color: "#6b7280" }}
            >
              Mã tài sản không thể thay đổi khi chỉnh sửa.
            </small>
          )}
        </label>


        <label>
          Tên tài sản

          <input
            required
            value={form.name}
            onChange={(event) =>
              setForm({
                ...form,
                name:
                  event.target.value,
              })
            }
          />

        </label>


        <label>
          Loại

          <select
            value={form.type}
            onChange={(event) =>
              setForm({
                ...form,
                type:
                  event.target.value,
              })
            }
          >

            <option value="Computer">
              Computer
            </option>

            <option value="Phone">
              Phone
            </option>

            <option value="Vehicle">
              Vehicle
            </option>

            <option value="Other">
              Other
            </option>

          </select>

        </label>


        <label>
          Chủ sở hữu

          {isAdmin ? (
            <select
              required
              value={form.ownerID}
              onChange={(event) =>
                setForm({
                  ...form,
                  ownerID: event.target.value,
                })
              }
            >
              <option value="">
                -- Chọn người dùng --
              </option>

              <option value="STORE">Kho cửa hàng (STORE)</option>

              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.fullName || user.username || user.id} ({user.id})
                </option>
              ))}
            </select>
          ) : (
            <input
              value={
                isWarehouse
                  ? `Admin (${ADMIN_OWNER_ID})`
                  : currentUser
                  ? `${currentUser.fullName || currentUser.username} (${currentUser.id})`
                  : form.ownerID
              }
              disabled
              readOnly
            />
          )}

          {!isAdmin && (
            <small
              style={{
                display: "block",
                marginTop: "6px",
                color: "#6b7280",
              }}
            >
              {isWarehouse
                ? "Sản phẩm mới được ghi dưới tên Admin."
                : "Chủ sở hữu được khóa theo tài khoản đang đăng nhập."}
            </small>
          )}
        </label>

        <label>
          Số lượng
          <input
            required
            type="number"
            min="1"
            step="1"
            value={form.quantity}
            onChange={(event) => setForm({ ...form, quantity: event.target.value })}
          />
        </label>


        <label>
          Giá trị

          <div style={{ position: "relative" }}>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9.]*"
              value={form.value}
              onChange={(event) => {
                const formatted = formatAssetValue(event.target.value);

                setForm({
                  ...form,
                  value: formatted,
                });
              }}
              placeholder="Ví dụ: 30.000.000"
              style={{
                paddingRight: "58px",
              }}
            />

            <span
              style={{
                position: "absolute",
                right: "14px",
                top: "50%",
                transform: "translateY(-50%)",
                color: "#64748b",
                fontWeight: 600,
                pointerEvents: "none",
              }}
            >
              VNĐ
            </span>
          </div>

          <small
            style={{
              display: "block",
              marginTop: "6px",
              color: "#6b7280",
            }}
          >
            Tự động phân cách hàng nghìn bằng dấu chấm.
          </small>
        </label>


        <label>
          Trạng thái

          <select
            value={form.status}
            onChange={(event) =>
              setForm({
                ...form,
                status:
                  event.target.value,
              })
            }
          >

            <option value="Active">
              Active
            </option>

            <option value="Pending">
              Pending
            </option>

            <option value="Inactive">
              Inactive
            </option>

          </select>

        </label>


        <label>
          Serial Number

          <input
            value={
              form.serialNumber
            }
            onChange={(event) =>
              setForm({
                ...form,
                serialNumber:
                  event.target.value,
              })
            }
          />

        </label>


        <label>
          Mô tả

          <input
            value={
              form.description
            }
            onChange={(event) =>
              setForm({
                ...form,
                description:
                  event.target.value,
              })
            }
          />

        </label>


        <div className="modal-actions">

          <button
            type="button"
            className="secondary-button"
            onClick={onClose}
          >
            Hủy
          </button>


          <button
            className="primary-button"
            disabled={
              !initial &&
              (assetIdStatus === "taken" ||
                assetIdStatus === "checking" ||
                assetIdStatus === "error" ||
                !form.id.trim())
            }
          >
            Lưu tài sản
          </button>

        </div>

      </form>

    </div>
  );
}


/*
 * =====================================================
 * USER MODAL
 * =====================================================
 */

function UserModal({
  roles,
  initial,
  contactOnly,
  allowRoleEdit,
  onClose,
  onSave,
}) {
  const isEdit = Boolean(initial);
  const [form, setForm] = useState({
    id: initial?.id || "",
    username: initial?.username || "",
    password: "",
    fullName: initial?.fullName || "",
    role: normalizeRole(initial?.role) || roles[0] || "customer",
    contact: initial?.contact || "",
    contactOnly: Boolean(contactOnly),
  });

  return (
    <div className="modal-backdrop">
      <form
        className="modal"
        onSubmit={(event) => {
          event.preventDefault();
          onSave(form);
        }}
      >
        <h2>{contactOnly ? "Cập nhật SĐT/email" : isEdit ? "Sửa thông tin người dùng" : "Thêm người dùng"}</h2>

        {isEdit && (
          <label>
            Mã hệ thống
            <input value={form.id} disabled readOnly />
          </label>
        )}

        <label>
          SĐT/email
          <input
            value={form.contact}
            placeholder="Để trống sẽ dùng user_STT"
            onChange={(event) => setForm({ ...form, contact: event.target.value })}
          />
          {!isEdit && (
            <small className="muted">Mã hệ thống được tự động tạo theo dạng user_STT.</small>
          )}
        </label>

        {!contactOnly && (
          <>
            <label>
              Họ và tên
              <input
                required
                value={form.fullName}
                placeholder="Nguyễn Văn A"
                onChange={(event) => setForm({ ...form, fullName: event.target.value })}
              />
            </label>

            {!isEdit && (
              <>
                <label>
                  Username
                  <input
                    required
                    value={form.username}
                    placeholder="nguyenvana"
                    onChange={(event) => setForm({ ...form, username: event.target.value })}
                  />
                </label>
                <label>
                  Password
                  <input
                    required
                    type="password"
                    minLength={8}
                    autoComplete="new-password"
                    value={form.password}
                    placeholder="Tối thiểu 8 ký tự"
                    onChange={(event) => setForm({ ...form, password: event.target.value })}
                  />
                </label>
              </>
            )}

            <label>
              Vai trò
              <select
                value={form.role}
                disabled={isEdit && !allowRoleEdit}
                onChange={(event) => setForm({ ...form, role: event.target.value })}
              >
                {(isEdit && !roles.includes(form.role) ? [form.role, ...roles] : roles).map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABELS[role] || role}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>Hủy</button>
          <button className="primary-button">
            {isEdit ? "Lưu thay đổi" : "Tạo người dùng"}
          </button>
        </div>
      </form>
    </div>
  );
}


/*
 * =====================================================
 * TRANSFER MODAL
 * =====================================================
 */

function TransferModal({
  asset,
  users,
  currentRole,
  onClose,
  onSave,
}) {
  const isSales = currentRole === "sales";
  const isCustomer = currentRole === "customer";
  const availableUsers = users.filter((user) =>
    user.id !== asset?.ownerID &&
    (!isSales || normalizeRole(user.role) === "customer")
  );
  const [owner, setOwner] = useState(isCustomer ? "STORE" : "");
  const [quantity, setQuantity] = useState(1);
  const [showNewCustomer, setShowNewCustomer] = useState(false);
  const [customerForm, setCustomerForm] = useState({
    id: "",
    username: "",
    password: "",
    fullName: "",
    contact: "",
  });

  const generateSaleAssetId = () =>
    `SALE-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;

  const submit = (event) => {
    event.preventDefault();
    let selectedOwner = owner;
    if (isSales && showNewCustomer) {
      selectedOwner = "NEW_CUSTOMER";
    }
    if (!selectedOwner) return;
    onSave({
      ownerID: selectedOwner,
      quantity: isCustomer ? Number(asset?.quantity || 1) : Number(quantity),
      newAssetID: generateSaleAssetId(),
      newCustomer: isSales && showNewCustomer ? customerForm : null,
      recipient: isSales && showNewCustomer
        ? { ...customerForm, id: "Tự động", role: "CUSTOMER" }
        : null,
    });
  };

  return (
    <div className="modal-backdrop">
      <form className="modal" onSubmit={submit}>
        <h2>{isCustomer ? "Bán lại cho cửa hàng" : "Bán / chuyển quyền sở hữu"}</h2>
        <p className="muted">{asset?.name} ({asset?.id}) · Có {Number(asset?.quantity || 1)} sản phẩm</p>

        <label>
          Chủ sở hữu hiện tại
          <input disabled value={asset?.ownerID || ""} />
        </label>

        {isCustomer ? (
          <label>
            Bên mua lại
            <input disabled value="Kho cửa hàng (STORE)" />
          </label>
        ) : (
          <>
            <label>
              {isSales ? "Khách hàng" : "Chủ sở hữu mới"}
              <select
                required={!showNewCustomer}
                disabled={showNewCustomer}
                value={owner}
                onChange={(event) => setOwner(event.target.value)}
              >
                <option value="">-- Chọn người nhận --</option>
                {availableUsers.map((user) => (
                  <option key={user.id} value={user.id}>
                    {isSales
                      ? `${user.fullName || "Khách hàng"} (${ROLE_LABELS[normalizeRole(user.role)] || user.role})`
                      : `${user.fullName || user.username || user.id} (${user.id})`}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Số lượng bán/chuyển
              <input
                required
                type="number"
                min="1"
                max={Number(asset?.quantity || 1)}
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
              />
            </label>

            {isSales && (
              <label style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={showNewCustomer}
                  onChange={(event) => setShowNewCustomer(event.target.checked)}
                />
                Thêm khách hàng mới ngay khi bán
              </label>
            )}

            {isSales && showNewCustomer && (
              <div className="user-card">
                <input placeholder="SĐT/email (để trống sẽ dùng user_STT)" value={customerForm.contact} onChange={(event) => setCustomerForm({ ...customerForm, contact: event.target.value })} />
                <input required placeholder="Username" value={customerForm.username} onChange={(event) => setCustomerForm({ ...customerForm, username: event.target.value })} />
                <input required placeholder="Họ và tên" value={customerForm.fullName} onChange={(event) => setCustomerForm({ ...customerForm, fullName: event.target.value })} />
                <input required minLength={8} type="password" placeholder="Password tối thiểu 8 ký tự" value={customerForm.password} onChange={(event) => setCustomerForm({ ...customerForm, password: event.target.value })} />
              </div>
            )}
          </>
        )}

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>Hủy</button>
          <button className="primary-button" disabled={!isCustomer && !showNewCustomer && !owner}>
            {isCustomer ? "Xác nhận bán lại" : "Xác nhận bán/chuyển"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default App;
