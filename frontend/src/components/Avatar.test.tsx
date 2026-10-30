import { render, screen } from "@testing-library/react";

import { avatarTone, initials } from "@/lib/avatar";

import { Avatar } from "./Avatar";

describe("Avatar", () => {
  it("takes initials from the first and last word of the name", () => {
    expect(initials("Ravi Kumar")).toBe("RK");
    expect(initials("  sri  lakshmi  steels ")).toBe("SS");
    expect(initials("Madurai")).toBe("M");
    expect(initials("   ")).toBe("?");
  });

  it("keeps the same navy or orange tone for the same name", () => {
    expect(avatarTone("Ravi Kumar")).toBe(avatarTone("Ravi Kumar"));
    const tones = new Set(["Ravi Kumar", "Anita", "Bala", "Chandra"].map(avatarTone));
    expect(tones).toEqual(new Set(["navy", "orange"]));
  });

  it("is decorative next to a name, and an image when it stands alone", () => {
    const { rerender } = render(<Avatar name="Ravi Kumar" />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("RK")).toHaveAttribute("aria-hidden", "true");
    rerender(<Avatar name="Ravi Kumar" label="Signed in as Ravi Kumar" size={32} />);
    expect(screen.getByRole("img", { name: "Signed in as Ravi Kumar" })).toHaveAttribute(
      "data-size",
      "32",
    );
  });
});
