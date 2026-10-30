import { dueStatus, prepareDues, type ReceivableRow } from "./dues";

const row = (over: Partial<ReceivableRow>): ReceivableRow =>
  ({
    party_id: 1,
    party_name: "Ravi Traders",
    balance: "1000.00",
    advance: "0.00",
    overdue: "0.00",
    oldest_due_date: null,
    days_late: null,
    credit_limit: "10000.00",
    utilisation_pct: "10.00",
    dso_days: null,
    last_payment_date: null,
    ...over,
  }) as ReceivableRow;

describe("dueStatus", () => {
  it.each([
    ["79.99", "ok"],
    ["80", "near_limit"],
    ["80.00", "near_limit"],
    ["99.99", "near_limit"],
    ["100", "near_limit"],
    ["100.00", "near_limit"],
    ["100.01", "over_limit"],
    ["250.00", "over_limit"],
    ["0", "ok"],
  ])("credit used %s%% is %s", (pct, status) => {
    expect(dueStatus(row({ utilisation_pct: pct }))).toBe(status);
  });

  it("is overdue from the first day late, and not on day 0 or with no late bill", () => {
    expect(dueStatus(row({ days_late: 1 }))).toBe("overdue");
    expect(dueStatus(row({ days_late: 30 }))).toBe("overdue");
    expect(dueStatus(row({ days_late: 0 }))).toBe("ok");
    expect(dueStatus(row({ days_late: null }))).toBe("ok");
  });

  it("is Cash when the customer has no credit limit", () => {
    expect(dueStatus(row({ credit_limit: null, utilisation_pct: null }))).toBe("cash");
  });

  it("still says Overdue for a no-limit customer with a late bill", () => {
    expect(dueStatus(row({ credit_limit: null, utilisation_pct: null, days_late: 5 }))).toBe(
      "overdue",
    );
  });

  it("puts Over limit before Overdue before Near limit", () => {
    expect(dueStatus(row({ utilisation_pct: "120.00", days_late: 9 }))).toBe("over_limit");
    expect(dueStatus(row({ utilisation_pct: "85.00", days_late: 9 }))).toBe("overdue");
    expect(dueStatus(row({ utilisation_pct: "85.00", days_late: 0 }))).toBe("near_limit");
  });
});

describe("prepareDues", () => {
  const rows = [
    row({ party_id: 1, party_name: "Ravi Traders", balance: "5000.00", overdue: "0.00" }),
    row({
      party_id: 2,
      party_name: "Sri Lakshmi Builders",
      balance: "3000.00",
      overdue: "3000.00",
      days_late: 12,
    }),
    row({ party_id: 3, party_name: "Anand Constructions", balance: "9000.00", overdue: "0.00" }),
    row({ party_id: 4, party_name: "Settled Co", balance: "0.00" }),
    row({ party_id: 5, party_name: "Advance Co", balance: "-500.00" }),
  ];
  const ids = (list: ReceivableRow[]) => list.map((r) => r.party_id);

  it("keeps only customers who owe, most overdue first and then most owed", () => {
    expect(ids(prepareDues(rows, { q: "", status: "" }))).toEqual([2, 3, 1]);
  });

  it("searches by name, ignoring case", () => {
    expect(ids(prepareDues(rows, { q: "ANAND", status: "" }))).toEqual([3]);
  });

  it("filters by status", () => {
    expect(ids(prepareDues(rows, { q: "", status: "overdue" }))).toEqual([2]);
    expect(ids(prepareDues(rows, { q: "", status: "ok" }))).toEqual([3, 1]);
  });
});
