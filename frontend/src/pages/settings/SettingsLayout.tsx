import { NavLink, Outlet } from "react-router";

import { PageHeader } from "@/components/PageHeader";
import { purposeOf } from "@/modules";

import styles from "./SettingsLayout.module.css";

const TABS = [
  { to: "/settings", label: "Shop details", end: true },
  { to: "/settings/users", label: "Users", end: false },
  { to: "/settings/locations", label: "Shops and godown", end: false },
  { to: "/settings/charges", label: "Charge types", end: false },
  { to: "/settings/pin", label: "Approval PIN", end: false },
  { to: "/settings/opening", label: "Opening balances", end: false },
  { to: "/settings/lock", label: "Books lock", end: false },
  { to: "/settings/audit", label: "Audit log", end: false },
  { to: "/settings/system", label: "System", end: false },
];

/** Settings: the sections in a column on the left from 1100 px, a scrolling strip above that. */
export function SettingsLayout() {
  return (
    <section aria-labelledby="settings-title" className={styles.page}>
      <PageHeader title="Settings" titleId="settings-title" subtitle={purposeOf("/settings")} />
      <div className={styles.layout}>
        <nav aria-label="Settings sections" className={styles.nav}>
          <ul className={styles.list}>
            {TABS.map((tab) => (
              <li key={tab.to}>
                <NavLink
                  to={tab.to}
                  end={tab.end}
                  className={({ isActive }) => (isActive ? styles.active : styles.link)}
                >
                  {tab.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className={styles.content}>
          <Outlet />
        </div>
      </div>
    </section>
  );
}
