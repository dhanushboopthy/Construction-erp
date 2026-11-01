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

const ROW = {
  id: 5,
  number: "T-000005",
  subject: "Cannot print the bill",
  category: "printing",
  priority: "urgent",
  status: "open",
  raised_by_name: "Ravi Kumar",
  created_at: "2026-10-30T09:00:00Z",
  last_reply_at: null,
  unread: true,
  tenant_id: 7,
  tenant_name: "Acme Steels",
  tenant_slug: "acme",
  assigned_admin_id: null,
  assigned_admin_name: null,
};
const DETAIL = {
  ...ROW,
  closed_at: null,
  messages: [
    {
      id: 1,
      author_kind: "company_user",
      author_name: "Ravi Kumar",
      body: "The PDF is blank.",
      created_at: "2026-10-30T09:00:00Z",
    },
  ],
};
const COUNTS = {
  open: 4,
  in_progress: 2,
  waiting_on_company: 1,
  resolved: 0,
  closed: 3,
  urgent_open: 1,
  unassigned: 3,
};
const LIST = { items: [ROW], total: 1, limit: 25, offset: 0, counts: COUNTS };
const STAFF = [
  {
    id: 1,
    full_name: "Duolink Ops",
    email: "ops@duolink.app",
    role: "super_admin",
    is_active: true,
  },
  { id: 2, full_name: "Help Desk", email: "h@duolink.app", role: "support", is_active: true },
];
const COMPANIES = {
  items: [{ id: 7, name: "Acme Steels", slug: "acme" }],
  total: 1,
  limit: 200,
  offset: 0,
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
  [/\/admin\/tenants\?/, () => COMPANIES],
  [/\/admin\/staff$/, () => STAFF],
];

describe("AdminApp Support page (M22)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("has a Support entry after Payments on Alt 9", async () => {
    stubApi([...base, [/\/admin\/support\/tickets\?/, () => LIST]]);
    const user = userEvent.setup();
    renderAt("/admin");
    const nav = await screen.findByRole("navigation");
    const links = within(nav).getAllByRole("link");
    const names = links.map((l) => l.textContent ?? "");
    expect(names.findIndex((n) => n.startsWith("Support"))).toBe(
      names.findIndex((n) => n.startsWith("Payments")) + 1,
    );
    await user.keyboard("{Alt>}{9}{/Alt}");
    expect(await screen.findByRole("heading", { name: "Support" })).toBeInTheDocument();
  });

  it("shows the counts as tiles and the queue as a table", async () => {
    stubApi([...base, [/\/admin\/support\/tickets\?/, () => LIST]]);
    renderAt("/admin/support");
    await screen.findByRole("link", { name: "Cannot print the bill" });
    const counts = screen.getByLabelText("Ticket counts");
    for (const [label, value] of [
      ["Open", "4"],
      ["In progress", "2"],
      ["Waiting on company", "1"],
      ["Urgent open", "1"],
      ["Unassigned", "3"],
    ]) {
      expect(within(counts).getByText(label).parentElement).toHaveTextContent(`${label}${value}`);
    }
    expect(screen.getByRole("link", { name: "Cannot print the bill" })).toHaveAttribute(
      "href",
      "/admin/support/5",
    );
    expect(screen.getByRole("link", { name: "Acme Steels" })).toHaveAttribute(
      "href",
      "/admin/companies/7?tab=support",
    );
    expect(screen.getByText("Unassigned", { selector: "td" })).toBeInTheDocument();
    expect(screen.getByText("New message:")).toBeInTheDocument();
  });

  it("keeps the filters in the address and sends them to the API", async () => {
    const calls = stubApi([...base, [/\/admin\/support\/tickets\?/, () => LIST]]);
    const user = userEvent.setup();
    renderAt("/admin/support");
    await screen.findByRole("link", { name: "Cannot print the bill" });
    await user.selectOptions(screen.getByLabelText("Status"), "in_progress");
    await user.selectOptions(screen.getByLabelText("Priority"), "urgent");
    await user.selectOptions(screen.getByLabelText("Assigned"), "unassigned");
    await user.selectOptions(await screen.findByRole("combobox", { name: "Company" }), "7");
    await user.type(screen.getByLabelText("Search"), "print");
    await waitFor(() => {
      const last = calls.filter((c) => c.url.includes("/support/tickets?")).at(-1)?.url ?? "";
      for (const part of [
        "status=in_progress",
        "priority=urgent",
        "assigned=unassigned",
        "tenant_id=7",
        "q=print",
      ]) {
        expect(last).toContain(part);
      }
    });
    expect(window.location.search).toContain("status=in_progress");
    expect(window.location.search).toContain("q=print");
  });

  it("reads filters from the address", async () => {
    const calls = stubApi([...base, [/\/admin\/support\/tickets\?/, () => LIST]]);
    renderAt("/admin/support?assigned=me&tenant_id=7");
    expect(await screen.findByLabelText("Assigned")).toHaveValue("me");
    await waitFor(() => {
      const last = calls.filter((c) => c.url.includes("/support/tickets?")).at(-1)?.url ?? "";
      expect(last).toContain("assigned=me");
      expect(last).toContain("tenant_id=7");
    });
  });

  it("says when nothing matches", async () => {
    stubApi([...base, [/\/admin\/support\/tickets\?/, () => ({ ...LIST, items: [], total: 0 })]]);
    renderAt("/admin/support?status=closed");
    expect(await screen.findByText(/No ticket matches/)).toBeInTheDocument();
  });
});

describe("AdminApp Support thread (M22)", () => {
  afterEach(() => vi.unstubAllGlobals());

  const thread = (admin: object = ADMIN, detail: object = DETAIL) =>
    stubApi(
      [
        ...base,
        [
          /\/admin\/support\/tickets\/5$/,
          (_u, init) =>
            init?.method === "PATCH" ? { ...detail, ...JSON.parse(String(init.body)) } : detail,
        ],
        [
          /\/admin\/support\/tickets\/5\/reply$/,
          () => ({ ...detail, status: "waiting_on_company" }),
        ],
      ],
      admin,
    );

  it("shows the conversation and sends a reply", async () => {
    const calls = thread();
    const user = userEvent.setup();
    renderAt("/admin/support/5");
    expect(await screen.findByText("The PDF is blank.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/reply or choose a status/);
    await user.type(screen.getByLabelText("Your reply"), "Which printer?");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    await waitFor(() =>
      expect(JSON.parse(calls.find((c) => c.url.endsWith("/reply"))?.body ?? "{}")).toEqual({
        body: "Which printer?",
      }),
    );
  });

  it("sends a status alone with the reply", async () => {
    const calls = thread();
    const user = userEvent.setup();
    renderAt("/admin/support/5");
    await screen.findByText("The PDF is blank.");
    await user.selectOptions(screen.getByLabelText("Set status with this reply"), "resolved");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    await waitFor(() =>
      expect(JSON.parse(calls.find((c) => c.url.endsWith("/reply"))?.body ?? "{}")).toEqual({
        status: "resolved",
      }),
    );
  });

  it("changes status and priority", async () => {
    const calls = thread();
    const user = userEvent.setup();
    renderAt("/admin/support/5");
    await screen.findByText("The PDF is blank.");
    const panel = screen.getByRole("group", { name: "Handle ticket" });
    await user.selectOptions(within(panel).getByLabelText("Status"), "in_progress");
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toBe(
        JSON.stringify({ status: "in_progress" }),
      ),
    );
    await user.selectOptions(within(panel).getByLabelText("Priority"), "low");
    await waitFor(() =>
      expect(calls.filter((c) => c.method === "PATCH").at(-1)?.body).toBe(
        JSON.stringify({ priority: "low" }),
      ),
    );
  });

  it("assigns to me, and lets a Super Admin pick any staff member", async () => {
    const calls = thread();
    const user = userEvent.setup();
    renderAt("/admin/support/5");
    await screen.findByText("The PDF is blank.");
    await user.click(screen.getByRole("button", { name: "Assign to me" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toBe(
        JSON.stringify({ assigned_admin_id: 1 }),
      ),
    );
    await user.selectOptions(await screen.findByLabelText("Assigned to"), "2");
    await waitFor(() =>
      expect(calls.filter((c) => c.method === "PATCH").at(-1)?.body).toBe(
        JSON.stringify({ assigned_admin_id: 2 }),
      ),
    );
  });

  it("gives Support only Assign to me, and never asks for the staff list", async () => {
    const calls = thread(SUPPORT);
    const user = userEvent.setup();
    renderAt("/admin/support/5");
    await screen.findByText("The PDF is blank.");
    expect(screen.queryByLabelText("Assigned to")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send reply" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Assign to me" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toBe(
        JSON.stringify({ assigned_admin_id: 2 }),
      ),
    );
    expect(calls.some((c) => c.url.endsWith("/admin/staff"))).toBe(false);
  });
});

describe("AdminApp company Support tab (M22)", () => {
  afterEach(() => vi.unstubAllGlobals());

  const TENANT = {
    id: 7,
    slug: "acme",
    name: "Acme Steels",
    status: "active",
    trial_state: "none",
  };

  it("lists this company's tickets and links to the thread", async () => {
    const calls = stubApi([
      [/\/admin\/tenants\/7$/, () => TENANT],
      [/\/admin\/support\/tickets\?/, () => LIST],
    ]);
    renderAt("/admin/companies/7?tab=support");
    const link = await screen.findByRole("link", { name: "Cannot print the bill" });
    expect(link).toHaveAttribute("href", "/admin/support/5");
    expect(calls.some((c) => c.url.includes("tenant_id=7"))).toBe(true);
    expect(screen.queryByRole("columnheader", { name: "Company" })).not.toBeInTheDocument();
  });

  it("says when the company has raised nothing", async () => {
    stubApi([
      [/\/admin\/tenants\/7$/, () => TENANT],
      [/\/admin\/support\/tickets\?/, () => ({ ...LIST, items: [], total: 0 })],
    ]);
    renderAt("/admin/companies/7?tab=support");
    expect(await screen.findByText("This company has not raised a ticket.")).toBeInTheDocument();
  });
});
