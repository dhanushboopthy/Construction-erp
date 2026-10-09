import { NavLink, Outlet } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { modulesFor } from "@/modules";

import styles from "./AppShell.module.css";

const ROLE_LABEL = { owner: "Owner", counter: "Counter", accountant: "Accountant" } as const;

export function AppShell() {
  const { user, signOut } = useAuth();
  const modules = user ? modulesFor(user.role) : [];
  useModuleShortcuts(modules);
  if (!user) return null;

  const shopNames = user.locations.map((l) => l.name).join(", ") || "All locations";

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Modules">
        <div className={styles.brand}>Construction ERP</div>
        <nav>
          <ul className={styles.nav}>
            {modules.map((m) => (
              <li key={m.path}>
                <NavLink
                  to={m.path}
                  end={m.path === "/"}
                  className={({ isActive }) => (isActive ? styles.active : undefined)}
                >
                  <span>{m.label}</span>
                  <kbd className={styles.kbd} aria-label={`Alt ${m.shortcut}`}>
                    Alt {m.shortcut}
                  </kbd>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <div className={styles.main}>
        <header className={styles.topbar}>
          <span className={styles.where}>{shopNames}</span>
          <span className={styles.who}>
            {user.full_name} <span className={styles.role}>{ROLE_LABEL[user.role]}</span>
          </span>
          <button type="button" className={styles.signOut} onClick={() => void signOut()}>
            Sign out
          </button>
        </header>
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
