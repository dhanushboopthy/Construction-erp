import { Bell } from "lucide-react";
import { useRef } from "react";
import { NavLink, Outlet } from "react-router";

import { useTenant } from "@/api/tenant";
import { useAuth } from "@/auth/AuthContext";
import { useAlerts } from "@/hooks/useAlerts";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { initials } from "@/lib/avatar";
import { modulesFor, type ModuleLink } from "@/modules";

import styles from "./AppShell.module.css";
import { iconFor } from "./moduleIcons";
import { TopBar } from "./TopBar";
import { usePopover } from "./usePopover";

function NavItem({ module: m }: { module: ModuleLink }) {
  const Icon = iconFor(m.path);
  return (
    <li>
      <NavLink
        to={m.path}
        end={m.path === "/"}
        title={`${m.label} (Alt ${m.shortcut.toUpperCase()})`}
        className={({ isActive }) => (isActive ? styles.active : undefined)}
      >
        <Icon className={styles.icon} size={20} strokeWidth={1.9} aria-hidden="true" />
        <span className={styles.label}>{m.label}</span>
        <kbd className={styles.kbd} aria-label={`Alt ${m.shortcut}`}>
          Alt {m.shortcut.toUpperCase()}
        </kbd>
      </NavLink>
    </li>
  );
}

export function AppShell() {
  const { user, signOut } = useAuth();
  const modules = user ? modulesFor(user.role) : [];
  useModuleShortcuts(modules);
  const tenant = useTenant();
  const alertsNav = useRef<HTMLButtonElement>(null);
  const alertsMenu = usePopover([alertsNav]);
  const alerts = useAlerts(alertsMenu.open);
  if (!user) return null;

  const where = user.locations.map((l) => `${l.code} · ${l.name}`).join(", ") || "All locations";
  const main = modules.filter((m) => m.path !== "/settings");
  const settings = modules.find((m) => m.path === "/settings");
  // The name comes from the API. Until it arrives (or if it fails) the product name stands in.
  const name = tenant.data?.name ?? "Construction ERP";

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Modules">
        <div className={styles.brand}>
          <span className={styles.appIcon} aria-hidden="true">
            {tenant.data ? initials(name) : ""}
          </span>
          <span className={styles.brandText}>
            <span className={styles.brandName}>{name}</span>
            <span className={styles.brandSub}>Construction ERP</span>
          </span>
        </div>
        <nav className={styles.navArea} aria-label="Modules">
          <ul className={styles.nav}>
            {main.map((m) => (
              <NavItem key={m.path} module={m} />
            ))}
            <li>
              <button
                ref={alertsNav}
                type="button"
                className={styles.navButton}
                title="Alerts"
                aria-haspopup="dialog"
                aria-expanded={alertsMenu.open}
                onClick={alertsMenu.toggle}
              >
                <Bell className={styles.icon} size={20} strokeWidth={1.9} aria-hidden="true" />
                <span className={styles.label}>Alerts</span>
                {alerts.count > 0 ? (
                  <>
                    <span className={styles.badge} aria-hidden="true">
                      {alerts.count}
                    </span>
                    <span className={styles.srOnly}>
                      {alerts.count === 1 ? "1 alert" : `${alerts.count} alerts`}
                    </span>
                  </>
                ) : null}
              </button>
            </li>
          </ul>
          {settings ? (
            <ul className={`${styles.nav} ${styles.navFooter}`}>
              <NavItem module={settings} />
            </ul>
          ) : null}
        </nav>
        <p className={styles.tagline}>{tenant.data?.tagline}</p>
      </aside>
      <div className={styles.main}>
        <TopBar
          user={user}
          where={where}
          onSignOut={() => void signOut()}
          alerts={alerts}
          alertsMenu={alertsMenu}
        />
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
