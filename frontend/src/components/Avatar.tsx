import { avatarTone, initials } from "@/lib/avatar";

import styles from "./Avatar.module.css";

/**
 * The person's initials in a circle. Decorative by default: the name is written next to it. Pass
 * `label` where the avatar stands alone (it then becomes an image with that name).
 */
export function Avatar({
  name,
  size = 40,
  label,
}: {
  name: string;
  size?: 32 | 40;
  label?: string;
}) {
  return (
    <span
      className={styles.avatar}
      data-size={size}
      data-tone={avatarTone(name)}
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
    >
      {initials(name)}
    </span>
  );
}
