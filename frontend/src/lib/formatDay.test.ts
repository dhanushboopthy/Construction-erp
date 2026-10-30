import { formatDay } from "./format";

describe("formatDay", () => {
  it("writes a date the way the shop reads it, without shifting it by time zone", () => {
    expect(formatDay("2026-10-09")).toBe("9 Oct 2026");
    expect(formatDay("2026-01-01")).toBe("1 Jan 2026");
    expect(formatDay("2026-10-09T23:30:00+05:30")).toBe("9 Oct 2026");
  });

  it("shows a dash when there is no date", () => {
    expect(formatDay(null)).toBe("—");
    expect(formatDay(undefined)).toBe("—");
  });
});
