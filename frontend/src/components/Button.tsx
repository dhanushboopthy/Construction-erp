import type { ButtonHTMLAttributes } from "react";

import styles from "./Button.module.css";

/** Primary: orange, one per screen. Secondary: outlined. Ghost: text only, for the quiet third action. */
type Variant = "primary" | "secondary" | "ghost";

export function Button({
  variant = "secondary",
  className,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type={type}
      className={[styles.button, styles[variant], className].filter(Boolean).join(" ")}
      {...rest}
    />
  );
}
