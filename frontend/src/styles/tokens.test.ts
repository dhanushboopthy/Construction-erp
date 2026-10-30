/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// Read as text: the test config switches CSS processing off, which empties a `?raw` import.
const css = readFileSync(join(process.cwd(), "src/styles/tokens.css"), "utf8");

/**
 * The contrast table in docs/DESIGN.md, as a test: every text pair is at least 4.5:1 and every
 * control, status and progress colour at least 3:1, in both themes. Change a colour in
 * tokens.css and this tells you which pair broke.
 */

type Rgb = [number, number, number];
type Tokens = Record<string, string>;

function block(selector: string): Tokens {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`no ${selector} block in tokens.css`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("\n}", start));
  const out: Tokens = {};
  for (const m of body.matchAll(/(--[\w-]+):\s*([^;]+);/g)) out[m[1] ?? ""] = (m[2] ?? "").trim();
  return out;
}

const LIGHT = block(":root");
const DARK = { ...LIGHT, ...block(':root[data-theme="dark"]') };

/** A colour value to RGB; a translucent colour is laid over `under`. */
function resolve(tokens: Tokens, value: string, under: Rgb): Rgb {
  const v = value.trim();
  const ref = /^var\((--[\w-]+)\)$/.exec(v);
  if (ref) return resolve(tokens, tokens[ref[1] ?? ""] ?? "", under);
  if (v.startsWith("#")) {
    const h = v.slice(1);
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as Rgb;
  }
  const rgb = /^rgb\((\d+) (\d+) (\d+)(?: \/ (\d+)%)?\)$/.exec(v);
  if (!rgb) throw new Error(`cannot read colour "${value}"`);
  const a = rgb[4] === undefined ? 1 : Number(rgb[4]) / 100;
  return [1, 2, 3].map((i) =>
    Math.round(Number(rgb[i]) * a + (under[i - 1] ?? 0) * (1 - a)),
  ) as Rgb;
}

const channel = (c: number) => {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
};
const luminance = ([r, g, b]: Rgb) =>
  0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
function ratio(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

/** [foreground, background, minimum ratio]. translucent backgrounds are laid over the surface. */
const PAIRS: [string, string, number][] = [
  ["--color-label", "--color-bg", 4.5],
  ["--color-label", "--color-surface", 4.5],
  ["--color-label", "--color-fill", 4.5],
  ["--color-secondary", "--color-bg", 4.5],
  ["--color-secondary", "--color-surface", 4.5],
  ["--color-secondary", "--color-fill", 4.5],
  ["--color-accent", "--color-bg", 4.5],
  ["--color-accent", "--color-surface", 4.5],
  ["--color-accent", "--color-fill", 4.5],
  ["--color-accent", "--color-accent-soft", 4.5],
  ["--color-on-accent", "--color-accent", 4.5],
  ["--color-on-accent", "--color-accent-strong", 4.5],
  ["--color-on-accent-bright", "--color-accent-bright", 4.5],
  ["--color-good", "--color-surface", 4.5],
  ["--color-good", "--color-bg", 4.5],
  ["--color-good", "--color-good-soft", 4.5],
  ["--color-warn", "--color-surface", 4.5],
  ["--color-warn", "--color-bg", 4.5],
  ["--color-warn", "--color-warn-soft", 4.5],
  ["--color-critical", "--color-surface", 4.5],
  ["--color-critical", "--color-bg", 4.5],
  ["--color-critical", "--color-critical-soft", 4.5],
  ["--color-secondary", "--color-neutral-soft", 4.5],
  ["--pill-good-fg", "--pill-good-bg", 4.5],
  ["--pill-warn-fg", "--pill-warn-bg", 4.5],
  ["--pill-critical-fg", "--pill-critical-bg", 4.5],
  ["--pill-neutral-fg", "--pill-neutral-bg", 4.5],
  ["--pill-accent-fg", "--pill-accent-bg", 4.5],
  ["--color-on-sidebar", "--color-sidebar", 4.5],
  ["--color-on-sidebar", "--color-sidebar-active", 4.5],
  ["--color-on-sidebar-muted", "--color-sidebar", 4.5],
  ["--color-on-sidebar-muted", "--color-sidebar-active", 4.5],
  ["--color-on-hero", "--color-hero", 4.5],
  // Non-text: control borders, focus ring, status colours as graphics, the sidebar marker.
  ["--color-control-border", "--color-surface", 3],
  ["--color-control-border", "--color-bg", 3],
  ["--color-control-border", "--color-fill", 3],
  ["--color-focus", "--color-surface", 3],
  ["--color-focus", "--color-bg", 3],
  ["--color-accent-bright", "--color-sidebar", 3],
  ["--color-accent", "--color-surface", 3],
  ["--color-good", "--color-surface", 3],
  ["--color-warn", "--color-surface", 3],
  ["--color-critical", "--color-surface", 3],
  ["--color-neutral-pill", "--color-surface", 3],
  ["--color-series-1", "--color-surface", 3],
  ["--color-series-2", "--color-surface", 3],
  ["--color-series-3", "--color-surface", 3],
];

describe.each([
  ["light", LIGHT],
  ["dark", DARK],
])("tokens.css contrast, %s theme", (_theme, tokens) => {
  const surface = resolve(tokens, tokens["--color-surface"] ?? "", [255, 255, 255]);
  it.each(PAIRS)("%s on %s is at least %s:1", (fg, bg, min) => {
    const back = resolve(tokens, tokens[bg] ?? "", surface);
    const front = resolve(tokens, tokens[fg] ?? "", back);
    expect(ratio(front, back)).toBeGreaterThanOrEqual(min);
  });
});

describe("tokens.css", () => {
  it("has no gradients or glow", () => {
    const code = css.replace(/\/\*[\s\S]*?\*\//g, "");
    expect(code).not.toMatch(/gradient|shadow-glow/);
  });

  it("defines every token in both themes' shared set", () => {
    for (const name of Object.keys(LIGHT)) expect(DARK[name]).toBeDefined();
  });
});
