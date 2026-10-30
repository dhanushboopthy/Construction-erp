import { includesText } from "./filters";

describe("includesText", () => {
  it("matches any value, ignoring case and spaces around the search", () => {
    expect(includesText(" ravi ", "INV/1", "Ravi Traders")).toBe(true);
    expect(includesText("inv/1", "INV/1", "Ravi Traders")).toBe(true);
    expect(includesText("anand", "INV/1", "Ravi Traders")).toBe(false);
  });

  it("matches everything when the search is empty", () => {
    expect(includesText("", "x")).toBe(true);
    expect(includesText("   ", null)).toBe(true);
  });

  it("copes with numbers and missing values", () => {
    expect(includesText("12", 4120)).toBe(true);
    expect(includesText("x", null, undefined)).toBe(false);
  });
});
