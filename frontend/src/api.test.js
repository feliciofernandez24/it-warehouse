import { beforeEach, expect, test, vi } from "vitest";
import { api, request } from "./api";
const response = (data, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => data,
});
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  localStorage.clear();
});
test("login sends same-origin credentials and CSRF obtained first", async () => {
  fetch
    .mockResolvedValueOnce(response({ csrfToken: "test-csrf" }))
    .mockResolvedValueOnce(
      response({
        user: { username: "reader" },
        csrfToken: "rotated-test-csrf",
      }),
    );
  await api.login("reader", "test-only-password");
  expect(fetch.mock.calls[0][0]).toBe("/api/auth/csrf/");
  expect(fetch.mock.calls[1][1]).toEqual(
    expect.objectContaining({
      credentials: "same-origin",
      method: "POST",
      headers: expect.objectContaining({ "X-CSRFToken": "test-csrf" }),
    }),
  );
  expect(localStorage.length).toBe(0);
});
test("logout uses a fresh CSRF token", async () => {
  fetch
    .mockResolvedValueOnce(response({ csrfToken: "logout-csrf" }))
    .mockResolvedValueOnce(response({ csrfToken: "after-logout" }));
  await api.logout();
  expect(fetch.mock.calls[1][1].headers["X-CSRFToken"]).toBe("logout-csrf");
});
test("protected 401 dispatches session expiry", async () => {
  const handler = vi.fn();
  window.addEventListener("session-expired", handler);
  fetch.mockResolvedValue(
    response({ detail: "Authentication required." }, 401),
  );
  await expect(request("/api/inventory/assets/")).rejects.toMatchObject({
    status: 401,
  });
  expect(handler).toHaveBeenCalledOnce();
  window.removeEventListener("session-expired", handler);
});
test("invalid upstream response gives a clear status error", async () => {
  fetch.mockResolvedValue({
    ok: false,
    status: 502,
    json: async () => {
      throw new Error("bad gateway");
    },
  });
  await expect(request("/api/dashboard/summary/")).rejects.toThrow(
    "Request failed (502).",
  );
});
test("external URLs are never used with session credentials", async () => {
  await expect(request("https://evil.invalid/api/")).rejects.toThrow(
    "Only same-origin",
  );
  expect(fetch).not.toHaveBeenCalled();
});
