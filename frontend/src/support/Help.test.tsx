import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, session } from "@/test/mockApi";

import { UNREAD_POLL_MS } from "./api";
import type { TicketDetail, TicketRow } from "./types";

const ROW: TicketRow = {
  id: 5,
  number: "T-000005",
  subject: "Cannot print the bill",
  category: "printing",
  priority: "high",
  status: "waiting_on_company",
  raised_by_name: "Shop Owner",
  created_at: "2026-10-30T09:00:00Z",
  last_reply_at: "2026-10-31T09:00:00Z",
  unread: true,
};
const DETAIL: TicketDetail = {
  ...ROW,
  assigned_admin_name: "Duolink Ops",
  closed_at: null,
  can_close: true,
  messages: [
    {
      id: 1,
      author_kind: "company_user",
      author_name: "Shop Owner",
      body: "The PDF is blank.",
      created_at: "2026-10-30T09:00:00Z",
    },
    {
      id: 2,
      author_kind: "platform_admin",
      author_name: "Duolink Ops",
      body: "Which printer do you use?",
      created_at: "2026-10-31T09:00:00Z",
    },
  ],
};
const TENANT = { name: "Anand Steels", tagline: "t" };

function shell(
  user = OWNER,
  extra: Record<string, Parameters<typeof mockApi>[0][string]> = {},
  tenant: object = TENANT,
) {
  return mockApi({
    ...session(user),
    "GET /tenant": () => ({ body: tenant }),
    "GET /stock": () => ({ body: [] }),
    "GET /eway-bills/pending": () => ({ body: [] }),
    "GET /support/tickets/unread-count": () => ({ body: { unread: 0 } }),
    ...extra,
  });
}

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Help menu entry (M22)", () => {
  it("shows no dot when nothing is unread", async () => {
    shell();
    const user = userEvent.setup();
    renderAt("/items");
    await user.click(await screen.findByRole("button", { name: /Account menu/ }));
    expect(await screen.findByRole("link", { name: "Help" })).toHaveAttribute("href", "/help");
    expect(screen.queryByTestId("help-dot")).not.toBeInTheDocument();
  });

  it("shows a dot on Help when a reply is unread", async () => {
    shell(OWNER, { "GET /support/tickets/unread-count": () => ({ body: { unread: 2 } }) });
    const user = userEvent.setup();
    renderAt("/items");
    await user.click(await screen.findByRole("button", { name: /Account menu/ }));
    expect(await screen.findByTestId("help-dot")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Help/ })).toHaveTextContent("2 new replies");
  });

  it("asks for the unread count again every minute", async () => {
    expect(UNREAD_POLL_MS).toBe(60_000);
    shell();
    const client = createQueryClient();
    window.history.pushState({}, "", "/items");
    render(<App client={client} />);
    await screen.findByRole("button", { name: /Account menu/ });
    await waitFor(() => {
      const query = client.getQueryCache().find({ queryKey: ["support", "unread"] });
      expect(query?.observers[0]?.options.refetchInterval).toBe(60_000);
    });
  });
});

describe("Help page (M22)", () => {
  it("lists tickets and filters by status", async () => {
    const { calls } = shell(OWNER, {
      "GET /support/tickets": () => ({ body: { items: [ROW], total: 1 } }),
    });
    const user = userEvent.setup();
    renderAt("/help");
    expect(await screen.findByRole("link", { name: "Cannot print the bill" })).toHaveAttribute(
      "href",
      "/help/5",
    );
    expect(screen.getByText("T-000005")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("Waiting on company")).toBeInTheDocument();
    expect(screen.getByText("New reply:")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Status"), "closed");
    await waitFor(() => expect(window.location.search).toBe("?status=closed"));
    // A second request goes out for the chosen status.
    await waitFor(() =>
      expect(calls.filter((c) => c.path === "/support/tickets").length).toBeGreaterThan(1),
    );
  });

  it("is the same screen for a counter user", async () => {
    shell(COUNTER, { "GET /support/tickets": () => ({ body: { items: [], total: 0 } }) });
    renderAt("/help");
    expect(await screen.findByText(/No tickets yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New ticket" })).toBeEnabled();
  });

  it("raises a ticket and opens it", async () => {
    const { calls } = shell(OWNER, {
      "GET /support/tickets": () => ({ body: { items: [], total: 0 } }),
      "POST /support/tickets": () => ({ status: 201, body: { ...DETAIL, unread: false } }),
      "GET /support/tickets/5": () => ({ body: DETAIL }),
    });
    const user = userEvent.setup();
    renderAt("/help");
    await user.click(await screen.findByRole("button", { name: "New ticket" }));
    const form = screen.getByRole("form", { name: "New ticket" });
    await user.click(screen.getByRole("button", { name: "Send ticket" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/subject/);
    await user.type(screen.getByLabelText("Subject"), "Cannot print the bill");
    await user.selectOptions(screen.getByLabelText("Category"), "printing");
    await user.selectOptions(screen.getByLabelText("Priority"), "high");
    await user.type(screen.getByLabelText("Message"), "The PDF is blank.");
    expect(form).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send ticket" }));
    expect(
      await screen.findByRole("heading", { name: "Cannot print the bill" }),
    ).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST" && c.path === "/support/tickets")?.body).toEqual({
      subject: "Cannot print the bill",
      category: "printing",
      priority: "high",
      body: "The PDF is blank.",
    });
    expect(window.location.pathname).toBe("/help/5");
  });

  it("keeps Help usable when the company is read-only", async () => {
    shell(
      OWNER,
      { "GET /support/tickets": () => ({ body: { items: [], total: 0 } }) },
      { ...TENANT, access_state: "read_only" },
    );
    const user = userEvent.setup();
    renderAt("/help");
    const button = await screen.findByRole("button", { name: "New ticket" });
    await waitFor(() => expect(screen.getByText(/read-only|ended/i)).toBeInTheDocument());
    expect(button).toBeEnabled();
    await user.click(button);
    expect(screen.getByRole("button", { name: "Send ticket" })).toBeEnabled();
  });
});

describe("Ticket thread (M22)", () => {
  const open = (extra: Record<string, Parameters<typeof mockApi>[0][string]> = {}, user = OWNER) =>
    shell(user, { "GET /support/tickets/5": () => ({ body: DETAIL }), ...extra });

  it("shows the conversation and sends a reply", async () => {
    const { calls } = open({
      "POST /support/tickets/5/reply": () => ({ body: DETAIL }),
    });
    const user = userEvent.setup();
    renderAt("/help/5");
    expect(await screen.findByText("Which printer do you use?")).toBeInTheDocument();
    expect(screen.getByText("The PDF is blank.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Your reply"), "An HP laser.");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path === "/support/tickets/5/reply")?.body).toEqual({
        body: "An HP laser.",
      }),
    );
    await waitFor(() => expect(screen.getByLabelText("Your reply")).toHaveValue(""));
  });

  it("closes a ticket the signed-in user raised", async () => {
    let current: TicketDetail = DETAIL;
    const { calls } = open({
      "GET /support/tickets/5": () => ({ body: current }),
      "POST /support/tickets/5/close": () => {
        current = {
          ...DETAIL,
          status: "closed",
          closed_at: "2026-11-01T09:00:00Z",
          can_close: false,
        };
        return { body: current };
      },
    });
    const user = userEvent.setup();
    renderAt("/help/5");
    await user.click(await screen.findByRole("button", { name: "Close ticket" }));
    expect(await screen.findByText(/This ticket is closed/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/support/tickets/5/close")).toBe(true);
    expect(screen.queryByRole("button", { name: "Close ticket" })).not.toBeInTheDocument();
  });

  it("offers no Close ticket on a ticket someone else raised", async () => {
    open({ "GET /support/tickets/5": () => ({ body: { ...DETAIL, can_close: false } }) }, COUNTER);
    renderAt("/help/5");
    await screen.findByText("Which printer do you use?");
    expect(screen.queryByRole("button", { name: "Close ticket" })).not.toBeInTheDocument();
  });

  it("has no reply box on a closed ticket", async () => {
    open({ "GET /support/tickets/5": () => ({ body: { ...DETAIL, status: "closed" } }) });
    renderAt("/help/5");
    expect(await screen.findByText(/This ticket is closed/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Your reply")).not.toBeInTheDocument();
  });

  it("says in plain words when the ticket was closed meanwhile", async () => {
    open({
      "POST /support/tickets/5/reply": () => ({
        status: 409,
        body: { code: "TICKET_CLOSED", message: "ticket closed", field: null },
      }),
    });
    const user = userEvent.setup();
    renderAt("/help/5");
    await user.type(await screen.findByLabelText("Your reply"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/This ticket is closed/);
  });

  it("can still reply and close while the company is read-only", async () => {
    open({}, OWNER);
    shell(
      OWNER,
      { "GET /support/tickets/5": () => ({ body: DETAIL }) },
      { ...TENANT, access_state: "read_only" },
    );
    renderAt("/help/5");
    expect(await screen.findByRole("button", { name: "Send reply" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Close ticket" })).toBeEnabled();
  });
});
