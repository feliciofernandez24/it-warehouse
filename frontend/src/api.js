let csrfToken = null;
export class ApiError extends Error {
  constructor(message, status, details = null) {
    super(message);
    this.status = status;
    this.details = details;
  }
}
export async function request(path, options = {}) {
  if (!path.startsWith("/api/"))
    throw new Error("Only same-origin API paths are allowed");
  const method = options.method || "GET";
  const headers = { Accept: "application/json", ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken)
    headers["X-CSRFToken"] = csrfToken;
  const response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: "same-origin",
  });
  let data;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/api/auth/"))
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(
      typeof data?.detail === "string"
        ? data.detail
        : "Request failed (" + response.status + ").",
      response.status,
      data,
    );
  }
  if (data?.csrfToken) csrfToken = data.csrfToken;
  return data;
}
export const api = {
  save: async (path, method, body) => {
    if (!["POST", "PUT", "PATCH"].includes(method))
      throw new Error("Unsupported change method");
    await request("/api/auth/csrf/");
    return request(path, { method, body: JSON.stringify(body) });
  },
  me: () => request("/api/auth/me/"),
  login: async (username, password) => {
    await request("/api/auth/csrf/");
    return request("/api/auth/login/", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },
  logout: async () => {
    await request("/api/auth/csrf/");
    return request("/api/auth/logout/", { method: "POST" });
  },
};
