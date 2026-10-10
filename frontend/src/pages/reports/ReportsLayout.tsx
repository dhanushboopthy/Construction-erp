import { NavLink, Outlet } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import styles from "@/components/Ledger.module.css";

const TABS = [
  { to: "/reports", label: "Daily closing", end: true, roles: ["owner", "counter", "accountant"] },
  { to: "/reports/profit", label: "Profit", end: false, roles: ["owner"] },
  { to: "/reports/pnl", label: "Profit & loss", end: false, roles: ["owner"] },
  { to: "/reports/dues", label: "Dues", end: false, roles: ["owner", "accountant"] },
  {
    to: "/reports/itc-reversal",
    label: "ITC to reverse",
    end: false,
    roles: ["owner", "accountant"],
  },
  {
    to: "/reports/segments",
    label: "Sales by segment",
    end: false,
    roles: ["owner", "accountant"],
  },
];

export function ReportsLayout() {
  const { user } = useAuth();
  return (
    <section aria-labelledby="reports-title" className={styles.page}>
      <h1 id="reports-title" className={styles.title}>
        Reports
      </h1>
      <nav aria-label="Report sections">
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
