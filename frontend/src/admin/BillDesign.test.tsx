import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
const TENANT = { id: 7, slug: "acme", name: "Acme Steels", status: "active", trial_state: "none" };

function design(id: number, slot: string, version: number, extra: object = {}) {
  return {
    id,
    slot,
    name: version === 1 ? "Plain" : "Fancy",
    version,
    is_active: false,
    used: false,
    html_bytes: 4000,
    images: [],
    removed: [],
    uploaded_by_name: "Duolink Ops",
    created_at: "2026-11-02T09:00:00Z",
    activated_at: null,
    ...extra,
  };
}
const LIST = {
  templates: [
    design(12, "tax_invoice", 2, { is_active: true }),
    design(11, "tax_invoice", 1, { used: true }),
    design(13, "credit_note", 1),
  ],
  secondary_logo: null,
};
const REPORT = {
  unknown: ["{{invoice.nope}}"],
  other_slot: ["{{note.against}}"],
  outside_rows: ["{{item.qty}}"],
  in_styles: [],
  item_rows: 1,
  hsn_rows: 1,
  images: ["company.logo"],
  missing_images: ["gone.png"],
  unused_images: [],
  page_size: null,
  removed: ["<script> element"],
  missing_fields: [],
  warnings: ["The design sets no page size; A4 is used."],
};
const REGISTRY = {
  fields: [
    {
      key: "invoice.number",
      group: "invoice",
      description: "The document's number",
      sample: "MS/2627/000123",
      slots: ["tax_invoice"],
      image: false,
    },
  ],
  formats: ["symbol", "upper"],
  slots: ["tax_invoice"],
  required: { tax_invoice: ["Seller's GSTIN", "Invoice total"] },
  limits: { html_bytes: 512000, image_bytes: 2097152, images: 20 },
};

type Route = (url: string, init?: RequestInit) => unknown;
type Call = { url: string; method: string; body?: BodyInit | null };

function stubApi(routes: [RegExp, Route][], admin: object = ADMIN) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      calls.push({ url, method: init?.method ?? "GET", body: init?.body });
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

const base = "\\/admin\\/tenants\\/7\\/bill-templates";
const routes: [RegExp, Route][] = [
  [/\/admin\/tenants\/7$/, () => TENANT],
  [new RegExp(`${base}$`), () => LIST],
  [new RegExp(`${base}\\/field-registry$`), () => REGISTRY],
  [new RegExp(`${base}\\/\\d+\\/diagnostics$`), () => REPORT],
  [
    new RegExp(`${base}\\/\\d+\\/preview$`),
    () => new Response(new Blob(["%PDF-1.7"], { type: "application/pdf" }), { status: 200 }),
  ],
];

describe("AdminApp company Bill design tab (M28)", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows a card for each kind of document with its versions and what is in use", async () => {
    stubApi(routes);
    renderAt("/admin/companies/7?tab=bill-design");
    const tax = await screen.findByRole("region", { name: "Tax invoice" });
    expect(within(tax).getByText("New documents use Fancy, version 2.")).toBeInTheDocument();
    expect(within(tax).getByText("Plain · v1")).toBeInTheDocument();
    expect(within(tax).getByText("In use")).toBeInTheDocument();
    expect(within(tax).getByText("Printed on bills")).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Proforma invoice" })).getByText(
        "Built-in layout.",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Proforma invoice" })).getByText(
        "No design uploaded.",
      ),
    ).toBeInTheDocument();
    // A design a bill was printed on, or that is in use, cannot be deleted.
    expect(within(tax).queryByRole("button", { name: /^Delete/ })).not.toBeInTheDocument();
    const credit = screen.getByRole("region", { name: "Credit note" });
    expect(
      within(credit).getByRole("button", { name: "Delete Credit note version 1" }),
    ).toBeInTheDocument();
  });

  it("previews a design in a frame, fetched fresh with the access token", async () => {
    const calls = stubApi(routes);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=bill-design");
    await user.click(await screen.findByRole("button", { name: "Preview Tax invoice version 2" }));
    const frame = await screen.findByTitle("Preview of Tax invoice, version 2");
    expect(frame).toHaveAttribute("src", "blob:preview");
    expect(
      calls.some((c) => c.url.endsWith("/bill-templates/12/preview") && c.method === "POST"),
    ).toBe(true);
  });

  it("lists what prints blank, what was removed and what is missing", async () => {
    stubApi(routes);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=bill-design");
    await user.click(await screen.findByRole("button", { name: "Check Tax invoice version 2" }));
    expect(await screen.findByText("{{invoice.nope}}")).toBeInTheDocument();
    expect(screen.getByText("{{note.against}}")).toBeInTheDocument();
    expect(screen.getByText("{{item.qty}}")).toBeInTheDocument();
    expect(screen.getByText("gone.png")).toBeInTheDocument();
    expect(screen.getByText("<script> element")).toBeInTheDocument();
    expect(screen.getByText("The design sets no page size; A4 is used.")).toBeInTheDocument();
    expect(screen.getByText(/Page size: A4 \(default\)/)).toBeInTheDocument();
  });

  it("activates, deactivates and deletes as a Super Admin", async () => {
    const calls = stubApi([
      ...routes,
      [new RegExp(`${base}\\/\\d+\\/(activate|deactivate)$`), () => design(1, "tax_invoice", 1)],
      [new RegExp(`${base}\\/13$`), () => new Response(null, { status: 204 })],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=bill-design");
    await user.click(await screen.findByRole("button", { name: "Activate Tax invoice version 1" }));
    await user.click(screen.getByRole("button", { name: "Deactivate Tax invoice version 2" }));
    await user.click(screen.getByRole("button", { name: "Delete Credit note version 1" }));
    await waitFor(() => {
      const writes = calls.filter((c) => c.method !== "GET" && !c.url.endsWith("/auth/refresh"));
      expect(writes.map((c) => `${c.method} ${c.url.split("/bill-templates")[1]}`)).toEqual([
        "POST /11/activate",
        "POST /12/deactivate",
        "DELETE /13",
      ]);
    });
  });

  it("says why a delete was refused", async () => {
    stubApi([
      ...routes,
      [
        new RegExp(`${base}\\/13$`),
        () =>
          new Response(
            JSON.stringify({ code: "TEMPLATE_IN_USE", message: "An issued document uses it." }),
            { status: 409 },
          ),
      ],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=bill-design");
    await user.click(await screen.findByRole("button", { name: "Delete Credit note version 1" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("An issued document uses it.");
  });

  it("uploads a design with its images and shows what cleaning removed", async () => {
    const made = {
      ...design(14, "proforma", 1),
      removed: ["<script> element"],
      diagnostics: { ...REPORT, missing_images: [], unknown: [], warnings: [] },
    };
    const calls = stubApi([
      [new RegExp(`${base}$`), (_u, init) => (init?.method === "POST" ? made : LIST)],
      ...routes,
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=bill-design");
    await screen.findByRole("heading", { name: "Upload a design" });
    await user.selectOptions(screen.getByLabelText("Kind of document"), "proforma");
    await user.type(screen.getByLabelText("Name of the design"), "Letterhead");
    await user.upload(
      screen.getByLabelText("HTML file"),
      new File(["<p>x</p>"], "bill.html", { type: "text/html" }),
    );
    await user.upload(screen.getByLabelText("Images it uses"), [
      new File(["a"], "stamp.png", { type: "image/png" }),
    ]);
    await user.click(screen.getByRole("button", { name: "Upload design" }));
    expect(await screen.findByText(/Saved as Proforma invoice, version 1/)).toBeInTheDocument();
    expect(screen.getByText("<script> element")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/bill-templates"));
    const form = post?.body as FormData;
    expect(form.get("slot")).toBe("proforma");
    expect(form.get("name")).toBe("Letterhead");
    expect((form.get("html") as File).name).toBe("bill.html");
    expect((form.getAll("images") as File[]).map((f) => f.name)).toEqual(["stamp.png"]);
  });

  it("shows the server's reason when a design leaves out a GST field", async () => {
    stubApi([
      [
        new RegExp(`${base}$`),
        (_u, init) =>
          init?.method === "POST"
            ? new Response(
                JSON.stringify({
                  code: "TEMPLATE_MISSING_FIELDS",
                  message: "This design leaves out what a GST document must show: Seller's GSTIN.",
                }),
                { status: 409 },
              )
            : LIST,
      ],
      ...routes,
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=bill-design");
    await screen.findByRole("heading", { name: "Upload a design" });
    await user.type(screen.getByLabelText("Name of the design"), "Bare");
    await user.upload(screen.getByLabelText("HTML file"), new File(["<p>x</p>"], "bill.html"));
    await user.click(screen.getByRole("button", { name: "Upload design" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Seller's GSTIN");
  });

  it("checks the name and the file before sending anything", async () => {
    const calls = stubApi(routes);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=bill-design");
    await screen.findByRole("heading", { name: "Upload a design" });
    await user.click(screen.getByRole("button", { name: "Upload design" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Give the design a name.");
    await user.type(screen.getByLabelText("Name of the design"), "Bare");
    await user.click(screen.getByRole("button", { name: "Upload design" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose the HTML file.");
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/bill-templates"))).toBe(false);
  });

  it("sets and removes the second logo", async () => {
    let logo: object | null = null;
    const calls = stubApi([
      [new RegExp(`${base}$`), () => ({ ...LIST, secondary_logo: logo })],
      [
        new RegExp(`${base}\\/secondary-logo$`),
        (_u, init) => {
          logo =
            init?.method === "PUT"
              ? { content_type: "image/png", sha256: "abcdef0123456789" }
              : null;
          return { ...LIST, secondary_logo: logo };
        },
      ],
      ...routes,
    ]);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=bill-design");
    expect(await screen.findByText(/None set\./)).toBeInTheDocument();
    await user.upload(
      screen.getByLabelText("Second logo file"),
      new File(["x"], "logo.png", { type: "image/png" }),
    );
    expect(await screen.findByText("Second logo saved.")).toBeInTheDocument();
    expect(await screen.findByText(/Set \(abcdef0123\)/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove second logo" }));
    expect(await screen.findByText("Second logo removed.")).toBeInTheDocument();
    expect(calls.filter((c) => c.url.endsWith("/secondary-logo")).map((c) => c.method)).toEqual([
      "PUT",
      "DELETE",
    ]);
  });

  it("lists the placeholders only when opened", async () => {
    const calls = stubApi(routes);
    const user = userEvent.setup();
    renderAt("/admin/companies/7?tab=bill-design");
    await user.click(await screen.findByText("Placeholders a design can use"));
    expect(await screen.findByRole("cell", { name: "{{invoice.number}}" })).toBeInTheDocument();
    expect(
      screen.getByText(/Required on a tax invoice: Seller's GSTIN; Invoice total\./),
    ).toBeInTheDocument();
    expect(calls.filter((c) => c.url.endsWith("/field-registry"))).toHaveLength(1);
  });

  it("lets Support read and preview but not change anything", async () => {
    stubApi(routes, SUPPORT);
    renderAt("/admin/companies/7?tab=bill-design");
    const tax = await screen.findByRole("region", { name: "Tax invoice" });
    expect(
      within(tax).getByRole("button", { name: "Preview Tax invoice version 2" }),
    ).toBeInTheDocument();
    expect(
      within(tax).getByRole("button", { name: "Check Tax invoice version 2" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^(Activate|Deactivate|Delete)/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Upload a design" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Choose second logo" })).not.toBeInTheDocument();
  });
});
