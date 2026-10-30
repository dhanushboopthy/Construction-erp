import { useState } from "react";

import { initials } from "@/lib/avatar";

import styles from "./BrandMark.module.css";

/**
 * The shop's mark in the sidebar and on the sign-in page: its logo when it has one, else a tile
 * with the initials of its name. `className` is the tile (size, shape and colour) from the page.
 * If the logo cannot be loaded the initials stand in, so the corner is never empty or broken.
 */
export function BrandMark({
  name,
  logoUrl,
  className,
}: {
  /** Undefined while the name is still loading: the tile is then empty. */
  name: string | undefined;
  logoUrl?: string | null;
  className?: string | undefined;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  const showLogo = logoUrl && failed !== logoUrl;
  return (
    <span
      className={className}
      style={showLogo ? { background: "var(--color-logo-plate)" } : undefined}
      aria-hidden="true"
    >
      {showLogo ? (
        <img src={logoUrl} alt="" className={styles.logo} onError={() => setFailed(logoUrl)} />
      ) : name ? (
        initials(name)
      ) : (
        ""
      )}
    </span>
  );
}
