import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const ACCOUNTANT = { ...OWNER, id: 3, username: "accounts", role: "accountant" as const };
const RATE = { rate: "18.00", taxable: "1000.00", igst: "0.00", cgst: "90.00", sgst: "90.00" };

const GSTR1 = {
  period: "2026-10",
  gstin: null,
  b2b: [
    {
      ctin: "33AAPFU0939F1Z2",
      party_name: "Ravi Builders",
      number: "S1/26-27/00001",
      invoice_date: "2026-10-09",
      value: "1180.00",
      pos: "33",
      taxable: "1000.00",
      igst: "0.00",
      cgst: "90.00",
      sgst: "90.00",
      rates: [RATE],
    },
  ],
  b2cl: [],
  b2cs: [
    {
      supply: "INTRA",
      pos: "33",
      rate: "28.00",
      taxable: "1521.80",
      igst: "0.00",
      cgst: "213.05",
      sgst: "213.05",
    },
  ],
  cdnr: [],
  cdnur: [],
  hsn: [
    {
      hsn: "72142090",
      description: "TMT bar",
      uqc: "KGS",
      quantity: "3500.000",
      rate: "18.00",
      value: "1.00",
      taxable: "196000.00",
      igst: "0.00",
      cgst: "7560.00",
      sgst: "7560.00",
    },
  ],
  docs: [
    {
      nature: "Invoices for outward supply",
      series: "S1/26-27",
      first: "S1/26-27/00001",
      last: "S1/26-27/00004",
      count: 3,
      gaps: [3],
    },
  ],
  totals: {
    invoices: 3,
    notes: 0,
    taxable: "200184.95",
    igst: "0.00",
    cgst: "8145.89",
    sgst: "8145.89",
  },
};

const HEADS = { taxable: "0.00", igst: "0.00", cgst: "0.00", sgst: "0.00" };

const GSTR3B = {
  period: "2026-10",
  gstin: null,
  outward_taxable: { ...HEADS, taxable: "200184.95", cgst: "8145.89", sgst: "8145.89" },
  outward_nil: "0.00",
  itc_books: { ...HEADS, cgst: "49500.00", sgst: "49500.00" },
  itc_reversed: { ...HEADS, cgst: "9900.00", sgst: "9900.00" },
  itc_in_2b: null,
  net_payable: { ...HEADS, cgst: "-31454.11", sgst: "-31454.11" },
};

const NO_2B = { period: "2026-10", file_name: null, imported_rows: 0, counts: {}, rows: [] };

function routes(extra = {}) {
  return {
    "GET /gst/gstr1": () => ({ body: GSTR1 }),
    "GET /gst/gstr3b": () => ({ body: GSTR3B }),
    "GET /gst/gstr2b": () => ({ body: NO_2B }),
    ...extra,
  };
}

describe("GST returns", () => {
  it("shows the GSTR-1 tables, flags missing document numbers and an unset GSTIN", async () => {
    mockApi({ ...session(ACCOUNTANT), ...routes() });
    renderAt("/reports/gst");
    expect(await screen.findByText(/GSTIN is not set/)).toBeVisible();
    const b2b = await screen.findByRole("table", { name: "B2B bills" });
    expect(within(b2b).getByText("33AAPFU0939F1Z2")).toBeVisible();
    expect(screen.getByRole("table", { name: /Other B2C sales/ })).toBeVisible();
    const docs = within(screen.getByRole("table", { name: "Documents issued" }));
    expect(docs.getByText("S1/26-27/00004")).toBeVisible();
    expect(docs.getAllByText("3")).toHaveLength(2); // three issued, and number 3 is missing
    const nb = screen.getByRole("table", { name: "GSTR-3B figures" });
    expect(within(nb).getByText("Tax to pay (sales tax less net input tax)")).toBeVisible();
    expect(screen.getByText(/No GSTR-2B file for this month yet/)).toBeVisible();
  });

  it("downloads the exports with the chosen month", async () => {
    const user = userEvent.setup();
    URL.createObjectURL = () => "blob:x";
    URL.revokeObjectURL = () => undefined;
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const { calls } = mockApi({
      ...session(OWNER),
      ...routes({ "GET /gst/gstr1/export": () => ({ body: {} }) }),
    });
    renderAt("/reports/gst");
    await user.click(await screen.findByRole("button", { name: "Download GSTR-1 Excel" }));
    await vi.waitFor(() => expect(calls.some((c) => c.path === "/gst/gstr1/export")).toBe(true));
    await vi.waitFor(() => expect(click).toHaveBeenCalled());
    click.mockRestore();
  });

  it("uploads a GSTR-2B file and shows the match", async () => {
    const user = userEvent.setup({ applyAccept: false });
    let loaded = false;
    const { fetchMock } = mockApi({
      ...session(ACCOUNTANT),
      ...routes({
        "GET /gst/gstr2b": () => ({
          body: loaded
            ? {
                period: "2026-10",
                file_name: "2b.csv",
                imported_rows: 2,
                counts: { matched: 1, mismatch: 0, missing_in_2b: 0, missing_in_books: 1 },
                rows: [
                  {
                    status: "missing_in_books",
                    gstin: "29ABCDE1234F1Z5",
                    supplier: "Other mill",
                    number: "Z-77",
                    books_date: null,
                    books_taxable: null,
                    books_tax: null,
                    portal_taxable: "1000.00",
                    portal_tax: "180.00",
                    difference_taxable: "1000.00",
                    difference_tax: "180.00",
                  },
                  {
                    status: "matched",
                    gstin: "33BBBBB1234B1Z1",
                    supplier: "Mills",
                    number: "B-1",
                    books_date: "2026-10-09",
                    books_taxable: "550000.00",
                    books_tax: "99000.00",
                    portal_taxable: "550000.00",
                    portal_tax: "99000.00",
                    difference_taxable: "0.00",
                    difference_tax: "0.00",
                  },
                ],
              }
            : NO_2B,
        }),
        "POST /gst/gstr2b": () => {
          loaded = true;
          return {
            status: 201,
            body: { id: 1, period: "2026-10", file_name: "2b.csv", row_count: 2 },
          };
        },
      }),
    });
    renderAt("/reports/gst");
    await user.upload(
      await screen.findByLabelText(/Upload GSTR-2B for/),
      new File(["a,b"], "2b.csv", { type: "text/csv" }),
    );
    expect(await screen.findByText("GSTR-2B file 2b.csv is loaded.")).toBeVisible();
    expect(await screen.findByText("In 2B, not in our books")).toBeVisible();
    expect(screen.getByText(/1 matched · 0 differ/)).toBeVisible();
    const post = fetchMock.mock.calls.find(
      ([url, init]) => String(url).endsWith("/gst/gstr2b") && init?.method === "POST",
    );
    expect((post?.[1]?.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("is closed to counter staff", async () => {
    mockApi({ ...session(COUNTER) });
    renderAt("/reports/gst");
    expect(await screen.findByText("Not available for your role")).toBeVisible();
  });
});
