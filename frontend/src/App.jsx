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
    loadAll();
  }, []);


  /*
   * =====================================================
   * FILTER ASSETS
   * =====================================================
   */

  const filteredAssets =
    useMemo(() => {
      return assets.filter(
        (asset) =>
          [
            asset.id,
            asset.name,
            asset.type,
            asset.ownerID,
            asset.status,
          ]
            .join(" ")
            .toLowerCase()
            .includes(
              query.toLowerCase()
            )
      );
    }, [
      assets,
      query,
    ]);


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

      assets.forEach(
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
    }, [assets]);


  const activeCount =
    assets.filter(
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

  const addTransaction = (
    action,
    asset,
    detail = ""
  ) => {
    setTransactions(
      (previous) => [
        {
          id:
            "TX-" +
            Date.now(),

          action,

          assetID:
            asset.id,

          assetName:
            asset.name,

          detail,

          time:
            new Date().toLocaleString(
              "vi-VN"
            ),
        },

        ...previous,
      ]
    );
  };


  /*
   * =====================================================
   * CREATE USER
   * =====================================================
   */

  const createUser =
    async (form) => {
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
   * CREATE / UPDATE ASSET
   * =====================================================
   */

  const saveAsset =
    async (form) => {
      const isEdit =
        Boolean(editing);

      const asset = {
        ...form,

        id:
          form.id?.trim() ||
          `A${String(
            assets.length + 1
          ).padStart(3, "0")}`,

        name:
          form.name.trim(),

        type:
          form.type,

        ownerID:
          form.ownerID.trim(),

        value:
          Number(
            form.value || 0
          ),

        status:
          form.status,

        serialNumber:
          form.serialNumber || "",

        description:
          form.description || "",
      };


      if (!asset.ownerID) {
        setNotice(
          "Vui lòng chọn chủ sở hữu"
        );

        return;
      }


      const ownerExists =
        users.some(
          (user) =>
            user.id ===
            asset.ownerID
        );


      if (!ownerExists) {
        setNotice(
          `User ${asset.ownerID} chưa tồn tại trên Blockchain`
        );

        return;
      }


      try {
        setLoading(true);

        if (isEdit) {
          await invokeChaincode(
            "UpdateAsset",
            [
              asset.id,

              asset.name,

              asset.type,

              asset.ownerID,

              asset.value,

              asset.status,

              asset.serialNumber,

              asset.description,
            ]
          );
        } else {
          await invokeChaincode(
            "CreateAsset",
            [
              asset.id,

              asset.name,

              asset.type,

              asset.ownerID,

              asset.value,

              asset.status,

              asset.serialNumber,

              asset.description,
            ]
          );
        }


        await loadAssets();


        addTransaction(
          isEdit
            ? "Cập nhật tài sản"
            : "Thêm tài sản",

          asset,

          `Chủ sở hữu: ${asset.ownerID}`
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

        setNotice(
          `Lỗi Blockchain: ${error.message}`
        );
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
      if (
        !window.confirm(
          `Xóa tài sản ${asset.name}?`
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
          asset
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

  const transferAsset =
    async (ownerID) => {
      if (!selected) {
        return;
      }


      if (
        !ownerID ||
        ownerID ===
          selected.ownerID
      ) {
        setNotice(
          "Vui lòng chọn chủ sở hữu mới"
        );

        return;
      }


      const ownerExists =
        users.some(
          (user) =>
            user.id === ownerID
        );


      if (!ownerExists) {
        setNotice(
          `User ${ownerID} chưa tồn tại trên Blockchain`
        );

        return;
      }


      try {
        setLoading(true);

        const oldOwner =
          selected.ownerID;


        await invokeChaincode(
          "TransferAsset",
          [
            selected.id,
            ownerID,
          ]
        );


        await loadAssets();


        const updated = {
          ...selected,
          ownerID,
        };


        setSelected(
          updated
        );


        addTransaction(
          "Chuyển quyền sở hữu",
          updated,
          `${oldOwner} → ${ownerID}`
        );


        setNotice(
          "Đã chuyển quyền sở hữu trên Blockchain"
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
   * DASHBOARD
   * =====================================================
   */

  const renderDashboard =
    () => (
      <>
        <div className="welcome">
          <div>
            <h2>
              Xin chào, Canh Tung 👋
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
            value={assets.length}
            small={`${activeCount} đang hoạt động`}
          />

          <Stat
            icon="👥"
            tone="green"
            label="Người dùng"
            value={users.length}
            small="Quản lý trên Blockchain"
          />

          <Stat
            icon="↗"
            tone="purple"
            label="Giao dịch"
            value={transactions.length}
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
          assets={assets.slice(0, 6)}
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
    () => (
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
              {transactions.length ? (
                transactions.map(
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
            label="Blockchain Users"
            value={`${users.length} users`}
          />


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

  return (
    <div className="app">

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
            [
              "dashboard",
              "▣",
              "Dashboard",
            ],

            [
              "assets",
              "▤",
              "Tài sản",
            ],

            [
              "users",
              "♙",
              "Người dùng",
            ],

            [
              "transactions",
              "◷",
              "Lịch sử giao dịch",
            ],
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
              CT
            </div>

            <div>

              <div className="user-name">
                Canh Tung
              </div>

              <div className="user-role">
                Administrator
              </div>

            </div>

          </div>

        </header>


        <section className="content">

          {notice && (
            <div className="notice">

              {notice}

              <button
                onClick={() =>
                  setNotice("")
                }
              >
                ×
              </button>

            </div>
          )}


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
            renderUsers()}

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
          onClose={() =>
            setModal(null)
          }
          onSave={transferAsset}
        />
      )}


      {selected &&
        page === "assets" && (
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

                <button
                  className="primary-button"
                  onClick={() =>
                    setModal(
                      "transfer"
                    )
                  }
                >
                  Chuyển quyền
                </button>


                <button
                  className="secondary-button"
                  onClick={() => {
                    setEditing(
                      selected
                    );

                    setSelected(
                      null
                    );

                    setModal(
                      "asset"
                    );
                  }}
                >
                  Chỉnh sửa
                </button>


                <button
                  className="danger-button"
                  onClick={() =>
                    deleteAsset(
                      selected
                    )
                  }
                >
                  Xóa
                </button>

              </div>

            </aside>

          </div>
        )}

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
  onClose,
  onSave,
}) {
  const [
    form,
    setForm,
  ] = useState(
    initial || {
      id: "",
      name: "",
      type: "Computer",
      ownerID: "",
      value: "",
      status: "Active",
      serialNumber: "",
      description: "",
    }
  );


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
          {initial
            ? "Cập nhật tài sản"
            : "Thêm tài sản mới"}
        </h2>


        <label>
          Mã tài sản

          <input
            required
            value={form.id}
            disabled={
              Boolean(initial)
            }
            onChange={(event) =>
              setForm({
                ...form,
                id:
                  event.target.value,
              })
            }
            placeholder="A004"
          />

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

          <select
            required
            value={form.ownerID}
            onChange={(event) =>
              setForm({
                ...form,
                ownerID:
                  event.target.value,
              })
            }
          >

            <option value="">
              -- Chọn người dùng --
            </option>

            {users.map(
              (user) => (
                <option
                  key={user.id}
                  value={user.id}
                >
                  {user.fullName ||
                    user.username ||
                    user.id}{" "}
                  ({user.id})
                </option>
              )
            )}

          </select>

        </label>


        <label>
          Giá trị

          <input
            type="number"
            min="0"
            value={form.value}
            onChange={(event) =>
              setForm({
                ...form,
                value:
                  event.target.value,
              })
            }
          />

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
  onClose,
  onSave,
}) {
  const [
    owner,
    setOwner,
  ] = useState("");


  const availableUsers =
    users.filter(
      (user) =>
        user.id !==
        asset?.ownerID
    );


  return (
    <div className="modal-backdrop">

      <form
        className="modal"
        onSubmit={(event) => {
          event.preventDefault();

          onSave(owner);
        }}
      >

        <h2>
          Chuyển quyền sở hữu
        </h2>


        <p className="muted">
          {asset?.name} ({asset?.id})
        </p>


        <label>
          Chủ sở hữu hiện tại

          <input
            disabled
            value={
              asset?.ownerID ||
              ""
            }
          />

        </label>


        <label>
          Chủ sở hữu mới

          <select
            required
            value={owner}
            onChange={(event) =>
              setOwner(
                event.target.value
              )
            }
          >

            <option value="">
              -- Chọn người dùng --
            </option>

            {availableUsers.map(
              (user) => (
                <option
                  key={user.id}
                  value={user.id}
                >
                  {user.fullName ||
                    user.username ||
                    user.id}{" "}
                  ({user.id})
                </option>
              )
            )}

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
            Xác nhận chuyển
          </button>

        </div>

      </form>

    </div>
  );
}


export default App;
