import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

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
const SUPPORT = {
  ...ADMIN,
  id: 2,
  email: "help@duolink.app",
  full_name: "Help Desk",
  role: "support",
};
const signedIn = (admin: object) => ({
  access_token: "t",
  token_type: "bearer",
  expires_in: 1800,
  admin,
});

const MEMBER = {
  id: 3,
  email: "meena@duolink.app",
  full_name: "Meena Iyer",
  mobile: "+91 98765 43210",
  role: "support",
  is_active: true,
  locked: false,
  must_change_password: false,
  open_sessions: 0,
  last_login_at: null,
  created_at: "2026-10-30T09:00:00Z",
};
const ME_ROW = {
  ...MEMBER,
  id: 1,
  email: ADMIN.email,
  full_name: ADMIN.full_name,
  role: "super_admin",
};

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

const failure = (status: number, code: string, message: string) =>
  new Response(JSON.stringify({ code, message }), { status });

/** Answer each request from `routes` by its path (first match wins); anything else is 404. */
function stubApi(routes: [RegExp, Route][], admin: object | null = ADMIN) {
  const calls: { url: string; method: string; body?: string }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
    if (url.endsWith("/admin/auth/refresh")) {
      return admin
        ? new Response(JSON.stringify(signedIn(admin)), { status: 200 })
        : new Response(JSON.stringify({ code: "NOT_AUTHENTICATED" }), { status: 401 });
    }
    const match = routes.find(([pattern]) => pattern.test(url));
    if (match) {
      const answer = match[1](url, init);
      if (answer instanceof Response) return answer;
      return new Response(JSON.stringify(answer), { status: 200 });
    }
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
    stubApi([], null);
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

  it("shows the signed-in admin's role beside their name", async () => {
    stubApi([[/\/admin\/overview$/, () => OVERVIEW]]);
    renderAt("/admin");
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByText("Super Admin")).toBeInTheDocument();
  });
});

describe("AdminApp roles (ADR 0013)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows Support the company list and the role, with no button to add a company", async () => {
    stubApi([[/\/admin\/tenants\?/, () => page([ACME])]], SUPPORT);
    renderAt("/admin/companies");
    expect(await screen.findByRole("link", { name: "Acme Steels" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add company" })).not.toBeInTheDocument();
    expect(screen.getByText("Support")).toBeInTheDocument();
  });

  it("keeps Support out of the company form and the change buttons", async () => {
    stubApi(
      [
        [/\/admin\/tenants\/7$/, () => ACME_DETAIL],
        [/\/admin\/users\?/, () => page([])],
      ],
      SUPPORT,
    );
    renderAt("/admin/companies/7");
    expect(await screen.findByRole("heading", { name: "Acme Steels" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save plan" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Suspend company" })).not.toBeInTheDocument();
    expect(screen.getByText("Only a Super Admin changes a company.")).toBeInTheDocument();
  });

  it("sends Support back from the add-company address", async () => {
    stubApi([[/\/admin\/tenants\?/, () => page([ACME])]], SUPPORT);
    renderAt("/admin/companies/new");
    expect(await screen.findByRole("heading", { name: "Companies" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Company code")).not.toBeInTheDocument();
  });

  it("gives Support a user's facts but none of the support actions", async () => {
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
    stubApi([[/\/admin\/users\?/, () => page([ravi])]], SUPPORT);
    const user = userEvent.setup();
    renderAt("/admin/users");
    await user.click(await screen.findByRole("button", { name: "Ravi Kumar" }));
    expect(await screen.findByRole("complementary", { name: "Ravi Kumar" })).toHaveTextContent(
      "Acme Steels",
    );
    for (const name of ["Reset password", "Deactivate", "Sign out everywhere"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("lets Support read the staff list but not add or edit anyone", async () => {
    stubApi([[/\/admin\/staff$/, () => [ME_ROW, MEMBER]]], SUPPORT);
    const user = userEvent.setup();
    renderAt("/admin/staff");
    expect(await screen.findByText("meena@duolink.app")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add staff member" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Meena Iyer" }));
    expect(screen.queryByRole("button", { name: "Reset password" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });
});

describe("AdminApp staff", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("adds a staff member who defaults to Support, with a temporary password", async () => {
    const staff = [ME_ROW];
    const calls = stubApi([
      [
        /\/admin\/staff$/,
        (_url, init) => {
          if (init?.method === "POST") {
            staff.push(MEMBER);
            return MEMBER;
          }
          return staff;
        },
      ],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/staff");
    await user.click(await screen.findByRole("button", { name: "Add staff member" }));
    await user.type(screen.getByLabelText("Full name"), "Meena Iyer");
    await user.type(screen.getByLabelText("Email"), "meena@duolink.app");
    await user.type(screen.getByLabelText("Mobile"), "+91 98765 43210");
    expect(screen.getByLabelText("Role")).toHaveValue("support");
    await user.type(screen.getByLabelText("Temporary password"), "temp-pass-123");
    await user.click(
      within(screen.getByRole("form", { name: "Add staff member" })).getByRole("button", {
        name: "Add staff member",
      }),
    );
    const sent = calls.find((c) => c.method === "POST" && c.url.endsWith("/admin/staff"));
    expect(JSON.parse(sent?.body ?? "{}")).toEqual({
      full_name: "Meena Iyer",
      email: "meena@duolink.app",
      mobile: "+91 98765 43210",
      password: "temp-pass-123",
      role: "support",
    });
    expect(await screen.findByRole("button", { name: "Meena Iyer" })).toBeInTheDocument();
  });

  it("will not send a temporary password that is too short", async () => {
    const calls = stubApi([[/\/admin\/staff$/, () => [ME_ROW]]]);
    const user = userEvent.setup();
    renderAt("/admin/staff");
    await user.click(await screen.findByRole("button", { name: "Add staff member" }));
    await user.type(screen.getByLabelText("Full name"), "Meena Iyer");
    await user.type(screen.getByLabelText("Email"), "meena@duolink.app");
    await user.type(screen.getByLabelText("Temporary password"), "short");
    await user.click(
      within(screen.getByRole("form", { name: "Add staff member" })).getByRole("button", {
        name: "Add staff member",
      }),
    );
    expect(await screen.findByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/admin/staff"))).toBe(false);
  });

  it("does not let an admin change their own role, and shows the server's refusal", async () => {
    stubApi([
      [
        /\/admin\/staff\/1$/,
        () =>
          failure(409, "SELF_CHANGE", "You cannot change your own role or deactivate yourself."),
      ],
      [/\/admin\/staff$/, () => [ME_ROW, MEMBER]],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/staff");
    await user.click(await screen.findByRole("button", { name: "Duolink Ops" }));
    expect(screen.getByLabelText("Role")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Deactivate" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You cannot change your own role");
  });

  it("shows a staff member's reset password once", async () => {
    stubApi([
      [/\/admin\/staff\/3\/reset-password$/, () => ({ temporary_password: "Temp-Staff-77" })],
      [/\/admin\/staff$/, () => [ME_ROW, MEMBER]],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/staff");
    await user.click(await screen.findByRole("button", { name: "Meena Iyer" }));
    await user.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByLabelText("Temporary password")).toHaveTextContent("Temp-Staff-77");
  });
});

describe("AdminApp temporary passwords", () => {
  afterEach(() => vi.unstubAllGlobals());

  const TEMPORARY = { ...SUPPORT, must_change_password: true };

  it("sends an admin with a temporary password to the change screen from any page", async () => {
    stubApi([[/\/admin\/overview$/, () => OVERVIEW]], TEMPORARY);
    renderAt("/admin/companies");
    expect(
      await screen.findByRole("heading", { name: "Choose a new password" }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/admin/change-password");
  });

  it("changes the password, signs out, and asks for the new one at sign-in", async () => {
    const calls = stubApi(
      [[/\/admin\/auth\/change-password$/, () => new Response(null, { status: 204 })]],
      TEMPORARY,
    );
    const user = userEvent.setup();
    renderAt("/admin");
    await user.type(await screen.findByLabelText("Temporary password"), "temp-pass-123");
    await user.type(screen.getByLabelText("New password"), "brand-new-pass-1");
    await user.type(screen.getByLabelText("New password again"), "brand-new-pass-2");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("The two new passwords are not the same.")).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith("/change-password"))).toBe(false);

    await user.clear(screen.getByLabelText("New password again"));
    await user.type(screen.getByLabelText("New password again"), "brand-new-pass-1");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    const sent = calls.find((c) => c.url.endsWith("/change-password"));
    expect(JSON.parse(sent?.body ?? "{}")).toEqual({
      current_password: "temp-pass-123",
      new_password: "brand-new-pass-1",
    });
    expect(await screen.findByRole("heading", { name: "Duolink admin" })).toBeInTheDocument();
    expect(screen.getByText("Password changed. Sign in with the new one.")).toBeInTheDocument();
  });

  it("shows the server's reason when the new password is refused", async () => {
    stubApi(
      [
        [
          /\/admin\/auth\/change-password$/,
          () => failure(409, "PASSWORD_UNCHANGED", "Choose a password you have not used just now."),
        ],
      ],
      TEMPORARY,
    );
    const user = userEvent.setup();
    renderAt("/admin/change-password");
    await user.type(await screen.findByLabelText("Temporary password"), "temp-pass-123");
    await user.type(screen.getByLabelText("New password"), "temp-pass-123");
    await user.type(screen.getByLabelText("New password again"), "temp-pass-123");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(
      await screen.findByText("Choose a password you have not used just now."),
    ).toBeInTheDocument();
  });
});
