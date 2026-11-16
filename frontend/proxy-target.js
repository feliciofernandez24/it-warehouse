export function proxyTarget(value) {
  try {
    const url = new URL(value || "http://localhost:8000");
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error();
    return url.href;
  } catch {
    throw new Error("VITE_PROXY_TARGET must be a valid HTTP(S) URL without credentials, query or fragment.");
  }
}
