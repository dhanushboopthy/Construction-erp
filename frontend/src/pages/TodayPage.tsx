import { useToday } from "@/api/reports";
import { useAuth } from "@/auth/AuthContext";
import { formatMoney } from "@/lib/format";
import { StockPage } from "@/pages/stock/StockPage";

import styles from "./TodayPage.module.css";

/**
 * The owner's "10-second questions" (interview Q25): items and stock, what customers owe, what
 * we owe, today's sales, and today's profit (owner only). Counter staff see their own shop's sales.
 */
export function TodayPage() {
  const { user } = useAuth();
  const today = useToday();
  const t = today.data;
  const rupee = (value: string | null | undefined) => (value == null ? "—" : formatMoney(value));

  const figures = [
    { label: "Items in stock", value: t ? String(t.items_in_stock) : "—" },
    { label: "Customers owe", value: rupee(t?.customers_owe) },
    ...(user?.role !== "counter" ? [{ label: "We owe suppliers", value: rupee(t?.we_owe) }] : []),
    { label: "Sales today", value: rupee(t?.sales_today) },
    ...(user?.role === "owner" ? [{ label: "Profit today", value: rupee(t?.profit_today) }] : []),
  ];

  return (
    <section aria-labelledby="today-title">
      <h1 id="today-title" className={styles.title}>
        Today
      </h1>
      {today.isError ? (
        <p role="alert" className={styles.note}>
          Today&apos;s figures could not be loaded.
        </p>
      ) : null}
      <dl className={styles.strip}>
        {figures.map((f) => (
          <div key={f.label} className={styles.figure}>
            <dt>{f.label}</dt>
            <dd className="num">{f.value}</dd>
          </div>
        ))}
      </dl>
      {t && Number(t.returns_today) > 0 ? (
        <p className={styles.note}>Returns taken today: ₹{formatMoney(t.returns_today)}.</p>
      ) : null}
      <h2 className={styles.stockTitle}>Stock</h2>
      <StockPage />
    </section>
  );
}
