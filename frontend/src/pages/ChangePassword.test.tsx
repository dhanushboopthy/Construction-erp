import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { mockApi, OWNER, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

const TEMPORARY = { ...OWNER, must_change_password: true };
const TENANT = {
  slug: "acme",
  status: "active",
  name: "Acme Steels",
  tagline: "Bill fast. Close on time.",
  logo_url: null,
};

afterEach(() => vi.unstubAllGlobals());

describe("a temporary password (set by Duolink when it onboarded the company)", () => {
  it("sends the user to choose their own before any screen opens", async () => {
    const { calls } = mockApi({ ...session(TEMPORARY), "GET /tenant": () => ({ body: TENANT }) });
    renderAt("/sales");
    expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeVisible();
    expect(window.location.pathname).toBe("/change-password");
    expect(calls.some((c) => c.path === "/invoices")).toBe(false);
  });

  it("checks the two new passwords match, then changes it and asks for a fresh sign-in", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(TEMPORARY),
      "GET /tenant": () => ({ body: TENANT }),
      "POST /auth/change-password": () => ({ status: 204 }),
    });
    renderAt("/");
    await user.type(await screen.findByLabelText("Temporary password"), "temp-pass-123");
    await user.type(screen.getByLabelText("New password"), "brand-new-pass-1");
    await user.type(screen.getByLabelText("New password again"), "brand-new-pass-2");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("The two new passwords are not the same.")).toBeVisible();
    expect(calls.some((c) => c.path === "/auth/change-password")).toBe(false);

    await user.clear(screen.getByLabelText("New password again"));
    await user.type(screen.getByLabelText("New password again"), "brand-new-pass-1");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("heading", { name: "Sign in to the shop" })).toBeVisible();
    expect(screen.getByText("Password changed. Sign in with the new one.")).toBeVisible();
    expect(calls.find((c) => c.path === "/auth/change-password")?.body).toEqual({
      current_password: "temp-pass-123",
      new_password: "brand-new-pass-1",
    });
  });

  it("shows the server's reason when the new password is refused", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(TEMPORARY),
      "GET /tenant": () => ({ body: TENANT }),
      "POST /auth/change-password": () => ({
        status: 409,
        body: {
          code: "PASSWORD_UNCHANGED",
          message: "Choose a password you have not used just now.",
        },
      }),
    });
    renderAt("/change-password");
    await user.type(await screen.findByLabelText("Temporary password"), "temp-pass-123");
    await user.type(screen.getByLabelText("New password"), "temp-pass-123");
    await user.type(screen.getByLabelText("New password again"), "temp-pass-123");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("Choose a password you have not used just now.")).toBeVisible();
  });

  it("lets a user with a normal password straight in", async () => {
    mockApi({ ...session(OWNER), "GET /tenant": () => ({ body: TENANT }) });
    renderAt("/change-password");
    expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeVisible();
    expect(screen.getByText("You will be signed out and asked to sign in again.")).toBeVisible();
  });
});
