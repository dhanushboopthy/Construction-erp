/**
 * Screenshots of every screen, for comparing the UI before and after the "Site navy" refactor
 * (docs/UI_REFACTOR_PLAN.md, T0 and T9).
 *
 *   npm run shots                         # needs the dev stack: `make up && make seed`
 *   npm run shots -- --out screenshots/after-t4 --roles owner --only sales,reports
 *
 * Output (git-ignored): screenshots/<label>/<role>/<theme>-<width>/<screen>.png, plus
 * manifest.json listing what was captured and anything that went wrong.
 *
 * Signs in with the development seed users (docs/DEVELOPMENT.md). Never point this at production.
 * Animation is switched off (reduced motion) so every shot is the settled state.
 */
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseArgs } from "node:util";

import { chromium, type Browser } from "playwright";

import type { Role } from "../src/api/types.ts";
import { modulesFor } from "../src/modules.ts";
import { ALL, SCREENS, settle, signIn, slug, type Screen } from "./shared.ts";

const WIDTHS = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
];
const THEMES = ["light", "dark"] as const;

const { values: args } = parseArgs({
  options: {
    base: { type: "string", default: process.env.SHOTS_BASE_URL ?? "http://localhost:5173" },
    out: { type: "string", default: "screenshots/baseline" },
    roles: { type: "string", default: ALL.join(",") },
    only: { type: "string" }, // comma-separated substrings of the screen path
  },
});

const roles = (args.roles ?? ALL.join(",")).split(",").map((r) => r.trim()) as Role[];
const only = args.only?.split(",").map((s) => s.trim());

function screensFor(role: Role): Screen[] {
  return SCREENS.filter(
    (s) => s.roles.includes(role) && (!only || only.some((o) => s.path.includes(o))),
  );
}

/** Fail loudly if a module in src/modules.ts has no screen above, or the reverse. */
function checkCoverage() {
  const problems: string[] = [];
  for (const role of ALL) {
    for (const m of modulesFor(role)) {
      const hit = SCREENS.find((s) => s.path === m.path && s.roles.includes(role));
      if (!hit) problems.push(`${m.path} (${m.label}) is a module for ${role} but not in SCREENS`);
    }
  }
  if (problems.length) throw new Error(`Screen list out of date:\n  ${problems.join("\n  ")}`);
}

interface Entry {
  role: Role | "anonymous";
  theme: string;
  width: number;
  path: string;
  file: string;
  finalPath: string;
  apiErrors: string[];
}

async function capture(
  browser: Browser,
  base: string,
  outDir: string,
  role: Role | "anonymous",
  theme: (typeof THEMES)[number],
  size: { width: number; height: number },
  paths: string[],
): Promise<Entry[]> {
  const context = await browser.newContext({
    viewport: size,
    colorScheme: theme,
    reducedMotion: "reduce",
    locale: "en-IN",
    timezoneId: "Asia/Kolkata",
  });
  await context.addInitScript((t) => localStorage.setItem("erp-theme", t), theme);
  const page = await context.newPage();
  const apiErrors: string[] = [];
  page.on("response", (res) => {
    const signedOutRefresh = role === "anonymous" && res.url().endsWith("/auth/refresh");
    if (res.url().includes("/api/") && res.status() >= 400 && !signedOutRefresh) {
      apiErrors.push(`${res.status()} ${new URL(res.url()).pathname}`);
    }
  });

  const entries: Entry[] = [];
  try {
    if (role !== "anonymous") await signIn(page, base, role);
    for (const p of paths) {
      apiErrors.length = 0;
      await page.goto(`${base}${p}`);
      await settle(page, role === "anonymous");
      const dir = path.join(outDir, role, `${theme}-${size.width}`);
      await mkdir(dir, { recursive: true });
      const file = path.join(dir, `${slug(p)}.png`);
      await page.screenshot({ path: file, fullPage: true });
      entries.push({
        role,
        theme,
        width: size.width,
        path: p,
        file: path.relative(outDir, file),
        finalPath: new URL(page.url()).pathname,
        apiErrors: [...apiErrors],
      });
    }
  } finally {
    await context.close();
  }
  return entries;
}

async function main() {
  checkCoverage();
  const base = (args.base ?? "").replace(/\/$/, "");
  const outDir = path.resolve(args.out ?? "screenshots/baseline");
  // The folder is emptied first, so refuse anything outside the git-ignored screenshots/ folder.
  if (!outDir.startsWith(`${path.resolve("screenshots")}${path.sep}`)) {
    throw new Error(`--out must be a folder inside screenshots/ (got ${outDir})`);
  }
  await rm(outDir, { recursive: true, force: true });
  await mkdir(outDir, { recursive: true });

  const browser = await chromium.launch();
  const entries: Entry[] = [];
  try {
    for (const theme of THEMES) {
      for (const size of WIDTHS) {
        entries.push(
          ...(await capture(browser, base, outDir, "anonymous", theme, size, ["/login"])),
        );
        for (const role of roles) {
          const paths = screensFor(role).map((s) => s.path);
          console.log(`${role} ${theme} ${size.width}px: ${paths.length} screens`);
          entries.push(...(await capture(browser, base, outDir, role, theme, size, paths)));
        }
      }
    }
  } finally {
    await browser.close();
  }

  const redirected = entries.filter((e) => e.path !== "/login" && e.finalPath !== e.path);
  const failed = entries.filter((e) => e.apiErrors.length > 0);
  await writeFile(
    path.join(outDir, "manifest.json"),
    JSON.stringify(
      { base, taken: new Date().toISOString(), shots: entries.length, entries },
      null,
      2,
    ),
  );
  console.log(`\n${entries.length} screenshots in ${path.relative(process.cwd(), outDir)}`);
  for (const e of redirected) console.error(`REDIRECTED  ${e.role} ${e.path} -> ${e.finalPath}`);
  for (const e of failed) {
    console.error(
      `API ERROR   ${e.role} ${e.theme}-${e.width} ${e.path}: ${e.apiErrors.join(", ")}`,
    );
  }
  if (redirected.length > 0) process.exitCode = 1;
}

await main();
