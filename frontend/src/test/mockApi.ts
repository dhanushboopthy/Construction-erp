import type { Location, ShopSettings, User } from "@/api/types";

/** A tiny in-memory API for screen tests: routes "METHOD /path" to handlers. */
export type Handler = (body: unknown, url: URL) => { status?: number; body?: unknown };

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

export function mockApi(routes: Record<string, Handler>) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    calls.push({ method, path, body });
    const handler = routes[`${method} ${path}`];
    if (!handler) {
      return new Response(JSON.stringify({ code: "NOT_FOUND", message: "no mock" }), {
        status: 404,
      });
    }
    const result = handler(body, url);
    const status = result.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(result.body ?? null), { status });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export const S1: Location = {
  id: 1,
  code: "S1",
  name: "Shop 1",
  kind: "shop",
  address: "",
  state_code: "33",
  phone: null,
  is_active: true,
  created_at: "2026-10-09T10:00:00Z",
};
export const G1: Location = { ...S1, id: 3, code: "G1", name: "Godown", kind: "godown" };

export const OWNER: User = {
  id: 1,
  username: "owner",
  full_name: "Shop Owner",
  role: "owner",
  is_active: true,
  last_login_at: "2026-10-09T10:00:00Z",
  locations: [],
};
export const COUNTER: User = {
  id: 2,
  username: "counter1",
  full_name: "Counter, Shop 1",
  role: "counter",
  is_active: true,
  last_login_at: null,
  locations: [S1],
};

export const SETTINGS: ShopSettings = {
  id: 1,
  legal_name: "Demo Construction Materials",
  trade_name: null,
  gstin: null,
  state_code: "33",
  address: "",
  phone: null,
  email: null,
  bank_name: null,
  bank_account_no: null,
  bank_ifsc: null,
  invoice_terms: null,
  financial_year_start_month: 4,
  return_window_days: 2,
  weight_variance_pct: "0.50",
  default_credit_limit: "10000.00",
  default_credit_days: 7,
  include_gst_in_cost: false,
  rates_include_gst: false,
  cash_receipt_limit: "200000.00",
  eway_threshold_interstate: "50000.00",
  eway_threshold_intrastate: "100000.00",
  einvoice_enabled: false,
  timezone: "Asia/Kolkata",
};

/** Signed in as `user` through the refresh cookie. */
export function session(user: User): Record<string, Handler> {
  return {
    "POST /auth/refresh": () => ({
      body: { access_token: "t", token_type: "bearer", expires_in: 1800, user },
    }),
    "GET /auth/me": () => ({ body: user }),
  };
}
