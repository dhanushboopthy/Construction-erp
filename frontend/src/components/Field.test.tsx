import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CheckField, SelectField, TextAreaField, TextField } from "./Field";

describe("Field", () => {
  it("puts the label above the input and names it", () => {
    render(<TextField label="Customer name" />);
    expect(screen.getByLabelText("Customer name")).toBeVisible();
  });

  it("describes the input with its hint and its error, and marks it invalid", () => {
    render(<TextField label="GSTIN" hint="15 characters" error="Not a valid GSTIN" />);
    const input = screen.getByLabelText("GSTIN");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("15 characters Not a valid GSTIN");
  });

  it("is not invalid without an error", () => {
    render(<TextField label="GSTIN" />);
    expect(screen.getByLabelText("GSTIN")).not.toHaveAttribute("aria-invalid");
  });

  it("shows the rule a setting controls", () => {
    render(<TextField label="Credit days" rule="B8" />);
    expect(screen.getByText("Rule B8")).toBeVisible();
  });

  it("takes typing and selecting", async () => {
    const user = userEvent.setup();
    render(
      <>
        <TextField label="Remark" />
        <SelectField label="Shop" defaultValue="">
          <option value="">Choose</option>
          <option value="s1">Shop 1</option>
        </SelectField>
        <TextAreaField label="Note" />
      </>,
    );
    await user.type(screen.getByLabelText("Remark"), "cash");
    await user.selectOptions(screen.getByLabelText("Shop"), "s1");
    await user.type(screen.getByLabelText("Note"), "hello");
    expect(screen.getByLabelText("Remark")).toHaveValue("cash");
    expect(screen.getByLabelText("Shop")).toHaveValue("s1");
    expect(screen.getByLabelText("Note")).toHaveValue("hello");
  });

  it("checkbox: the label toggles it and the hint describes it", async () => {
    const user = userEvent.setup();
    render(<CheckField label="Allow credit" hint="Needs a limit" />);
    await user.click(screen.getByText("Allow credit"));
    const box = screen.getByRole("checkbox", { name: /Allow credit/ });
    expect(box).toBeChecked();
    expect(box).toHaveAccessibleDescription("Needs a limit");
  });
});
