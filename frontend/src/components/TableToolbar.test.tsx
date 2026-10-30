import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";

import { useTableFilters } from "@/hooks/useTableFilters";

import { TableToolbar } from "./TableToolbar";

const STATUSES = [
  { value: "overdue", label: "Overdue" },
  { value: "ok", label: "OK" },
];

function Screen({ debounceMs = 0 }: { debounceMs?: number }) {
  const filters = useTableFilters();
  const location = useLocation();
  return (
    <>
      <TableToolbar
        filters={filters}
        searchPlaceholder="Customer name"
        statusOptions={STATUSES}
        dateRange
        debounceMs={debounceMs}
      />
      <output aria-label="url">{location.search}</output>
      <output aria-label="rows for">{filters.q || "all"}</output>
    </>
  );
}

const open = (url = "/") =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Screen />
    </MemoryRouter>,
  );

describe("TableToolbar", () => {
  it("names every control", () => {
    open();
    expect(screen.getByRole("search")).toBeVisible();
    expect(screen.getByRole("searchbox", { name: "Search" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Status" })).toBeVisible();
    expect(screen.getByLabelText("From")).toBeVisible();
    expect(screen.getByLabelText("To")).toBeVisible();
  });

  it("keeps the search in the URL after a pause in typing", async () => {
    const user = userEvent.setup();
    open();
    await user.type(screen.getByRole("searchbox"), "ravi");
    expect(await screen.findByText("ravi", { selector: "output" })).toBeVisible();
    expect(screen.getByLabelText("url")).toHaveTextContent("?q=ravi");
  });

  it("does not change the URL on every keystroke", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <Screen debounceMs={400} />
      </MemoryRouter>,
    );
    await user.type(screen.getByRole("searchbox"), "ravi");
    expect(screen.getByLabelText("url")).toHaveTextContent("");
    expect(await screen.findByText("?q=ravi")).toBeVisible();
  });

  it("keeps the status and dates in the URL, and removes a cleared filter", async () => {
    const user = userEvent.setup();
    open();
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "overdue");
    expect(screen.getByLabelText("url")).toHaveTextContent("?status=overdue");
    await user.type(screen.getByLabelText("From"), "2026-10-01");
    expect(screen.getByLabelText("url")).toHaveTextContent("status=overdue");
    expect(screen.getByLabelText("url")).toHaveTextContent("from=2026-10-01");
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "");
    expect(screen.getByLabelText("url")).not.toHaveTextContent("status");
  });

  it("starts from the URL, so Back and a pasted link show the same rows", () => {
    open("/?q=anand&status=ok");
    expect(screen.getByRole("searchbox")).toHaveValue("anand");
    expect(screen.getByRole("combobox", { name: "Status" })).toHaveValue("ok");
  });

  it('"/" jumps to the search box', async () => {
    const user = userEvent.setup();
    open();
    await user.keyboard("/");
    expect(screen.getByRole("searchbox")).toHaveFocus();
  });
});
