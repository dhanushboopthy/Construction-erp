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
  open_sessions: 2,
};

const kind = (key: string, label: string, count: number, blocked_by: object[] = []) => ({
  key,
  label,
  count,
  tables: [{ table: key, count }],
  blocked_by,
  can_delete: blocked_by.length === 0,
});
const INVENTORY = {
  company_name: "Acme Steels",
  total: 160,
  items: [
    kind("quotes", "Quotations and proformas", 3),
    kind("sales", "Sales bills", 120),
    kind("parties", "Parties and sites", 37, [{ key: "sales", label: "Sales bills", count: 120 }]),
  ],
};
const PREVIEW = {
  everything: false,
  kinds: [],
  tables: [{ table: "sales_quote", count: 3 }],
  total: 3,
  files: 0,
  blocked: [],
  message: null,
};
const RESULT = {
  operation: "selected",
  kinds: ["quotes"],
  tables: [{ table: "sales_quote", count: 3 }],
  total: 3,
  backup_id: 44,
  series_reset: [{ series: "S1Q/26-27", from_number: 4, to_number: 1 }],
  files_removed: 0,
};
const SERIES = {
  location_id: 1,
  location_code: "S1",
  doc_type: "sales_invoice",
  doc_label: "Bill",
  financial_year: "26-27",
  prefix: "S1",
  highest_existing: 7,
  highest_number: "S1/26-27/00007",
  configured_next: 8,
  minimum_next: 8,
  next_document: "S1/26-27/00008",
  ahead_of_documents: false,
  suggested_next: null,
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

function rowOf(table: HTMLElement, text: string): HTMLElement {
  const row = within(table)
    .getAllByRole("row")
    .find((r) => within(r).queryByText(text));
  if (!row) throw new Error(`No row for ${text}`);
  return row;
}

const base: [RegExp, Route][] = [
  [/\/admin\/notifications$/, () => ({ count: 0, items: [] })],
  [/\/admin\/tenants\/7$/, () => TENANT],
];

afterEach(() => vi.unstubAllGlobals());

describe("Company Data tab (M26)", () => {
  it("is hidden from Support and shown to a Super Admin", async () => {
    stubApi(base, SUPPORT);
    renderAt("/admin/companies/7");
    expect(await screen.findByRole("heading", { name: "Acme Steels" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Data" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Numbering" })).not.toBeInTheDocument();
    vi.unstubAllGlobals();
    stubApi(base);
    renderAt("/admin/companies/7");
    expect(await screen.findByRole("link", { name: "Data" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Numbering" })).toBeInTheDocument();
  });

  it("lists each kind with its blockers and shows four columns on View", async () => {
    stubApi([
      ...base,
      [
        /\/tenants\/7\/data\/quotes$/,
        () => ({
          key: "quotes",
          label: "Quotations and proformas",
          columns: ["Number", "Kind", "Date", "Customer"],
          rows: [["S1Q/26-27/00003", "quotation", "2026-11-02", "Ravi Builders"]],
          total: 3,
        }),
      ],
      [/\/tenants\/7\/data$/, () => INVENTORY],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=data");
    const table = await screen.findByRole("table", { name: "Company data" });
    expect(within(table).getByText("120 Sales bills")).toBeInTheDocument();
    expect(within(table).getByText("Parties and sites")).toBeInTheDocument();
    const [view] = within(table).getAllByRole("button", { name: "View" });
    await user.click(view as HTMLElement);
    const panel = await screen.findByRole("region", {
      name: "Latest rows of Quotations and proformas",
    });
    expect(within(panel).getAllByRole("columnheader")).toHaveLength(4);
    expect(within(panel).getByText("Ravi Builders")).toBeInTheDocument();
  });

  it("asks for a fresh preview each time the dialog opens and waits for the typed word", async () => {
    const calls = stubApi([
      ...base,
      [/\/data\/preview/, () => PREVIEW],
      [/\/data\/delete$/, () => RESULT],
      [/\/tenants\/7\/data$/, () => INVENTORY],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=data");
    const table = await screen.findByRole("table", { name: "Company data" });
    const quotes = rowOf(table, "Quotations and proformas");
    await user.click(within(quotes).getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Delete company data" });
    expect(await within(dialog).findByText(/will be removed/)).toBeInTheDocument();
    const confirm = within(dialog).getByRole("button", { name: "Delete selected data" });
    expect(confirm).toBeDisabled();
    const field = within(dialog).getByLabelText("Type DELETE to continue");
    await user.type(field, "delete");
    expect(confirm).toBeDisabled(); // the word is case-sensitive
    await user.clear(field);
    await user.type(field, "DELETE");
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    expect(await within(dialog).findByText(/safety backup \(number 44\)/)).toBeInTheDocument();
    expect(within(dialog).getByText(/S1Q\/26-27 \(was 4\)/)).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && /\/data\/delete$/.test(c.url));
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ keys: ["quotes"], confirm: "DELETE" });

    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    await user.click(within(quotes).getByRole("button", { name: "Delete" }));
    await screen.findByRole("alertdialog", { name: "Delete company data" });
    await waitFor(() =>
      expect(calls.filter((c) => /\/data\/preview/.test(c.url)).length).toBeGreaterThanOrEqual(2),
    );
  });

  it("keeps delete disabled and names the blocker when a selection is blocked", async () => {
    stubApi([
      ...base,
      [
        /\/data\/preview/,
        () => ({
          ...PREVIEW,
          message: "Parties and sites is blocked by 120 Sales bills.",
          blocked: [{ key: "parties", label: "Parties and sites", blocked_by: [] }],
        }),
      ],
      [/\/tenants\/7\/data$/, () => INVENTORY],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=data");
    const table = await screen.findByRole("table", { name: "Company data" });
    const parties = rowOf(table, "Parties and sites");
    await user.click(within(parties).getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Delete company data" });
    expect(await within(dialog).findByText(/blocked by 120 Sales bills/)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText("Type DELETE to continue"), "DELETE");
    expect(within(dialog).getByRole("button", { name: "Delete selected data" })).toBeDisabled();
  });

  it("enables delete-everything only with the word, the exact name and the tick", async () => {
    const calls = stubApi([
      ...base,
      [/\/data\/preview/, () => ({ ...PREVIEW, everything: true, total: 160 })],
      [/\/data\/delete-all$/, () => ({ ...RESULT, operation: "all" })],
      [/\/tenants\/7\/data$/, () => INVENTORY],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=data");
    const zone = await screen.findByRole("region", { name: "Danger zone" });
    await user.click(within(zone).getByRole("button", { name: "Delete all company data…" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Delete all company data" });
    await within(dialog).findByText(/will be removed/);
    const go = within(dialog).getByRole("button", { name: "Delete all company data" });
    expect(go).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Type DELETE to continue"), "DELETE");
    const name = within(dialog).getByLabelText("Type the company's exact name");
    await user.type(name, "acme steels");
    await user.click(within(dialog).getByRole("checkbox"));
    expect(go).toBeDisabled(); // wrong case
    await user.clear(name);
    await user.type(name, "Acme Steels");
    expect(go).toBeEnabled();
    await user.click(go);
    await waitFor(() => expect(calls.some((c) => /\/data\/delete-all$/.test(c.url))).toBe(true));
    const post = calls.find((c) => /\/data\/delete-all$/.test(c.url));
    expect(JSON.parse(post?.body ?? "{}")).toEqual({
      confirm: "DELETE",
      company_name: "Acme Steels",
      acknowledged: true,
    });
  });
});

describe("Company Numbering tab (M26)", () => {
  it("shows both numbers and the next document, and refuses a low value as it is typed", async () => {
    const calls = stubApi([
      ...base,
      [
        /\/tenants\/7\/numbering$/,
        (_url, init) =>
          init?.method === "PATCH"
            ? { ...SERIES, configured_next: 20, next_document: "S1/26-27/00020" }
            : { items: [SERIES] },
      ],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=numbering");
    const table = await screen.findByRole("table", { name: "Number series" });
    expect(within(table).getByText("S1/26-27/00008")).toBeInTheDocument();
    expect(within(table).getByText("Bill")).toBeInTheDocument();
    await user.click(within(table).getByRole("button", { name: "Set" }));
    const form = await screen.findByRole("form", { name: /Set Bill number for S1 26-27/ });
    const next = within(form).getByLabelText("Next number");
    await user.clear(next);
    await user.type(next, "5");
    expect(
      await within(form).findByText("The next number must be 8 or higher."),
    ).toBeInTheDocument();
    const save = within(form).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    await user.clear(next);
    await user.type(next, "20");
    expect(save).toBeDisabled(); // a reason is required
    await user.type(within(form).getByLabelText("Reason"), "New printed book");
    expect(save).toBeEnabled();
    await user.click(save);
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    const patch = calls.find((c) => c.method === "PATCH");
    expect(JSON.parse(patch?.body ?? "{}")).toEqual({
      location_id: 1,
      doc_type: "sales_invoice",
      financial_year: "26-27",
      next_number: 20,
      reason: "New printed book",
    });
  });

  it("says when a counter is ahead of its documents and offers the value that closes the gap", async () => {
    stubApi([
      ...base,
      [
        /\/tenants\/7\/numbering$/,
        () => ({
          items: [{ ...SERIES, configured_next: 20, ahead_of_documents: true, suggested_next: 8 }],
        }),
      ],
    ]);
    renderAt("/admin/companies/7?tab=numbering");
    expect(await screen.findByText(/Ahead of its documents: 8 closes the gap/)).toBeInTheDocument();
  });
});
