import { useAuth } from "@/auth/AuthContext";

import styles from "./TodayPage.module.css";

/**
 * The owner's "10-second questions" (interview Q25): items and stock, outstanding bills,
 * payables, today's sales, and today's profit (owner only). Figures arrive with Milestones
 * 4-7 and 12; until then the strip shows dashes, never made-up numbers.
 */
export function TodayPage() {
  const { user } = useAuth();
  const isOwner = user?.role === "owner";

  const figures = [
    { label: "Items in stock", value: "—" },
    { label: "Customers owe", value: "—" },
    { label: "We owe suppliers", value: "—" },
    { label: "Sales today", value: "—" },
    ...(isOwner ? [{ label: "Profit today", value: "—" }] : []),
  ];

  return (
    <section aria-labelledby="today-title">
      <h1 id="today-title" className={styles.title}>
        Today
      </h1>
      <dl className={styles.strip}>
        {figures.map((f) => (
          <div key={f.label} className={styles.figure}>
            <dt>{f.label}</dt>
            <dd className="num">{f.value}</dd>
          </div>
        ))}
      </dl>
      <p className={styles.note}>
        Figures appear once purchases, billing and payments are built. Stock per item will be listed
        here.
      </p>
    </section>
  );
}
