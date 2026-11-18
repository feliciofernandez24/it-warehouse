import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import { api, request } from "./api";
vi.mock("./api", () => ({
  api: { me: vi.fn(), login: vi.fn(), logout: vi.fn() },
  request: vi.fn(),
}));
const user = {
  username: "test-reader",
  permissions: [
    "inventory.view_asset",
    "warehouse.view_warehouse",
    "warehouse.view_storagelocation",
  ],
};
const summary = {
  total_assets: 0,
  total_warehouses: 0,
  total_categories: 0,
  stock_totals: { all: 0, available: 0 },
  low_stock_count: 0,
  low_stock: [],
  recent_activity: [],
  recent_activity_permitted: true,
};
beforeEach(() => {
  vi.resetAllMocks();
  window.location.hash = "#/dashboard";
  api.me.mockResolvedValue({ user });
  request.mockResolvedValue(summary);
});
test("anonymous protected route shows login without inventory request", async () => {
  window.location.hash = "#/assets";
  api.me.mockRejectedValue({ status: 401 });
  render(<App />);
  expect(await screen.findByText("Welcome back")).toBeInTheDocument();
  expect(request).not.toHaveBeenCalled();
});
test("login renders the authenticated dashboard", async () => {
  api.me.mockRejectedValue({ status: 401 });
  api.login.mockResolvedValue({ user });
  render(<App />);
  fireEvent.change(await screen.findByLabelText("Username"), {
    target: { value: "test-reader" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "test-only-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in →" }));
  expect(await screen.findByText("Recent stock activity")).toBeInTheDocument();
  expect(api.login).toHaveBeenCalledWith("test-reader", "test-only-password");
});
test("failed login is visible and password is cleared", async () => {
  api.me.mockRejectedValue({ status: 401 });
  api.login.mockRejectedValue(new Error("Invalid username or password."));
  render(<App />);
  fireEvent.change(await screen.findByLabelText("Username"), {
    target: { value: "test-reader" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "wrong-test-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in →" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Invalid username or password.",
  );
  expect(screen.getByLabelText("Password")).toHaveValue("");
});
test("dashboard displays real API empty states", async () => {
  render(<App />);
  expect(await screen.findByText("No stock activity yet")).toBeInTheDocument();
  expect(screen.getByText("No low-stock alerts")).toBeInTheDocument();
  expect(request).toHaveBeenCalledWith(
    "/api/dashboard/summary/",
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
});
test("logout returns to login", async () => {
  api.logout.mockResolvedValue({});
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
  expect(await screen.findByText("Welcome back")).toBeInTheDocument();
  expect(api.logout).toHaveBeenCalledOnce();
});
test("API errors offer a retry", async () => {
  request
    .mockRejectedValueOnce(new Error("Permission denied."))
    .mockResolvedValue(summary);
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Permission denied.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("No stock activity yet")).toBeInTheDocument();
});
test("asset pagination, server search and filter work", async () => {
  window.location.hash = "#/assets";
  request.mockImplementation(async (path) => ({
    count: 2,
    next: path.includes("page=2") ? null : "/api/inventory/assets/?page=2",
    previous: path.includes("page=2") ? "previous" : null,
    results: [
      {
        id: 1,
        asset_tag: "TEST-ASSET",
        device_name: "Test server",
        lifecycle_status: "QUARANTINED",
      },
    ],
  }));
  render(<App />);
  await screen.findByText("TEST-ASSET");
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => expect(screen.getByText(/Page 2/)).toBeInTheDocument());
  fireEvent.change(screen.getByLabelText("Search Assets"), {
    target: { value: "Alpha" },
  });
  await waitFor(() =>
    expect(request).toHaveBeenLastCalledWith(
      expect.stringContaining("search=Alpha"),
      expect.anything(),
    ),
  );
  fireEvent.change(screen.getByLabelText("Filter"), {
    target: { value: "AVAILABLE" },
  });
  await waitFor(() =>
    expect(request).toHaveBeenLastCalledWith(
      expect.stringContaining("lifecycle_status=AVAILABLE"),
      expect.anything(),
    ),
  );
});
test("catalog empty state is clear", async () => {
  window.location.hash = "#/assets";
  request.mockResolvedValue({
    count: 0,
    results: [],
    next: null,
    previous: null,
  });
  render(<App />);
  expect(await screen.findByText("No assets found")).toBeInTheDocument();
});
test("client routes deny missing model permission", async () => {
  window.location.hash = "#/assets";
  api.me.mockResolvedValue({ user: { ...user, permissions: [] } });
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "You do not have permission",
  );
  expect(request).not.toHaveBeenCalled();
});
test("session expiry returns to sign-in", async () => {
  render(<App />);
  await screen.findByText("No stock activity yet");
  fireEvent(window, new Event("session-expired"));
  expect(await screen.findByText("Welcome back")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Your session expired");
});


test("dashboard renders nonempty immutable activity without master deletion controls", async () => {
  request.mockResolvedValue({...summary,recent_activity:[{id:7,operation_type:"STOCK_IN",quantity:2,recorded_at:"2026-11-18T00:00:00Z"}]});
  render(<App/>);
  expect(await screen.findByRole("cell",{name:"Stock In"})).toBeInTheDocument();
  expect(screen.getByRole("cell",{name:"2"})).toBeInTheDocument();
  expect(screen.queryByRole("button",{name:/Delete/})).not.toBeInTheDocument();
});
