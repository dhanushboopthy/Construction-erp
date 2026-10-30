import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { mockApi, OWNER } from "@/test/mockApi";

function renderLogin() {
  window.history.pushState({}, "", "/login");
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const signedOut = {
  "POST /auth/refresh": () => ({ status: 401, body: { code: "NOT_AUTHENTICATED", message: "x" } }),
};

describe("Sign-in page", () => {
  it("shows whose shop it is, from the API, before anyone has signed in", async () => {
    const { calls } = mockApi({
      ...signedOut,
      "GET /tenant": () => ({
        body: { name: "Anand Steels", tagline: "Bill fast. Close on time." },
      }),
    });
    renderLogin();
    expect(await screen.findAllByText("Anand Steels")).not.toHaveLength(0);
    expect(screen.getByText("Bill fast. Close on time.")).toBeVisible();
    expect(screen.getByText("AS")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "Sign in to the shop" })).toBeVisible();
    // Asked without a token: nobody is signed in.
    const call = calls.find((c) => c.path === "/tenant");
    expect(call?.headers.authorization).toBeUndefined();
  });

  it("follows the API: another business shows its own name and nothing fixed", async () => {
    mockApi({
      ...signedOut,
      "GET /tenant": () => ({
        body: { name: "Sri Lakshmi Hardware", tagline: "Steel for every site" },
      }),
    });
    renderLogin();
    expect((await screen.findAllByText("Sri Lakshmi Hardware")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/BuildTrack/)).toBeNull();
    expect(screen.queryByText("Anand Steels")).toBeNull();
  });

  it("still lets people sign in when the name cannot be read", async () => {
    mockApi({
      ...signedOut,
      "GET /tenant": () => ({ status: 500, body: { code: "X", message: "x" } }),
    });
    renderLogin();
    expect(await screen.findByLabelText("Username")).toBeVisible();
    expect(screen.getAllByText("Construction ERP").length).toBeGreaterThan(0);
  });

  it("works with the keyboard alone: type, Tab, type, Enter", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...signedOut,
      "GET /tenant": () => ({ body: { name: "Anand Steels", tagline: "x" } }),
      "POST /auth/login": () => ({
        body: { access_token: "t", token_type: "bearer", expires_in: 1800, user: OWNER },
      }),
      "GET /reports/today": () => ({ status: 404, body: null }),
    });
    renderLogin();
    // The username box has focus on arrival.
    await screen.findByLabelText("Username");
    expect(screen.getByLabelText("Username")).toHaveFocus();
    await user.keyboard("owner");
    await user.tab();
    expect(screen.getByLabelText("Password")).toHaveFocus();
    await user.keyboard("owner-pass-123{Enter}");
    await vi.waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path === "/auth/login")).toBe(true),
    );
    expect(calls.find((c) => c.path === "/auth/login")?.body).toEqual({
      username: "owner",
      password: "owner-pass-123",
    });
  });

  it("says what went wrong under the form", async () => {
    const user = userEvent.setup();
    mockApi({
      ...signedOut,
      "GET /tenant": () => ({ body: { name: "Anand Steels", tagline: "x" } }),
      "POST /auth/login": () => ({
        status: 401,
        body: { code: "INVALID_CREDENTIALS", message: "Wrong username or password." },
      }),
    });
    renderLogin();
    await user.type(await screen.findByLabelText("Username"), "owner");
    await user.type(screen.getByLabelText("Password"), "nope{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong username or password.");
  });
});
