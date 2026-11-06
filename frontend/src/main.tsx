import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { AppUpdates } from "./pwa/AppUpdates";
import { startInstallCapture } from "./pwa/install";
import { startPwa } from "./pwa/updates";
import "./styles/global.css";

// admin.<domain> is the Duolink admin console (ADR 0012); its code loads only there, so shop
// users never download it. On a one-domain install (ADMIN_ON_MAIN_HOST) the admin signs in on the
// company's own sign-in page and the console opens at /admin on the same address.
const AdminApp = lazy(() => import("./admin/AdminApp").then((m) => ({ default: m.AdminApp })));
const { hostname, pathname } = window.location;
const isAdminHost =
  hostname.startsWith("admin.") || pathname === "/admin" || pathname.startsWith("/admin/");

// The manifest names the company at this address (Milestone 29); the console has its own.
const manifest = document.createElement("link");
manifest.rel = "manifest";
manifest.href = isAdminHost ? "/admin.webmanifest" : "/api/v1/tenant/manifest.webmanifest";
document.head.appendChild(manifest);

// The service worker runs in the production build only: in development it would serve stale
// files over Vite's own.
if (import.meta.env.PROD) void startPwa().catch(() => undefined);

// The browser's "install this app" offer arrives early; keep it for the top bar's button.
startInstallCapture();

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing in index.html");

createRoot(root).render(
  <StrictMode>
    {isAdminHost ? (
      <Suspense fallback={<p role="status">Loading…</p>}>
        <AdminApp />
      </Suspense>
    ) : (
      <App />
    )}
    <AppUpdates />
  </StrictMode>,
);
