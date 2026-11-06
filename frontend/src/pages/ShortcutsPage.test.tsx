import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { mockApi, OWNER, session } from "@/test/mockApi";

type Item = { action_id: string; combo: string };

/** The signed-in owner, with `saved` as the shortcuts they changed on the server. */
function shell(saved: Item[] = []) {
  let stored = saved;
  return mockApi({
    ...session(OWNER),
    "GET /tenant": () => ({ body: { name: "Anand Steels", tagline: "" } }),
    "GET /stock": () => ({ body: [] }),
    "GET /eway-bills/pending": () => ({ body: [] }),
    "GET /me/shortcuts": () => ({ body: { items: stored } }),
    "PUT /me/shortcuts": (body) => {
      stored = (body as { items: Item[] }).items;
      return { body: { items: stored } };
    },
  });
}

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

const row = (name: RegExp) =>
  screen.getByText(name, { selector: "strong" }).closest("li") as HTMLElement;

afterEach(() => vi.unstubAllGlobals());

describe("Keyboard shortcuts page", () => {
  it("opens from anywhere with Ctrl+Shift+Alt+1", async () => {
    const user = userEvent.setup();
    shell();
    renderAt("/items");
    await screen.findByRole("navigation", { name: "Modules" });
    await user.keyboard("{Control>}{Shift>}{Alt>}1{/Alt}{/Shift}{/Control}");
    expect(await screen.findByRole("heading", { name: "Keyboard shortcuts" })).toBeVisible();
    expect(window.location.pathname).toBe("/shortcuts");
  });

  it("is in the account menu", async () => {
    const user = userEvent.setup();
    shell();
    renderAt("/");
    await user.click(await screen.findByRole("button", { name: /Account menu/ }));
    await user.click(screen.getByRole("link", { name: "Keyboard shortcuts" }));
    expect(await screen.findByRole("heading", { name: "Keyboard shortcuts" })).toBeVisible();
  });

  it("lists every screen and the page action with their defaults", async () => {
    shell();
    renderAt("/shortcuts");
    await screen.findByRole("heading", { name: "Keyboard shortcuts" });
    expect(within(row(/^Sales bills$/)).getByLabelText("Alt plus 2")).toBeVisible();
    expect(within(row(/^New record$/)).getByLabelText("Alt plus N")).toBeVisible();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("records a new combination, saves it, and the app uses it", async () => {
    const user = userEvent.setup();
    const { calls } = shell();
    renderAt("/shortcuts");
    await screen.findByRole("heading", { name: "Keyboard shortcuts" });

    await user.click(screen.getByRole("button", { name: "Change the shortcut for Sales bills" }));
    expect(screen.getByRole("status")).toHaveTextContent(/Press the new shortcut/);
    await user.keyboard("{Alt>}{Shift>}s{/Shift}{/Alt}");
    expect(within(row(/^Sales bills$/)).getByLabelText("Alt plus Shift plus S")).toBeVisible();
    // Recording did not leave the page, and nothing is saved yet.
    expect(window.location.pathname).toBe("/shortcuts");
    expect(calls.some((c) => c.method === "PUT")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/Saved/)).toBeVisible();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      items: [{ action_id: "go:/sales", combo: "Alt+Shift+S" }],
    });

    // The new key works, the old one no longer does, and the sidebar hint follows.
    await user.keyboard("{Alt>}{Shift>}s{/Shift}{/Alt}");
    expect(window.location.pathname).toBe("/sales");
    await user.keyboard("{Alt>}2{/Alt}");
    expect(window.location.pathname).toBe("/sales");
    expect(screen.getByRole("link", { name: /Sales bills/ })).toHaveAttribute(
      "title",
      "Sales bills (Alt Shift S)",
    );
  });

  it("refuses a combination another action already uses", async () => {
    const user = userEvent.setup();
    const { calls } = shell();
    renderAt("/shortcuts");
    await screen.findByRole("heading", { name: "Keyboard shortcuts" });
    await user.click(screen.getByRole("button", { name: "Change the shortcut for Purchases" }));
    await user.keyboard("{Alt>}2{/Alt}"); // Alt+2 is Sales bills
    expect(screen.getByRole("alert")).toHaveTextContent(/Alt\+2 already runs "Sales bills"/);
    // It keeps listening for another key; cancelling leaves the shortcut as it was.
    await user.keyboard("{Escape}");
    expect(within(row(/^Purchases$/)).getByLabelText("Alt plus 3")).toBeVisible();
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("refuses keys the browser takes, and Esc cancels", async () => {
    const user = userEvent.setup();
    shell();
    renderAt("/shortcuts");
    await screen.findByRole("heading", { name: "Keyboard shortcuts" });
    await user.click(screen.getByRole("button", { name: "Change the shortcut for Purchases" }));
    await user.keyboard("{Alt>}d{/Alt}");
    expect(screen.getByRole("alert")).toHaveTextContent(/used by the browser/);
    await user.keyboard("{Escape}");
    expect(screen.queryByText("Press a shortcut…")).toBeNull();
  });

  it("shows what the user changed, and restores a default", async () => {
    const user = userEvent.setup();
    const { calls } = shell([{ action_id: "new", combo: "Alt+B" }]);
    renderAt("/shortcuts");
    await screen.findByRole("heading", { name: "Keyboard shortcuts" });
    const newRow = row(/^New record$/);
    expect(await within(newRow).findByLabelText("Alt plus B")).toBeVisible();
    expect(within(newRow).getByText(/was/)).toBeVisible();

    await user.click(
      within(newRow).getByRole("button", { name: "Use the default shortcut for New record" }),
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/Saved/);
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ items: [] });
  });

  it("uses a saved change for the page's new button", async () => {
    const user = userEvent.setup();
    shell([{ action_id: "new", combo: "Alt+B" }]);
    renderAt("/purchases");
    await screen.findByRole("navigation", { name: "Modules" });
    // Wait for the user's own shortcuts to load, then the old key is dead and the new one works.
    await vi.waitFor(async () => {
      await user.keyboard("{Alt>}b{/Alt}");
      expect(window.location.pathname).toBe("/purchases/new");
    });
  });
});
