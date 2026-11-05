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

const LIMITS = {
  daily_limit: 50,
  monthly_limit: 500,
  warn_at_percent: 80,
  cache_hours: 168,
  secret_key_set: true,
};
const GSP = {
  kind: "gsp",
  provider: "sandbox",
  base_url: "https://gsp.example/api",
  key_last4: "9876",
  status: "connected",
  source: "database",
  effective_provider: "sandbox",
  credential_fields: ["client_id", "client_secret", "username", "password"],
  connected_at: "2026-11-03T09:00:00Z",
  last_success_at: "2026-11-03T10:00:00Z",
  last_failure_at: null,
  last_failure_message: null,
  ...LIMITS,
};
const LOOKUP = {
  ...GSP,
  kind: "gstin_lookup",
  provider: null,
  base_url: "",
  key_last4: null,
  status: "not_connected",
  source: "gsp_account",
  credential_fields: ["api_key"],
  last_success_at: null,
};
const counts = (total: number) => ({ ok: total, failed: 0, cached: 0, blocked: 0, total });
const USAGE = [
  {
    kind: "gsp",
    today: counts(3),
    week: counts(9),
    month: { ok: 20, failed: 2, cached: 0, blocked: 0, total: 22 },
  },
  {
    kind: "gstin_lookup",
    today: counts(1),
    week: counts(4),
    month: { ok: 6, failed: 0, cached: 5, blocked: 1, total: 12 },
  },
];
const COMPANY_ROW = {
  tenant_id: 7,
  slug: "acme",
  name: "Acme Steels",
  calls_today: 4,
  calls_month: 12,
  cached_month: 0,
  blocked_month: 0,
  failed_month: 1,
  near_limit: true,
  over_limit: false,
};
const FAILURE = {
  id: 1,
  at: "2026-11-03T10:00:00Z",
  tenant_id: 7,
  tenant_name: "Acme Steels",
  operation: "generate_eway",
  error_code: "GSP_DOWN",
  latency_ms: 20,
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

const reads: [RegExp, Route][] = [
  [/\/admin\/integrations$/, () => [GSP, LOOKUP]],
  [/\/admin\/integrations\/usage$/, () => USAGE],
  [/\/admin\/integrations\/\w+\/companies$/, () => [COMPANY_ROW]],
  [/\/admin\/integrations\/\w+\/failures$/, () => [FAILURE]],
];

describe("AdminApp Integrations page (M27)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is reachable from the sidebar and with Alt 0", async () => {
    stubApi([...reads, [/\/admin\/overview$/, () => ({})]]);
    const user = userEvent.setup();
    renderAt("/admin/support");
    await screen.findByRole("navigation");
    await user.keyboard("{Alt>}{0}{/Alt}");
    expect(await screen.findByRole("heading", { name: "Integrations" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/admin/integrations");
  });

  it("shows both cards, the key's last four characters only, usage and the companies", async () => {
    stubApi(reads);
    renderAt("/admin/integrations");
    const gsp = await screen.findByRole("article", { name: "GSP (e-way bill and IRN)" });
    expect(within(gsp).getByText("Connected")).toBeInTheDocument();
    expect(within(gsp).getByText(/9876/)).toBeInTheDocument();
    expect(within(gsp).getByText("Using the settings saved here.")).toBeInTheDocument();
    const lookup = screen.getByRole("article", { name: "GSTIN lookup" });
    expect(within(lookup).getByText("Not connected here")).toBeInTheDocument();
    expect(within(lookup).getByText("Using the GSP account's settings.")).toBeInTheDocument();

    const tiles = await within(gsp).findByLabelText("GSP (e-way bill and IRN) usage");
    for (const [label, value] of [
      ["Calls today", "3"],
      ["This month", "22"],
      ["Failed (month)", "2"],
    ]) {
      const tile = within(tiles).getByText(label).closest("div");
      expect(tile).not.toBeNull();
      expect(within(tile as HTMLElement).getByText(value)).toBeInTheDocument();
    }
    const table = await within(gsp).findByRole("table", { name: /calls per company/ });
    expect(within(table).getByText("Acme Steels")).toBeInTheDocument();
    expect(within(table).getByText("Near")).toBeInTheDocument();
    expect(await within(gsp).findByText(/generate_eway · GSP_DOWN/)).toBeInTheDocument();
  });

  it("never asks for a saved key back and sends only what was typed", async () => {
    const calls = stubApi([...reads, [/\/admin\/integrations\/gsp$/, () => GSP]]);
    const user = userEvent.setup();
    renderAt("/admin/integrations");
    const gsp = await screen.findByRole("article", { name: "GSP (e-way bill and IRN)" });
    await user.click(within(gsp).getByRole("button", { name: "Edit connection" }));
    const secret = within(gsp).getByLabelText("Client secret");
    expect(secret).toHaveAttribute("type", "password");
    expect(secret).toHaveValue("");
    expect(within(gsp).getByText(/Saved key ends in 9876/)).toBeInTheDocument();
    await user.type(within(gsp).getByLabelText("Password"), "New-Portal-Pass-0001");
    await user.click(within(gsp).getByRole("button", { name: "Save connection" }));
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.url).toMatch(/\/admin\/integrations\/gsp$/);
    expect(JSON.parse(put?.body ?? "{}")).toEqual({
      provider: "sandbox",
      base_url: "https://gsp.example/api",
      client_id: null,
      client_secret: null,
      username: null,
      password: "New-Portal-Pass-0001",
    });
  });

  it("reports a failed test as an answer", async () => {
    stubApi([
      ...reads,
      [
        /\/admin\/integrations\/gsp\/test$/,
        () => ({
          ok: false,
          latency_ms: 12,
          error_code: "GSP_UNREACHABLE",
          message: "Cannot reach the GSP",
          integration: { ...GSP, status: "failing" },
        }),
      ],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/integrations");
    const gsp = await screen.findByRole("article", { name: "GSP (e-way bill and IRN)" });
    await user.click(within(gsp).getByRole("button", { name: "Test connection" }));
    expect(await within(gsp).findByText(/Connection failed: Cannot reach the GSP/)).toBeVisible();
  });

  it("saves limits and confirms before disconnecting", async () => {
    const calls = stubApi([
      ...reads,
      [/\/admin\/integrations\/gstin_lookup\/limits$/, () => LOOKUP],
      [/\/admin\/integrations\/gsp\/disconnect$/, () => ({ ...GSP, provider: null })],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/integrations");
    const lookup = await screen.findByRole("article", { name: "GSTIN lookup" });
    await user.click(within(lookup).getByRole("button", { name: "Limits" }));
    const daily = within(lookup).getByLabelText("Daily limit per company");
    await user.clear(daily);
    await user.type(daily, "5");
    await user.click(within(lookup).getByRole("button", { name: "Save limits" }));
    const patch = calls.find((c) => c.method === "PATCH");
    expect(JSON.parse(patch?.body ?? "{}")).toEqual({
      daily_limit: 5,
      monthly_limit: 500,
      warn_at_percent: 80,
      cache_hours: 168,
    });

    const gsp = screen.getByRole("article", { name: "GSP (e-way bill and IRN)" });
    await user.click(within(gsp).getByRole("button", { name: "Disconnect" }));
    expect(calls.some((c) => c.url.endsWith("/gsp/disconnect"))).toBe(false); // asks first
    const confirm = within(gsp).getByRole("group", { name: "Confirm disconnect" });
    await user.click(within(confirm).getByRole("button", { name: "Disconnect" }));
    expect(calls.some((c) => c.url.endsWith("/gsp/disconnect") && c.method === "POST")).toBe(true);
  });

  it("gives Support the status only: no buttons, usage or companies", async () => {
    const calls = stubApi([...reads], SUPPORT);
    renderAt("/admin/integrations");
    const gsp = await screen.findByRole("article", { name: "GSP (e-way bill and IRN)" });
    expect(within(gsp).getByText("Connected")).toBeInTheDocument();
    expect(within(gsp).queryByRole("button")).toBeNull();
    expect(within(gsp).queryByText("Companies this month")).toBeNull();
    expect(calls.some((c) => /usage|companies|failures/.test(c.url))).toBe(false);
  });

  it("warns when the server has no secret key to save keys with", async () => {
    stubApi([
      [/\/admin\/integrations$/, () => [{ ...GSP, secret_key_set: false }, LOOKUP]],
      ...reads.slice(1),
    ]);
    renderAt("/admin/integrations");
    expect(await screen.findAllByText(/INTEGRATION_SECRET_KEY is not set/)).toHaveLength(1);
  });
});
