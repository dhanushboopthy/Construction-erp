import { NavLink, Outlet } from "react-router";

import styles from "@/components/Ledger.module.css";

const TABS = [
  { to: "/transport", label: "Trips", end: true },
  { to: "/transport/vehicles", label: "Vehicles", end: false },
  { to: "/transport/direct", label: "Direct sales", end: false },
];

export function TransportLayout() {
  return (
    <section aria-labelledby="transport-title" className={styles.page}>
      <h1 id="transport-title" className={styles.title}>
        Transport
      </h1>
      <nav aria-label="Transport sections">
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
