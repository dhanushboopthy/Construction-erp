import { afterEach, describe, expect, it, vi } from "vitest";

import { newUuid } from "./uuid";

const V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("newUuid", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns a v4 UUID", () => {
    expect(newUuid()).toMatch(V4);
  });

  it("still works when crypto.randomUUID is missing (plain-HTTP page)", () => {
    vi.stubGlobal("crypto", { getRandomValues: crypto.getRandomValues.bind(crypto) });
    const a = newUuid();
    expect(a).toMatch(V4);
    expect(newUuid()).not.toBe(a);
  });
});
