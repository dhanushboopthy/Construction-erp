import { routeFor, type SwRequest } from "./swRoutes";

const ORIGIN = "https://acme.duolink.app";
const PRECACHED = new Set(["/index.html", "/favicon.svg", "/icons/duolink-mark.svg"]);

function route(path: string, init: Partial<SwRequest> = {}, origin = ORIGIN) {
  return routeFor(
    { url: `${origin}${path}`, method: "GET", mode: "no-cors", ...init },
    ORIGIN,
    PRECACHED,
  );
}

describe("what the service worker does with a request", () => {
  it("never keeps an API answer", () => {
    for (const path of [
      "/api/v1/tenant",
      "/api/v1/tenant/logo?v=abc",
      "/api/v1/invoices?limit=50",
      "/api/v1/auth/refresh",
      "/api/v1/admin/tenants",
      "/api/v1/tenant/manifest.webmanifest",
      "/api",
    ]) {
      expect(route(path), path).toBe("network");
      expect(route(path, { mode: "cors" }), path).toBe("network");
    }
  });

  it("leaves every write to the network, whatever the address", () => {
    for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
      expect(route("/assets/app-1a2b.js", { method }), method).toBe("network");
      expect(route("/", { method, mode: "navigate" }), method).toBe("network");
    }
  });

  it("leaves other origins alone", () => {
    expect(route("/assets/x.js", {}, "https://cdn.example")).toBe("network");
  });

  it("serves a page load network first, with the shell as the fallback", () => {
    expect(route("/", { mode: "navigate" })).toBe("shell");
    expect(route("/sales/new", { mode: "navigate" })).toBe("shell");
  });

  it("keeps the build's files", () => {
    expect(route("/assets/index-9f8e7d.js")).toBe("cache");
    expect(route("/favicon.svg")).toBe("cache");
    expect(route("/icons/duolink-mark.svg")).toBe("cache");
  });

  it("does not keep anything it does not know", () => {
    expect(route("/something-else.json")).toBe("network");
  });
});
