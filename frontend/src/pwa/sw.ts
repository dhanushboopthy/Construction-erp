/**
 * The service worker (Milestone 29), written by hand: no PWA plugin is installed. The build
 * (scripts/serviceWorker.ts) bundles this file to /sw.js with the list of the build's files and
 * a build id, so every new build is a new worker the browser notices.
 *
 * It keeps the app shell only (the page, its scripts, styles, fonts and icons) so the app opens
 * with no connection and says so. It never keeps an API answer: see swRoutes.ts. It never takes
 * over by itself either: a new build waits until the person presses "Update now".
 */
import { CACHE_PREFIX, routeFor, SHELL_URL } from "./swRoutes";

declare const __PRECACHE__: string[];
declare const __BUILD_ID__: string;

// The few service worker types used here (the app is compiled with the DOM types, not the
// WebWorker ones).
interface ExtendableEvent extends Event {
  waitUntil(promise: Promise<unknown>): void;
}
interface FetchEvent extends ExtendableEvent {
  request: Request;
  respondWith(response: Promise<Response>): void;
}
interface WorkerScope {
  location: Location;
  skipWaiting(): Promise<void>;
  clients: { claim(): Promise<void> };
  addEventListener(type: "install" | "activate", listener: (event: ExtendableEvent) => void): void;
  addEventListener(type: "fetch", listener: (event: FetchEvent) => void): void;
  addEventListener(type: "message", listener: (event: MessageEvent) => void): void;
}

const worker = self as unknown as WorkerScope;
const CACHE = `${CACHE_PREFIX}${__BUILD_ID__}`;
const PRECACHED = new Set(__PRECACHE__);

worker.addEventListener("install", (event) => {
  // No skipWaiting here: the page decides when the new build takes over.
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(__PRECACHE__)));
});

worker.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => worker.clients.claim()),
  );
});

worker.addEventListener("message", (event) => {
  const data = event.data as { type?: string } | null;
  // Sent by "Update now" only, never on its own.
  if (data?.type === "SKIP_WAITING") void worker.skipWaiting();
});

async function fromCache(request: Request): Promise<Response> {
  const hit = await caches.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  // A build file opened later (the admin's screens, say) is kept for the next time offline.
  if (response.ok && new URL(request.url).pathname.startsWith("/assets/")) {
    const cache = await caches.open(CACHE);
    await cache.put(request, response.clone());
  }
  return response;
}

async function page(request: Request): Promise<Response> {
  try {
    return await fetch(request);
  } catch (error) {
    const shell = await caches.match(SHELL_URL);
    if (shell) return shell;
    throw error;
  }
}

worker.addEventListener("fetch", (event) => {
  const { request } = event;
  const route = routeFor(request, worker.location.origin, PRECACHED);
  if (route === "network") return; // the browser fetches it; nothing is kept
  event.respondWith(route === "shell" ? page(request) : fromCache(request));
});
