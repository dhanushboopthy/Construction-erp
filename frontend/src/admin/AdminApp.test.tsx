import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";

import { AdminApp } from "./AdminApp";

const ADMIN = { id: 1, email: "ops@duolink.app", full_name: "Duolink Ops", last_login_at: null };
const SIGNED_IN = { access_token: "t", token_type: "bearer", expires_in: 1800, admin: ADMIN };

const ACME = {
  id: 7,
  slug: "acme",
  name: "Acme Steels",
  status: "trial",
  plan: "trial",
  trial_ends_at: "2026-11-07T09:00:00Z",
  trial_state: "running",
  users: 1,
  max_users: 5,
  locations: 2,
  max_locations: 2,
  bills_30d: 12,
  last_sign_in_at: null,
  created_at: "2026-10-24T09:00:00Z",
};
const ACME_DETAIL = {
  ...ACME,
  own_max_users: null,
  own_max_locations: null,
  suspended_at: null,
  suspended_reason: null,
  open_sessions: 2,
};
const OVERVIEW = {
  tenants_total: 3,
  tenants_by_status: { trial: 1, active: 2, suspended: 0, cancelled: 0 },
  new_tenants_this_month: 1,
  active_users: 9,
  open_sessions: 4,
  sign_ins_24h: 6,
  sign_ins_7d: 30,
  failed_sign_ins_24h: 2,
  failed_sign_ins_7d: 5,
  trials_ending: [],
};
const page = <T,>(items: T[]) => ({ items, total: items.length, limit: 200, offset: 0 });

type Route = (url: string, init?: RequestInit) => unknown;

/** Answer each request from `routes` by its path (first match wins); anything else is 404. */
function stubApi(routes: [RegExp, Route][], signedIn = true) {
  const calls: { url: string; method: string; body?: string }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
    if (url.endsWith("/admin/auth/refresh")) {
      return signedIn
        ? new Response(JSON.stringify(SIGNED_IN), { status: 200 })
        : new Response(JSON.stringify({ code: "NOT_AUTHENTICATED" }), { status: 401 });
    }
    const match = routes.find(([pattern]) => pattern.test(url));
    if (match) return new Response(JSON.stringify(match[1](url, init)), { status: 200 });
    return new Response(JSON.stringify({ code: "NOT_FOUND", message: "Not found" }), {
      status: 404,
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<AdminApp client={createQueryClient()} />);
}

describe("AdminApp", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks for a sign-in when there is no admin session", async () => {
    stubApi([], false);
    renderAt("/admin/companies");
    expect(await screen.findByRole("heading", { name: "Duolink admin" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("opens on the overview: companies by status and sign-ins", async () => {
    stubApi([[/\/admin\/overview$/, () => OVERVIEW]]);
    renderAt("/admin");
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    const legend = screen.getByRole("list", { name: "Companies by status" });
    expect(within(legend).getByText("Active").parentElement).toHaveTextContent("Active 2");
    expect(screen.getByText("Wrong passwords, last 24 hours").parentElement).toHaveTextContent("2");
    expect(screen.getByText("No trial ends in the next 7 days.")).toBeInTheDocument();
  });

  it("lists companies with their status in words and their usage", async () => {
    stubApi([[/\/admin\/tenants\?/, () => page([ACME])]]);
    renderAt("/admin/companies");
    const row = (await screen.findByRole("link", { name: "Acme Steels" })).closest("tr");
    if (!row) throw new Error("the company has no table row");
    expect(within(row).getByText("On trial")).toBeInTheDocument();
    expect(within(row).getAllByText(/of/)[0]).toHaveTextContent("1 of 5");
  });

  it("asks once more before suspending, saying who is signed out", async () => {
    const calls = stubApi([
      [/\/admin\/tenants\/7\/suspend$/, () => ({ ...ACME_DETAIL, status: "suspended" })],
      [/\/admin\/tenants\/7$/, () => ACME_DETAIL],
      [/\/admin\/users\?/, () => page([])],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7");
    await user.type(await screen.findByLabelText("Reason"), "Invoice unpaid");
    await user.click(screen.getByRole("button", { name: "Suspend company" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Suspend Acme Steels? 2 signed-in people are signed out now",
    );
    expect(calls.some((c) => c.url.endsWith("/suspend"))).toBe(false);
    await user.click(screen.getByRole("button", { name: "Suspend now" }));
    const sent = calls.find((c) => c.url.endsWith("/suspend"));
    expect(sent?.method).toBe("POST");
    expect(JSON.parse(sent?.body ?? "{}")).toEqual({ reason: "Invoice unpaid" });
  });

  it("shows a reset password once, in the user's support panel", async () => {
    const ravi = {
      id: 11,
      tenant_id: 7,
      tenant_slug: "acme",
      tenant_name: "Acme Steels",
      username: "ravi",
      full_name: "Ravi Kumar",
      role: "owner",
      is_active: true,
      locked: false,
      failed_login_count: 0,
      last_login_at: null,
    };
    stubApi([
      [/\/admin\/users\/11\/reset-password$/, () => ({ temporary_password: "Temp-Pass-42" })],
      [/\/admin\/users\?/, () => page([ravi])],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/users");
    await user.click(await screen.findByRole("button", { name: "Ravi Kumar" }));
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByLabelText("Temporary password")).toHaveTextContent("Temp-Pass-42");
  });
});
