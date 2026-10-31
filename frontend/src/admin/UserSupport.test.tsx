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

const RAVI = {
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
  last_login_at: "2026-10-30T09:00:00Z",
  mobile: "+91 98765 43210",
  must_change_password: false,
  removed_at: null,
};
const SESSIONS = [
  {
    id: "s-1",
    device: "Chrome on Windows",
    user_agent: "x",
    ip: "10.0.0.5",
    signed_in_at: "2026-10-30T09:00:00Z",
    last_used_at: "2026-10-31T08:00:00Z",
    expires_at: "2026-11-30T09:00:00Z",
  },
  {
    id: "s-2",
    device: "Chrome on Android",
    user_agent: "y",
    ip: "10.0.0.9",
    signed_in_at: "2026-10-29T09:00:00Z",
    last_used_at: "2026-10-31T07:00:00Z",
    expires_at: "2026-11-30T09:00:00Z",
  },
];

const page = <T,>(items: T[], total = items.length) => ({ items, total, limit: 50, offset: 0 });
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
      if (answer === undefined) return new Response(null, { status: 204 });
      return new Response(JSON.stringify(answer), { status: 200 });
    }),
  );
  return calls;
}

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<AdminApp client={createQueryClient()} />);
}

const directory = (rows: unknown[], total?: number): [RegExp, Route] => [
  /\/admin\/users\?/,
  () => page(rows, total),
];
const sessions: [RegExp, Route] = [/\/admin\/users\/11\/sessions$/, () => SESSIONS];

async function openRavi() {
  const user = userEvent.setup();
  renderAt("/admin/users");
  await user.click(await screen.findByRole("button", { name: "Ravi Kumar" }));
  return { user, drawer: await screen.findByRole("complementary", { name: "Ravi Kumar" }) };
}

describe("AdminApp users directory (M19)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the role, status and removed filters to the API", async () => {
    const calls = stubApi([[/\/admin\/tenants\?/, () => page([])], directory([RAVI])]);
    const user = userEvent.setup();
    renderAt("/admin/users");
    await screen.findByRole("button", { name: "Ravi Kumar" });

    await user.selectOptions(screen.getByLabelText("Role"), "owner");
    await user.selectOptions(screen.getByLabelText("Status"), "locked");
    await user.click(screen.getByLabelText("Show removed"));
    await waitFor(() => {
      const last = calls.filter((c) => c.url.includes("/admin/users?")).at(-1)?.url ?? "";
      expect(last).toContain("role=owner");
      expect(last).toContain("locked=true");
      expect(last).toContain("include_removed=true");
    });

    await user.selectOptions(screen.getByLabelText("Status"), "never");
    await waitFor(() => {
      const last = calls.filter((c) => c.url.includes("/admin/users?")).at(-1)?.url ?? "";
      expect(last).toContain("never_signed_in=true");
      expect(last).not.toContain("locked=");
    });
  });

  it("pages through a long list and says where it is", async () => {
    const calls = stubApi([directory([RAVI], 120)]);
    const user = userEvent.setup();
    renderAt("/admin/users");
    expect(await screen.findByText(/120 users, showing 1 to 50/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("offset=50") && c.url.includes("limit=50"))).toBe(
        true,
      ),
    );
    expect(await screen.findByText(/showing 51 to 100/)).toBeInTheDocument();
  });

  it("says when someone has never signed in and marks removed accounts", async () => {
    const gone = { ...RAVI, id: 12, full_name: "Old Hand", last_login_at: null, removed_at: "x" };
    stubApi([directory([gone])]);
    renderAt("/admin/users");
    const row = (await screen.findByRole("button", { name: "Old Hand" })).closest("tr");
    if (!row) throw new Error("no row");
    expect(within(row).getByText("Never signed in")).toBeInTheDocument();
    expect(within(row).getByText("Removed")).toBeInTheDocument();
  });
});

describe("AdminApp user drawer (M19)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists where the user is signed in and lets a Super Admin end one session", async () => {
    const calls = stubApi([
      [/\/admin\/users\/11\/sessions\/s-2$/, () => undefined],
      sessions,
      directory([RAVI]),
    ]);
    const { user, drawer } = await openRavi();
    expect(await within(drawer).findByText("Chrome on Windows")).toBeInTheDocument();
    expect(within(drawer).getByText("10.0.0.9")).toBeInTheDocument();
    await user.click(
      within(drawer).getByRole("button", { name: "End session on Chrome on Android" }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.method === "DELETE")?.url).toMatch(/\/users\/11\/sessions\/s-2$/),
    );
  });

  it("saves an edit with the reason, and asks for one first", async () => {
    const calls = stubApi([
      [/\/admin\/users\/11$/, () => ({ ...RAVI, full_name: "Ravi K" })],
      sessions,
      directory([RAVI]),
    ]);
    const { user, drawer } = await openRavi();
    const name = within(drawer).getByLabelText("Full name");
    await user.clear(name);
    await user.type(name, "Ravi K");
    await user.click(within(drawer).getByRole("button", { name: "Save changes" }));
    expect(await within(drawer).findByText(/Write why/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);

    await user.type(within(drawer).getByLabelText("Reason for the change"), "Owner asked");
    await user.click(within(drawer).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    const sent = JSON.parse(calls.find((c) => c.method === "PATCH")?.body ?? "{}");
    expect(sent).toMatchObject({
      full_name: "Ravi K",
      username: "ravi",
      role: "owner",
      mobile: "+91 98765 43210",
      reason: "Owner asked",
    });
  });

  it("shows the server's message when the username is taken", async () => {
    stubApi([
      [
        /\/admin\/users\/11$/,
        () =>
          new Response(
            JSON.stringify({ code: "USERNAME_TAKEN", message: "That username is taken" }),
            {
              status: 409,
            },
          ),
      ],
      sessions,
      directory([RAVI]),
    ]);
    const { user, drawer } = await openRavi();
    await user.type(within(drawer).getByLabelText("Reason for the change"), "Owner asked");
    await user.click(within(drawer).getByRole("button", { name: "Save changes" }));
    expect(await within(drawer).findByRole("alert")).toHaveTextContent("That username is taken");
  });

  it("shows a reset password once, with a copy button", async () => {
    stubApi([
      [/\/admin\/users\/11\/reset-password$/, () => ({ temporary_password: "Temp-Pass-42" })],
      sessions,
      directory([RAVI]),
    ]);
    const { user, drawer } = await openRavi();
    await user.click(within(drawer).getByRole("button", { name: "Reset password" }));
    expect(await within(drawer).findByLabelText("Temporary password")).toHaveTextContent(
      "Temp-Pass-42",
    );
    expect(within(drawer).getByText(/must change it/)).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Copy password" }));
    expect(await within(drawer).findByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(await navigator.clipboard.readText()).toBe("Temp-Pass-42");
  });

  it("removes access only after the username is typed exactly, with a fresh session count", async () => {
    let sessionFetches = 0;
    const calls = stubApi([
      [
        /\/admin\/users\/11\/remove$/,
        () => ({ ...RAVI, is_active: false, removed_at: "2026-11-01T00:00:00Z" }),
      ],
      [
        /\/admin\/users\/11\/sessions$/,
        () => {
          sessionFetches += 1;
          return SESSIONS;
        },
      ],
      directory([RAVI]),
    ]);
    const { user, drawer } = await openRavi();
    await within(drawer).findByText("Chrome on Windows");
    const before = sessionFetches;

    await user.click(within(drawer).getByRole("button", { name: "Remove access…" }));
    const dialog = await screen.findByRole("alertdialog");
    await waitFor(() => expect(sessionFetches).toBeGreaterThan(before)); // fetched on open
    expect(await within(dialog).findByText(/2 sessions end now/)).toBeInTheDocument();

    const confirm = within(dialog).getByRole("button", { name: "Remove access" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Reason for removing"), "Left the company");
    await user.type(within(dialog).getByLabelText("Type ravi to confirm"), "Ravi");
    expect(confirm).toBeDisabled(); // case matters
    await user.clear(within(dialog).getByLabelText("Type ravi to confirm"));
    await user.type(within(dialog).getByLabelText("Type ravi to confirm"), "ravi");
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/remove"))).toBe(true));
    expect(JSON.parse(calls.find((c) => c.url.endsWith("/remove"))?.body ?? "{}")).toEqual({
      confirm_username: "ravi",
      reason: "Left the company",
    });
  });

  it("gives a removed account no actions at all", async () => {
    const gone = { ...RAVI, is_active: false, removed_at: "2026-11-01T00:00:00Z" };
    stubApi([directory([gone])]);
    const { drawer } = await openRavi();
    expect(within(drawer).getByText(/This account was removed/)).toBeInTheDocument();
    for (const name of ["Reactivate", "Reset password", "Save changes", "Remove access…"]) {
      expect(within(drawer).queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(within(drawer).queryByText("Signed in on")).not.toBeInTheDocument();
  });

  it("lets Support read the sessions but not end one, edit, reset or remove", async () => {
    stubApi([sessions, directory([RAVI])], SUPPORT);
    const { drawer } = await openRavi();
    expect(await within(drawer).findByText("Chrome on Android")).toBeInTheDocument();
    for (const name of [/End session/, "Save changes", "Reset password", "Remove access…"]) {
      expect(within(drawer).queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(within(drawer).queryByLabelText("Reason for the change")).not.toBeInTheDocument();
  });
});
