import React, { useEffect, useState } from "react";
import { api, request } from "./api";
import { MasterEditor, canManage, management } from "./MasterData";
import { InventoryOperations } from "./InventoryOperations";
const pages = {
  operations: { title: "Inventory Operations", subtitle: "Register, receive, transfer, issue and return equipment", icon: "+" },
  dashboard: {
    title: "Overview",
    subtitle: "A clear view of your warehouse",
    icon: "◫",
  },
  assets: {
    title: "Assets",
    subtitle: "Track serialized equipment across your warehouses",
    icon: "▣",
    path: "inventory/assets",
    permission: "inventory.view_asset",
    columns: [
      "asset_tag",
      "device_name",
      "product_name",
      "condition",
      "lifecycle_status",
      "location_name",
    ],
  },
  categories: {
    title: "Categories",
    subtitle: "Browse your equipment taxonomy",
    icon: "▦",
    path: "inventory/categories",
    permission: "inventory.view_assetcategory",
    columns: ["code", "name", "description", "is_active"],
  },
  manufacturers: {
    title: "Manufacturers",
    subtitle: "The makers behind your equipment",
    icon: "◇",
    path: "inventory/manufacturers",
    permission: "inventory.view_manufacturer",
    columns: ["code", "name", "description", "is_active"],
  },
  products: {
    title: "Product Models",
    subtitle: "Explore the serialized and bulk catalog",
    icon: "▤",
    path: "inventory/product-models",
    permission: "inventory.view_productmodel",
    columns: [
      "sku_code",
      "name",
      "category_name",
      "manufacturer_name",
      "tracking_mode",
    ],
  },
  warehouses: {
    title: "Warehouses",
    subtitle: "Your sites and their storage spaces",
    icon: "⌂",
    path: "warehouses",
    permission: "warehouse.view_warehouse",
    columns: ["code", "name", "address", "is_active"],
  },
  locations: {
    title: "Storage Locations",
    subtitle: "Find areas, racks, shelves and bins",
    icon: "⌖",
    path: "locations",
    permission: "warehouse.view_storagelocation",
    columns: ["code", "name", "warehouse_name", "kind", "parent_id"],
  },
};
const label = (key) =>
  key.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
const number = (value) => Number(value ?? 0).toLocaleString();
function State({ error, loading, children, retry }) {
  if (loading)
    return (
      <div className="state" role="status">
        <span className="spinner" />
        Loading workspace…
      </div>
    );
  if (error)
    return (
      <div className="state error" role="alert">
        <strong>Unable to load this view</strong>
        <p>{error}</p>
        {retry && <button onClick={retry}>Try again</button>}
      </div>
    );
  return children;
}
function Login({ onLogin }) {
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await api.login(username, password);
      setPassword("");
      onLogin(data.user);
    } catch (e) {
      setError(e.message);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-layout">
      <aside className="login-brand">
        <div className="brand-mark">W</div>
        <span className="eyebrow">IT WAREHOUSE</span>
        <h1>
          Everything in
          <br />
          its right place.
        </h1>
        <p>
          One workspace for your equipment,
          <br />
          catalog and warehouse locations.
        </p>
        <div className="brand-grid" aria-hidden="true">
          {[1, 2, 3, 4, 5, 6].map((n) => (
            <span key={n} />
          ))}
        </div>
        <small>Equipment clarity. Operational confidence.</small>
      </aside>
      <main className="login-main">
        <form onSubmit={submit} className="login-card">
          <span className="eyebrow">YOUR WORKSPACE AWAITS</span>
          <h2>Welcome back</h2>
          <p className="muted">Sign in with your IT Warehouse account.</p>
          {error && (
            <p role="alert" className="notice error">
              {error}
            </p>
          )}
          <label htmlFor="username">Username</label>
          <input
            id="username"
            autoComplete="username"
            required
            maxLength={150}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={1024}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button className="primary" disabled={busy}>
            {busy ? "Signing in…" : "Sign in →"}
          </button>
          <p className="login-help">
            Need access? Contact your warehouse administrator.
          </p>
        </form>
        <small className="login-footer">
          IT Warehouse · Inventory workspace
        </small>
      </main>
    </div>
  );
}
function Dashboard() {
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    setData(null);
    setError("");
    request("/api/dashboard/summary/", { signal: c.signal })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [retry]);
  return (
    <State
      error={error}
      loading={!data && !error}
      retry={() => setRetry((x) => x + 1)}
    >
      {data && (
        <>
          <div className="summary-grid">
            {[
              ["Total assets", data.total_assets, "▣", "Serialized equipment"],
              ["Warehouses", data.total_warehouses, "⌂", "Registered sites"],
              [
                "Available stock",
                data.stock_totals.available,
                "▤",
                number(data.stock_totals.all) + " units across all states",
              ],
              [
                "Low-stock items",
                data.low_stock_count,
                "↘",
                "Below configured thresholds",
              ],
            ].map(([title, value, icon, caption]) => (
              <article className="summary-card" key={title}>
                <span className="metric-icon">{icon}</span>
                <p>{title}</p>
                <strong>{number(value)}</strong>
                <small>{caption}</small>
              </article>
            ))}
          </div>
          <div className="dashboard-grid">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Recent stock activity</h2>
                  <p className="muted">Latest permitted ledger entries</p>
                </div>
                <span className="pill">Read only</span>
              </div>
              {!data.recent_activity_permitted ? (
                <div className="state">
                  Your account does not have access to stock activity.
                </div>
              ) : !data.recent_activity.length ? (
                <div className="state">
                  <span className="empty-icon">↗</span>
                  <strong>No stock activity yet</strong>
                  <p>Recorded movements will appear here.</p>
                </div>
              ) : (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Movement</th>
                        <th>Quantity</th>
                        <th>Recorded</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_activity.map((row) => (
                        <tr key={row.id}>
                          <td>{label(row.operation_type.toLowerCase())}</td>
                          <td>{number(row.quantity)}</td>
                          <td>{new Date(row.recorded_at).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Stock watch</h2>
                  <p className="muted">Available bulk stock by site</p>
                </div>
              </div>
              {!data.low_stock.length ? (
                <div className="state">
                  <span className="empty-icon">✓</span>
                  <strong>No low-stock alerts</strong>
                  <p>Items below their configured minimum appear here.</p>
                </div>
              ) : (
                <ul className="alerts">
                  {data.low_stock.map((row) => (
                    <li key={row.product_model_id + "-" + row.warehouse_id}>
                      <strong>Product #{row.product_model_id}</strong>
                      <small>Warehouse #{row.warehouse_id}</small>
                      <span className="badge warning">
                        {number(row.available_quantity)} /{" "}
                        {number(row.minimum_quantity)} units
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="panel-foot">
                {number(data.total_categories)} catalog categories
              </div>
            </section>
          </div>
          <div className="workspace-note">
            ⓘ{" "}
            <p>
              This workspace provides inventory visibility. Stock posting and
              import review are not available here.
            </p>
          </div>
        </>
      )}
    </State>
  );
}
function Catalog({ page, config, initialWarehouse, user }) {
  const [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState(""),
    [warehouse, setWarehouse] = useState(initialWarehouse || ""),
    [sites, setSites] = useState([]),
    [index, setIndex] = useState(1),
    [data, setData] = useState(null),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0),
    [detail, setDetail] = useState(null),
    [editing, setEditing] = useState(null),
    [notice, setNotice] = useState("");
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(search);
      setIndex(1);
    }, 250);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    if (page !== "locations") return;
    const c = new AbortController();
    request("/api/warehouses/?page_size=100", { signal: c.signal })
      .then((x) => setSites(x.results))
      .catch(() => {});
    return () => c.abort();
  }, [page]);
  useEffect(() => {
    const c = new AbortController(),
      params = new URLSearchParams({ page: index, search: query });
    if (filter)
      params.set(
        page === "assets"
          ? "lifecycle_status"
          : page === "products"
            ? "tracking_mode"
            : "is_active",
        filter,
      );
    if (warehouse) params.set("warehouse", warehouse);
    setData(null);
    setError("");
    request("/api/" + config.path + "/?" + params, { signal: c.signal })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [page, config.path, index, query, filter, warehouse, retry]);
  async function open(id) {
    try {
      setDetail(await request("/api/" + config.path + "/" + id + "/"));
    } catch (e) {
      setError(e.message);
    }
  }
  return (
    <>
      {editing && (
        <MasterEditor
          page={page}
          id={editing.id}
          user={user}
          onClose={() => setEditing(null)}
          onSaved={(message) => {
            setEditing(null);
            setNotice(message);
            setRetry((x) => x + 1);
          }}
        />
      )}
      <div className="management-bar">
        {canManage(user, page, "add") && (
          <button
            className="primary"
            onClick={() => {
              setNotice("");
              setEditing({ id: null });
            }}
          >
            Register {management[page].singular}
          </button>
        )}
        {notice && (
          <p className="success-notice" role="status">
            {notice}
          </p>
        )}
      </div>
      <section className="panel">
        <div className="toolbar">
          <label className="search-field">
            <span aria-hidden="true">⌕</span>
            <input
              aria-label={"Search " + config.title}
              placeholder={"Search " + config.title.toLowerCase() + "…"}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          {["assets", "products"].includes(page) && (
            <select
              aria-label="Filter"
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setIndex(1);
              }}
            >
              <option value="">
                All {page === "assets" ? "statuses" : "tracking modes"}
              </option>
              {(page === "assets"
                ? ["AVAILABLE", "QUARANTINED", "ASSIGNED", "DISPOSED", "LOST"]
                : ["BULK", "SERIALIZED"]
              ).map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          )}
          {["categories", "manufacturers", "warehouses", "locations"].includes(
            page,
          ) && (
            <select
              aria-label="Record status"
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setIndex(1);
              }}
            >
              <option value="">All records</option>
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </select>
          )}
          {page === "locations" && (
            <select
              aria-label="Warehouse"
              value={warehouse}
              onChange={(e) => {
                setWarehouse(e.target.value);
                setIndex(1);
              }}
            >
              <option value="">All warehouses</option>
              {sites.map((w) => (
                <option value={w.id} key={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          )}
          <span className="pill">
            {canManage(user, page, "add") || canManage(user, page, "change")
              ? "Master data"
              : "Read only"}
          </span>
        </div>
        <State
          error={error}
          loading={!data && !error}
          retry={() => setRetry((x) => x + 1)}
        >
          {data &&
            (data.results.length ? (
              <>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        {config.columns.map((k) => (
                          <th key={k}>{label(k)}</th>
                        ))}
                        {["assets", "warehouses"].includes(page) && (
                          <th>Details</th>
                        )}
                        {canManage(user, page, "change") && <th>Manage</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {data.results.map((row) => (
                        <tr key={row.id}>
                          {config.columns.map((k) => (
                            <td key={k}>
                              {typeof row[k] === "boolean" ? (
                                <span className="badge">
                                  {row[k] ? "Active" : "Inactive"}
                                </span>
                              ) : k.includes("status") ||
                                k === "tracking_mode" ? (
                                <span className="badge">{row[k]}</span>
                              ) : (
                                (row[k] ?? "—")
                              )}
                            </td>
                          ))}
                          {page === "assets" && (
                            <td>
                              <button
                                className="text-button"
                                onClick={() => open(row.id)}
                              >
                                View asset
                              </button>
                            </td>
                          )}
                          {page === "warehouses" && (
                            <td>
                              <button
                                className="text-button"
                                onClick={() => open(row.id)}
                              >
                                View warehouse
                              </button>
                              {" / "}
                              <a href={"#/locations?warehouse=" + row.id}>
                                Browse locations →
                              </a>
                            </td>
                          )}
                          {canManage(user, page, "change") && (
                            <td>
                              <button
                                className="text-button"
                                onClick={() => {
                                  setNotice("");
                                  setEditing({ id: row.id });
                                }}
                              >
                                Edit {management[page].singular}
                              </button>
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <footer className="pagination">
                  <span>
                    {number(data.count)} {config.title.toLowerCase()} · Page{" "}
                    {index}
                  </span>
                  <div>
                    <button
                      disabled={!data.previous}
                      onClick={() => setIndex((x) => x - 1)}
                    >
                      Previous
                    </button>
                    <button
                      disabled={!data.next}
                      onClick={() => setIndex((x) => x + 1)}
                    >
                      Next
                    </button>
                  </div>
                </footer>
              </>
            ) : (
              <div className="state">
                <span className="empty-icon">▦</span>
                <strong>No {config.title.toLowerCase()} found</strong>
                <p>
                  {search || filter || warehouse
                    ? "Try adjusting your search or filters."
                    : "Records will appear here when available."}
                </p>
              </div>
            ))}
        </State>
      </section>
      {detail && (
        <section
          className="panel detail"
          aria-label={page === "assets" ? "Asset detail" : "Warehouse detail"}
        >
          <div className="panel-heading">
            <h2>{detail.asset_tag || detail.name}</h2>
            <button onClick={() => setDetail(null)}>Close</button>
          </div>
          <dl>
            {Object.entries(detail).map(([k, v]) => (
              <div key={k}>
                <dt>{label(k)}</dt>
                <dd>{v ?? "—"}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </>
  );
}
export default function App() {
  const [user, setUser] = useState(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [route, setRoute] = useState(window.location.hash.slice(2) || "dashboard"),
    [mobile, setMobile] = useState(false),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    api
      .me()
      .then((x) => {
        if (active) setUser(x.user);
      })
      .catch((e) => {
        if (active && e.status !== 401) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    const change = () => {
        setRoute(window.location.hash.slice(2) || "dashboard");
        setMobile(false);
      },
      expired = () => {
        setUser(null);
        setError("Your session expired. Sign in again.");
      };
    window.addEventListener("hashchange", change);
    window.addEventListener("session-expired", expired);
    return () => {
      active = false;
      window.removeEventListener("hashchange", change);
      window.removeEventListener("session-expired", expired);
    };
  }, []);
  if (loading) return <State loading />;
  if (!user)
    return (
      <>
        {error && (
          <p className="session-notice" role="alert">
            {error}
          </p>
        )}
        <Login
          onLogin={(u) => {
            setUser(u);
            setError("");
          }}
        />
      </>
    );
  const key = route.split("?")[0],
    config = pages[key];
  async function signOut() {
    setBusy(true);
    setError("");
    try {
      await api.logout();
      setUser(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="app-shell">
      <aside className={"sidebar " + (mobile ? "open" : "")}>
        <a className="brand" href="#/dashboard">
          <span className="brand-mark">W</span>
          <span>
            IT Warehouse<small>INVENTORY WORKSPACE</small>
          </span>
        </a>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {Object.entries(pages)
            .filter(
              ([name, p]) =>
                (name !== "operations" || user.manual_inventory_enabled === true) && (!p.permission || user.permissions.includes(p.permission)),
            )
            .map(([name, p]) => (
              <a
                key={name}
                href={"#/" + name}
                className={key === name ? "active" : ""}
                aria-current={key === name ? "page" : undefined}
              >
                <span>{p.icon}</span>
                {p.title}
              </a>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" /> Inventory visibility
          <span className="sidebar-version">
            Phase 4B · Master data workspace
          </span>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="menu-button"
            aria-label="Toggle navigation"
            onClick={() => setMobile(!mobile)}
          >
            ☰
          </button>
          <span className="breadcrumb">
            Workspace <span>/</span> {config?.title || "Not found"}
          </span>
          <div className="account">
            <span className="avatar">
              {user.username.slice(0, 2).toUpperCase()}
            </span>
            <span>{user.username}</span>
            <button onClick={signOut} disabled={busy}>
              {busy ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </header>
        <main className="workspace">
          <div className="page-heading">
            <div>
              <span className="eyebrow">IT WAREHOUSE</span>
              <h1>{config?.title || "Page not found"}</h1>
              <p className="muted">
                {config?.subtitle || "Choose a page from the navigation."}
              </p>
            </div>
            <span className="workspace-tag">Inventory workspace</span>
          </div>
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          {!config ? (
            <a href="#/dashboard">Back to overview</a>
          ) : key === "dashboard" ? (
            <Dashboard />
          ) : key === "operations" ? (
            user.manual_inventory_enabled === true ? <InventoryOperations user={user} /> : <p>Manual inventory operations are not enabled in this deployment.</p>
          ) : config.permission &&
            !user.permissions.includes(config.permission) ? (
            <p role="alert">You do not have permission to view this page.</p>
          ) : (
            <Catalog
              key={route}
              page={key}
              config={config}
              user={user}
              initialWarehouse={new URLSearchParams(route.split("?")[1]).get(
                "warehouse",
              )}
            />
          )}
        </main>
        <footer className="app-footer">
          IT Warehouse <span>Secure sessions · Inventory visibility</span>
        </footer>
      </div>
    </div>
  );
}
