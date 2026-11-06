import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";

import { createQueryClient } from "@/api/queryClient";
import { mockApi } from "@/test/mockApi";

import { AppUpdates, ForcedUpdateWatch } from "./AppUpdates";
import { ConnectionNotice } from "./ConnectionNotice";
import { useUnsavedChanges } from "./unsaved";
import {
  CHECK_EVERY_MS,
  applyUpdate,
  checkForUpdate,
  getPwaState,
  resetPwa,
  shellCached,
  startPwa,
  useForcedUpdateCheck,
} from "./updates";

/** A service worker and its registration, as far as the app uses them. */
class FakeWorker extends EventTarget {
  state = "installed";
  posted: unknown[] = [];
  postMessage(message: unknown) {
    this.posted.push(message);
  }
}

class FakeRegistration extends EventTarget {
  active: FakeWorker | null = new FakeWorker();
  waiting: FakeWorker | null = null;
  installing: FakeWorker | null = null;
  update = vi.fn(async () => undefined);

  /** A new build was downloaded and installed: it waits. */
  newBuild() {
    const worker = new FakeWorker();
    this.installing = worker;
    this.dispatchEvent(new Event("updatefound"));
    worker.dispatchEvent(new Event("statechange"));
    this.waiting = worker;
    this.installing = null;
    return worker;
  }
}

class FakeContainer extends EventTarget {
  controller: object | null = {};
  registration = new FakeRegistration();
  register = vi.fn(async () => this.registration);
}

function setup(container = new FakeContainer()) {
  const win = Object.assign(new EventTarget(), {
    setInterval: window.setInterval.bind(window),
    clearInterval: window.clearInterval.bind(window),
    matchMedia: () => ({ matches: false }),
    location: { reload: vi.fn() },
  }) as unknown as Window;
  return { container: container as unknown as ServiceWorkerContainer, fake: container, win };
}

afterEach(() => {
  resetPwa();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("the update flow", () => {
  it("registers the worker and shows nothing while there is no new build", async () => {
    const { container, fake, win } = setup();
    await startPwa({ container, win });
    expect(fake.register).toHaveBeenCalledWith("/sw.js", { scope: "/", updateViaCache: "none" });
    expect(getPwaState()).toMatchObject({
      worker: "active",
      updateWaiting: false,
      offlineReady: true,
    });
    render(<AppUpdates />);
    expect(screen.queryByText("A new version is ready.")).not.toBeInTheDocument();
  });

  it("checks for a new build every 30 minutes and when the window gets focus", async () => {
    vi.useFakeTimers();
    const { container, fake, win } = setup();
    await startPwa({ container, win });
    const update = fake.registration.update;
    expect(update).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(CHECK_EVERY_MS);
    expect(update).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(CHECK_EVERY_MS);
    expect(update).toHaveBeenCalledTimes(2);
    win.dispatchEvent(new Event("focus"));
    expect(update).toHaveBeenCalledTimes(3);
  });

  it("a failed check (no connection) is ignored", async () => {
    const { container, fake, win } = setup();
    fake.registration.update.mockRejectedValueOnce(new TypeError("offline"));
    await startPwa({ container, win });
    await expect(checkForUpdate()).resolves.toBeUndefined();
  });

  it("shows the toast for a new build and reloads nothing by itself", async () => {
    const { container, fake, win } = setup();
    await startPwa({ container, win });
    render(<AppUpdates />);
    act(() => void fake.registration.newBuild());
    expect(await screen.findByText("A new version is ready.")).toBeInTheDocument();
    expect(win.location.reload).not.toHaveBeenCalled();
    expect(fake.registration.waiting?.posted).toEqual([]); // not told to take over
  });

  it("Update now tells the waiting build to take over, then reloads once it has", async () => {
    const user = userEvent.setup();
    const { container, fake, win } = setup();
    await startPwa({ container, win });
    render(<AppUpdates />);
    act(() => void fake.registration.newBuild());
    await user.click(await screen.findByRole("button", { name: "Update now" }));
    expect(fake.registration.waiting?.posted).toEqual([{ type: "SKIP_WAITING" }]);
    expect(win.location.reload).not.toHaveBeenCalled();
    fake.dispatchEvent(new Event("controllerchange")); // the new build is in charge
    expect(win.location.reload).toHaveBeenCalledTimes(1);
  });

  it("the first worker taking charge reloads nobody", async () => {
    const { container, fake, win } = setup();
    fake.controller = null;
    await startPwa({ container, win });
    fake.dispatchEvent(new Event("controllerchange"));
    expect(win.location.reload).not.toHaveBeenCalled();
  });

  it("Later hides the toast until the next build", async () => {
    const user = userEvent.setup();
    const { container, fake, win } = setup();
    await startPwa({ container, win });
    render(<AppUpdates />);
    act(() => void fake.registration.newBuild());
    await user.click(await screen.findByRole("button", { name: "Later" }));
    expect(screen.queryByText("A new version is ready.")).not.toBeInTheDocument();
    act(() => void fake.registration.newBuild());
    expect(await screen.findByText("A new version is ready.")).toBeInTheDocument();
  });

  it("never reloads while a form has unsaved changes", async () => {
    const user = userEvent.setup();
    const { container, fake, win } = setup();
    await startPwa({ container, win });
    function Form() {
      useUnsavedChanges(true);
      return <p>an open bill</p>;
    }
    const form = render(<Form />);
    render(<AppUpdates />);
    act(() => void fake.registration.newBuild());
    await user.click(await screen.findByRole("button", { name: "Update now" }));
    expect(screen.getByText(/Save or cancel the open form first/)).toBeInTheDocument();
    expect(fake.registration.waiting?.posted).toEqual([]);
    fake.dispatchEvent(new Event("controllerchange"));
    expect(win.location.reload).not.toHaveBeenCalled();
    expect(applyUpdate()).toBe("unsaved");

    form.unmount(); // the bill is saved or cancelled
    await user.click(screen.getByRole("button", { name: "Update now" }));
    expect(fake.registration.waiting?.posted).toEqual([{ type: "SKIP_WAITING" }]);
  });

  it("an open form also asks the browser before the tab is closed", () => {
    const { unmount } = renderHook(() => useUnsavedChanges(true));
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    unmount();
    const later = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(later);
    expect(later.defaultPrevented).toBe(false);
  });

  it("says so, and does nothing, with a browser that has no service workers", async () => {
    const { win } = setup();
    await startPwa({ container: undefined, win });
    expect(getPwaState().worker).toBe("unsupported");
    expect(applyUpdate()).toBe("nothing");
    await expect(checkForUpdate()).resolves.toBeUndefined();
  });

  it("remembers the browser's offer to install the app", async () => {
    const { container, win } = setup();
    await startPwa({ container, win });
    expect(getPwaState().installable).toBe(false);
    win.dispatchEvent(new Event("beforeinstallprompt"));
    expect(getPwaState().installable).toBe(true);
    win.dispatchEvent(new Event("appinstalled"));
    expect(getPwaState()).toMatchObject({ installable: false, installed: true });
  });
});

describe("force update", () => {
  it("looks for a new build when the generation changes, not before", async () => {
    const { container, fake, win } = setup();
    await startPwa({ container, win });
    const { rerender } = renderHook(({ g }) => useForcedUpdateCheck(g), {
      initialProps: { g: undefined as number | undefined },
    });
    rerender({ g: 3 }); // the first reading is only noted
    expect(fake.registration.update).not.toHaveBeenCalled();
    rerender({ g: 3 });
    expect(fake.registration.update).not.toHaveBeenCalled();
    rerender({ g: 4 }); // Duolink forced an update
    expect(fake.registration.update).toHaveBeenCalledTimes(1);
    expect(win.location.reload).not.toHaveBeenCalled(); // and nobody is reloaded
  });

  it("an open bill form is not reloaded: the toast appears and the form keeps its text", async () => {
    const user = userEvent.setup();
    const { container, fake, win } = setup();
    await startPwa({ container, win });
    // The company app reads the generation from GET /tenant on every poll.
    let generation = 1;
    mockApi({
      "GET /tenant": () => ({
        body: {
          slug: "main",
          status: "active",
          name: "Shop",
          tagline: "",
          app_generation: generation,
        },
      }),
    });
    function Bill() {
      useUnsavedChanges(true);
      return <input aria-label="Quantity" defaultValue="" />;
    }
    const client = createQueryClient();
    render(
      <QueryClientProvider client={client}>
        <Bill />
        <ForcedUpdateWatch />
        <AppUpdates />
      </QueryClientProvider>,
    );
    await user.type(screen.getByLabelText("Quantity"), "25");
    await vi.waitFor(() => expect(client.getQueryData(["tenant"])).toBeDefined());

    generation = 2; // Duolink forces an update; the next poll sees it
    await act(async () => {
      await client.refetchQueries({ queryKey: ["tenant"] });
    });
    await vi.waitFor(() => expect(fake.registration.update).toHaveBeenCalledTimes(1));
    act(() => void fake.registration.newBuild()); // the check finds a new build
    await user.click(await screen.findByRole("button", { name: "Update now" }));

    expect(screen.getByLabelText("Quantity")).toHaveValue("25"); // still there
    expect(win.location.reload).not.toHaveBeenCalled();
    expect(fake.registration.waiting?.posted).toEqual([]);
    expect(screen.getByText(/Save or cancel the open form first/)).toBeInTheDocument();
  });
});

describe("no connection", () => {
  it("says so on every screen, and goes away with the network", () => {
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    render(<ConnectionNotice />);
    expect(screen.getByRole("alert")).toHaveTextContent(/No connection/);
    expect(screen.getByRole("alert")).toHaveTextContent(/cannot be saved/);
    online.mockReturnValue(true);
    act(() => void window.dispatchEvent(new Event("online")));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    online.mockRestore();
  });
});

describe("the offline shell", () => {
  it("is ready when a worker cache holds the page", async () => {
    const hit = { match: vi.fn(async () => new Response("shell")) };
    const store = {
      keys: async () => ["other", "erp-shell-abc123"],
      open: async () => hit,
    } as unknown as CacheStorage;
    expect(await shellCached(store)).toBe(true);
    expect(await shellCached({ keys: async () => ["other"], open: vi.fn() } as never)).toBe(false);
    expect(await shellCached(undefined)).toBe(false);
  });
});
