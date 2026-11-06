import { comboFromEvent, isEditorKey, keysOf, normaliseCombo, usedBy, whyNot } from "./combo";

const press = (over: Partial<Parameters<typeof comboFromEvent>[0]>) => ({
  altKey: true,
  ctrlKey: false,
  metaKey: false,
  shiftKey: false,
  key: "",
  ...over,
});

describe("normaliseCombo", () => {
  it.each([
    ["Alt+N", "Alt+N"],
    ["alt+n", "Alt+N"],
    [" ALT + shift + 7 ", "Alt+Shift+7"],
    ["shift+alt+q", "Alt+Shift+Q"],
  ])("%s becomes %s", (raw, stored) => {
    expect(normaliseCombo(raw)).toBe(stored);
  });

  it.each([
    "",
    "N",
    "Alt",
    "Alt+",
    "Shift+N",
    "Ctrl+Alt+N",
    "Alt+Meta+N",
    "Alt+Alt+N",
    "Alt+NN",
    "Alt+F4",
  ])("refuses %j", (raw) => {
    expect(normaliseCombo(raw)).toBeNull();
    expect(whyNot(raw)).not.toBeNull();
  });

  it.each(["Alt+D", "alt+f", "Alt+E"])("refuses %s because the browser takes it", (raw) => {
    expect(whyNot(raw)).toMatch(/browser/);
  });
});

describe("comboFromEvent", () => {
  it("reads the physical key, so Alt cannot change it", () => {
    expect(comboFromEvent(press({ code: "KeyN", key: "ñ" }))).toBe("Alt+N");
    expect(comboFromEvent(press({ code: "Digit2", key: "™" }))).toBe("Alt+2");
    expect(comboFromEvent(press({ code: "Numpad5", key: "5" }))).toBe("Alt+5");
  });

  it("falls back to the typed key", () => {
    expect(comboFromEvent(press({ key: "n" }))).toBe("Alt+N");
    expect(comboFromEvent(press({ key: "0" }))).toBe("Alt+0");
  });

  it("adds Shift", () => {
    expect(comboFromEvent(press({ code: "KeyN", key: "N", shiftKey: true }))).toBe("Alt+Shift+N");
  });

  it("is not a shortcut without Alt, or with Ctrl or Meta, or on a non-letter key", () => {
    expect(comboFromEvent(press({ altKey: false, code: "KeyN", key: "n" }))).toBeNull();
    expect(comboFromEvent(press({ ctrlKey: true, code: "KeyN", key: "n" }))).toBeNull();
    expect(comboFromEvent(press({ metaKey: true, code: "KeyN", key: "n" }))).toBeNull();
    expect(comboFromEvent(press({ code: "Enter", key: "Enter" }))).toBeNull();
    expect(comboFromEvent(press({ code: "AltLeft", key: "Alt" }))).toBeNull();
  });
});

describe("isEditorKey", () => {
  const editor = { ctrlKey: true, shiftKey: true, altKey: true, metaKey: false };
  it("is Ctrl+Shift+Alt+1 and nothing less", () => {
    expect(isEditorKey({ ...editor, code: "Digit1", key: "!" })).toBe(true);
    expect(isEditorKey({ ...editor, code: "", key: "1" })).toBe(true);
    expect(isEditorKey({ ...editor, ctrlKey: false, code: "Digit1", key: "1" })).toBe(false);
    expect(isEditorKey({ ...editor, shiftKey: false, code: "Digit1", key: "1" })).toBe(false);
    expect(isEditorKey({ ...editor, code: "Digit2", key: "2" })).toBe(false);
  });
});

describe("helpers", () => {
  it("splits a combination into its keys", () => {
    expect(keysOf("Alt+Shift+N")).toEqual(["Alt", "Shift", "N"]);
  });

  it("finds the action that already uses a combination", () => {
    const combos = { a: "Alt+1", b: "Alt+2" };
    expect(usedBy(combos, "Alt+2", "a")).toBe("b");
    expect(usedBy(combos, "Alt+2", "b")).toBeUndefined();
    expect(usedBy(combos, "Alt+9", "a")).toBeUndefined();
  });
});
