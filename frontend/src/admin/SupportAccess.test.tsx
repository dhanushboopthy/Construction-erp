import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "@/api/queryClient";

import { AdminApp } from "./AdminApp";

const ADMIN = {
  id: 1,
  email: "ops@duolink.app",
  full_name: "Duolink Ops",
  mobile: null,
  role: "super_admin",
  must_change_password: false,
  last_login_at: null,
};
const SUPPORT = { ...ADMIN, id: 2, full_name: "Help Desk", role: "support" };
const TENANT = {
  id: 7,
  slug: "acme",
  name: "Acme Steels",
  status: "active",
  plan: "BASIC",
  plan_id: 2,
  plan_name: "Basic",
  trial_ends_at: null,
  trial_state: "none",
  users: 1,
  max_users: 5,
  locations: 2,
  max_locations: 2,
  bills_30d: 12,
  last_sign_in_at: null,
  created_at: "2026-10-24T09:00:00Z",
  own_max_users: null,
  own_max_locations: null,
  suspended_at: null,
  suspended_reason: null,
  open_sessions: 0,
};
const LIVE = {
  live: true,
  grant_id: 3,
  starts_at: "2026-11-05T09:00:00Z",
  ends_at: new Date(Date.now() + 3 * 3600_000).toISOString(),
  seconds_left: 10_800,
  owner_only_figures: false,
  reason: "The bill print looks wrong",
  ticket_number: null,
  granted_by_name: "Ravi Kumar",
  open_sessions: 0,
};
const OFF = {
  ...LIVE,
  live: false,
  grant_id: null,
  starts_at: null,
  ends_at: null,
  seconds_left: 0,
  reason: null,
  granted_by_name: null,
};
const SESSION = {
  id: 9,
  tenant_id: 7,
  tenant_slug: "acme",
  tenant_name: "Acme Steels",
  admin_id: 1,
  admin_name: "Duolink Ops",
  reason: "Checking the bill print",
  status: "stale",
  started_at: "2026-11-05T08:00:00Z",
  expires_at: "2026-11-05T10:00:00Z",
  ended_at: "2026-11-05T10:00:00Z",
  end_reason: null,
  request_count: 14,
  owner_only_figures: false,
};
const SESSIONS = { items: [SESSION], total: 1, open: 0, stale: 1, limit: 100, offset: 0 };
const STARTED = {
  session_id: 9,
  token: "tok",
  expires_at: "2026-11-05T11:00:00Z",
  entry_url: "http://acme.localhost/support-entry#token=tok",
};

type Route = (url: string, init?: RequestInit) => unknown;
type Call = { url: string; method: string; body?: string };

function stubApi(routes: [RegExp, Route][], admin: object = ADMIN) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
      if (url.endsWith("/admin/auth/refresh")) {
        return new Response(
          JSON.stringify({ access_token: "t", token_type: "bearer", expires_in: 1800, admin }),
          { status: 200 },
        );
      }
      const match = routes.find(([pattern]) => pattern.test(url));
      if (!match) return new Response(JSON.stringify({ code: "NOT_FOUND" }), { status: 404 });
      const answer = match[1](url, init);
      if (answer instanceof Response) return answer;
      return new Response(JSON.stringify(answer), { status: 200 });
    }),
  );
  return calls;
}

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<AdminApp client={createQueryClient()} />);
}

const company = (access: object): [RegExp, Route][] => [
  [/\/admin\/tenants\/7\/support-access$/, () => access],
  [/\/admin\/tenants\/7$/, () => TENANT],
  [/\/admin\/audit\/support-sessions/, () => SESSIONS],
];

afterEach(() => vi.unstubAllGlobals());

describe("Company access (M23)", () => {
  it("enters the company read-only while the owner's grant is live", async () => {
    const open = vi.fn();
    vi.stubGlobal("open", open);
    const user = userEvent.setup();
    const calls = stubApi([
      ...company(LIVE),
      [/\/admin\/tenants\/7\/support-session$/, () => STARTED],
    ]);
    renderAt("/admin/companies/7?tab=access");
    expect(await screen.findByText("Access granted")).toBeInTheDocument();
    expect(screen.getByText(/Ravi Kumar/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Why are you entering"), "Checking the bill print");
    await user.click(screen.getByRole("button", { name: "Enter company (read-only)" }));
    await vi.waitFor(() => expect(open).toHaveBeenCalled());
    expect(open).toHaveBeenCalledWith(STARTED.entry_url, "_blank", "noopener");
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/support-session"));
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ reason: "Checking the bill print" });
  });

  it("disables entering with no grant and tells the admin why", async () => {
    stubApi(company(OFF));
    renderAt("/admin/companies/7?tab=access");
    expect(await screen.findByText("No access")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enter company (read-only)" })).toBeDisabled();
    expect(screen.getByText(/has not allowed Duolink in/)).toBeInTheDocument();
  });

  it("shows Support the status but offers no way in", async () => {
    stubApi(company(LIVE), SUPPORT);
    renderAt("/admin/companies/7?tab=access");
    expect(await screen.findByText("Access granted")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Enter company/ })).not.toBeInTheDocument();
    expect(screen.getByText("Only a Super Admin can enter a company.")).toBeInTheDocument();
  });

  it("lists the visits on the Activity page, a never-ended one marked", async () => {
    stubApi(company(LIVE));
    renderAt("/admin/activity?view=access");
    const table = await screen.findByRole("table");
    expect(within(table).getByText("Duolink Ops")).toBeInTheDocument();
    expect(within(table).getByText("14")).toBeInTheDocument();
    expect(within(table).getByText("Never left: window closed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Company access" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
