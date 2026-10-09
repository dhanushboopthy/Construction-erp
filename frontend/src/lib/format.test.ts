import { formatDateTime, formatMoney, isAmount, plural, trimDecimal } from "./format";

describe("formatMoney", () => {
  it("groups in lakhs and crores", () => {
    expect(formatMoney("10000.00")).toBe("10,000.00");
    expect(formatMoney("200000")).toBe("2,00,000.00");
    expect(formatMoney("12345678.5")).toBe("1,23,45,678.50");
    expect(formatMoney("-950.25")).toBe("-950.25");
  });
});

describe("isAmount", () => {
  it("accepts up to two decimals and rejects the rest", () => {
    expect(isAmount("10000")).toBe(true);
    expect(isAmount("0.50")).toBe(true);
    expect(isAmount("1.234")).toBe(false);
    expect(isAmount("-5")).toBe(false);
    expect(isAmount("")).toBe(false);
  });
});

describe("formatDateTime", () => {
  it("shows shop time and a dash for never", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("2026-10-09T11:00:00Z")).toMatch(/9 Oct 2026/);
  });
});

describe("trimDecimal and plural", () => {
  it("drops trailing zeros and pluralises counts", () => {
    expect(trimDecimal("20.000000")).toBe("20");
    expect(trimDecimal("1.2500")).toBe("1.25");
    expect(trimDecimal("1000")).toBe("1000");
    expect(trimDecimal("0.0000")).toBe("0");
    expect(plural(1, "item")).toBe("1 item");
    expect(plural(50, "item")).toBe("50 items");
  });
});
