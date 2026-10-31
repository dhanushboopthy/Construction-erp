import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";

import { AdminApp } from "./AdminApp";
import { COMPANY_TABS } from "./companyTabs";

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
  plan: "TRIAL",
  plan_id: 1,
  plan_name: "Trial",
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
    renderAt("/admin/companies/7?tab=subscription");
    expect(await screen.findByRole("heading", { name: "Acme Steels" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save plan" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Plan")).not.toBeInTheDocument();
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

const SELLER = {
  legal_name: "Acme Steels Private Limited",
  registration_no: "33AAPFU0939F1ZV",
  pan: null,
  cin: null,
  address: "12 Race Course Road",
  state_code: "33",
};
const USAGE = {
  users: 3,
  shops: 2,
  bills_7d: 4,
  bills_30d: 12,
  bills_90d: 40,
  purchases_30d: 5,
  attachments: 2,
  attachment_bytes: 2048,
};
const FULL_DETAIL = {
  ...ACME_DETAIL,
  owner_name: "Ravi Kumar",
  owner_email: "ravi@acme.example",
  owner_mobile: "+91 98765 43210",
  city: "Coimbatore",
  state_code: "33",
  notes: "Pays by cheque.",
  last_activity_at: "2026-10-31T09:00:00Z",
  cancelled_at: null,
  cancelled_reason: null,
};
/** The form section under a heading, for fields that repeat a label (Full name, Password). */
function formSection(heading: string): HTMLElement {
  const section = screen.getByRole("heading", { name: heading }).closest("fieldset");
  if (!section) throw new Error(`no form section called ${heading}`);
  return section;
}

const planOf = (id: number, code: string, name: string, active = true) => ({
  id,
  code,
  name,
  short_description: "",
  long_description: "",
  max_users: 5 * id,
  max_locations: 2 * id,
  features: [],
  is_active: active,
  is_popular: false,
  sort_order: id,
  prices: [
    {
      id,
      duration_value: 1,
      duration_unit: "month",
      price: "0.00",
      currency: "INR",
      is_active: true,
    },
  ],
  companies: 1,
  created_at: "2026-10-24T09:00:00Z",
  updated_at: "2026-10-24T09:00:00Z",
});
const PLANS = [
  planOf(1, "TRIAL", "Trial"),
  planOf(2, "BASIC", "Basic"),
  planOf(3, "PRO", "Pro", false),
];

const COMPANY_ROUTES: [RegExp, Route][] = [
  [/\/admin\/billing\/plans/, (url) => PLANS.filter((p) => p.is_active || !url.includes("false"))],
  [/\/admin\/tenants\/7\/seller-details$/, () => SELLER],
  [/\/admin\/tenants\/7\/usage$/, () => USAGE],
  [/\/admin\/tenants\/7$/, () => FULL_DETAIL],
  [/\/admin\/users\?/, () => page([])],
  [/\/admin\/activity\?/, () => page([])],
  [/\/admin\/audit\?/, () => page([])],
];

describe("AdminApp company page (M18)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists its tabs from one registry, and a tab is kept in the address", async () => {
    expect(COMPANY_TABS.map((t) => t.key)).toEqual([
      "overview",
      "users",
      "subscription",
      "usage",
      "activity",
    ]);
    stubApi(COMPANY_ROUTES);
    const user = userEvent.setup();
    renderAt("/admin/companies/7");
    const tabs = await screen.findByRole("navigation", { name: "Company sections" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(["Overview", "Users", "Subscription", "Usage", "Activity"]);
    await user.click(within(tabs).getByRole("link", { name: "Usage" }));
    expect(window.location.search).toBe("?tab=usage");
    expect(await screen.findByText("Bills, last 90 days")).toBeInTheDocument();
    expect(screen.getByText("2 (2.0 KB)")).toBeInTheDocument();
    expect(screen.getByText(/Counts only/)).toBeInTheDocument();
  });

  it("shows Support every tab with the facts and none of the edit controls", async () => {
    stubApi(COMPANY_ROUTES, SUPPORT);
    renderAt("/admin/companies/7");
    expect(await screen.findByText("Pays by cheque.")).toBeInTheDocument();
    expect(await screen.findByText("Acme Steels Private Limited")).toBeInTheDocument();
    expect(screen.getByText("33AAPFU0939F1ZV")).toBeInTheDocument();
    for (const name of [
      "Save contact",
      "Save seller details",
      "Suspend company",
      "Close company",
      "Choose logo",
      "Remove logo",
    ]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    const tabs = screen.getByRole("navigation", { name: "Company sections" });
    expect(within(tabs).getAllByRole("link")).toHaveLength(5);
  });

  it("filters the Activity tab to this company", async () => {
    const calls = stubApi(COMPANY_ROUTES);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=activity");
    await screen.findByText("What Duolink admins did here");
    expect(calls.some((c) => /\/activity\?.*tenant_id=7/.test(c.url))).toBe(true);
    expect(calls.some((c) => /\/audit\?.*tenant_id=7/.test(c.url))).toBe(true);
    await user.click(screen.getByRole("link", { name: "Users" }));
    expect(window.location.search).toBe("?tab=users");
  });

  it("corrects the GSTIN with a reason, sending only what changed", async () => {
    const calls = stubApi([
      [
        /\/admin\/tenants\/7\/seller-details$/,
        (_u, init) =>
          init?.method === "PATCH" ? { ...SELLER, registration_no: "33ABCDE1234F1Z5" } : SELLER,
      ],
      ...COMPANY_ROUTES.slice(2),
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7");
    const gstin = await screen.findByLabelText("GSTIN");
    expect(gstin).toHaveValue("33AAPFU0939F1ZV");
    await user.clear(gstin);
    await user.type(gstin, "33abcde1234f1z5");
    await user.click(screen.getByRole("button", { name: "Save seller details" }));
    expect(await screen.findByText("Write why, in a few words.")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);

    await user.type(screen.getByLabelText("Reason for the change"), "New certificate");
    await user.click(screen.getByRole("button", { name: "Save seller details" }));
    expect(await screen.findByText("Seller details saved.")).toBeInTheDocument();
    const sent = calls.find((c) => c.method === "PATCH" && c.url.endsWith("/seller-details"));
    expect(JSON.parse(sent?.body ?? "{}")).toEqual({
      reason: "New certificate",
      registration_no: "33ABCDE1234F1Z5",
    });
  });

  it("saves the contact record, with blanks sent as null", async () => {
    const calls = stubApi([
      [
        /\/admin\/tenants\/7$/,
        (_u, init) => (init?.method === "PATCH" ? { ...FULL_DETAIL, city: "Salem" } : FULL_DETAIL),
      ],
      ...COMPANY_ROUTES.filter(([re]) => !re.test("/admin/tenants/7")),
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7");
    const city = await screen.findByLabelText("City");
    await user.clear(city);
    await user.type(city, "Salem");
    await user.clear(screen.getByLabelText("Internal notes"));
    await user.click(screen.getByRole("button", { name: "Save contact" }));
    expect(await screen.findByText("Contact saved.")).toBeInTheDocument();
    const sent = JSON.parse(calls.find((c) => c.method === "PATCH")?.body ?? "{}");
    expect(sent).toMatchObject({ city: "Salem", notes: null, owner_name: "Ravi Kumar" });
  });

  it("asks once more before closing a company, saying who is signed out", async () => {
    const calls = stubApi([
      [/\/admin\/tenants\/7\/cancel$/, () => ({ ...FULL_DETAIL, status: "cancelled" })],
      ...COMPANY_ROUTES,
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7");
    await user.click(await screen.findByRole("button", { name: "Close company" }));
    expect(
      await screen.findByText("Write why, in a few words. The company's owner may ask."),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Reason"), "Left for another vendor");
    await user.click(screen.getByRole("button", { name: "Close company" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Close Acme Steels? 2 signed-in people are signed out now",
    );
    expect(calls.some((c) => c.url.endsWith("/cancel"))).toBe(false);
    await user.click(screen.getByRole("button", { name: "Close now" }));
    const sent = calls.find((c) => c.url.endsWith("/cancel"));
    expect(sent?.method).toBe("POST");
    expect(JSON.parse(sent?.body ?? "{}")).toEqual({ reason: "Left for another vendor" });
  });

  it("reopens a closed company only with a reason", async () => {
    const closed = {
      ...FULL_DETAIL,
      status: "cancelled",
      cancelled_at: "2026-10-30T09:00:00Z",
      cancelled_reason: "Left for another vendor",
      open_sessions: 0,
    };
    const calls = stubApi([
      [/\/admin\/tenants\/7\/reactivate$/, () => FULL_DETAIL],
      [/\/admin\/tenants\/7$/, () => closed],
      ...COMPANY_ROUTES.slice(0, 2),
      ...COMPANY_ROUTES.slice(3),
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7");
    expect(await screen.findByRole("heading", { name: "Closed" })).toBeInTheDocument();
    expect(screen.getByText("Left for another vendor")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reopen company" }));
    expect(await screen.findByText("Say why this company is being reopened.")).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith("/reactivate"))).toBe(false);
    await user.type(screen.getByLabelText("Reason"), "Paid in full");
    await user.click(screen.getByRole("button", { name: "Reopen company" }));
    await vi.waitFor(() => expect(calls.some((c) => c.url.endsWith("/reactivate"))).toBe(true));
    expect(JSON.parse(calls.find((c) => c.url.endsWith("/reactivate"))?.body ?? "{}")).toEqual({
      reason: "Paid in full",
    });
  });

  it("uploads a logo, refusing a file over 200 KB before it is sent", async () => {
    const calls = stubApi([[/\/admin\/tenants\/7\/logo$/, () => FULL_DETAIL], ...COMPANY_ROUTES]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7");
    const input = await screen.findByLabelText("Logo file");
    await user.upload(
      input,
      new File([new Uint8Array(300 * 1024)], "big.png", { type: "image/png" }),
    );
    expect(
      await screen.findByText("The logo is larger than 200 KB. Use a smaller file."),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith("/logo"))).toBe(false);
    await user.upload(input, new File([new Uint8Array(1024)], "ok.png", { type: "image/png" }));
    expect(await screen.findByText("Logo saved.")).toBeInTheDocument();
    expect(calls.find((c) => c.url.endsWith("/logo"))?.method).toBe("POST");
  });
});

describe("AdminApp add company (M18)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the whole onboarding form and shows the owner's sign-in address", async () => {
    const calls = stubApi([
      [/\/admin\/tenants$/, () => ({ ...FULL_DETAIL, sign_in_url: "https://acme.duolink.app" })],
      ...COMPANY_ROUTES,
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/new");
    await user.type(await screen.findByLabelText("Legal name"), "Acme Steels");
    await user.type(screen.getByLabelText("City"), "Coimbatore");
    await user.type(screen.getByLabelText("Name on bills"), "Acme Steels Private Limited");
    await user.type(screen.getByLabelText("GSTIN"), "33aapfu0939f1zv");
    await user.clear(screen.getByLabelText("Shop name"));
    await user.type(screen.getByLabelText("Shop name"), "Acme Main");
    await user.clear(screen.getByLabelText("Shop code"));
    await user.type(screen.getByLabelText("Shop code"), "am");
    await user.clear(screen.getByLabelText("Trial length (days)"));
    await user.type(screen.getByLabelText("Trial length (days)"), "30");
    const owner = formSection("First owner");
    await user.type(within(owner).getByLabelText("Full name"), "Ravi Kumar");
    await user.type(within(owner).getByLabelText("Email"), "ravi@acme.example");
    await user.type(within(owner).getByLabelText("Mobile"), "9876543210");
    await user.type(within(owner).getByLabelText("Password"), "ravi-pass-123");
    await user.click(
      within(owner).getByLabelText("Make them choose a new password at first sign-in"),
    );
    await user.click(screen.getByRole("button", { name: "Create company" }));

    const sent = JSON.parse(
      calls.find((c) => c.method === "POST" && c.url.endsWith("/admin/tenants"))?.body ?? "{}",
    );
    expect(sent).toEqual({
      name: "Acme Steels",
      slug: "acme-steels",
      plan: "TRIAL",
      trial_days: 30,
      start_active: false,
      state_code: "33",
      city: "Coimbatore",
      legal_name: "Acme Steels Private Limited",
      registration_no: "33AAPFU0939F1ZV",
      shop_name: "Acme Main",
      shop_code: "AM",
      owner_full_name: "Ravi Kumar",
      owner_username: "owner",
      owner_email: "ravi@acme.example",
      owner_mobile: "9876543210",
      owner_password: "ravi-pass-123",
      require_owner_password_change: true,
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Its owner can sign in at https://acme.duolink.app now.",
    );
  });

  it("starts active with no trial length, and a paid plan sends neither", async () => {
    const calls = stubApi([
      [/\/admin\/tenants$/, () => ({ ...FULL_DETAIL, sign_in_url: "https://acme.duolink.app" })],
      ...COMPANY_ROUTES,
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/new");
    await user.type(await screen.findByLabelText("Legal name"), "Beta");
    await user.selectOptions(screen.getByLabelText("Start"), "active");
    expect(screen.queryByLabelText("Trial length (days)")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Plan"), "BASIC");
    expect(screen.queryByLabelText("Start")).not.toBeInTheDocument();
    // The archived plan is not offered when adding a company.
    expect(within(screen.getByLabelText("Plan")).queryByText("Pro")).not.toBeInTheDocument();
    const owner = formSection("First owner");
    await user.type(within(owner).getByLabelText("Full name"), "Bala");
    await user.type(within(owner).getByLabelText("Password"), "bala-pass-123");
    await user.click(screen.getByRole("button", { name: "Create company" }));
    const sent = JSON.parse(
      calls.find((c) => c.method === "POST" && c.url.endsWith("/admin/tenants"))?.body ?? "{}",
    );
    expect(sent).toMatchObject({ plan: "BASIC", trial_days: null, start_active: false });
  });
});

describe("AdminApp company list (M18)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("searches, filters, sorts and pages, keeping each in the address", async () => {
    const many = Array.from({ length: 25 }, (_, i) => ({
      ...ACME,
      id: i + 1,
      slug: `c${i}`,
      name: `Company ${i}`,
    }));
    const calls = stubApi([
      [
        /\/admin\/tenants\?/,
        (url) => ({
          items: many,
          total: 40,
          limit: 25,
          offset: Number(new URL(url, "http://x").searchParams.get("offset") ?? 0),
        }),
      ],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies");
    expect(await screen.findByText("40 companies, showing 1 to 25")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Name, code, owner or GSTIN")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next" }));
    await vi.waitFor(() => expect(window.location.search).toContain("page=1"));
    expect(calls.some((c) => /offset=25/.test(c.url))).toBe(true);

    await user.selectOptions(screen.getByLabelText("Trial"), "ended");
    await vi.waitFor(() => expect(window.location.search).toContain("trial=ended"));
    expect(window.location.search).not.toContain("page="); // a new filter starts at page one
    await user.selectOptions(screen.getByLabelText("Sort by"), "users");
    await user.selectOptions(screen.getByLabelText("Order"), "desc");
    await user.click(screen.getByLabelText("Ending within 30 days"));
    await vi.waitFor(() =>
      expect(
        calls.some(
          (c) =>
            /expiring=true/.test(c.url) &&
            /sort=users/.test(c.url) &&
            /order=desc/.test(c.url) &&
            /trial=ended/.test(c.url),
        ),
      ).toBe(true),
    );

    await user.type(screen.getByRole("searchbox", { name: "Search" }), "33AAPFU0939F1ZV");
    await user.tab();
    await vi.waitFor(() => expect(calls.some((c) => /q=33AAPFU0939F1ZV/.test(c.url))).toBe(true));
  });

  it("hides Add company from Support and shows the owner and last activity", async () => {
    stubApi(
      [
        [
          /\/admin\/tenants\?/,
          () =>
            page([
              {
                ...ACME,
                owner_name: "Ravi Kumar",
                city: "Coimbatore",
                last_activity_at: "2026-10-31T09:00:00Z",
              },
            ]),
        ],
      ],
      SUPPORT,
    );
    renderAt("/admin/companies");
    expect(await screen.findByText("Ravi Kumar")).toBeInTheDocument();
    expect(screen.getByText(/Coimbatore/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add company" })).not.toBeInTheDocument();
  });
});
