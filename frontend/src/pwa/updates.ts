import { useEffect, useRef, useSyncExternalStore } from "react";

import { CACHE_PREFIX, SHELL_URL } from "./swRoutes";
import { hasUnsavedChanges } from "./unsaved";

/**
 * The installed app and its updates (Milestone 29): registers the service worker, looks for a
 * new build every 30 minutes and when the window comes back into focus, and knows whether one is
 * waiting. Nothing here reloads the page by itself: only "Update now" does, and not while a form
 * has unsaved changes.
 */

export const CHECK_EVERY_MS = 30 * 60_000;

export type WorkerState = "unsupported" | "none" | "installing" | "active";

export interface PwaState {
  worker: WorkerState;
  /** A new build is installed and waits for "Update now". */
  updateWaiting: boolean;
  /** The person chose "Later"; the toast comes back with the next build. */
  dismissed: boolean;
  /** A service worker controls this page, so the app shell opens with no connection. */
  offlineReady: boolean;
  /** The browser has offered to install the app (and it is not installed yet). */
  installable: boolean;
  /** Running as an installed app, in its own window. */
  installed: boolean;
}

/** Chrome's install offer; not in the DOM types yet. */
interface InstallPromptEvent extends Event {
  prompt: () => Promise<unknown>;
}

const INITIAL: PwaState = {
  worker: "none",
  updateWaiting: false,
  dismissed: false,
  offlineReady: false,
  installable: false,
  installed: false,
};

let state: PwaState = INITIAL;
const listeners = new Set<() => void>();
let registration: ServiceWorkerRegistration | null = null;
let waiting: ServiceWorker | null = null;
let installPrompt: InstallPromptEvent | null = null;
let reloadAsked = false;
let stopWatching: (() => void) | null = null;

function set(patch: Partial<PwaState>) {
  state = { ...state, ...patch };
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getPwaState(): PwaState {
  return state;
}

export function usePwa(): PwaState {
  return useSyncExternalStore(subscribe, getPwaState);
}

function markWaiting(worker: ServiceWorker) {
  waiting = worker;
  set({ updateWaiting: true, dismissed: false });
}

function track(reg: ServiceWorkerRegistration, container: ServiceWorkerContainer) {
  if (reg.waiting && container.controller) markWaiting(reg.waiting);
  reg.addEventListener("updatefound", () => {
    const next = reg.installing;
    if (!next) return;
    if (!reg.active) set({ worker: "installing" });
    next.addEventListener("statechange", () => {
      if (next.state === "installed") {
        // With a worker already in charge this is a new build; otherwise it is the first one.
        if (container.controller) markWaiting(next);
        else set({ offlineReady: true });
      }
      if (next.state === "activated") set({ worker: "active", offlineReady: true });
    });
  });
}

export interface StartOptions {
  container?: ServiceWorkerContainer | undefined;
  win?: Window;
  url?: string;
}

/** Register /sw.js and start watching for new builds. Called once, from main.tsx, in a
 * production build only. */
export async function startPwa({
  container = navigator.serviceWorker as ServiceWorkerContainer | undefined,
  win = window,
  url = "/sw.js",
}: StartOptions = {}): Promise<void> {
  const onInstallOffer = (event: Event) => {
    installPrompt = event as InstallPromptEvent;
    set({ installable: true });
  };
  const onInstalled = () => {
    installPrompt = null;
    set({ installable: false, installed: true });
  };
  win.addEventListener("beforeinstallprompt", onInstallOffer);
  win.addEventListener("appinstalled", onInstalled);
  set({ installed: win.matchMedia?.("(display-mode: standalone)").matches ?? false });
  if (!container) {
    set({ worker: "unsupported" });
    return;
  }
  container.addEventListener("controllerchange", () => {
    // Only after "Update now": the first worker taking charge reloads nobody.
    if (reloadAsked) win.location.reload();
  });
  const reg = await container.register(url, { scope: "/", updateViaCache: "none" });
  registration = reg;
  set({
    worker: reg.active ? "active" : "installing",
    offlineReady: Boolean(container.controller),
  });
  track(reg, container);

  const timer = win.setInterval(() => void checkForUpdate(), CHECK_EVERY_MS);
  const onFocus = () => void checkForUpdate();
  win.addEventListener("focus", onFocus);
  stopWatching = () => {
    win.clearInterval(timer);
    win.removeEventListener("focus", onFocus);
    win.removeEventListener("beforeinstallprompt", onInstallOffer);
    win.removeEventListener("appinstalled", onInstalled);
  };
}

/** Ask the browser to look for a new sw.js now. Harmless offline: a failed check is ignored. */
export async function checkForUpdate(): Promise<void> {
  if (!registration) return;
  try {
    await registration.update();
  } catch {
    // No connection, or the server is down: the next check will try again.
  }
}

export type ApplyResult = "updating" | "unsaved" | "nothing";

/** "Update now": the waiting build takes over and the page reloads, unless a form has changes
 * not yet saved, when nothing happens and the caller says so. */
export function applyUpdate(): ApplyResult {
  if (!waiting) return "nothing";
  if (hasUnsavedChanges()) return "unsaved";
  reloadAsked = true;
  waiting.postMessage({ type: "SKIP_WAITING" });
  return "updating";
}

/** "Later": hide the toast until the next build. */
export function dismissUpdate(): void {
  set({ dismissed: true });
}

/** The browser's own install question, when it has offered one. */
export async function promptInstall(): Promise<void> {
  const offer = installPrompt;
  if (!offer) return;
  installPrompt = null;
  set({ installable: false });
  await offer.prompt();
}

/**
 * Duolink's "force update" (Milestone 29): when the release generation from GET /tenant changes,
 * look for a new build now instead of at the next half-hourly check. A new build then shows the
 * toast; nothing reloads.
 */
export function useForcedUpdateCheck(generation: number | undefined): void {
  const seen = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (generation === undefined) return;
    if (seen.current !== undefined && generation !== seen.current) void checkForUpdate();
    seen.current = generation;
  }, [generation]);
}

function subscribeOnline(onChange: () => void) {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

/** Whether the browser thinks it has a network connection. */
export function useOnline(): boolean {
  return useSyncExternalStore(subscribeOnline, () => navigator.onLine);
}

/** Whether the app shell is in the service worker's cache (Diagnostics). */
export async function shellCached(store: CacheStorage | undefined = globalThis.caches) {
  if (!store) return false;
  const keys = await store.keys();
  for (const key of keys.filter((k) => k.startsWith(CACHE_PREFIX))) {
    const cache = await store.open(key);
    if (await cache.match(SHELL_URL)) return true;
  }
  return false;
}

/** Tests only: forget the registration and every listener. */
export function resetPwa(): void {
  stopWatching?.();
  stopWatching = null;
  registration = null;
  waiting = null;
  installPrompt = null;
  reloadAsked = false;
  state = INITIAL;
  for (const listener of listeners) listener();
}
