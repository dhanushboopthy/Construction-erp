import type { ReactNode } from "react";

import styles from "./PageHeader.module.css";

/** The top of a screen: a small eyebrow (shop or section), the title, what the screen is for,
 * and the screen's actions on the right. */
export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
  titleId,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  /** Id for the `<h1>`, so the section can point `aria-labelledby` at it. */
  titleId?: string;
}) {
  return (
    <header className={styles.header}>
      <div className={styles.text}>
        {eyebrow ? <p className={styles.eyebrow}>{eyebrow}</p> : null}
        <h1 id={titleId} className={styles.title}>
          {title}
        </h1>
        {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
      </div>
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </header>
  );
}
