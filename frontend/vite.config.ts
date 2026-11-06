/// <reference types="vitest/config" />
import { readFileSync } from "node:fs";
import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { serviceWorker } from "./scripts/serviceWorker";

// In development the API runs on :8000; in production nginx serves both on one origin.
const apiTarget = process.env.VITE_API_PROXY ?? "http://localhost:8000";

// The build stamp the admin's "App and updates" page shows (Milestone 29): the package version,
// and APP_BUILD (the commit, say) or else the time of the build.
const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as {
  version: string;
};
const appBuild = process.env.APP_BUILD || new Date().toISOString().slice(0, 16).replace("T", " ");

export default defineConfig({
  plugins: [
    react(),
    serviceWorker({ entry: fileURLToPath(new URL("./src/pwa/sw.ts", import.meta.url)) }),
  ],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __APP_BUILD__: JSON.stringify(appBuild),
  },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    testTimeout: 20_000,
  },
});
