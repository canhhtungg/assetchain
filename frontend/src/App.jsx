import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_URL =
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:5000";

const CHAINLAUNCH_URL =
  import.meta.env.VITE_CHAINLAUNCH_URL ||
  "http://127.0.0.1:8100/api/v1";

const CHAINCODE_ID =
  import.meta.env.VITE_CHAINCODE_ID || "1";

const KEY_ID =
  import.meta.env.VITE_KEY_ID || "6";

const CHAINLAUNCH_USER =
  import.meta.env.VITE_CHAINLAUNCH_USER || "admin";

const CHAINLAUNCH_PASSWORD =
  import.meta.env.VITE_CHAINLAUNCH_PASSWORD ||
  "1d45cc8f4f5a9cfa1e2a0575";


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

  const [transactions, setTransactions] =
    useState(() => {
      try {
        return (
          JSON.parse(
            localStorage.getItem(
              "assetchain-transactions"
            )
          ) || []
        );
      } catch {
        return [];
      }
    });

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

  const [currentUser, setCurrentUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("assetchain-session")) || null;
    } catch {
      return null;
    }
  });

  const [loginUsername, setLoginUsername] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

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

  const isAdmin = currentUser?.role?.toLowerCase() === "admin";
  const isUser = currentUser?.role?.toLowerCase() === "user";

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

  useEffect(() => {
    localStorage.setItem(
      "assetchain-transactions",
      JSON.stringify(transactions)
    );
  }, [transactions]);


  /*
   * =====================================================
   * CHAINLAUNCH
   * =====================================================
   */

  const invokeChaincode = async (
    functionName,
    args = []
  ) => {
    const auth =
      "Basic " +
      btoa(
        `${CHAINLAUNCH_USER}:${CHAINLAUNCH_PASSWORD}`
      );

    const response = await fetch(
      `${CHAINLAUNCH_URL}/sc/fabric/chaincodes/${CHAINCODE_ID}/invoke`,
      {
        method: "POST",

        headers: {
          "Content-Type":
            "application/json",

          Authorization: auth,
        },

        body: JSON.stringify({
          key_id: String(KEY_ID),

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


  /*
   * =====================================================
   * LOAD ASSETS
   * =====================================================
   */

  const loadAssets = async () => {
    try {
      const data =
        await invokeChaincode(
          "GetAllAssets",
          []
        );

      const result =
        parseChaincodeResult(
          data,
          []
        );

      const blockchainAssets =
        Array.isArray(result)
          ? result
          : [];


      const formattedAssets =
        blockchainAssets.map(
          (asset) => ({
            ...asset,

            value: Number(
              asset.value || 0
            ),

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
      const data =
        await invokeChaincode(
          "GetAllUsers",
          []
        );

      const result =
        parseChaincodeResult(
          data,
          []
        );

      const blockchainUsers =
        Array.isArray(result)
          ? result
          : [];

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


  /*
   * =====================================================
   * NETWORK
   * =====================================================
   */

  const loadNetworks = async () => {
    try {
      const response =
        await fetch(
          `${API_URL}/api/fabric/networks`
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
    if (isAdmin) return assets;
    return assets.filter((asset) => asset.ownerID === currentUser?.id);
  }, [assets, currentUser, isAdmin]);

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


  /*
   * =====================================================
   * TRANSACTION HISTORY
   * =====================================================
   */

  const addTransaction = (action, asset, detail = "", meta = {}) => {
    setTransactions((previous) => [
      {
        id: "TX-" + Date.now(),
        action,
        assetID: asset.id,
        assetName: asset.name,
        ownerID: meta.ownerID || asset.ownerID || "",
        fromOwnerID: meta.fromOwnerID || "",
        toOwnerID: meta.toOwnerID || "",
        actorID: currentUser?.id || "",
        actorUsername: currentUser?.username || "",
        detail,
        time: new Date().toLocaleString("vi-VN"),
      },
      ...previous,
    ]);
  };


  /*
   * =====================================================
   * CREATE USER
   * =====================================================
   */

  const createUser =
    async (form) => {
      if (!isAdmin) {
        setNotice("Chỉ Admin mới có quyền tạo người dùng");
        return;
      }

      try {
        setLoading(true);

        await invokeChaincode(
          "CreateUser",
          [
            form.id.trim(),

            form.username.trim(),

            form.fullName.trim(),

            form.role,
          ]
        );

        await loadUsers();

        setNotice(
          `Đã tạo người dùng ${form.id} trên Blockchain`
        );

        setModal(null);
      } catch (error) {
        console.error(error);

        setNotice(
          `Lỗi Blockchain: ${error.message}`
        );
      } finally {
        setLoading(false);
      }
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
   * CREATE / UPDATE ASSET
   * =====================================================
   */

  const saveAsset = async (form) => {
    const isEdit = Boolean(editing);

    if (isEdit && !isAdmin && editing?.ownerID !== currentUser?.id) {
      setNotice("Bạn chỉ có thể chỉnh sửa tài sản của chính mình");
      return;
    }

    const ownerID = isAdmin ? form.ownerID?.trim() : currentUser?.id;

    const asset = {
      ...form,
      id: form.id?.trim() || `A${String(assets.length + 1).padStart(3, "0")}`,
      name: form.name.trim(),
      type: form.type,
      ownerID,
      value: parseAssetValue(form.value),
      status: form.status,
      serialNumber: form.serialNumber || "",
      description: form.description || "",
    };

    if (!asset.ownerID) {
      setNotice("Vui lòng chọn chủ sở hữu");
      return;
    }

    if (!users.some((user) => user.id === asset.ownerID)) {
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
        await invokeChaincode("UpdateAsset", [
          asset.id, asset.name, asset.type, asset.ownerID, asset.value,
          asset.status, asset.serialNumber, asset.description,
        ]);
      } else {
        await invokeChaincode("CreateAsset", [
          asset.id, asset.name, asset.type, asset.ownerID, asset.value,
          asset.status, asset.serialNumber, asset.description,
        ]);
      }

      await loadAssets();
      addTransaction(
        isEdit ? "Cập nhật tài sản" : "Thêm tài sản",
        asset,
        isEdit
          ? `Đã sửa thông tin tài sản • Chủ sở hữu: ${asset.ownerID}`
          : `Chủ sở hữu: ${asset.ownerID}`,
        { ownerID: asset.ownerID }
      );

      setNotice(
        isEdit
          ? "Đã cập nhật tài sản trên Blockchain"
          : "Đã thêm tài sản vào Blockchain"
      );
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

  const deleteAsset =
    async (asset) => {
      const isOwner = asset?.ownerID === currentUser?.id;

      // Admin được xóa mọi tài sản, User chỉ được xóa tài sản của chính mình.
      if (!isAdmin && !isOwner) {
        setNotice(
          "Bạn chỉ có thể xóa tài sản do chính mình sở hữu"
        );
        return;
      }

      if (
        !window.confirm(
          `Xóa tài sản ${asset.name}?\n\nThao tác này sẽ xóa tài sản khỏi Blockchain.`
        )
      ) {
        return;
      }

      try {
        setLoading(true);

        await invokeChaincode(
          "DeleteAsset",
          [
            asset.id,
          ]
        );

        await loadAssets();


        addTransaction(
          "Xóa tài sản",
          asset,
          `Chủ sở hữu: ${asset.ownerID}`,
          { ownerID: asset.ownerID }
        );


        setNotice(
          "Đã xóa tài sản khỏi Blockchain"
        );


        setSelected(null);
      } catch (error) {
        console.error(error);

        setNotice(
          `Lỗi Blockchain: ${error.message}`
        );
      } finally {
        setLoading(false);
      }
    };


  /*
   * =====================================================
   * TRANSFER ASSET
   * =====================================================
   */

  const transferAsset = async (ownerID) => {
    if (!selected) return;

    if (isUser && selected.ownerID !== currentUser?.id) {
      setNotice("Bạn chỉ có thể chuyển tài sản của chính mình");
      return;
    }

    if (!ownerID || ownerID === selected.ownerID) {
      setNotice("Vui lòng chọn User ID mới khác chủ sở hữu hiện tại");
      return;
    }

    if (!users.some((user) => user.id === ownerID)) {
      setNotice(`User ${ownerID} chưa tồn tại trên Blockchain`);
      return;
    }

    try {
      setLoading(true);
      const oldOwner = selected.ownerID;
      await invokeChaincode("TransferAsset", [selected.id, ownerID]);

      const updated = { ...selected, ownerID };
      await loadAssets();
      addTransaction(
        "Chuyển quyền sở hữu",
        updated,
        `${oldOwner} → ${ownerID}`,
        { fromOwnerID: oldOwner, toOwnerID: ownerID, ownerID }
      );
      setNotice("Đã chuyển quyền sở hữu trên Blockchain");
      setModal(null);
      setSelected(null);
    } catch (error) {
      console.error(error);
      setNotice(`Lỗi Blockchain: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const verifyTransferUser = async (userID) => {
    const normalizedID = userID?.trim();

    if (!normalizedID) {
      setNotice("Vui lòng nhập User ID người nhận");
      return null;
    }

    if (normalizedID === selected?.ownerID) {
      setNotice("Không thể chuyển tài sản cho chính chủ sở hữu hiện tại");
      return null;
    }

    try {
      setLoading(true);
      const data = await invokeChaincode("GetUser", [normalizedID]);
      const result = parseChaincodeResult(data, null);
      if (!result || Array.isArray(result) || !result.id) {
        throw new Error(`User ${normalizedID} không tồn tại`);
      }
      return result;
    } catch (error) {
      console.error(error);
      setNotice(`Không tìm thấy người dùng: ${error.message}`);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const login = async () => {
    const username = loginUsername.trim();
    if (!username) {
      setNotice("Vui lòng nhập username");
      return;
    }

    try {
      setLoginLoading(true);
      const data = await invokeChaincode("GetAllUsers", []);
      const result = parseChaincodeResult(data, []);
      const userList = Array.isArray(result) ? result : [];
      setUsers(userList);

      const user = userList.find(
        (item) => item.username?.trim().toLowerCase() === username.toLowerCase()
      );

      if (!user) {
        setNotice("Username không tồn tại trên Blockchain");
        return;
      }

      setCurrentUser(user);
      localStorage.setItem("assetchain-session", JSON.stringify(user));
      setLoginUsername("");
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

          <button
            className="primary-button"
            onClick={() => {
              setEditing(null);

              setModal("asset");
            }}
          >
            ＋ Thêm tài sản
          </button>
        </div>


        <div className="stats">
          <Stat
            icon="📦"
            tone="blue"
            label="Tổng tài sản"
            value={visibleAssets.length}
            small={`${activeCount} đang hoạt động`}
          />

          <Stat
            icon="👥"
            tone="green"
            label={isAdmin ? "Người dùng" : "Tài khoản"}
            value={isAdmin ? users.length : 1}
            small={isAdmin ? "Quản lý trên Blockchain" : "Tài khoản hiện tại"}
          />

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

            <button
              className="primary-button"
              onClick={() => {
                setEditing(null);

                setModal("asset");
              }}
            >
              ＋ Thêm tài sản
            </button>
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
      if (!isAdmin) return null;
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

          <button
            className="primary-button"
            onClick={() =>
              setModal("user")
            }
          >
            ＋ Thêm người dùng
          </button>
        </div>


        <div className="simple-grid">
          {users.length ? (
            users.map(
              (user) => (
                <div
                  className="user-card"
                  key={user.id}
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

                    <span>
                      ID: {user.id}
                    </span>

                    <span>
                      Username:{" "}
                      {user.username}
                    </span>

                    <span>
                      Role: {user.role}
                    </span>

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


  // User chỉ được xem giao dịch có liên quan trực tiếp đến chính mình.
  // KHÔNG lọc theo assetID vì hai User có thể đã từng nhập trùng mã tài sản
  // trong lịch sử cũ; lọc theo assetID sẽ làm lộ giao dịch của người khác.
  const visibleTransactions = useMemo(() => {
    if (isAdmin) return transactions;

    const userID = currentUser?.id;
    if (!userID) return [];

    return transactions.filter((transaction) =>
      transaction.actorID === userID ||
      transaction.ownerID === userID ||
      transaction.fromOwnerID === userID ||
      transaction.toOwnerID === userID
    );
  }, [transactions, currentUser, isAdmin]);

  /*
   * =====================================================
   * TRANSACTIONS PAGE
   * =====================================================
   */

  const renderTransactions =
    () => (
      <>
        <div className="page-toolbar">
          <div>
            <h2>
              Lịch sử giao dịch
            </h2>

            <p>
              Các thao tác thực hiện từ ứng dụng
            </p>
          </div>
        </div>


        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>MÃ</th>
                <th>THAO TÁC</th>
                <th>TÀI SẢN</th>
                <th>CHI TIẾT</th>
                <th>THỜI GIAN</th>
              </tr>
            </thead>

            <tbody>
              {visibleTransactions.length ? (
                visibleTransactions.map(
                  (transaction) => (
                    <tr
                      key={
                        transaction.id
                      }
                    >
                      <td>
                        {
                          transaction.id
                        }
                      </td>

                      <td>
                        {
                          transaction.action
                        }
                      </td>

                      <td>
                        {
                          transaction.assetName
                        }{" "}
                        <small>
                          (
                          {
                            transaction.assetID
                          }
                          )
                        </small>
                      </td>

                      <td>
                        {
                          transaction.detail ||
                          "-"
                        }
                      </td>

                      <td>
                        {
                          transaction.time
                        }
                      </td>
                    </tr>
                  )
                )
              ) : (
                <tr>
                  <td
                    colSpan="5"
                    className="empty"
                  >
                    Chưa có giao dịch nào
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
            label="ChainLaunch API"
            value={CHAINLAUNCH_URL}
          />

          <Setting
            label="Chaincode"
            value={`assetcc (ID: ${CHAINCODE_ID})`}
          />

          <Setting
            label="Key ID"
            value={KEY_ID}
          />

          <Setting
            label="Backend API"
            value={API_URL}
          />

          <Setting
            label="Tài khoản hiện tại"
            value={currentUser?.username || "-"}
          />

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

          <h1 className="login-title" style={{ marginBottom: "8px" }}>Đăng nhập</h1>
          <p className="login-subtitle muted" style={{ marginBottom: "24px" }}>
            Đăng nhập bằng username được lưu trên Hyperledger Fabric
          </p>

          <label>
            Username
            <input
              autoFocus
              required
              value={loginUsername}
              onChange={(event) => setLoginUsername(event.target.value)}
              placeholder="Nhập username"
            />
          </label>

          <button
            className="primary-button"
            type="submit"
            disabled={loginLoading}
            style={{ width: "100%", marginTop: "20px" }}
          >
            {loginLoading ? "Đang kiểm tra Blockchain..." : "Đăng nhập"}
          </button>

          <p className="muted" style={{ marginTop: "18px", fontSize: "13px", textAlign: "center" }}>
            Demo: username được xác thực trực tiếp từ Blockchain.
          </p>
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
            ["assets", "▤", "Tài sản"],
            ...(isAdmin ? [["users", "♙", "Người dùng"]] : []),
            ["transactions", "◷", "Lịch sử giao dịch"],
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
                {isAdmin ? "Administrator" : "User"}
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
            (isAdmin ? renderUsers() : null)}

          {page === "transactions" &&
            renderTransactions()}

          {page === "settings" &&
            renderSettings()}

        </section>

      </main>


      {modal === "asset" && (
        <AssetModal
          initial={editing}
          users={users}
          currentUser={currentUser}
          isAdmin={isAdmin}
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
          onClose={() =>
            setModal(null)
          }
          onSave={createUser}
        />
      )}


      {modal === "transfer" && (
        <TransferModal
          asset={selected}
          users={users}
          isAdmin={isAdmin}
          currentUser={currentUser}
          onVerifyUser={verifyTransferUser}
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

                {(isAdmin || selected.ownerID === currentUser?.id) && (
                  <button
                    className="primary-button"
                    onClick={() => setModal("transfer")}
                  >
                    Chuyển quyền
                  </button>
                )}

                {(isAdmin || selected.ownerID === currentUser?.id) && (
                  <button
                    className="secondary-button"
                    onClick={() => {
                      if (!isAdmin && selected.ownerID !== currentUser?.id) {
                        setNotice("Bạn chỉ có thể chỉnh sửa tài sản của chính mình");
                        return;
                      }

                      setEditing(selected);
                      setSelected(null);
                      setModal("asset");
                    }}
                  >
                    Chỉnh sửa
                  </button>
                )}

                {(isAdmin || selected.ownerID === currentUser?.id) && (
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
                colSpan="6"
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
    initial || {
      id: generateAssetId(),
      name: "",
      type: "Computer",
      ownerID: currentUser?.id || "",
      value: "",
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

              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.fullName || user.username || user.id} ({user.id})
                </option>
              ))}
            </select>
          ) : (
            <input
              value={
                currentUser
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
              Chủ sở hữu được khóa theo tài khoản đang đăng nhập.
            </small>
          )}
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
  onClose,
  onSave,
}) {
  const [
    form,
    setForm,
  ] = useState({
    id: "",
    username: "",
    fullName: "",
    role: "user",
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

        <h2>
          Thêm người dùng
        </h2>


        <label>
          User ID

          <input
            required
            value={form.id}
            placeholder="user01"
            onChange={(event) =>
              setForm({
                ...form,
                id:
                  event.target.value,
              })
            }
          />

        </label>


        <label>
          Username

          <input
            required
            value={form.username}
            placeholder="nguyenvana"
            onChange={(event) =>
              setForm({
                ...form,
                username:
                  event.target.value,
              })
            }
          />

        </label>


        <label>
          Họ và tên

          <input
            required
            value={form.fullName}
            placeholder="Nguyen Van A"
            onChange={(event) =>
              setForm({
                ...form,
                fullName:
                  event.target.value,
              })
            }
          />

        </label>


        <label>
          Vai trò

          <select
            value={form.role}
            onChange={(event) =>
              setForm({
                ...form,
                role:
                  event.target.value,
              })
            }
          >

            <option value="user">
              User
            </option>

            <option value="admin">
              Admin
            </option>

          </select>

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
          >
            Tạo người dùng
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
  isAdmin,
  currentUser,
  onVerifyUser,
  onClose,
  onSave,
}) {
  const [owner, setOwner] = useState("");
  const [targetID, setTargetID] = useState("");
  const [targetUser, setTargetUser] = useState(null);
  const [verifying, setVerifying] = useState(false);

  const availableUsers = users.filter((user) => user.id !== asset?.ownerID);

  const verifyUser = async () => {
    setVerifying(true);
    const result = await onVerifyUser(targetID);
    setTargetUser(result);
    setVerifying(false);
  };

  return (
    <div className="modal-backdrop">
      <form
        className="modal"
        onSubmit={(event) => {
          event.preventDefault();
          if (isAdmin) onSave(owner);
          else if (targetUser) onSave(targetUser.id);
        }}
      >
        <h2>Chuyển quyền sở hữu</h2>

        <p className="muted">
          {asset?.name} ({asset?.id})
        </p>

        <label>
          Chủ sở hữu hiện tại
          <input disabled value={asset?.ownerID || ""} />
        </label>

        {isAdmin ? (
          <label>
            Chủ sở hữu mới
            <select
              required
              value={owner}
              onChange={(event) => setOwner(event.target.value)}
            >
              <option value="">-- Chọn người dùng --</option>
              {availableUsers.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.fullName || user.username || user.id} ({user.id})
                </option>
              ))}
            </select>
          </label>
        ) : (
          <>
            <label>
              User ID người nhận
              <div style={{ display: "flex", gap: "8px" }}>
                <input
                  required
                  value={targetID}
                  onChange={(event) => {
                    setTargetID(event.target.value);
                    setTargetUser(null);
                  }}
                  placeholder="Ví dụ: user01"
                />
                <button
                  type="button"
                  className="secondary-button"
                  onClick={verifyUser}
                  disabled={verifying}
                >
                  {verifying ? "Đang kiểm tra..." : "Kiểm tra"}
                </button>
              </div>
            </label>

            {targetUser && (
              <div className="user-card">
                <div className="avatar">
                  {(targetUser.fullName || targetUser.id).slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <strong>{targetUser.fullName || targetUser.id}</strong>
                  <span>ID: {targetUser.id}</span>
                  <span>Username: {targetUser.username}</span>
                  <span>Role: {targetUser.role}</span>
                </div>
              </div>
            )}
          </>
        )}

        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            Hủy
          </button>

          <button className="primary-button" disabled={!isAdmin && !targetUser}>
            Xác nhận chuyển
          </button>
        </div>
      </form>
    </div>
  );
}

export default App;
