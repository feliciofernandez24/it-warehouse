import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MasterEditor, canManage } from "./MasterData";
import App from "./App";
import { api, request } from "./api";
vi.mock("./api", () => ({
  api: { me: vi.fn(), save: vi.fn(), login: vi.fn(), logout: vi.fn() },
  request: vi.fn(),
}));
const user = {
  username: "editor",
  permissions: [
    "inventory.view_assetcategory",
    "inventory.add_assetcategory",
    "inventory.change_assetcategory",
    "inventory.view_manufacturer",
    "inventory.add_manufacturer",
    "inventory.change_manufacturer",
    "inventory.view_productmodel",
    "inventory.add_productmodel",
    "inventory.change_productmodel",
    "inventory.view_asset",
    "inventory.add_asset",
    "inventory.change_asset",
    "warehouse.view_warehouse",
    "warehouse.add_warehouse",
    "warehouse.change_warehouse",
    "warehouse.view_storagelocation",
    "warehouse.add_storagelocation",
    "warehouse.change_storagelocation",
  ],
};
beforeEach(() => {
  vi.resetAllMocks();
  window.location.hash = "#/categories";
  api.me.mockResolvedValue({ user });
  api.save.mockResolvedValue({ id: 1, version: 0 });
  request.mockResolvedValue({
    count: 0,
    results: [],
    next: null,
    previous: null,
  });
});
function category() {
  fireEvent.change(screen.getByLabelText("Code *"), {
    target: { value: "NEW" },
  });
  fireEvent.change(screen.getByLabelText("Name *"), {
    target: { value: "New category" },
  });
  fireEvent.change(screen.getByLabelText("Reason for change *"), {
    target: { value: "Catalog registration" },
  });
}
test("category form submits an authenticated API payload and reports success", async () => {
  const saved = vi.fn();
  render(
    <MasterEditor
      page="categories"
      user={user}
      onClose={vi.fn()}
      onSaved={saved}
    />,
  );
  category();
  fireEvent.click(screen.getByRole("button", { name: "Create category" }));
  await waitFor(() =>
    expect(api.save).toHaveBeenCalledWith(
      "/api/management/categories/",
      "POST",
      {
        code: "NEW",
        name: "New category",
        description: "",
        is_active: true,
        change_reason: "Catalog registration",
      },
    ),
  );
  expect(saved).toHaveBeenCalledWith("Created category.");
});
test("field validation errors preserve entered values", async () => {
  api.save.mockRejectedValue(
    Object.assign(new Error("Validation failed"), {
      details: { code: ["This code already exists."] },
    }),
  );
  render(
    <MasterEditor
      page="categories"
      user={user}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  category();
  fireEvent.click(screen.getByRole("button", { name: "Create category" }));
  expect(
    await screen.findByText("This code already exists."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Name *")).toHaveValue("New category");
});
test("edit loads the server version and keeps code immutable", async () => {
  request.mockResolvedValue({
    id: 4,
    code: "OLD",
    name: "Old name",
    description: "",
    is_active: true,
    version: 7,
  });
  render(
    <MasterEditor
      page="categories"
      id={4}
      user={user}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await screen.findByDisplayValue("Old name");
  expect(screen.getByLabelText("Code *")).toHaveAttribute("readonly");
  fireEvent.change(screen.getByLabelText("Name *"), {
    target: { value: "Corrected" },
  });
  fireEvent.change(screen.getByLabelText("Reason for change *"), {
    target: { value: "Correction" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() =>
    expect(api.save).toHaveBeenCalledWith(
      "/api/management/categories/4/",
      "PATCH",
      expect.objectContaining({ expected_version: 7, name: "Corrected" }),
    ),
  );
});
test("stale conflicts remain visible without silently resubmitting", async () => {
  request.mockResolvedValue({
    id: 4,
    code: "OLD",
    name: "Old",
    version: 2,
    is_active: true,
  });
  api.save.mockRejectedValue(
    new Error(
      "This record changed since it was loaded. Refresh before saving.",
    ),
  );
  render(
    <MasterEditor
      page="categories"
      id={4}
      user={user}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await screen.findByDisplayValue("Old");
  fireEvent.change(screen.getByLabelText("Reason for change *"), {
    target: { value: "Correction" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Refresh before saving",
  );
  expect(api.save).toHaveBeenCalledOnce();
});
test("read-only users have no create or edit controls", async () => {
  api.me.mockResolvedValue({
    user: { ...user, permissions: ["inventory.view_assetcategory"] },
  });
  request.mockResolvedValue({
    count: 1,
    results: [{ id: 1, code: "CAT", name: "Category", is_active: true }],
    next: null,
    previous: null,
  });
  render(<App />);
  await screen.findByText("CAT");
  expect(
    screen.queryByRole("button", { name: "Register category" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Edit category" }),
  ).not.toBeInTheDocument();
  expect(
    canManage(
      { ...user, permissions: ["inventory.add_assetcategory"] },
      "categories",
      "add",
    ),
  ).toBe(false);
});
test("editor is permission guarded even when rendered directly", async () => {
  render(
    <MasterEditor
      page="categories"
      user={{ ...user, permissions: [] }}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "You do not have permission",
  );
  expect(api.save).not.toHaveBeenCalled();
});
test("cancel closes without mutation", () => {
  const close = vi.fn();
  render(
    <MasterEditor
      page="categories"
      user={user}
      onClose={close}
      onSaved={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(close).toHaveBeenCalledOnce();
  expect(api.save).not.toHaveBeenCalled();
});
test("pending submission disables duplicate writes", async () => {
  api.save.mockReturnValue(new Promise(() => {}));
  render(
    <MasterEditor
      page="categories"
      user={user}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  category();
  fireEvent.click(screen.getByRole("button", { name: "Create category" }));
  expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  expect(api.save).toHaveBeenCalledOnce();
});
test("product registration uses existing category and manufacturer associations", async () => {
  request.mockImplementation(async (path) => ({
    count: 1,
    next: null,
    previous: null,
    results: [
      {
        id: path.includes("manufacturers") ? 2 : 1,
        code: "TEST",
        name: path.includes("manufacturers") ? "Test maker" : "Test category",
      },
    ],
  }));
  render(
    <MasterEditor
      page="products"
      user={user}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await screen.findByRole("option", { name: "TEST · Test category" });
  fireEvent.change(screen.getByLabelText("SKU code *"), {
    target: { value: "MODEL" },
  });
  fireEvent.change(screen.getByLabelText("Name *"), {
    target: { value: "Product" },
  });
  fireEvent.change(screen.getByLabelText("Category"), {
    target: { value: "1" },
  });
  fireEvent.change(screen.getByLabelText("Manufacturer"), {
    target: { value: "2" },
  });
  fireEvent.change(screen.getByLabelText("Tracking mode *"), {
    target: { value: "BULK" },
  });
  fireEvent.change(screen.getByLabelText("Reason for change *"), {
    target: { value: "Catalog" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create product model" }));
  await waitFor(() =>
    expect(api.save).toHaveBeenCalledWith(
      "/api/management/product-models/",
      "POST",
      expect.objectContaining({
        category: 1,
        manufacturer: 2,
        tracking_mode: "BULK",
      }),
    ),
  );
});
test("relation lookup failure is visible", async () => {
  request.mockRejectedValue(new Error("Options unavailable."));
  render(
    <MasterEditor
      page="locations"
      user={user}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  expect(
    (await screen.findAllByText("Options unavailable.")).length,
  ).toBeGreaterThan(0);
});
test("asset editor exposes metadata but no position or tag controls", async () => {
  request.mockResolvedValue({
    id: 5,
    asset_tag: "AST-TEST",
    product_name: "Server",
    device_name: "Device",
    serial_raw: "TEST",
    version: 1,
  });
  render(
    <MasterEditor
      page="assets"
      id={5}
      user={user}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  await screen.findByDisplayValue("Device");
  expect(
    screen.getByText(/Tag, product, location and lifecycle cannot be changed/),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Lifecycle status")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Reason for change *"), {
    target: { value: "Metadata correction" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() =>
    expect(api.save).toHaveBeenCalledWith(
      "/api/management/assets/5/",
      "PATCH",
      expect.objectContaining({
        device_name: "Device",
        serial_raw: "TEST",
        expected_version: 1,
      }),
    ),
  );
});
test("asset registration makes the ledger blocker explicit", () => {
  render(
    <MasterEditor
      page="assets"
      user={user}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  expect(
    screen.getByText(
      /Registration is unavailable until an approved ledger-backed receipt/,
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Validate registration" }),
  ).toBeInTheDocument();
});
test("catalog create control opens form and refreshes after success", async () => {
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Register category" }),
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  category();
  fireEvent.click(screen.getByRole("button", { name: "Create category" }));
  expect(await screen.findByText("Created category.")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(
    request.mock.calls.filter(([p]) =>
      p.startsWith("/api/inventory/categories/"),
    ).length,
  ).toBeGreaterThanOrEqual(2);
});
test("catalog edit action loads the management record", async () => {
  request.mockImplementation(async (path) =>
    path.startsWith("/api/management/")
      ? { id: 1, code: "CAT", name: "Category", is_active: true, version: 0 }
      : {
          count: 1,
          results: [{ id: 1, code: "CAT", name: "Category", is_active: true }],
          next: null,
          previous: null,
        },
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Edit category" }));
  expect(await screen.findByDisplayValue("Category")).toBeInTheDocument();
  expect(request).toHaveBeenCalledWith(
    "/api/management/categories/1/",
    expect.anything(),
  );
});

test("master lists filter active and inactive records", async () => {
  render(<App />);
  fireEvent.change(await screen.findByLabelText("Record status"), {
    target: { value: "false" },
  });
  await waitFor(() =>
    expect(request).toHaveBeenLastCalledWith(
      expect.stringContaining("is_active=false"),
      expect.anything(),
    ),
  );
});
test("warehouse details reuse the existing read API", async () => {
  window.location.hash = "#/warehouses";
  request.mockImplementation(async (path) =>
    path === "/api/warehouses/1/"
      ? {
          id: 1,
          code: "WH",
          name: "Warehouse",
          address: "Test address",
          is_active: true,
        }
      : {
          count: 1,
          results: [{ id: 1, code: "WH", name: "Warehouse", is_active: true }],
          next: null,
          previous: null,
        },
  );
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "View warehouse" }),
  );
  expect(await screen.findByLabelText("Warehouse detail")).toHaveTextContent(
    "Test address",
  );
});
