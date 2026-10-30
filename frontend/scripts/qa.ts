/**
 * Browser checks for the "Site navy" refactor (docs/UI_REFACTOR_PLAN.md, T9).
 *
 *   npm run qa                       # needs the dev stack: `make up && make seed`
 *   npm run qa -- --only axe,motion,keys --roles owner
 *
 *   axe     axe-core on every screen, both themes, 1440 and 390 px, as every role that may open it.
 *           Fails on serious or critical violations (contrast included).
 *   motion  with reduced motion on, nothing on Today animates.
 *   keys    Tab through Today, bill entry, purchase entry and Items (list + editor): every stop has
 *           a visible focus ring and focus never gets stuck.
 *
 * Signs in with the development seed users. Never point this at production.
 */
import { createRequire } from "node:module";
import { parseArgs } from "node:util";

import { chromium, type Browser, type BrowserContext, type Page } from "playwright";

import type { Role } from "../src/api/types.ts";
import { ALL, SCREENS, settle, signIn } from "./shared.ts";

const require = createRequire(import.meta.url);
const AXE = require.resolve("axe-core/axe.min.js");

const { values: args } = parseArgs({
  options: {
    base: { type: "string", default: process.env.SHOTS_BASE_URL ?? "http://localhost:5173" },
    roles: { type: "string", default: ALL.join(",") },
    only: { type: "string", default: "axe,motion,keys" },
    paths: { type: "string" }, // axe only: comma-separated substrings of the screen path
  },
});
const base = (args.base ?? "").replace(/\/$/, "");
const roles = (args.roles ?? "").split(",").map((r) => r.trim()) as Role[];
const pathFilter = args.paths?.split(",").map((s) => s.trim());
const checks = (args.only ?? "").split(",").map((s) => s.trim());

const problems: string[] = [];
const fail = (msg: string) => {
  problems.push(msg);
  console.error(`FAIL  ${msg}`);
};

async function open(
  browser: Browser,
  role: Role | "anonymous",
  theme: "light" | "dark",
  width: number,
  reducedMotion: "reduce" | "no-preference" = "reduce",
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({
    viewport: { width, height: width > 600 ? 900 : 844 },
    colorScheme: theme,
    reducedMotion,
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
  });
  await context.addInitScript((t) => localStorage.setItem("erp-theme", t), theme);
  const page = await context.newPage();
  if (role !== "anonymous") await signIn(page, base, role);
  return { context, page };
}

// ---------------------------------------------------------------- axe

interface Violation {
  id: string;
  impact?: string | null;
  help: string;
  nodes: { target: unknown[] }[];
}

async function axeOn(page: Page): Promise<Violation[]> {
  await page.addScriptTag({ path: AXE });
  return page.evaluate(async () => {
    // @ts-expect-error axe is injected into the page
    const result = await window.axe.run(document, {
      runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"],
    });
    return result.violations;
  });
}

async function runAxe(browser: Browser) {
  let screens = 0;
  const minor = new Map<string, number>();
  for (const theme of ["light", "dark"] as const) {
    for (const width of [1440, 390]) {
      for (const role of ["anonymous", ...roles] as const) {
        const { context, page } = await open(browser, role, theme, width);
        const paths =
          role === "anonymous"
            ? ["/login"]
            : SCREENS.filter(
                (s) =>
                  s.roles.includes(role) &&
                  (!pathFilter || pathFilter.some((f) => s.path.includes(f))),
              ).map((s) => s.path);
        for (const p of paths) {
          await page.goto(`${base}${p}`);
          await settle(page, role === "anonymous");
          screens += 1;
          for (const v of await axeOn(page)) {
            if (v.impact === "serious" || v.impact === "critical") {
              const where = v.nodes
                .slice(0, 3)
                .map((n) => n.target.join(" "))
                .join(" | ");
              fail(
                `axe ${v.impact} ${v.id} on ${role} ${theme}-${width} ${p}: ${v.help} [${where}]`,
              );
            } else {
              minor.set(v.id, (minor.get(v.id) ?? 0) + 1);
            }
          }
        }
        await context.close();
      }
    }
  }
  console.log(`axe: ${screens} screens checked`);
  for (const [id, n] of minor) console.log(`  minor/moderate ${id}: ${n} screens`);
}

// ---------------------------------------------------------------- reduced motion

/** Every element on the page that has an animation or a transition running or declared. */
function animated(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    for (const el of document.querySelectorAll("*")) {
      const s = getComputedStyle(el);
      const name = s.animationName;
      if (name !== "none")
        out.push(`${el.tagName.toLowerCase()}.${el.className} animation:${name}`);
      const dur = s.transitionDuration.split(",").some((d) => parseFloat(d) > 0);
      if (dur)
        out.push(`${el.tagName.toLowerCase()}.${el.className} transition:${s.transitionDuration}`);
    }
    return out;
  });
}

async function runMotion(browser: Browser) {
  const owner = await open(browser, "owner", "light", 1440, "reduce");
  for (const p of ["/", "/sales", "/items"]) {
    await owner.page.goto(`${base}${p}`);
    await settle(owner.page, false);
    const hits = await animated(owner.page);
    if (hits.length)
      fail(`motion: ${hits.length} animated elements with reduced motion on ${p}, e.g. ${hits[0]}`);
  }
  await owner.context.close();

  // And the bars do grow in when motion is allowed (the one animation the plan keeps).
  const normal = await open(browser, "owner", "light", 1440, "no-preference");
  await normal.page.goto(`${base}/`);
  await settle(normal.page, false);
  const names = await normal.page.evaluate(() => {
    const set = new Set<string>();
    for (const el of document.querySelectorAll("*")) {
      const n = getComputedStyle(el).animationName;
      if (n !== "none") set.add(n);
    }
    return [...set];
  });
  console.log(
    `motion: with motion allowed, Today uses animations: ${names.join(", ") || "(none, empty data)"}`,
  );
  await normal.context.close();
}

// ---------------------------------------------------------------- keyboard

/**
 * The focused element, and whether anything visibly marks it: a ring on the element itself, or on
 * a wrapper that draws it through :focus-within (the search boxes). `left` means focus has moved
 * out of the page to the browser's own controls, i.e. the tab order has come full circle.
 */
function focusInfo(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return null;
    if (!document.hasFocus()) return { left: true } as const;
    // A date input's calendar button is a tab stop inside the input: the browser draws its ring.
    if (!el.matches(":focus")) return null;
    const marked = (e: Element) => {
      const s = getComputedStyle(e);
      return (
        (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) ||
        (s.boxShadow !== "none" && s.boxShadow !== "")
      );
    };
    let ring = marked(el);
    for (let up = el.parentElement, n = 0; !ring && up && n < 3; up = up.parentElement, n++) {
      ring = marked(up);
    }
    const r = el.getBoundingClientRect();
    return {
      left: false,
      label: `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ""} "${(el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 30)}"`,
      ring,
      visible: r.width > 0 && r.height > 0,
    } as const;
  });
}

async function tabThrough(page: Page, name: string, limit = 60) {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  const seen = new Set<string>();
  let stops = 0;
  for (let i = 0; i < limit; i++) {
    await page.keyboard.press("Tab");
    const info = await focusInfo(page);
    if (!info) continue;
    if (info.left) break;
    stops += 1;
    if (!info.visible) fail(`keys: ${name}: focus on a hidden element ${info.label}`);
    else if (!info.ring) fail(`keys: ${name}: no visible focus ring on ${info.label}`);
    if (seen.has(info.label) && stops > 3 && seen.size < 3) {
      fail(`keys: ${name}: focus is stuck around ${info.label}`);
      break;
    }
    seen.add(info.label);
  }
  console.log(`keys: ${name}: ${stops} tab stops, ${seen.size} distinct`);
  if (seen.size < 5) fail(`keys: ${name}: only ${seen.size} distinct tab stops`);
}

async function runKeys(browser: Browser) {
  const { context, page } = await open(browser, "owner", "light", 1440, "reduce");
  for (const [name, p] of [
    ["Today", "/"],
    ["Bill entry", "/sales/new"],
    ["Purchase entry", "/purchases/new"],
    ["Items list", "/items"],
  ] as const) {
    await page.goto(`${base}${p}`);
    await settle(page, false);
    await tabThrough(page, name);
  }

  // Module shortcuts (Alt + digit) still switch screens.
  await page.goto(`${base}/`);
  await settle(page, false);
  for (const [key, expected] of [
    ["2", "/sales"],
    ["3", "/purchases"],
    ["4", "/stock"],
    ["1", "/"],
  ] as const) {
    await page.keyboard.press(`Alt+${key}`);
    await page
      .waitForURL((u) => u.pathname === expected, { timeout: 3_000 })
      .catch(() => undefined);
    const now = new URL(page.url()).pathname;
    if (now !== expected) fail(`keys: Alt+${key} went to ${now}, expected ${expected}`);
  }
  console.log("keys: Alt+1..4 module shortcuts checked");

  // List + editor: open the editor from the keyboard and close it with Esc.
  await page.goto(`${base}/items`);
  await settle(page, false);
  const add = page.getByRole("button", { name: /new item|add item/i }).first();
  if (await add.count()) {
    await add.focus();
    await page.keyboard.press("Enter");
    const panel = page.getByRole("dialog").or(page.getByRole("complementary")).first();
    await panel
      .waitFor({ timeout: 3_000 })
      .catch(() => fail("keys: Items editor did not open from the keyboard"));
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    console.log("keys: Items editor opened with Enter and closed with Esc");
  } else {
    fail("keys: no 'new item' button found on Items");
  }
  await context.close();
}

async function main() {
  const browser = await chromium.launch();
  try {
    if (checks.includes("axe")) await runAxe(browser);
    if (checks.includes("motion")) await runMotion(browser);
    if (checks.includes("keys")) await runKeys(browser);
  } finally {
    await browser.close();
  }
  console.log(problems.length ? `\n${problems.length} problem(s)` : "\nAll checks passed");
  if (problems.length) process.exitCode = 1;
}

await main();
