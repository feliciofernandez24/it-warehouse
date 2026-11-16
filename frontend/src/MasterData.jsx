import React, { useEffect, useRef, useState } from "react";
import { api, request } from "./api";

const text = (key, label, extra = {}) => ({ key, label, ...extra });
const relation = (key, label, path, permission, extra = {}) => ({
  key,
  label,
  path,
  permission,
  type: "relation",
  ...extra,
});
const active = text("is_active", "Active", { type: "checkbox", initial: true });
const named = [
  text("code", "Code", { required: true, max: 64, immutable: true }),
  text("name", "Name", { required: true, max: 200 }),
  text("description", "Description", { type: "textarea" }),
  active,
];
export const management = {
  categories: {
    endpoint: "categories",
    model: "inventory.assetcategory",
    singular: "category",
    fields: named,
  },
  manufacturers: {
    endpoint: "manufacturers",
    model: "inventory.manufacturer",
    singular: "manufacturer",
    fields: named,
  },
  products: {
    endpoint: "product-models",
    model: "inventory.productmodel",
    singular: "product model",
    fields: [
      text("sku_code", "SKU code", {
        required: true,
        immutable: true,
        max: 64,
      }),
      text("name", "Name", { required: true, max: 200 }),
      relation(
        "category",
        "Category",
        "inventory/categories",
        "inventory.view_assetcategory",
        { required: true, caption: "category_name" },
      ),
      relation(
        "manufacturer",
        "Manufacturer",
        "inventory/manufacturers",
        "inventory.view_manufacturer",
        { caption: "manufacturer_name" },
      ),
      text("model_number", "Model number", { max: 160 }),
      text("part_number", "Part number", { max: 160 }),
      text("tracking_mode", "Tracking mode", {
        type: "select",
        required: true,
        choices: ["SERIALIZED", "BULK"],
      }),
      text("description", "Description", { type: "textarea" }),
      active,
    ],
  },
  warehouses: {
    endpoint: "warehouses",
    model: "warehouse.warehouse",
    singular: "warehouse",
    fields: [
      ...named.slice(0, 3),
      text("address", "Address", { type: "textarea" }),
      active,
    ],
  },
  locations: {
    endpoint: "locations",
    model: "warehouse.storagelocation",
    singular: "storage location",
    fields: [
      text("code", "Code", { required: true, max: 64, immutable: true }),
      text("name", "Name", { required: true, max: 200 }),
      relation(
        "warehouse",
        "Warehouse",
        "warehouses",
        "warehouse.view_warehouse",
        { required: true, caption: "warehouse_name" },
      ),
      relation(
        "parent",
        "Parent location",
        "locations",
        "warehouse.view_storagelocation",
        { warehouseDependent: true, caption: "parent_name" },
      ),
      text("kind", "Location kind", {
        type: "select",
        choices: ["AREA", "RACK", "SHELF", "BIN"],
        required: true,
      }),
      active,
    ],
  },
  assets: {
    endpoint: "assets",
    model: "inventory.asset",
    singular: "asset",
    fields: [
      text("device_name", "Device name", { required: true, max: 200 }),
      text("serial_raw", "Serial number", { max: 200 }),
      text("description", "Description", { type: "textarea" }),
      text("remarks", "Remarks", { type: "textarea" }),
    ],
  },
};
export function canManage(user, page, action) {
  const config = management[page];
  if (!config) return false;
  const [app, model] = config.model.split(".");
  return (
    user.permissions.includes(app + ".view_" + model) &&
    user.permissions.includes(app + "." + action + "_" + model)
  );
}

function Lookup({
  field,
  value,
  onChange,
  user,
  warehouse,
  currentLabel,
  exclude,
}) {
  const [data, setData] = useState(null),
    [search, setSearch] = useState(""),
    [page, setPage] = useState(1),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  const allowed = user.permissions.includes(field.permission);
  useEffect(() => {
    setPage(1);
  }, [search, warehouse]);
  useEffect(() => {
    if (!allowed) return;
    const c = new AbortController();
    const timer = setTimeout(() => {
      const params = new URLSearchParams({
        search,
        page,
        page_size: 25,
        is_active: "true",
      });
      if (field.warehouseDependent && warehouse)
        params.set("warehouse", warehouse);
      if (field.key === "product_model")
        params.set("tracking_mode", "SERIALIZED");
      setData(null);
      setError("");
      request("/api/" + field.path + "/?" + params, { signal: c.signal })
        .then(setData)
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [
    field.path,
    field.key,
    field.warehouseDependent,
    allowed,
    search,
    page,
    warehouse,
    retry,
  ]);
  const options = (data?.results || []).filter((row) => row.id !== exclude);
  return (
    <div className="lookup">
      <input
        aria-label={"Search " + field.label + " options"}
        placeholder="Search options…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        disabled={!allowed}
      />
      <select
        id={"field-" + field.key}
        aria-label={field.label}
        required={field.required}
        value={value ?? ""}
        disabled={!allowed}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">
          {field.required ? "Choose " + field.label.toLowerCase() : "None"}
        </option>
        {value && !options.some((row) => String(row.id) === String(value)) && (
          <option value={value}>{currentLabel || "Current selection"}</option>
        )}
        {options.map((row) => (
          <option value={row.id} key={row.id}>
            {row.code || row.sku_code} · {row.name}
          </option>
        ))}
      </select>
      {!allowed ? (
        <small role="alert">
          You need permission to view {field.label.toLowerCase()} options.
        </small>
      ) : error ? (
        <small role="alert">
          {error}{" "}
          <button type="button" onClick={() => setRetry((x) => x + 1)}>
            Retry options
          </button>
        </small>
      ) : !data ? (
        <small role="status">Loading options…</small>
      ) : (
        <small>
          {data.count} available · Page {page}{" "}
          <button
            type="button"
            disabled={!data.previous}
            onClick={() => setPage((x) => x - 1)}
          >
            Previous options
          </button>
          <button
            type="button"
            disabled={!data.next}
            onClick={() => setPage((x) => x + 1)}
          >
            Next options
          </button>
        </small>
      )}
    </div>
  );
}

function messages(value) {
  if (Array.isArray(value)) return value.join(" ");
  return typeof value === "string" ? value : "Please check this field.";
}

export function MasterEditor({ page, id, user, onClose, onSaved }) {
  const config = management[page];
  const [record, setRecord] = useState(null),
    [values, setValues] = useState({}),
    [loading, setLoading] = useState(Boolean(id)),
    [saving, setSaving] = useState(false),
    [error, setError] = useState(""),
    [errors, setErrors] = useState({});
  const first = useRef(null),
    dialog = useRef(null);
  const permission = canManage(user, page, id ? "change" : "add");
  const fields =
    page === "assets" && !id
      ? [
          relation(
            "product_model",
            "Product model",
            "inventory/product-models",
            "inventory.view_productmodel",
            { required: true },
          ),
          relation(
            "warehouse_filter",
            "Warehouse",
            "warehouses",
            "warehouse.view_warehouse",
            { helper: true },
          ),
          relation(
            "current_location",
            "Storage location",
            "locations",
            "warehouse.view_storagelocation",
            { required: true, warehouseDependent: true },
          ),
          ...config.fields,
        ]
      : config.fields;
  useEffect(() => {
    const defaults = Object.fromEntries(
      fields.map((f) => [
        f.key,
        f.initial ?? (f.type === "checkbox" ? true : ""),
      ]),
    );
    setValues({ ...defaults, change_reason: "" });
    if (!id) {
      first.current?.focus();
      return;
    }
    const c = new AbortController();
    request("/api/management/" + config.endpoint + "/" + id + "/", {
      signal: c.signal,
    })
      .then((data) => {
        setRecord(data);
        setValues({ ...defaults, ...data, change_reason: "" });
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => setLoading(false));
    return () => c.abort();
  }, [id, page]);
  useEffect(() => {
    const previous = document.activeElement;
    const close = (e) => {
      if (e.key === "Escape" && !saving) onClose();
      if (e.key === "Tab") {
        const nodes = Array.from(
          dialog.current?.querySelectorAll(
            "button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled)",
          ) || [],
        );
        if (!nodes.length) return;
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("keydown", close);
      previous?.focus?.();
    };
  }, [saving, onClose]);
  useEffect(() => {
    if (!loading) first.current?.focus();
  }, [loading]);
  function update(field, value) {
    setValues((old) => ({
      ...old,
      [field.key]: value,
      ...(["warehouse", "warehouse_filter"].includes(field.key)
        ? { parent: "", current_location: "" }
        : {}),
    }));
    setErrors((old) => ({ ...old, [field.key]: undefined }));
  }
  async function submit(e) {
    e.preventDefault();
    if (!permission || loading || saving) return;
    setSaving(true);
    setError("");
    setErrors({});
    const payload = { change_reason: values.change_reason };
    for (const field of fields) {
      if (field.helper) continue;
      payload[field.key] =
        field.type === "relation"
          ? values[field.key]
            ? Number(values[field.key])
            : null
          : values[field.key];
    }
    if (id) payload.expected_version = record.version;
    try {
      await api.save(
        "/api/management/" + config.endpoint + "/" + (id ? id + "/" : ""),
        id ? "PATCH" : "POST",
        payload,
      );
      onSaved((id ? "Updated " : "Created ") + config.singular + ".");
    } catch (e) {
      setError(e.message);
      setErrors(e.details && typeof e.details === "object" ? e.details : {});
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="editor-backdrop">
      <section
        ref={dialog}
        className="master-editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="editor-title"
      >
        <div className="panel-heading">
          <h2 id="editor-title">
            {id ? "Edit " : "Register "}
            {config.singular}
          </h2>
          <button
            type="button"
            disabled={saving}
            onClick={onClose}
            aria-label="Close editor"
          >
            Close
          </button>
        </div>
        {loading ? (
          <div className="state" role="status">
            Loading record…
          </div>
        ) : !permission ? (
          <div className="state error" role="alert">
            You do not have permission to make this change.
          </div>
        ) : (
          <form onSubmit={submit}>
            {page === "assets" && !id && (
              <p className="notice warning">
                Registration is unavailable until an approved ledger-backed
                receipt workflow exists. Phase 4B will not create an asset or
                stock movement.
              </p>
            )}
            {page === "assets" && id && record && (
              <p className="notice">
                Asset {record.asset_tag} · {record.product_name} ·{" "}
                {record.location_name || "No location"}. Tag, product, location
                and lifecycle cannot be changed here.
              </p>
            )}
            {error && (
              <p className="notice error" role="alert">
                {error}
              </p>
            )}
            <fieldset disabled={saving || Boolean(id && !record)}>
              {fields.map((field, index) => (
                <div className="editor-field" key={field.key}>
                  <label htmlFor={"field-" + field.key}>
                    {field.label}
                    {field.required ? " *" : ""}
                  </label>
                  {field.type === "relation" ? (
                    <Lookup
                      field={field}
                      value={values[field.key]}
                      onChange={(v) => update(field, v)}
                      user={user}
                      warehouse={values.warehouse || values.warehouse_filter}
                      currentLabel={record?.[field.caption]}
                      exclude={field.key === "parent" ? id : undefined}
                    />
                  ) : field.type === "textarea" ? (
                    <textarea
                      id={"field-" + field.key}
                      value={values[field.key] ?? ""}
                      onChange={(e) => update(field, e.target.value)}
                      maxLength={10000}
                      rows={3}
                    />
                  ) : field.type === "select" ? (
                    <select
                      id={"field-" + field.key}
                      required={field.required}
                      value={values[field.key] ?? ""}
                      onChange={(e) => update(field, e.target.value)}
                    >
                      <option value="">
                        Choose {field.label.toLowerCase()}
                      </option>
                      {field.choices.map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      ref={index === 0 ? first : undefined}
                      id={"field-" + field.key}
                      type={field.type === "checkbox" ? "checkbox" : "text"}
                      required={field.required}
                      maxLength={field.max}
                      readOnly={Boolean(id && field.immutable)}
                      checked={
                        field.type === "checkbox"
                          ? Boolean(values[field.key])
                          : undefined
                      }
                      value={
                        field.type === "checkbox"
                          ? undefined
                          : (values[field.key] ?? "")
                      }
                      onChange={(e) =>
                        update(
                          field,
                          field.type === "checkbox"
                            ? e.target.checked
                            : e.target.value,
                        )
                      }
                    />
                  )}
                  {id && field.immutable && (
                    <small>Existing identifiers cannot be changed.</small>
                  )}
                  {errors[field.key] && (
                    <small className="error" role="alert">
                      {messages(errors[field.key])}
                    </small>
                  )}
                </div>
              ))}
              <div className="editor-field">
                <label htmlFor="change-reason">Reason for change *</label>
                <textarea
                  id="change-reason"
                  required
                  maxLength={500}
                  rows={2}
                  value={values.change_reason ?? ""}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, change_reason: e.target.value }))
                  }
                />
                <small>
                  Use a brief business reason. Do not include credentials or
                  secrets.
                </small>
                {errors.change_reason && (
                  <small role="alert" className="error">
                    {messages(errors.change_reason)}
                  </small>
                )}
              </div>
            </fieldset>
            <footer className="editor-actions">
              <button type="button" disabled={saving} onClick={onClose}>
                Cancel
              </button>
              <button
                className="primary"
                disabled={saving || Boolean(id && !record)}
              >
                {saving
                  ? "Saving…"
                  : id
                    ? "Save changes"
                    : page === "assets"
                      ? "Validate registration"
                      : "Create " + config.singular}
              </button>
            </footer>
          </form>
        )}
      </section>
    </div>
  );
}
