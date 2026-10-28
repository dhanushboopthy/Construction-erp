import { addDays, fyBounds, fyLabel, fyStartYear, monthBounds } from "./dates";

describe("dates", () => {
  it("shifts by whole days across month ends", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
  });

  it("gives a month's first and last day, leap years included", () => {
    expect(monthBounds("2026-10")).toEqual(["2026-10-01", "2026-10-31"]);
    expect(monthBounds("2028-02")).toEqual(["2028-02-01", "2028-02-29"]);
    expect(monthBounds("2026-02")).toEqual(["2026-02-01", "2026-02-28"]);
  });

  it("puts January to March in the financial year that began the April before", () => {
    expect(fyStartYear("2026-04-01")).toBe(2026);
    expect(fyStartYear("2027-03-31")).toBe(2026);
    expect(fyBounds(2026)).toEqual(["2026-04-01", "2027-03-31"]);
    expect(fyLabel(2026)).toBe("2026-27");
    expect(fyLabel(2099)).toBe("2099-00");
  });
});
