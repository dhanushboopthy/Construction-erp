import { useSyncExternalStore } from "react";

/**
 * "Install app" (Milestone 29 follow-up). Chrome, Edge and Brave fire `beforeinstallprompt` once
 * the page is installable (HTTPS or localhost, a manifest and a service worker). The event comes
 * early, before any component exists, so it is caught here at start-up and kept until the button
 * asks for it. Safari has no such event: there the button never shows.
 */
interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let saved: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((l) => l());
}

export function startInstallCapture(target: Window = window): void {
  target.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); // keep the browser's own mini-bar away; the button asks instead
    saved = event as InstallPromptEvent;
    notify();
  });
  target.addEventListener("appinstalled", () => {
    saved = null;
    notify();
  });
}

/** Opens the browser's install dialog. The saved event works once; a new one comes if dismissed. */
export async function promptInstall(): Promise<"accepted" | "dismissed" | "unavailable"> {
  const event = saved;
  if (!event) return "unavailable";
  saved = null;
  notify();
  await event.prompt();
  const { outcome } = await event.userChoice;
  return outcome;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** True when the app is already running as an installed app (its own window, no browser bar). */
export function isInstalled(): boolean {
  const standalone = window.matchMedia?.("(display-mode: standalone)").matches ?? false;
  return standalone || (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

/** True while the browser has offered an install and the app is not yet installed. */
export function useCanInstall(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => saved !== null,
    () => false,
  );
}
