// @vitest-environment node
import type { Rollup } from "vite";
import { describe, expect, it } from "vitest";

import { shellFiles } from "./serviceWorker";

const chunk = (fileName: string, extra: object = {}) =>
  ({
    type: "chunk",
    fileName,
    isEntry: false,
    imports: [],
    ...extra,
  }) as unknown as Rollup.OutputChunk;
const asset = (fileName: string) => ({ type: "asset", fileName }) as unknown as Rollup.OutputAsset;

describe("which built files are the app shell", () => {
  it("keeps the page, the entry and what it imports, and leaves the admin console out", () => {
    const bundle = {
      "index.html": asset("index.html"),
      "assets/index.js": chunk("assets/index.js", {
        isEntry: true,
        imports: ["assets/vendor.js"],
        viteMetadata: { importedCss: new Set(["assets/index.css"]) },
      }),
      "assets/vendor.js": chunk("assets/vendor.js"),
      "assets/AdminApp.js": chunk("assets/AdminApp.js", {
        viteMetadata: { importedCss: new Set(["assets/AdminApp.css"]) },
      }),
      "assets/index.css": asset("assets/index.css"),
      "assets/AdminApp.css": asset("assets/AdminApp.css"),
      "assets/font.woff2": asset("assets/font.woff2"),
      "assets/index.js.map": asset("assets/index.js.map"),
    } as unknown as Rollup.OutputBundle;
    expect(shellFiles(bundle).sort()).toEqual([
      "assets/font.woff2",
      "assets/index.css",
      "assets/index.js",
      "assets/vendor.js",
      "index.html",
    ]);
  });
});
