import { NavLink, Outlet } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import styles from "@/components/Ledger.module.css";

const TABS = [
  { to: "/stock", label: "Stock levels", end: true, roles: ["owner", "counter", "accountant"] },
  {
    to: "/stock/transfers",
    label: "Transfers",
    end: false,
    roles: ["owner", "counter", "accountant"],
  },
  { to: "/stock/counts", label: "Counts", end: false, roles: ["owner", "counter", "accountant"] },
  {
    to: "/stock/adjustments",
    label: "Adjustments",
    end: false,
    roles: ["owner", "counter", "accountant"],
  },
  { to: "/stock/analysis", label: "Analysis", end: false, roles: ["owner"] },
  { to: "/stock/value", label: "Stock value", end: false, roles: ["owner", "accountant"] },
  { to: "/stock/shortages", label: "Weight shortages", end: false, roles: ["owner", "accountant"] },
];

export function StockLayout() {
  const { user } = useAuth();
  return (
    <section aria-labelledby="stock-title" className={styles.page}>
      <h1 id="stock-title" className={styles.title}>
        Stock
      </h1>
      <nav aria-label="Stock sections">
        <ul className={styles.tabs}>
          {TABS.filter((t) => user && t.roles.includes(user.role)).map((t) => (
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
