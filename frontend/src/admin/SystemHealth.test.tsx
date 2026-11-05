import { render, screen, waitFor, within } from "@testing-library/react";
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

const BELL = {
  count: 3,
  items: [
    {
      id: "companies-expired",
      level: "critical",
      title: "1 company has expired",
      body: "Their plan has ended.",
      link: "/admin/subscriptions?status=expired",
    },
    {
      id: "subscriptions-expiring",
      level: "warning",
      title: "2 subscriptions end within 7 days",
      body: "Renew them.",
      link: "/admin/subscriptions?status=active&expiring_within=7",
    },
    {
      id: "tickets-new",
      level: "info",
      title: "4 new tickets are waiting",
      body: "Nobody has picked these up.",
      link: "/admin/support?status=open",
    },
  ],
};
const HEALTH = {
  as_of: "2026-11-05T06:00:00Z",
  api: {
    started_at: "2026-11-02T06:00:00Z",
    uptime_seconds: 3 * 86400 + 4 * 3600,
    version: "1.17.0",
    changelog_version: "1.17.0",
    python_version: "3.13.1",
    environment: "production",
  },
  database: {
    up: true,
    round_trip_ms: "1.25",
    size_bytes: 52428800,
    connections_in_use: 4,
    server_version: "17.2",
    migrations: { name: "Database version", state: "ok", detail: "At the latest version (0037)." },
  },
  disks: [
    {
      name: "backups",
      watched: true,
      total_bytes: 1073741824,
      free_bytes: 107374182,
      free_percent: "10.0",
      low: true,
    },
    {
      name: "files",
      watched: false,
      total_bytes: null,
      free_bytes: null,
      free_percent: null,
      low: false,
    },
  ],
  backup: {
    check: { name: "Nightly backup", state: "ok", detail: "Newest backup is 3 hours old." },
    last_success_at: "2026-11-05T03:00:00Z",
    age_hours: 3,
    stale: false,
    offsite_synced_at: null,
  },
  gsp: { name: "E-way bill provider", state: "warn", detail: "Pretend provider." },
  counters: {
    companies: 5,
    active_users: 21,
    open_sessions: 7,
    audit_events_today: 130,
    admin_actions_today: 9,
    open_tickets: 4,
  },
  maintenance: { enabled: false, message: null },
};
const OFF = {
  enabled: false,
  message: null,
  cause: null,
  operator_enabled: false,
  operator_message: null,
  changed_by: null,
  enabled_at: null,
  updated_at: null,
  restoring: false,
};
const AUDIT = {
  items: [
    {
      id: 11,
      at: "2026-11-05T05:00:00Z",
      admin_email: "ops@duolink.app",
      action: "maintenance_on",
      tenant_slug: null,
      target_user_id: null,
      target_admin_email: null,
      details: { message: "Back at 9 pm" },
      ip: null,
    },
  ],
  total: 1,
  limit: 100,
  offset: 0,
};
const STAFF = [
  { id: 1, full_name: "Duolink Ops", email: "ops@duolink.app", role: "super_admin" },
  { id: 2, full_name: "Help Desk", email: "h@duolink.app", role: "support" },
];
const SETTINGS = {
  security: {
    environment: "production",
    base_domain: "duolink.app",
    admin_subdomain: "admin",
    default_company: null,
    api_docs_enabled: false,
    cookie_secure: true,
    insecure_cookies_allowed: false,
    row_level_security_role_set: true,
    jwt_algorithm: "HS256",
    access_token_minutes: 30,
    refresh_token_hours: 12,
    login_max_attempts: 5,
    login_lock_minutes: 15,
    cors_origins: [],
    storage_provider: "local",
    gsp_provider: "live",
    backups_watched: true,
    max_upload_mb: 8,
  },
  lifecycle: {
    trial_days: 14,
    max_trial_days: 90,
    banner_days: 7,
    ending_soon_days: 7,
    notice_days: 7,
    backup_stale_hours: 26,
    disk_low_free_percent: 20,
    failed_admin_sign_ins_limit: 10,
    maintenance_cache_seconds: 5,
  },
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

const base: [RegExp, Route][] = [
  [/\/admin\/notifications$/, () => BELL],
  [/\/admin\/staff$/, () => STAFF],
  [/\/admin\/tenants\?/, () => ({ items: [], total: 0, limit: 200, offset: 0 })],
];

describe("AdminApp bell (M24)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("counts what needs attention and opens a list with level words and links", async () => {
    stubApi([...base, [/\/admin\/overview$/, () => ({})]]);
    const user = userEvent.setup();
    renderAt("/admin/staff");
    const bell = await screen.findByRole("button", { name: "Notifications, 3 to look at" });
    expect(bell).toHaveTextContent("3");
    await user.click(bell);
    const panel = screen.getByRole("dialog", { name: "Notifications" });
    expect(within(panel).getByText("Urgent")).toBeInTheDocument();
    expect(within(panel).getByText("Warning")).toBeInTheDocument();
    expect(within(panel).getByText("For information")).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "1 company has expired" })).toHaveAttribute(
      "href",
      "/admin/subscriptions?status=expired",
    );
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument();
    expect(bell).toHaveFocus();
  });

  it("says so when nothing needs attention, and shows no count", async () => {
    stubApi([
      ...base.filter(([p]) => !p.test("/admin/notifications")),
      [/\/notifications$/, () => ({ count: 0, items: [] })],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/staff");
    const bell = await screen.findByRole("button", { name: "Notifications" });
    await user.click(bell);
    expect(await screen.findByText("Nothing needs attention.")).toBeInTheDocument();
  });
});

describe("AdminApp System page (M24)", () => {
  afterEach(() => vi.unstubAllGlobals());

  const system: [RegExp, Route][] = [
    ...base,
    [/\/admin\/system\/health$/, () => HEALTH],
    [/\/admin\/system\/maintenance$/, () => OFF],
  ];

  it("shows the API, database, disks, backups and counters", async () => {
    stubApi(system);
    renderAt("/admin/system");
    expect(await screen.findByRole("heading", { name: "System health" })).toBeInTheDocument();
    expect(await screen.findByText("3 d 4 h")).toBeInTheDocument();
    expect(screen.getByText("1.25 ms")).toBeInTheDocument();
    expect(screen.getByText("50.0 MB")).toBeInTheDocument();
    expect(screen.getByText(/102.4 MB free of 1.0 GB/)).toBeInTheDocument();
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(screen.getByText("Not watched here")).toBeInTheDocument();
    expect(screen.getByText(/\(3 h ago\)/)).toBeInTheDocument();
    expect(screen.getByText("Not known")).toBeInTheDocument();
    expect(screen.getByText("130")).toBeInTheDocument();
  });

  it("lets a Super Admin turn maintenance on after confirming, with the message", async () => {
    const calls = stubApi([
      ...system.filter(([p]) => !p.test("/admin/system/maintenance")),
      [
        /\/admin\/system\/maintenance$/,
        (_url, init) =>
          init?.method === "POST"
            ? {
                ...OFF,
                enabled: true,
                operator_enabled: true,
                message: "Back at 9 pm",
                operator_message: "Back at 9 pm",
                changed_by: "Duolink Ops",
                enabled_at: "2026-11-05T06:10:00Z",
              }
            : OFF,
      ],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/system");
    await user.type(await screen.findByLabelText(/Message for companies/), "Back at 9 pm");
    await user.click(screen.getByRole("button", { name: "Turn maintenance on" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Close the ERP to every company");
    const switches = () => calls.filter((c) => c.method === "POST" && /maintenance$/.test(c.url));
    expect(switches()).toHaveLength(0); // nothing is sent until it is confirmed
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Turn maintenance on" }),
    );
    expect(await screen.findByText("On: companies cannot use the ERP")).toBeInTheDocument();
    const post = switches()[0];
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ enabled: true, message: "Back at 9 pm" });
    expect(screen.getByRole("button", { name: "Turn maintenance off" })).toBeInTheDocument();
  });

  it("shows Support the state but no switch", async () => {
    stubApi(system, SUPPORT);
    renderAt("/admin/system");
    expect(await screen.findByText("Off: companies are working")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Turn maintenance on" })).not.toBeInTheDocument();
    expect(screen.getByText("Only a Super Admin can switch maintenance mode.")).toBeInTheDocument();
  });
});

describe("AdminApp Audit log page (M24)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("has three tabs and sends every filter to the server", async () => {
    const calls = stubApi([...base, [/\/admin\/audit\?/, () => AUDIT]]);
    const user = userEvent.setup();
    renderAt("/admin/audit");
    expect(await screen.findByText("Turned maintenance mode on")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Audit views" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(["Admin actions", "Company access", "Sign-ins"]);
    await user.type(screen.getByLabelText("From"), "2026-11-01");
    await user.type(screen.getByLabelText("To"), "2026-11-05");
    await user.selectOptions(await screen.findByLabelText("Admin"), "2");
    await user.selectOptions(screen.getByLabelText("Action"), "maintenance_on");
    await waitFor(() => {
      const url =
        calls
          .map((c) => c.url)
          .filter((u) => /\/admin\/audit\?/.test(u))
          .at(-1) ?? "";
      expect(url).toContain("date_from=2026-11-01");
      expect(url).toContain("date_to=2026-11-05");
      expect(url).toContain("admin_id=2");
      expect(url).toContain("action=maintenance_on");
    });
  });

  it("exports the filtered rows as CSV for a Super Admin only", async () => {
    const blob = new Blob(["id\r\n11\r\n"], { type: "text/csv" });
    const calls = stubApi([
      ...base,
      [/\/admin\/audit\/export/, () => new Response(blob, { status: 200 })],
      [/\/admin\/audit\?/, () => AUDIT],
    ]);
    vi.stubGlobal(
      "URL",
      Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }),
    );
    const saved = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const user = userEvent.setup();
    renderAt("/admin/audit?action=maintenance_on&date_from=2026-11-01");
    await user.click(await screen.findByRole("button", { name: "Export CSV" }));
    await waitFor(() => expect(calls.some((c) => /\/audit\/export/.test(c.url))).toBe(true));
    const url = calls.find((c) => /\/audit\/export/.test(c.url))?.url ?? "";
    expect(url).toContain("action=maintenance_on");
    expect(url).toContain("date_from=2026-11-01");
    await waitFor(() => expect(saved).toHaveBeenCalled());
    saved.mockRestore();
  });

  it("hides the export from Support", async () => {
    stubApi([...base, [/\/admin\/audit\?/, () => AUDIT]], SUPPORT);
    renderAt("/admin/audit");
    await screen.findByText("Turned maintenance mode on");
    expect(screen.queryByRole("button", { name: "Export CSV" })).not.toBeInTheDocument();
  });

  it("says company access is not switched on yet", async () => {
    stubApi(base);
    renderAt("/admin/audit?tab=access");
    expect(await screen.findByText(/not switched on yet/)).toBeInTheDocument();
  });
});

describe("AdminApp Platform settings page (M24)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("explains the plan lifecycle and shows the configuration, with links to the controls", async () => {
    stubApi([...base, [/\/admin\/system\/settings$/, () => SETTINGS]]);
    renderAt("/admin/settings");
    expect(await screen.findByRole("heading", { name: "Platform settings" })).toBeInTheDocument();
    expect(screen.getByText(/14-day trial/)).toBeInTheDocument();
    expect(screen.getByText("read-only", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("5 wrong passwords for 15 min")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Plans and prices" })).toHaveAttribute(
      "href",
      "/admin/plans",
    );
    expect(
      screen.getByRole("link", { name: "Maintenance mode and system health" }),
    ).toHaveAttribute("href", "/admin/system");
    expect(screen.queryByText(/secret|password hash/i)).not.toBeInTheDocument();
  });
});
