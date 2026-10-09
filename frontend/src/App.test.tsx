import { render, screen } from "@testing-library/react";

import { App } from "./App";

describe("App", () => {
  beforeEach(() => {
    // No refresh cookie: the API answers 401, so the login screen shows.
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () => new Response(JSON.stringify({ code: "NOT_AUTHENTICATED" }), { status: 401 }),
      ),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("shows the sign-in form when there is no session", async () => {
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Sign in to the shop" })).toBeInTheDocument();
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
  });
});
