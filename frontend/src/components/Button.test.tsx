import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Button } from "./Button";

describe("Button", () => {
  it("is a type=button by default so it never submits a form by accident", () => {
    render(<Button>Add line</Button>);
    expect(screen.getByRole("button", { name: "Add line" })).toHaveAttribute("type", "button");
  });

  it("submits a form when asked to", () => {
    render(
      <Button variant="primary" type="submit">
        Save bill
      </Button>,
    );
    expect(screen.getByRole("button", { name: "Save bill" })).toHaveAttribute("type", "submit");
  });

  it.each(["primary", "secondary", "ghost"] as const)("renders the %s variant", (variant) => {
    render(<Button variant={variant}>Go</Button>);
    expect(screen.getByRole("button", { name: "Go" }).className).toMatch(new RegExp(variant));
  });

  it("works from the keyboard and not when disabled", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Go</Button>);
    await user.tab();
    await user.keyboard("{Enter}");
    expect(onClick).toHaveBeenCalledTimes(1);
    rerender(
      <Button onClick={onClick} disabled>
        Go
      </Button>,
    );
    await user.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
