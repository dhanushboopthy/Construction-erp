import type { Location, ShopSettings, User } from "@/api/types";

/** A tiny in-memory API for screen tests: routes "METHOD /path" to handlers. */
export type Handler = (body: unknown, url: URL) => { status?: number; body?: unknown };

export interface Call {
  method: string;
  path: string;
  body: unknown;
  headers: Record<string, string>;
}

export function mockApi(routes: Record<string, Handler>) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    calls.push({
      method,
      path,
      body,
      headers: Object.fromEntries(new Headers(init?.headers).entries()),
    });
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
  counter_can_enter_purchases: true,
  expense_approval_limit: "5000.00",
  adjustment_approval_limit: "10000.00",
  itc_reverse_shortages: true,
  provision_pct_current: "0.00",
  provision_pct_1_15: "1.00",
  provision_pct_16_30: "2.00",
  provision_pct_31_60: "10.00",
  provision_pct_over_60: "50.00",
  default_lead_time_days: 7,
  default_safety_days: 2,
  fsn_fast_min_days: 15,
  nrv_selling_cost_pct: "0.00",
  nrv_writedown_enabled: true,
  bank_match_days: 3,
  exception_round_amount: "1000.00",
  exception_count_days: 2,
  exception_returns_count: 4,
  exception_returns_days: 30,
  exception_cash_near_pct: "80.00",
  exception_shortage_count: 3,
  locked_through: null,
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

export const TMT_ITEM = {
  id: 10,
  name: "TMT bar 12 mm Fe500D",
  category: "tmt" as const,
  brand: "Kamachi",
  hsn: "72142090",
  gst_rate: "18.00",
  base_unit: "kg",
  base_whole_only: false,
  size: "12 mm",
  grade: "Fe500D",
  weight_per_piece_kg: "10.656",
  is_active: true,
  units: [{ id: 1, unit: "ton", factor_to_base: "1000.000000", whole_only: false }],
};

export const PARTY = {
  id: 20,
  name: "Ravi Builders",
  type: "customer" as const,
  segment: "contractor" as const,
  gstin: null,
  state_code: "33",
  address: "",
  phone: "9876543210",
  credit_allowed: true,
  credit_limit: "15000.00",
  credit_days: 10,
  is_active: true,
  created_at: "2026-10-09T10:00:00Z",
  sites: [
    {
      id: 30,
      party_id: 20,
      name: "Anna Nagar villa",
      address: "",
      state_code: "33",
      gstin: null,
      is_active: true,
    },
  ],
};

export const page = <T>(items: T[]) => ({ items, total: items.length, limit: 200, offset: 0 });

export const SUPPLIER = {
  ...PARTY,
  id: 40,
  name: "Steel Mills",
  type: "supplier" as const,
  segment: null,
  credit_allowed: false,
  credit_limit: null,
  credit_days: null,
  sites: [],
};

export const COMPONENTS = [
  {
    id: 1,
    name: "Unloading",
    basis: "per_ton" as const,
    default_amount: "250.00",
    is_active: true,
  },
  { id: 2, name: "Weighbridge", basis: "flat" as const, default_amount: "150.00", is_active: true },
];

export const PREVIEW = {
  goods_value: "550000.00",
  gst_amount: "99000.00",
  charges_total: "6650.00",
  supplier_payable: "649000.00",
  gst_in_cost: false,
  lines: [
    {
      item_id: 10,
      item_name: "TMT bar 12 mm Fe500D",
      base_unit: "kg",
      billed_qty: "10000.000",
      received_qty: "10000.000",
      goods_value: "550000.00",
      gst_amount: "99000.00",
      charges_total: "6650.00",
      total_cost: "556650.00",
      unit_cost: "55.6650",
      costs: [],
    },
  ],
};
