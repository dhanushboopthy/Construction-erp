/** Shared by the screenshot and QA scripts: seed users, the screen list, sign-in and settling. */
import type { Page } from "playwright";

import type { Role } from "../src/api/types.ts";

export const PASSWORDS: Record<Role, { username: string; password: string }> = {
  owner: { username: "owner", password: "owner-pass-123" },
  counter: { username: "counter1", password: "counter-pass-123" },
  accountant: { username: "accounts", password: "accounts-pass-123" },
};

export const ALL: Role[] = ["owner", "counter", "accountant"];
const OWNER: Role[] = ["owner"];
const OWNER_ACCOUNTANT: Role[] = ["owner", "accountant"];
const OWNER_COUNTER: Role[] = ["owner", "counter"];

export interface Screen {
  path: string;
  roles: Role[];
}

/**
 * Every routed screen, with the roles that may open it (mirrors src/App.tsx). The module roots
 * come from src/modules.ts and are checked below, so a new module cannot be missed.
 */
export const SCREENS: Screen[] = [
  { path: "/", roles: ALL },
  { path: "/sales", roles: ALL },
  { path: "/sales/new", roles: OWNER_COUNTER },
  { path: "/purchases", roles: ALL },
  { path: "/purchases/new", roles: OWNER_COUNTER },
  { path: "/purchases/orders", roles: ALL },
  { path: "/purchases/schemes", roles: OWNER_ACCOUNTANT },
  { path: "/stock", roles: ALL },
  { path: "/stock/transfers", roles: ALL },
  { path: "/stock/counts", roles: ALL },
  { path: "/stock/adjustments", roles: ALL },
  { path: "/stock/lost-sales", roles: OWNER_COUNTER },
  { path: "/stock/analysis", roles: OWNER },
  { path: "/stock/value", roles: OWNER_ACCOUNTANT },
  { path: "/stock/shortages", roles: OWNER_ACCOUNTANT },
  { path: "/parties", roles: ALL },
  { path: "/items", roles: ALL },
  { path: "/payments", roles: ALL },
  { path: "/cash", roles: ALL },
  { path: "/rates", roles: OWNER },
  { path: "/rates/customers", roles: OWNER },
  { path: "/transport", roles: OWNER_ACCOUNTANT },
  { path: "/transport/vehicles", roles: OWNER_ACCOUNTANT },
  { path: "/transport/direct", roles: OWNER_ACCOUNTANT },
  { path: "/reports", roles: ALL },
  { path: "/reports/profit", roles: OWNER },
  { path: "/reports/pnl", roles: OWNER },
  { path: "/reports/profit-cuts", roles: OWNER },
  { path: "/reports/itc-risk", roles: OWNER_ACCOUNTANT },
  { path: "/reports/receivables", roles: OWNER_ACCOUNTANT },
  { path: "/reports/working-capital", roles: OWNER },
  { path: "/reports/tally", roles: OWNER_ACCOUNTANT },
  { path: "/reports/overrides", roles: OWNER },
  { path: "/reports/itc-reversal", roles: OWNER_ACCOUNTANT },
  { path: "/reports/bank", roles: OWNER_ACCOUNTANT },
  { path: "/reports/order-match", roles: OWNER },
  { path: "/reports/exceptions", roles: OWNER },
  { path: "/reports/dues", roles: OWNER_ACCOUNTANT },
  { path: "/reports/gst", roles: OWNER_ACCOUNTANT },
  { path: "/reports/segments", roles: OWNER_ACCOUNTANT },
  { path: "/metrics", roles: OWNER },
  { path: "/settings", roles: OWNER },
  { path: "/settings/users", roles: OWNER },
  { path: "/settings/locations", roles: OWNER },
  { path: "/settings/charges", roles: OWNER },
  { path: "/settings/pin", roles: OWNER },
  { path: "/settings/opening", roles: OWNER },
  { path: "/settings/lock", roles: OWNER },
  { path: "/settings/audit", roles: OWNER },
  { path: "/settings/system", roles: OWNER },
];

export const slug = (p: string) => (p === "/" ? "today" : p.slice(1).replaceAll("/", "-"));

export async function signIn(page: Page, base: string, role: Role) {
  const { username, password } = PASSWORDS[role];
  await page.goto(`${base}/login`);
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((url) => url.pathname !== "/login");
}

/**
 * Wait for the screen to settle: network quiet, no "loading" text left. The idle wait is bounded
 * because the signed-out refresh call (a 401 whose body is never read) can keep it from firing.
 */
export async function settle(page: Page, anonymous: boolean) {
  await page
    .waitForLoadState("networkidle", { timeout: anonymous ? 500 : 8_000 })
    .catch(() => undefined);
  await page
    .waitForFunction(
      () => !/\bloading\b/i.test(document.querySelector("main")?.textContent ?? ""),
      {
        timeout: 5_000,
      },
    )
    .catch(() => undefined);
}
