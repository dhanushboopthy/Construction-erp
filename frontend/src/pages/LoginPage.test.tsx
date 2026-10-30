import { render, screen, within } from "@testing-library/react";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";

// A fresh cache per test: the company is cached for the whole visit.
const renderApp = () => render(<App client={createQueryClient()} />);

/** The API answers GET /tenant with `tenant`; every other call is "not signed in". */
function stubApi(tenant: { status: number; body: unknown }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.endsWith("/api/v1/tenant")) {
        return new Response(JSON.stringify(tenant.body), { status: tenant.status });
      }
      return new Response(JSON.stringify({ code: "NOT_AUTHENTICATED" }), { status: 401 });
    }),
  );
}

describe("LoginPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the company this address belongs to", async () => {
    stubApi({
      status: 200,
      body: {
        slug: "acme",
        status: "active",
        name: "Acme Steels",
        tagline: "Bill fast. Close on time.",
        logo_url: null,
      },
    });
    renderApp();
    const brand = await screen.findByRole("complementary", { name: "About this shop" });
    expect(await within(brand).findByText("Acme Steels")).toBeInTheDocument();
    expect(within(brand).getByText("Bill fast. Close on time.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("says why nobody can sign in at a suspended company's address", async () => {
    stubApi({
      status: 403,
      body: {
        code: "TENANT_SUSPENDED",
        message: "This company's account is suspended. Contact Duolink support.",
        field: null,
        request_id: null,
      },
    });
    renderApp();
    expect(await screen.findByText(/account is suspended/)).toHaveAttribute("role", "alert");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
    expect(screen.getByLabelText("Username")).toBeDisabled();
  });
});
