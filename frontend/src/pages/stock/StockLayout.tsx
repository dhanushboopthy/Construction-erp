import { NavLink, Outlet } from "react-router";

import styles from "@/components/Ledger.module.css";

const TABS = [
  { to: "/stock", label: "Stock levels", end: true },
  { to: "/stock/transfers", label: "Transfers", end: false },
  { to: "/stock/counts", label: "Counts", end: false },
];

export function StockLayout() {
  return (
    <section aria-labelledby="stock-title" className={styles.page}>
      <h1 id="stock-title" className={styles.title}>
        Stock
      </h1>
      <nav aria-label="Stock sections">
        <ul className={styles.tabs}>
          {TABS.map((t) => (
            <li key={t.to}>
              <NavLink
                to={t.to}
                end={t.end}
                className={({ isActive }) => (isActive ? styles.tabActive : styles.tab)}
              >
                {t.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <Outlet />
    </section>
  );
}
