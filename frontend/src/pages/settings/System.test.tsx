import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const STATUS = {
  version: "1.0.0",
  environment: "production",
  test_watermark: false,
  database: "ok",
  migrations: { name: "Database version", state: "ok", detail: "At the latest version (0014)." },
  backup: { name: "Nightly backup", state: "fail", detail: "The newest backup is 52 hours old." },
  last_backup_at: "2026-10-07T21:00:00Z",
  storage: { name: "File storage", state: "ok", detail: "Saving and reading files works (local)." },
  gsp: { name: "E-way bill provider", state: "warn", detail: "Pretend provider (development)." },
  unclosed: ["S1"],
  as_of: "2026-10-09",
};

describe("System page", () => {
  it("shows what needs action first and lists shops that did not close yesterday", async () => {
    mockApi({ ...session(OWNER), "GET /system/status": () => ({ body: STATUS }) });
    renderAt("/settings/system");
    const table = await screen.findByRole("table", { name: "System status" });
    expect(within(table).getByText("The newest backup is 52 hours old.")).toBeVisible();
    expect(within(table).getByText("Needs action")).toBeVisible();
    expect(within(table).getByText("Look at this")).toBeVisible();
    expect(screen.getByText(/Yesterday's day is not closed at S1/)).toBeVisible();
    expect(screen.getByText(/Version 1.0.0 · production$/)).toBeVisible();
  });

  it("runs the book checks and reports a problem plainly", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /system/status": () => ({ body: { ...STATUS, test_watermark: true } }),
      "POST /system/verify": () => ({
        body: {
          ok: false,
          checks: [
            { name: "Document numbers", state: "fail", detail: "bills S1/26-27: missing [3]" },
            { name: "Stock", state: "ok", detail: "2 items replayed" },
          ],
        },
      }),
    });
    renderAt("/settings/system");
    expect(await screen.findByText(/every PDF is stamped TEST/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Check the books and every stored file" }));
    expect(await screen.findByText(/Something does not add up/)).toBeVisible();
    const checks = screen.getByRole("table", { name: "Book checks" });
    expect(within(checks).getByText("bills S1/26-27: missing [3]")).toBeVisible();
    expect(calls.find((c) => c.path === "/system/verify")).toBeDefined();
    expect(window.location.pathname).toBe("/settings/system");
  });

  it("is closed to counter staff", async () => {
    mockApi({ ...session(COUNTER) });
    renderAt("/settings/system");
    expect(await screen.findByText("Not available for your role")).toBeVisible();
  });
});
