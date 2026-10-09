import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, OWNER, page, session } from "@/test/mockApi";

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App client={createQueryClient()} />);
}

afterEach(() => vi.unstubAllGlobals());

const ACCOUNTANT = { ...OWNER, id: 3, username: "accounts", role: "accountant" as const };

const PURCHASE = {
  id: 1,
  number: "S1P/26-27/00001",
  supplier_id: 40,
  supplier_name: "Steel Mills",
  location_id: 1,
  location_code: "S1",
  bill_no: "B-1",
  bill_date: "2026-10-08",
  due_date: null,
  mode: "stock",
  status: "posted",
  note: null,
  lines: [
    {
      id: 1,
      line_no: 1,
      item_id: 10,
      item_name: "TMT bar 12 mm Fe500D",
      unit: "ton",
      quantity: "10.000",
      received_quantity: "9.900",
      billed_qty: "10000.000",
      received_qty: "9900.000",
      base_unit: "kg",
      weight_variance_pct: "1.00",
      weight_flagged: true,
      weight_note: "Slip says 9,900 kg",
    },
  ],
};

const FILE_ROW = {
  id: 5,
  ref_type: "purchase",
  ref_id: 1,
  kind: "weighbridge",
  file_name: "slip.pdf",
  content_type: "application/pdf",
  size_bytes: 40,
  note: null,
  created_at: "2026-10-09T10:00:00Z",
  created_by: 2,
};

async function openPurchase(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "S1P/26-27/00001" }));
  return await screen.findByRole("complementary", { name: "S1P/26-27/00001" });
}

describe("Papers on a purchase", () => {
  it("shows the weight difference and lets staff add a slip", async () => {
    const user = userEvent.setup();
    let files = [FILE_ROW];
    const { fetchMock } = mockApi({
      ...session(COUNTER),
      "GET /purchases": () => ({ body: page([PURCHASE]) }),
      "GET /attachments": () => ({ body: files }),
      "POST /attachments": () => {
        files = [...files, { ...FILE_ROW, id: 6, file_name: "photo.png" }];
        return { status: 201, body: files[1] };
      },
    });
    renderAt("/purchases");
    const panel = await openPurchase(user);
    expect(within(panel).getByText("Weight differs by 1.00%")).toBeVisible();
    expect(within(panel).getByText("Slip says 9,900 kg")).toBeVisible();
    const papers = within(await within(panel).findByRole("group", { name: "Papers" }));
    expect(await papers.findByText(/Weighbridge slip · slip.pdf/)).toBeVisible();

    await user.selectOptions(papers.getByLabelText("Kind of paper"), "delivery");
    const file = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "photo.png", {
      type: "image/png",
    });
    await user.upload(papers.getByLabelText("Add photo or PDF"), file);
    expect(await papers.findByText(/· photo.png/)).toBeVisible();
    const post = fetchMock.mock.calls.find(
      ([url, init]) => String(url).endsWith("/attachments") && init?.method === "POST",
    );
    const form = post?.[1]?.body as FormData;
    expect(form.get("ref_type")).toBe("purchase");
    expect(form.get("ref_id")).toBe("1");
    expect(form.get("kind")).toBe("delivery");
    expect((form.get("file") as File).name).toBe("photo.png");
  });

  it("shows the server's reason when a file is refused", async () => {
    const user = userEvent.setup({ applyAccept: false });
    mockApi({
      ...session(COUNTER),
      "GET /purchases": () => ({ body: page([PURCHASE]) }),
      "GET /attachments": () => ({ body: [] }),
      "POST /attachments": () => ({
        status: 400,
        body: {
          code: "FILE_TYPE_NOT_ALLOWED",
          message: "Only photos (JPEG, PNG, WebP) and PDF files are accepted",
          field: null,
        },
      }),
    });
    renderAt("/purchases");
    const panel = await openPurchase(user);
    const papers = within(await within(panel).findByRole("group", { name: "Papers" }));
    await user.upload(
      papers.getByLabelText("Add photo or PDF"),
      new File(["hello"], "notes.txt", { type: "text/plain" }),
      // the input's accept list is a hint only; the server decides
    );
    expect(await papers.findByRole("alert")).toHaveTextContent(/Only photos/);
  });

  it("lets the accountant look but not add", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(ACCOUNTANT),
      "GET /purchases": () => ({ body: page([PURCHASE]) }),
      "GET /attachments": () => ({ body: [FILE_ROW] }),
      "GET /schemes": () => ({ body: [] }),
    });
    renderAt("/purchases");
    const panel = await openPurchase(user);
    const papers = within(await within(panel).findByRole("group", { name: "Papers" }));
    expect(await papers.findByText(/· slip.pdf/)).toBeVisible();
    expect(papers.queryByLabelText("Add photo or PDF")).toBeNull();
  });
});

const SCHEME = {
  id: 9,
  party_id: 40,
  party_name: "Steel Mills",
  name: "H2 rebate",
  item_id: 10,
  item_name: "TMT bar 12 mm Fe500D",
  category: null,
  unit: "kg",
  target_qty: "20000.000",
  period_start: "2026-10-01",
  period_end: "2027-03-31",
  rebate_rule: "percent",
  rebate_value: "2.0000",
  is_active: true,
  achieved: "21000.000",
  pct: "105.00",
  remaining: "0.000",
  reached: true,
  alert: false,
  projected_rebate: "23100.00",
  rebate_amount: null,
  rebate_booked_at: null,
};

describe("Supplier schemes", () => {
  it("shows progress and lets the owner book an earned rebate", async () => {
    const user = userEvent.setup();
    let booked = false;
    const { calls } = mockApi({
      ...session(OWNER),
      "GET /schemes": () => ({
        body: [
          booked
            ? { ...SCHEME, rebate_amount: "23100.00", rebate_booked_at: "2026-10-09T10:00:00Z" }
            : SCHEME,
        ],
      }),
      "GET /parties": () => ({ body: page([]) }),
      "GET /items": () => ({ body: page([]) }),
      "POST /schemes/9/book-rebate": () => {
        booked = true;
        return {
          body: { ...SCHEME, rebate_amount: "23100.00", rebate_booked_at: "2026-10-09T10:00:00Z" },
        };
      },
    });
    renderAt("/purchases/schemes");
    expect(await screen.findByText("21000 / 20000 kg")).toBeVisible();
    expect(screen.getByText("105.00%")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Book rebate for H2 rebate" }));
    expect(
      await screen.findByText(/Rebate of ₹23,100.00 booked as a credit from Steel Mills/),
    ).toBeVisible();
    expect(calls.some((c) => c.method === "POST" && c.path === "/schemes/9/book-rebate")).toBe(
      true,
    );
    expect(await screen.findByText("Booked ₹23,100.00")).toBeVisible();
  });

  it("checks the form before sending and shows how far a scheme has to go", async () => {
    const user = userEvent.setup();
    mockApi({
      ...session(OWNER),
      "GET /schemes": () => ({
        body: [
          {
            ...SCHEME,
            reached: false,
            achieved: "17000.000",
            pct: "85.00",
            remaining: "3000.000",
            alert: true,
            projected_rebate: "0.00",
          },
        ],
      }),
      "GET /parties": () => ({ body: page([]) }),
      "GET /items": () => ({ body: page([]) }),
    });
    renderAt("/purchases/schemes");
    expect(await screen.findByText("3000 kg to go")).toBeVisible();
    expect(screen.getByText(/nearly there/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save scheme" }));
    expect(screen.getByText("Pick the supplier and name the scheme.")).toBeVisible();
  });
});
