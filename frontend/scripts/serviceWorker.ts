/**
 * Builds /sw.js (Milestone 29). No PWA plugin is installed, so this small Vite plugin does the
 * one thing one would: after `vite build` has written the app, it bundles src/pwa/sw.ts with
 * the list of files that make up the app shell and an id made from their contents. A new build
 * therefore gives a new sw.js, which is how the browser notices it.
 *
 * The shell is index.html, the entry script and everything it imports statically, their styles,
 * the fonts and images, and the files in public/. Chunks only loaded later (the Duolink admin
 * console) are left out, so a shop's browser never downloads them; the worker keeps them once
 * opened. Nothing from /api is ever in the list.
 */
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { build } from "esbuild";
import type { Plugin, ResolvedConfig, Rollup } from "vite";

type Bundle = Rollup.OutputBundle;
type Chunk = Rollup.OutputChunk & { viteMetadata?: { importedCss: Set<string> } };

function filesIn(dir: string): string[] {
  let found: string[] = [];
  let names: string[];
  try {
    names = readdirSync(dir);
  } catch {
    return found; // no public folder
  }
  for (const name of names) {
    const path = join(dir, name);
    found = statSync(path).isDirectory() ? [...found, ...filesIn(path)] : [...found, path];
  }
  return found;
}

/** The built files of the app shell, by their file names in the output folder. */
export function shellFiles(bundle: Bundle): string[] {
  const chunks = new Map<string, Chunk>();
  for (const item of Object.values(bundle)) {
    if (item.type === "chunk") chunks.set(item.fileName, item);
  }
  const statics = new Set<string>();
  const visit = (fileName: string) => {
    if (statics.has(fileName)) return;
    statics.add(fileName);
    for (const imported of chunks.get(fileName)?.imports ?? []) visit(imported);
  };
  for (const chunk of chunks.values()) if (chunk.isEntry) visit(chunk.fileName);

  const shellCss = new Set<string>();
  const lazyCss = new Set<string>();
  for (const chunk of chunks.values()) {
    const css = chunk.viteMetadata?.importedCss ?? new Set<string>();
    for (const file of css) (statics.has(chunk.fileName) ? shellCss : lazyCss).add(file);
  }
  return Object.values(bundle)
    .filter((item) =>
      item.type === "chunk"
        ? statics.has(item.fileName)
        : !item.fileName.endsWith(".map") &&
          (shellCss.has(item.fileName) || !lazyCss.has(item.fileName)),
    )
    .map((item) => item.fileName);
}

export function serviceWorker({ entry }: { entry: string }): Plugin {
  let config: ResolvedConfig;
  return {
    name: "erp-service-worker",
    apply: "build",
    configResolved(resolved) {
      config = resolved;
    },
    async writeBundle(options, bundle) {
      const outDir = options.dir ?? config.build.outDir;
      const publicFiles = config.publicDir
        ? filesIn(config.publicDir).map((path) => relative(config.publicDir, path))
        : [];
      const files = [...new Set([...shellFiles(bundle), ...publicFiles])]
        .map((file) => file.split(sep).join("/"))
        .filter((file) => file !== "sw.js")
        .sort();
      const hash = createHash("sha256");
      for (const file of files) {
        hash.update(file);
        hash.update(readFileSync(join(outDir, file)));
      }
      const buildId = hash.digest("hex").slice(0, 12);
      const result = await build({
        entryPoints: [entry],
        bundle: true,
        write: false,
        format: "iife",
        target: "es2020",
        minify: true,
        define: {
          __PRECACHE__: JSON.stringify(files.map((file) => `/${file}`)),
          __BUILD_ID__: JSON.stringify(buildId),
        },
      });
      const code = result.outputFiles[0]?.text;
      if (!code) throw new Error("The service worker did not build");
      writeFileSync(join(outDir, "sw.js"), code);
      config.logger.info(`sw.js: ${files.length} shell files, build ${buildId}`);
    },
  };
}
