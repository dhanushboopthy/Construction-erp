import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { setAccessToken } from "@/api/client";
import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import {
  ReadOnlyContext,
  ReadOnlyReasonContext,
  SUPPORT_READ_ONLY_REASON,
} from "@/auth/ReadOnlyContext";
import { Button } from "@/components/Button";
import { OWNER, mockApi, session } from "@/test/mockApi";

const NOW = Date.now();
const GRANT = {
  id: 3,
  status: "live",
  starts_at: new Date(NOW).toISOString(),
  ends_at: new Date(NOW + 4 * 3600_000).toISOString(),
  seconds_left: 14_400,
  include_costs: false,
  reason: "The bill print looks wrong",
  ticket_id: null,
  ticket_number: null,
  granted_by_name: "Shop Owner",
  revoked_at: null,
  revoked_by_name: null,
};
const VISIT = {
  id: 9,
  grant_id: 3,
  admin_name: "Duolink Ops",
  reason: "Checking the bill print",
  status: "ended",
  started_at: "2026-11-05T08:00:00Z",
  ended_at: "2026-11-05T08:30:00Z",
  end_reason: "exited",
  request_count: 14,
  include_costs: false,
};
const SUPPORT_USER = {
  ...OWNER,
  id: 0,
  username: "duolink-support",
  full_name: "Duolink support: Duolink Ops",
};
const STATUS = {
  session_id: 9,
  company_name: "Anand Steels",
  admin_name: "Duolink Ops",
  started_at: "2026-11-05T08:00:00Z",
  expires_at: "2026-11-05T11:10:00Z",
  grant_ends_at: "2026-11-05T11:10:00Z",
  include_costs: false,
  read_only: true,
};
const TENANT = { name: "Anand Steels", tagline: "t", access_state: "full" };

const shell = {
  "GET /tenant": () => ({ body: TENANT }),
  "GET /stock": () => ({ body: [] }),
  "GET /eway-bills/pending": () => ({ body: [] }),
  "GET /support/tickets/unread-count": () => ({ body: { unread: 0 } }),
  "GET /support/tickets": () => ({ body: { items: [], total: 0, limit: 0, offset: 0 } }),
};

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => {
  setAccessToken(null);
  vi.unstubAllGlobals();
});

describe("Duolink support access, the owner's side (M23)", () => {
  it("shows access off, with the history, and grants it with the chosen terms", async () => {
    let live: object | null = null;
    const { calls } = mockApi({
      ...session(OWNER),
      ...shell,
      "GET /support-access": () => ({ body: { live, recent: [], durations: [1, 4, 24, 72] } }),
      "GET /support-access/sessions": () => ({ body: [VISIT] }),
      "POST /support-access/grants": () => {
        live = GRANT;
        return { status: 201, body: GRANT };
      },
    });
    const user = userEvent.setup();
    renderAt("/settings/support-access");
    expect(
      await screen.findByText("Access is off. Duolink cannot enter this company."),
    ).toBeInTheDocument();
    const history = await screen.findByRole("table");
    expect(within(history).getByText("Duolink Ops")).toBeInTheDocument();
    expect(within(history).getByText("14")).toBeInTheDocument();
    expect(within(history).getByText("Duolink left")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("For how long"), "24");
    await user.type(screen.getByLabelText("What do you want help with"), "Bill print is blank");
    await user.click(screen.getByLabelText("Show cost and margin"));
    await user.click(screen.getByRole("button", { name: "Give access" }));

    const post = calls.find((c) => c.method === "POST" && c.path === "/support-access/grants");
    expect(post?.body).toEqual({
      duration_hours: 24,
      include_costs: true,
      reason: "Bill print is blank",
      ticket_id: null,
    });
    expect(await screen.findByText("Access is on")).toBeInTheDocument();
  });

  it("shows the live grant with its time left and turns it off at once", async () => {
    let live: object | null = GRANT;
    const { calls } = mockApi({
      ...session(OWNER),
      ...shell,
      "GET /support-access": () => ({ body: { live, recent: [GRANT], durations: [1, 4, 24, 72] } }),
      "GET /support-access/sessions": () => ({ body: [] }),
      "POST /support-access/revoke": () => {
        live = null;
        return { body: { ...GRANT, status: "revoked" } };
      },
    });
    const user = userEvent.setup();
    renderAt("/settings/support-access");
    const on = await screen.findByRole("status", { name: "Support access is on" });
    expect(on).toHaveTextContent(/3 h (5\d|4\d) min left/);
    expect(on).toHaveTextContent("The bill print looks wrong");
    await user.click(screen.getByRole("button", { name: "Turn off now" }));
    expect(
      await screen.findByText("Access is off. Duolink cannot enter this company."),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.path === "/support-access/revoke")).toBe(
      true,
    );
  });

  it("is a Settings section for the owner", async () => {
    mockApi({
      ...session(OWNER),
      ...shell,
      "GET /support-access": () => ({
        body: { live: null, recent: [], durations: [1, 4, 24, 72] },
      }),
      "GET /support-access/sessions": () => ({ body: [] }),
    });
    renderAt("/settings");
    expect(await screen.findByRole("link", { name: "Duolink support access" })).toHaveAttribute(
      "href",
      "/settings/support-access",
    );
  });
});

describe("Inside a Duolink support session (M23)", () => {
  function enter() {
    return mockApi({
      ...shell,
      "GET /auth/me": () => ({ body: SUPPORT_USER }),
      "GET /support-session": () => ({ body: STATUS }),
      "POST /support-session/exit": () => ({ status: 204 }),
      "GET /reports/today": () => ({ body: null, status: 404 }),
    });
  }

  it("keeps the token in memory, removes it from the address bar and never tries a refresh", async () => {
    const { calls } = enter();
    renderAt("/support-entry#token=abc.def.ghi");
    expect(await screen.findByRole("status", { name: "Duolink support session" })).toBeVisible();
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/");
    expect(calls.some((c) => c.path === "/auth/refresh")).toBe(false);
    const me = calls.find((c) => c.path === "/auth/me");
    expect(me?.headers.authorization).toBe("Bearer abc.def.ghi");
    expect(window.localStorage.length + window.sessionStorage.length).toBe(0);
  });

  it("shows the banner with the company, read-only and when it ends", async () => {
    enter();
    renderAt("/support-entry#token=abc");
    const banner = await screen.findByRole("status", { name: "Duolink support session" });
    expect(banner).toHaveTextContent("Super Admin Mode");
    expect(banner).toHaveTextContent("Duolink support · read-only · viewing Anand Steels · ends ");
    expect(banner).not.toHaveTextContent("cost and margin shown");
    expect(within(banner).getByRole("button", { name: "Exit" })).toBeInTheDocument();
  });

  it("turns a save button off with the reason", () => {
    render(
      <ReadOnlyContext value={true}>
        <ReadOnlyReasonContext value={SUPPORT_READ_ONLY_REASON}>
          <Button variant="primary">Save</Button>
          <Button variant="primary" allowWhenReadOnly>
            Print
          </Button>
        </ReadOnlyReasonContext>
      </ReadOnlyContext>,
    );
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    expect(save).toHaveAttribute("title", "Read-only support session");
    expect(screen.getByRole("button", { name: "Print" })).toBeEnabled();
  });

  it("hides the access setting from the session that it governs", async () => {
    enter();
    const user = userEvent.setup();
    renderAt("/support-entry#token=abc");
    await screen.findByRole("status", { name: "Duolink support session" });
    await user.click(await screen.findByRole("link", { name: /Settings/ }));
    expect(await screen.findByRole("link", { name: "Users" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Duolink support access" })).not.toBeInTheDocument();
  });

  it("Exit tells the server, forgets the token and goes to sign in", async () => {
    const { calls } = enter();
    const user = userEvent.setup();
    renderAt("/support-entry#token=abc");
    const banner = await screen.findByRole("status", { name: "Duolink support session" });
    await user.click(within(banner).getByRole("button", { name: "Exit" }));
    await waitFor(() => expect(window.location.pathname).toBe("/login"));
    expect(calls.some((c) => c.method === "POST" && c.path === "/support-session/exit")).toBe(true);
    expect(screen.queryByRole("status", { name: "Duolink support session" })).toBeNull();
  });

  it("says the link has ended when the server refuses the token", async () => {
    mockApi({
      "GET /auth/me": () => ({
        status: 401,
        body: { code: "SUPPORT_SESSION_ENDED", message: "x" },
      }),
      "GET /support-session": () => ({
        status: 401,
        body: { code: "SUPPORT_SESSION_ENDED", message: "x" },
      }),
    });
    renderAt("/support-entry#token=dead");
    expect(
      await screen.findByRole("heading", { name: "This support link has ended" }),
    ).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter the company again");
  });

  it("a link with no token says so", async () => {
    mockApi({});
    renderAt("/support-entry");
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter the company again");
  });
});
