import { render, screen } from "@testing-library/react";

import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  it.each(["good", "warn", "critical", "neutral", "accent"] as const)(
    "shows its word for the %s tone, with the icon hidden from screen readers",
    (tone) => {
      const { container } = render(<StatusPill tone={tone} label="Overdue" />);
      expect(screen.getByText("Overdue")).toBeVisible();
      expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
      expect(container.firstElementChild).toHaveAttribute("data-tone", tone);
    },
  );

  it("cannot be rendered without a label (type-checked)", () => {
    // @ts-expect-error `label` is required: a pill is never colour alone.
    void (<StatusPill tone="good" />);
  });
});
