import { render, screen } from "@testing-library/react";

import { ProgressBar } from "./ProgressBar";

describe("ProgressBar", () => {
  it("is a named progressbar with its numbers and the percentage written out", () => {
    render(<ProgressBar value={30} max={120} label="Credit used" />);
    const bar = screen.getByRole("progressbar", { name: "Credit used" });
    expect(bar).toHaveAttribute("aria-valuenow", "30");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "120");
    expect(bar).toHaveAttribute("aria-valuetext", "25%");
    expect(screen.getByText("25%")).toBeVisible();
  });

  it("defaults to 0 to 100 and clamps what lies outside", () => {
    const { rerender } = render(<ProgressBar value={140} label="Used" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    rerender(<ProgressBar value={-5} label="Used" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText("0%")).toBeVisible();
  });

  it("does not divide by zero", () => {
    render(<ProgressBar value={0} max={0} label="Empty" />);
    expect(screen.getByText("0%")).toBeVisible();
  });
});
