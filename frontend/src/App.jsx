import { useEffect, useState } from "react";
import "./App.css";

const API_URL = "http://localhost:8080";
function App() {
const [asset, setAsset] = useState(null);
const [loading, setLoading] = useState(true);
const [error, setError] = useState("");

useEffect(() => {
  fetch(`${API_URL}/api/assets/A001`)
    .then((response) => {
      if (!response.ok) {
        throw new Error("Không thể lấy dữ liệu tài sản");
      }

      return response.json();
    })
    .then((data) => {
      console.log("Dữ liệu từ Backend:", data);
      setAsset(data.asset);
    })
    .catch((err) => {
      console.error("API ERROR:", err);
      setError(err.message);
    })
    .finally(() => {
      setLoading(false);
    });
}, []);
  return (
    <div className="app">

      {/* SIDEBAR */}
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

          <div className="menu-item active">
            <span className="menu-icon">▣</span>
            <span>Dashboard</span>
          </div>

          <div className="menu-item">
            <span className="menu-icon">▤</span>
            <span>Tài sản</span>
          </div>

          <div className="menu-item">
            <span className="menu-icon">♙</span>
            <span>Người dùng</span>
          </div>

          <div className="menu-item">
            <span className="menu-icon">◷</span>
            <span>Lịch sử giao dịch</span>
          </div>

        </nav>

        <div className="menu-title system-title">
          HỆ THỐNG
        </div>

        <div className="menu-item">
          <span className="menu-icon">⚙</span>
          <span>Cài đặt</span>
        </div>

        <div className="sidebar-bottom">

          <div className="network-status">

            <div className="status-dot"></div>

            <div>
              <div className="network-name">
                Fabric Network
              </div>

              <div className="network-online">
                ● Online
              </div>
            </div>

          </div>

        </div>

      </aside>


      {/* MAIN */}
      <main className="main">
	{error && (
	  <div className="error-message">
	    {error}
	  </div>
	)}
        {/* HEADER */}
        <header className="header">

          <div>
            <h1>
              Dashboard
            </h1>

            <p>
              Tổng quan hệ thống quản lý tài sản
            </p>
          </div>

          <div className="header-right">

            <button className="icon-button">
              🔔
              <span className="notification"></span>
            </button>

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

          </div>

        </header>


        {/* CONTENT */}
        <section className="content">

          {/* WELCOME */}
          <div className="welcome">

            <div>

              <h2>
                Xin chào, Canh Tung 👋
              </h2>

              <p>
                Theo dõi và quản lý tài sản trên Blockchain
              </p>

            </div>

            <button className="primary-button">
              <span>＋</span>
              Thêm tài sản
            </button>

          </div>


          {/* STATISTICS */}
          <div className="stats">

            <div className="stat-card">

              <div className="stat-icon blue">
                📦
              </div>

              <div className="stat-info">

                <span>
                  Tổng tài sản
                </span>

                <strong>
                  24
                </strong>

                <small>
                  ↗ 12% so với tháng trước
                </small>

              </div>

            </div>


            <div className="stat-card">

              <div className="stat-icon green">
                👥
              </div>

              <div className="stat-info">

                <span>
                  Người dùng
                </span>

                <strong>
                  12
                </strong>

                <small>
                  ↗ 8% so với tháng trước
                </small>

              </div>

            </div>


            <div className="stat-card">

              <div className="stat-icon purple">
                ↗
              </div>

              <div className="stat-info">

                <span>
                  Giao dịch
                </span>

                <strong>
                  86
                </strong>

                <small>
                  18 giao dịch hôm nay
                </small>

              </div>

            </div>


            <div className="stat-card">

              <div className="stat-icon orange">
                🛡
              </div>

              <div className="stat-info">

                <span>
                  Blockchain
                </span>

                <strong className="online-text">
                  Online
                </strong>

                <small>
                  Fabric Network
                </small>

              </div>

            </div>

          </div>


          {/* ASSET TYPES */}
          <div className="section-header">

            <div>

              <h2>
                Phân loại tài sản
              </h2>

              <p>
                Thống kê theo loại thiết bị
              </p>

            </div>

            <button className="view-all">
              Xem tất cả →
            </button>

          </div>


          <div className="asset-types">

            {/* COMPUTER */}
            <div className="asset-type-card">

              <div className="asset-type-icon computer">
                💻
              </div>

              <div>

                <span>
                  Máy tính
                </span>

                <strong>
                  10
                </strong>

              </div>

              <div className="percentage">
                42%
              </div>

            </div>


            {/* PHONE */}
            <div className="asset-type-card">

              <div className="asset-type-icon phone">
                📱
              </div>

              <div>

                <span>
                  Điện thoại
                </span>

                <strong>
                  8
                </strong>

              </div>

              <div className="percentage">
                33%
              </div>

            </div>


            {/* VEHICLE */}
            <div className="asset-type-card">

              <div className="asset-type-icon vehicle">
                🚗
              </div>

              <div>

                <span>
                  Phương tiện
                </span>

                <strong>
                  6
                </strong>

              </div>

              <div className="percentage">
                25%
              </div>

            </div>

          </div>


          {/* RECENT ASSETS */}
          <div className="section-header recent-header">

            <div>

              <h2>
                Tài sản gần đây
              </h2>

              <p>
                Danh sách tài sản mới được cập nhật
              </p>

            </div>

            <div className="search-box">

              <span>
                🔍
              </span>

              <input
                type="text"
                placeholder="Tìm kiếm tài sản..."
              />

            </div>

          </div>


          {/* TABLE */}
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

                  <th>
                  </th>

                </tr>

              </thead>


              <tbody>

                {/* ASSET 1 */}
                <tr>

                  <td>

                    <div className="asset-name">

                      <div className="table-icon">
                        💻
                      </div>

                      <div>

                        <strong>
			  {loading ? "Đang tải..." : asset?.name || "Không có dữ liệu"}
			</strong>

			<span>
			  {asset?.id || "A001"}
			</span>

                      </div>

                    </div>

                  </td>

                  <td>

                    <span className="type-badge">
                      Computer
                    </span>

                  </td>

                 <td>
		  {asset?.ownerID || "-"}
		</td>

                  <td>
		  {asset?.value
		    ? `${asset.value.toLocaleString("vi-VN")} ₫`
		    : "-"}
		</td>

                  <td>

                    <span className={`status ${asset?.status?.toLowerCase() || ""}`}>
			  {asset?.status || "-"}
			</span>

                  </td>

                  <td>
                    →
                  </td>

                </tr>


                {/* ASSET 2 */}
                <tr>

                  <td>

                    <div className="asset-name">

                      <div className="table-icon phone-bg">
                        📱
                      </div>

                      <div>

                        <strong>
                          iPhone 15 Pro cua CanhTung
                        </strong>

                        <span>
                          A002
                        </span>

                      </div>

                    </div>

                  </td>

                  <td>

                    <span className="type-badge">
                      Phone
                    </span>

                  </td>

                  <td>
                    Nguyen Van A
                  </td>

                  <td>
                    25,000,000 ₫
                  </td>

                  <td>

                    <span className="status active">
                      Active
                    </span>

                  </td>

                  <td>
                    →
                  </td>

                </tr>


                {/* ASSET 3 */}
                <tr>

                  <td>

                    <div className="asset-name">

                      <div className="table-icon vehicle-bg">
                        🚗
                      </div>

                      <div>

                        <strong>
                          Honda Vision
                        </strong>

                        <span>
                          A003
                        </span>

                      </div>

                    </div>

                  </td>

                  <td>

                    <span className="type-badge">
                      Vehicle
                    </span>

                  </td>

                  <td>
                    Canh Tung
                  </td>

                  <td>
                    35,000,000 ₫
                  </td>

                  <td>

                    <span className="status pending">
                      Pending
                    </span>

                  </td>

                  <td>
                    →
                  </td>

                </tr>

              </tbody>

            </table>

          </div>

        </section>

      </main>

    </div>
  );
}

export default App;
