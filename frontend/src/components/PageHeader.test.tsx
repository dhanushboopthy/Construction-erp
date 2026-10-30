import { render, screen } from "@testing-library/react";

import { PageHeader } from "./PageHeader";

describe("PageHeader", () => {
  it("shows eyebrow, title, subtitle and actions", () => {
    render(
      <PageHeader
        eyebrow="Shop 1"
        title="Today"
        subtitle="Sales, dues and stock at a glance."
        actions={<button type="button">New bill</button>}
        titleId="t"
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Today" })).toHaveAttribute("id", "t");
    expect(screen.getByText("Shop 1")).toBeVisible();
    expect(screen.getByText("Sales, dues and stock at a glance.")).toBeVisible();
    expect(screen.getByRole("button", { name: "New bill" })).toBeVisible();
  });

  it("leaves out what it is not given", () => {
    const { container } = render(<PageHeader title="Items" />);
    expect(container.querySelectorAll("p")).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "Items" })).toBeVisible();
  });
});
