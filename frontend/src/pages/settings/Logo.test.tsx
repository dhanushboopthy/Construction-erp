import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, session, SETTINGS } from "@/test/mockApi";

const TENANT = { name: "Anand Steels", tagline: "Bill fast. Close on time." };
const WITH_LOGO = { ...TENANT, logo_url: "/api/v1/tenant/logo?v=abc123def456" };

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

const png = (bytes = 100) => new File([new Uint8Array(bytes)], "logo.png", { type: "image/png" });
function must<T>(value: T | null | undefined): T {
  if (value == null) throw new Error("expected an element");
  return value;
}
const fileInput = () => must(document.querySelector<HTMLInputElement>("#logo-file"));
const logoImage = () => document.querySelector<HTMLImageElement>('img[src*="/tenant/logo"]');

afterEach(() => vi.unstubAllGlobals());

describe("Shop logo", () => {
  it("uploads a file, then the sidebar shows it instead of the initials", async () => {
    const user = userEvent.setup();
    const { fetchMock } = mockApi({
      ...session(OWNER),
      "GET /settings": () => ({ body: SETTINGS }),
      "GET /tenant": () => ({ body: TENANT }),
      "PUT /tenant/logo": () => ({ body: WITH_LOGO }),
    });
    renderAt("/settings");

    expect(await screen.findByRole("heading", { name: "Shop logo" })).toBeVisible();
    expect(logoImage()).toBeNull();
    await user.upload(fileInput(), png());

    expect(await screen.findByText("Logo saved.")).toBeVisible();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(String(put?.[0])).toBe("/api/v1/tenant/logo");
    const sent = (put?.[1]?.body as FormData).get("file") as File;
    expect(sent.name).toBe("logo.png");
    await waitFor(() => expect(logoImage()).not.toBeNull());
    expect(screen.getByRole("button", { name: "Replace logo" })).toBeVisible();
  });

  it("refuses a file over 200 KB without sending it", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /settings": () => ({ body: SETTINGS }),
      "GET /tenant": () => ({ body: TENANT }),
    });
    renderAt("/settings");
    await screen.findByRole("heading", { name: "Shop logo" });
    await user.upload(fileInput(), png(201 * 1024));
    expect(await screen.findByRole("alert")).toHaveTextContent("larger than 200 KB");
    expect(calls.some((c) => c.method === "PUT" && c.path === "/tenant/logo")).toBe(false);
  });

  it("shows the server's reason when it refuses the file", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      "GET /settings": () => ({ body: SETTINGS }),
      "GET /tenant": () => ({ body: TENANT }),
      "PUT /tenant/logo": () => ({
        status: 409,
        body: { code: "LOGO_NOT_SQUARE", message: "The logo must be square", field: "file" },
      }),
    });
    renderAt("/settings");
    await screen.findByRole("heading", { name: "Shop logo" });
    await user.upload(fileInput(), png());
    expect(await screen.findByRole("alert")).toHaveTextContent("The logo must be square");
  });

  it("removes the logo and goes back to the initials", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /settings": () => ({ body: SETTINGS }),
      "GET /tenant": () => ({ body: WITH_LOGO }),
      "DELETE /tenant/logo": () => ({ body: TENANT }),
    });
    renderAt("/settings");
    await user.click(await screen.findByRole("button", { name: "Remove logo" }));
    expect(await screen.findByText("Logo removed.")).toBeVisible();
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/tenant/logo")).toBe(true);
    await waitFor(() => expect(logoImage()).toBeNull());
    expect(screen.getAllByText("AS").length).toBeGreaterThan(0);
  });

  it("is not offered to counter staff, who cannot open Settings", async () => {
    mockApi({ ...session(COUNTER), "GET /tenant": () => ({ body: WITH_LOGO }) });
    renderAt("/settings");
    expect(
      await screen.findByRole("heading", { name: "Not available for your role" }),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: /logo/i })).toBeNull();
  });
});

describe("Logo in the shell and on the sign-in page", () => {
  it("shows the logo in the sidebar, and the initials if it will not load", async () => {
    mockApi({ ...session(COUNTER), "GET /tenant": () => ({ body: WITH_LOGO }) });
    renderAt("/");
    await waitFor(() => expect(logoImage()).not.toBeNull());
    expect(logoImage()).toHaveAttribute("alt", "");
    expect(screen.queryByText("AS")).toBeNull();
    fireEvent.error(must(logoImage()));
    expect(await screen.findByText("AS")).toBeVisible();
    expect(logoImage()).toBeNull();
  });

  it("shows the logo before anyone has signed in", async () => {
    mockApi({
      "POST /auth/refresh": () => ({
        status: 401,
        body: { code: "NOT_AUTHENTICATED", message: "x" },
      }),
      "GET /tenant": () => ({ body: WITH_LOGO }),
    });
    renderAt("/login");
    await waitFor(() => expect(logoImage()).not.toBeNull());
    expect(screen.getAllByText("Anand Steels").length).toBeGreaterThan(0);
  });
});
