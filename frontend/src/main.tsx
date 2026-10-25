import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles/global.css";

// admin.<domain> is the Duolink admin console (ADR 0012); its code loads only there, so shop
// users never download it.
const AdminApp = lazy(() => import("./admin/AdminApp").then((m) => ({ default: m.AdminApp })));
const isAdminHost = window.location.hostname.startsWith("admin.");

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
  </StrictMode>,
);
