import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "@/api/queryClient";

import { MAINTENANCE_EVENT, MAINTENANCE_RETRY_MS, MaintenanceGate } from "./MaintenanceGate";

let notice: { enabled: boolean; message: string | null } | "fail";

function renderGate() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MaintenanceGate>
        <p>The app</p>
      </MaintenanceGate>
    </QueryClientProvider>,
  );
}

describe("MaintenanceGate (M24)", () => {
  beforeEach(() => {
    notice = { enabled: false, message: null };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        notice === "fail"
          ? new Response("{}", { status: 500 })
          : new Response(JSON.stringify(notice), { status: 200 }),
      ),
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("shows the app when the platform is open", async () => {
    renderGate();
    expect(await screen.findByText("The app")).toBeInTheDocument();
  });

  it("shows a full-page Back soon screen with Duolink's message", async () => {
    notice = { enabled: true, message: "Back at 9 pm" };
    renderGate();
    expect(
      await screen.findByRole("heading", { name: "Back soon: Back at 9 pm" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("The app")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("checks again every 30 seconds");
  });

  it("says just Back soon when there is no message", async () => {
    notice = { enabled: true, message: null };
    renderGate();
    expect(await screen.findByRole("heading", { name: "Back soon" })).toBeInTheDocument();
  });

  it("shows the app again by itself once maintenance is over, asking every 30 seconds", async () => {
    notice = { enabled: true, message: "Moving servers" };
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderGate();
    await screen.findByRole("heading", { name: /Back soon/ });
    notice = { enabled: false, message: null };
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MAINTENANCE_RETRY_MS + 100);
    });
    expect(await screen.findByText("The app")).toBeInTheDocument();
  });

  it("asks again at once when a call is answered 503 MAINTENANCE", async () => {
    renderGate();
    await screen.findByText("The app");
    notice = { enabled: true, message: "Now" };
    act(() => {
      window.dispatchEvent(new Event(MAINTENANCE_EVENT));
    });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Back soon: Now" })).toBeVisible(),
    );
  });

  it("keeps the app if the question itself fails: the server refuses the work", async () => {
    notice = "fail";
    renderGate();
    expect(await screen.findByText("The app")).toBeInTheDocument();
  });
});
