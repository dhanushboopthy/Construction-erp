import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { Segmented } from "./Segmented";

const OPTIONS = [
  { value: "day", label: "Day" },
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
];

function Harness() {
  const [value, setValue] = useState("day");
  return <Segmented label="Period" options={OPTIONS} value={value} onChange={setValue} />;
}

describe("Segmented", () => {
  it("is a named radio group with one option checked and one tab stop", () => {
    render(<Harness />);
    expect(screen.getByRole("radiogroup", { name: "Period" })).toBeVisible();
    expect(screen.getByRole("radio", { name: "Day" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Week" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Week" })).toHaveAttribute("tabindex", "-1");
  });

  it("changes with a click", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("radio", { name: "Month" }));
    expect(screen.getByRole("radio", { name: "Month" })).toBeChecked();
  });

  it("moves with the arrow keys, wrapping round, and Home/End", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.tab();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Week" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Week" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("radio", { name: "Month" })).toBeChecked();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Day" })).toBeChecked();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "Month" })).toBeChecked();
  });
});
