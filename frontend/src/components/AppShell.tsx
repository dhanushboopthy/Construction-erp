import {
  Boxes,
  Building2,
  ChartColumn,
  LogOut,
  Package,
  Receipt,
  Settings,
  ShoppingCart,
  Sun,
  Tag,
  Truck,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { NavLink, Outlet } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { useModuleShortcuts } from "@/hooks/useModuleShortcuts";
import { modulesFor } from "@/modules";

import styles from "./AppShell.module.css";

const ROLE_LABEL = { owner: "Owner", counter: "Counter", accountant: "Accountant" } as const;

const ICONS: Record<string, LucideIcon> = {
  "/": Sun,
  "/sales": Receipt,
  "/purchases": ShoppingCart,
  "/stock": Boxes,
  "/parties": Users,
  "/items": Package,
  "/payments": Wallet,
  "/rates": Tag,
  "/transport": Truck,
  "/reports": ChartColumn,
  "/settings": Settings,
};

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  return (
    (parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")
  ).toUpperCase();
}

export function AppShell() {
  const { user, signOut } = useAuth();
  const modules = user ? modulesFor(user.role) : [];
  useModuleShortcuts(modules);
  if (!user) return null;

  const shopNames = user.locations.map((l) => l.name).join(", ") || "All locations";

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Modules">
        <div className={styles.brand}>
          <span className={styles.appIcon} aria-hidden="true">
            <Building2 size={18} strokeWidth={2.2} />
          </span>
          <span className={styles.brandName}>Construction ERP</span>
        </div>
        <nav>
          <ul className={styles.nav}>
            {modules.map((m) => {
              const Icon = ICONS[m.path] ?? Package;
              return (
                <li key={m.path}>
                  <NavLink
                    to={m.path}
                    end={m.path === "/"}
                    className={({ isActive }) => (isActive ? styles.active : undefined)}
                  >
                    <Icon className={styles.icon} size={18} strokeWidth={1.8} aria-hidden="true" />
                    <span className={styles.label}>{m.label}</span>
                    <kbd className={styles.kbd} aria-label={`Alt ${m.shortcut}`}>
                      ⌥{m.shortcut}
                    </kbd>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>
      <div className={styles.main}>
        <header className={styles.topbar}>
          <span className={styles.where}>{shopNames}</span>
          <span className={styles.who}>
            <span className={styles.avatar} aria-hidden="true">
              {initials(user.full_name)}
            </span>
            <span className={styles.name}>{user.full_name}</span>
            <span className={styles.role}>{ROLE_LABEL[user.role]}</span>
          </span>
          <button type="button" className={styles.signOut} onClick={() => void signOut()}>
            <LogOut size={15} strokeWidth={2} aria-hidden="true" />
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
