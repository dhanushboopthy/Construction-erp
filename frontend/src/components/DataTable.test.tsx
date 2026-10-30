import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DataTable, PrimaryCell, type Column } from "./DataTable";

interface Row {
  id: number;
  name: string;
  phone: string;
  owes: string;
}

const ROWS: Row[] = [
  { id: 1, name: "Ravi Traders", phone: "98400 11111", owes: "1,20,000.00" },
  { id: 2, name: "Sri Lakshmi Builders", phone: "98400 22222", owes: "35,500.00" },
  { id: 3, name: "Anand Constructions", phone: "98400 33333", owes: "0.00" },
];

const COLUMNS: Column<Row>[] = [
  {
    id: "name",
    header: "Customer",
    cell: (r) => <PrimaryCell name={r.name} sub={r.phone} avatar />,
  },
  { id: "owes", header: "Owes (₹)", numeric: true, cell: (r) => r.owes },
];

const base = {
  caption: "Customer dues",
  columns: COLUMNS,
  rows: ROWS,
  rowKey: (r: Row) => r.id,
  empty: "No customer owes money today.",
};

describe("DataTable", () => {
  it("names the table, shows a two-line first cell and right-aligned figures", () => {
    render(<DataTable {...base} />);
    expect(screen.getByRole("table", { name: "Customer dues" })).toBeVisible();
    expect(screen.getByText("Ravi Traders")).toBeVisible();
    expect(screen.getByText("98400 11111")).toBeVisible();
    expect(screen.getByRole("cell", { name: "1,20,000.00" }).className).toMatch(/numeric/);
    expect(screen.getByRole("columnheader", { name: "Owes (₹)" })).toBeVisible();
  });

  it("opens a row by clicking anywhere on it", async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(<DataTable {...base} onOpen={onOpen} />);
    await user.click(screen.getByText("Sri Lakshmi Builders"));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenLastCalledWith(ROWS[1]);
    await user.click(screen.getByRole("cell", { name: "35,500.00" }));
    expect(onOpen).toHaveBeenLastCalledWith(ROWS[1]);
  });

  it("opens the focused row with Enter, once", async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(<DataTable {...base} onOpen={onOpen} />);
    await user.tab();
    await user.keyboard("{Enter}");
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onOpen).toHaveBeenLastCalledWith(ROWS[0]);
  });

  it("moves between rows with Up and Down, stopping at the ends", async () => {
    const user = userEvent.setup();
    render(<DataTable {...base} onOpen={() => undefined} />);
    const buttons = screen.getAllByRole("button");
    await user.tab();
    expect(buttons[0]).toHaveFocus();
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(buttons[2]).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(buttons[2]).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(buttons[1]).toHaveFocus();
  });

  it("marks the selected row", () => {
    render(<DataTable {...base} onOpen={() => undefined} selectedKey={2} />);
    expect(screen.getByRole("button", { name: /Sri Lakshmi Builders/ })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: /Ravi Traders/ })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("has no row buttons or chevron column when rows do not open", () => {
    render(<DataTable {...base} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("says it is loading", () => {
    render(<DataTable {...base} loading />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows an error with a retry", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<DataTable {...base} error="Dues could not be loaded." onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Dues could not be loaded.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("says how to start when there are no rows", () => {
    render(<DataTable {...base} rows={[]} />);
    expect(screen.getByText("No customer owes money today.")).toBeVisible();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows a footer", () => {
    render(<DataTable {...base} footer="3 customers" />);
    expect(screen.getByText("3 customers")).toBeVisible();
  });

  it("lets the keyboard scroll a table that has no openable rows, and leaves the others alone", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<DataTable {...base} />);
    const region = screen.getByRole("region", { name: "Customer dues" });
    await user.tab();
    expect(region).toHaveFocus();
    unmount();

    render(<DataTable {...base} onOpen={() => undefined} />);
    expect(screen.queryByRole("region")).toBeNull();
  });
});
