/**
 * What the service worker does with each request (Milestone 29). Kept apart from the worker so
 * it can be tested: the worker itself only wires these answers to the cache.
 *
 * - "network": left to the browser, never cached. Every API call (bills, stock, the company's
 *   name and logo) is one: no company data is ever kept by the service worker, and a bill must
 *   reach the server to get its number.
 * - "shell": a page load. Network first; with no connection, the cached app shell, which then
 *   says "No connection".
 * - "cache": a file of the build (scripts, styles, fonts, icons). Their names change with every
 *   build, so the cached copy is always the right one.
 */
export type SwRoute = "network" | "shell" | "cache";

export interface SwRequest {
  url: string;
  method: string;
  mode: string;
}

export const SHELL_URL = "/index.html";
export const CACHE_PREFIX = "erp-shell-";

export function routeFor(request: SwRequest, origin: string, precached: ReadonlySet<string>) {
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== origin) return "network" satisfies SwRoute;
  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) return "network";
  if (request.mode === "navigate") return "shell";
  if (url.pathname.startsWith("/assets/") || precached.has(url.pathname)) return "cache";
  return "network";
}
