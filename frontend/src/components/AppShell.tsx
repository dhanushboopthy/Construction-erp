import { Factory, LogOut } from "lucide-react";
import { NavLink, Outlet } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { modulesFor, type ModuleLink } from "@/modules";

import styles from "./AppShell.module.css";
import { iconFor } from "./moduleIcons";
import { TopBar } from "./TopBar";

const ROLE_LABEL = { owner: "Owner", counter: "Counter", accountant: "Accountant" } as const;

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  return (
    (parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")
  ).toUpperCase();
}

function NavItem({ module: m }: { module: ModuleLink }) {
  const Icon = iconFor(m.path);
  return (
    <li>
      <NavLink
        to={m.path}
        end={m.path === "/"}
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
  if (!user) return null;

  const where = user.locations.map((l) => `${l.code} · ${l.name}`).join(", ") || "All locations";
  const main = modules.filter((m) => m.path !== "/settings");
  const settings = modules.find((m) => m.path === "/settings");

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Modules">
        <div className={styles.brand}>
          <span className={styles.appIcon} aria-hidden="true">
            <Factory size={22} strokeWidth={2} />
          </span>
          <span className={styles.brandName}>
            Construction<span className={styles.brandAccent}>ERP</span>
          </span>
        </div>
        <nav className={styles.navArea}>
          <ul className={styles.nav}>
            {main.map((m) => (
              <NavItem key={m.path} module={m} />
            ))}
          </ul>
          {settings ? (
            <ul className={`${styles.nav} ${styles.navFooter}`}>
              <NavItem module={settings} />
            </ul>
          ) : null}
        </nav>
        <div className={styles.userCard}>
          <span className={styles.avatar} aria-hidden="true">
            {initials(user.full_name)}
          </span>
          <span className={styles.userText}>
            <span className={styles.userName}>{user.full_name}</span>
            <span className={styles.userRole}>{ROLE_LABEL[user.role]}</span>
          </span>
          <button
            type="button"
            className={styles.signOut}
            onClick={() => void signOut()}
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut size={18} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      </aside>
      <div className={styles.main}>
        <TopBar role={user.role} where={where} onSignOut={() => void signOut()} />
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
