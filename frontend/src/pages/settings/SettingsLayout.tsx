import { NavLink, Outlet } from "react-router";

import styles from "@/components/Ledger.module.css";

const TABS = [
  { to: "/settings", label: "Shop details", end: true },
  { to: "/settings/users", label: "Users", end: false },
  { to: "/settings/locations", label: "Shops and godown", end: false },
];

export function SettingsLayout() {
  return (
    <section aria-labelledby="settings-title" className={styles.page}>
      <h1 id="settings-title" className={styles.title}>
        Settings
      </h1>
      <nav aria-label="Settings sections">
        <ul className={styles.tabs}>
          {TABS.map((tab) => (
            <li key={tab.to}>
              <NavLink
                to={tab.to}
                end={tab.end}
                className={({ isActive }) => (isActive ? styles.tabActive : styles.tab)}
              >
                {tab.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <Outlet />
    </section>
  );
}
