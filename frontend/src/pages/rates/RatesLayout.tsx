import { NavLink, Outlet } from "react-router";

import styles from "@/components/Ledger.module.css";
import { PageHeader } from "@/components/PageHeader";
import { purposeOf } from "@/modules";

const TABS = [
  { to: "/rates", label: "Today's rates", end: true },
  { to: "/rates/customers", label: "Customer rates", end: false },
];

export function RatesLayout() {
  return (
    <section aria-labelledby="rates-title" className={styles.page}>
      <PageHeader title="Daily rates" titleId="rates-title" subtitle={purposeOf("/rates")} />
      <nav aria-label="Rate sections">
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
