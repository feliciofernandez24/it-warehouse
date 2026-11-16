import { expect, test } from "vitest";
import { proxyTarget } from "../proxy-target";
test("proxy defaults to local backend", () => expect(proxyTarget()).toBe("http://localhost:8000/"));
test("proxy accepts Compose backend", () => expect(proxyTarget("http://backend:8000")).toBe("http://backend:8000/"));
test.each(["http://backend:8000git", "file:///etc/passwd", "http://user:secret@backend", "http://backend/#x"])("bad proxy configuration fails safely: %s", value => {
  expect(() => proxyTarget(value)).toThrow("VITE_PROXY_TARGET must be a valid HTTP(S) URL");
});
