import type { ButtonHTMLAttributes } from "react";

import { useReadOnly, useReadOnlyReason } from "@/auth/ReadOnlyContext";

import styles from "./Button.module.css";

/** Primary: orange, one per screen. Secondary: outlined. Ghost: text only, for the quiet third action. */
type Variant = "primary" | "secondary" | "ghost";

/**
 * When the company's plan has ended (read-only), a submit button or a primary button, which is
 * where a screen saves, is off with the reason as its tooltip. A primary button that only reads
 * (print, export) passes `allowWhenReadOnly`.
 */
export function Button({
  variant = "secondary",
  className,
  type = "button",
  allowWhenReadOnly = false,
  disabled,
  title,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  allowWhenReadOnly?: boolean;
}) {
  const readOnly = useReadOnly();
  const reason = useReadOnlyReason();
  const blocked = readOnly && !allowWhenReadOnly && (type === "submit" || variant === "primary");
  return (
    <button
      type={type}
      className={[styles.button, styles[variant], className].filter(Boolean).join(" ")}
      disabled={disabled || blocked}
      title={blocked ? reason : title}
      {...rest}
    />
  );
}
