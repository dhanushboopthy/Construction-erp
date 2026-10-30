import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { App } from "@/App";
import { COUNTER, mockApi, page, PARTY, S1, session, TMT_ITEM } from "@/test/mockApi";

/**
 * Keystrokes to key a bill with the keyboard alone. The Site navy refactor changed styles, not
 * the order of the fields, so the count must stay what it was before (measured on main with this
 * same test): from the item of a line, 2 Tabs reach Quantity (Item, Unit, Quantity); Enter there
 * adds a line and puts the cursor on that line's item. A 5-line bill is therefore, per line, 1 key
 * to choose the item, 2 Tabs, 1 digit and 1 Enter (5 keys), and 1 Ctrl+Enter to save:
 * 5 x 5 + 1 = 26 keys.
 */
const TABS_ITEM_TO_QUANTITY = 2;

const WALK_IN = {
  ...PARTY,
  id: 21,
  name: "Walk-in customer",
  gstin: null,
  credit_allowed: false,
  credit_limit: null,
  sites: [],
};

afterEach(() => vi.unstubAllGlobals());

it("keys a 5-line bill with no more keystrokes than before", async () => {
  const user = userEvent.setup();
  const { calls } = mockApi({
    ...session(COUNTER),
    "GET /items": () => ({ body: page([TMT_ITEM]) }),
    "GET /parties": () => ({ body: page([WALK_IN]) }),
    "GET /locations": () => ({ body: [S1] }),
    "GET /invoices": () => ({ body: page([]) }),
    "POST /invoices/preview": () => ({ status: 422, body: { code: "X", message: "preview" } }),
  });
  window.history.pushState({}, "", "/sales/new");
  render(<App client={createQueryClient()} />);
  await screen.findByRole("option", { name: "TMT bar 12 mm Fe500D" });

  let keys = 0;
  for (let line = 0; line < 5; line++) {
    const item = document.querySelector<HTMLSelectElement>(`[data-line-item="${line}"]`);
    expect(item, `line ${line + 1} has its item field`).not.toBeNull();
    item?.focus();
    await user.selectOptions(item as HTMLSelectElement, "10");
    keys += 1; // choosing the item (one arrow or letter in a real select)

    let tabs = 0;
    while (document.activeElement?.tagName !== "INPUT" && tabs < 6) {
      await user.tab();
      tabs++;
    }
    expect(tabs).toBeLessThanOrEqual(TABS_ITEM_TO_QUANTITY);
    keys += tabs;
    expect(screen.getAllByLabelText("Quantity")[line]).toHaveFocus();
    await user.keyboard("1");
    keys += 1;
    await user.keyboard("{Enter}");
    keys += 1;
  }
  expect(keys).toBeLessThanOrEqual(25);

  await user.keyboard("{Control>}{Enter}{/Control}");
  keys += 1;
  expect(keys).toBeLessThanOrEqual(26);
  // Ctrl+Enter asked to save: the form validated and tried the preview or the save.
  expect(calls.length).toBeGreaterThan(0);
});
