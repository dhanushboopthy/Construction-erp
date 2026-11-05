import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "@/api/queryClient";
import { resetPwa } from "@/pwa/updates";

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
const STATUS = {
  generation: 3,
  forced_at: "2026-11-04T10:30:00Z",
  forced_by: "Duolink Ops",
  backend_version: "1.0.0",
  backend_build: "4f2c9a1",
};

type Call = { url: string; method: string; body?: string };

function stubApi(admin: object = ADMIN) {
  const calls: Call[] = [];
  let status = STATUS;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body as string | undefined });
      if (url.endsWith("/admin/auth/refresh")) {
        return new Response(
          JSON.stringify({ access_token: "t", token_type: "bearer", expires_in: 1800, admin }),
          { status: 200 },
        );
      }
      if (url.endsWith("/system/app-update")) return new Response(JSON.stringify(status));
      if (url.endsWith("/system/force-update")) {
        status = { ...status, generation: status.generation + 1 };
        return new Response(JSON.stringify(status));
      }
      return new Response(JSON.stringify({ code: "NOT_FOUND" }), { status: 404 });
    }),
  );
  return calls;
}

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<AdminApp client={createQueryClient()} />);
}

describe("AdminApp App and updates page (M29)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    resetPwa();
  });

  it("has an entry in the menu on Alt 0", async () => {
    stubApi();
    const user = userEvent.setup();
    renderAt("/admin/staff");
    await screen.findByRole("link", { name: /App and updates/ });
    await user.keyboard("{Alt>}{0}{/Alt}");
    expect(await screen.findByRole("heading", { name: "App and updates" })).toBeInTheDocument();
  });

  it("shows both builds and how this browser stands", async () => {
    stubApi();
    renderAt("/admin/app");
    expect(await screen.findByText(/1\.0\.0 · build 4f2c9a1/)).toBeInTheDocument();
    const frontend = screen.getByText("Frontend").closest("tr");
    expect(frontend).toHaveTextContent(/build/);
    for (const row of [
      "Can be installed",
      "Service worker",
      "Offline shell",
      "Update waiting",
      "Browser",
    ]) {
      expect(screen.getByText(row)).toBeInTheDocument();
    }
    expect(screen.getByText("Browser").closest("tr")).toHaveTextContent(navigator.userAgent);
    expect(await screen.findByText("Not registered")).toBeInTheDocument();
    expect(screen.getByText("Not ready")).toBeInTheDocument(); // no worker cache in the test
    expect(screen.getByText(/Generation 3, last forced/)).toBeInTheDocument();
  });

  it("forces an update with a reason and shows the new generation", async () => {
    const calls = stubApi();
    const user = userEvent.setup();
    renderAt("/admin/app");
    await screen.findByText(/Generation 3/);
    await user.type(screen.getByLabelText("Reason (optional)"), "Release 1.29");
    await user.click(screen.getByRole("button", { name: "Force update" }));
    expect(await screen.findByText("Done. Generation is now 4.")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/force-update"));
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ reason: "Release 1.29" });
    await waitFor(() => expect(screen.getByText(/Generation 4/)).toBeInTheDocument());
  });

  it("gives Support the page but no Force update button", async () => {
    stubApi(SUPPORT);
    renderAt("/admin/app");
    expect(await screen.findByText(/Generation 3/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Force update" })).not.toBeInTheDocument();
    expect(screen.getByText("Only a Super Admin can force an update.")).toBeInTheDocument();
  });
});
