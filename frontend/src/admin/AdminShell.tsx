import { Activity, Building2, LayoutDashboard, LogOut, ShieldCheck, Users } from "lucide-react";
import { useEffect } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";

import styles from "@/components/AppShell.module.css";
import { ThemeToggle } from "@/components/ThemeToggle";

import adminStyles from "./Admin.module.css";
import { useAdminAuth } from "./AdminAuthContext";

const NAV = [
  { to: "/admin", label: "Overview", icon: LayoutDashboard, key: "1", end: true },
  { to: "/admin/companies", label: "Companies", icon: Building2, key: "2", end: false },
  { to: "/admin/users", label: "Users", icon: Users, key: "3", end: false },
  { to: "/admin/activity", label: "Activity", icon: Activity, key: "4", end: false },
];

function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  return (
    (parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")
  ).toUpperCase();
}

/** The Duolink admin frame: the company app's sidebar, with Duolink's own sections. */
export function AdminShell() {
  const { admin, signOut } = useAdminAuth();
  const navigate = useNavigate();

  // Alt+1-4 move between sections, as Alt+number does in the company app.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!event.altKey || event.ctrlKey || event.metaKey) return;
      const item = NAV.find((n) => event.code === `Digit${n.key}`);
      if (item) {
        event.preventDefault();
        void navigate(item.to);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  if (!admin) return null;

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Sections">
        <div className={styles.brand}>
          <span className={styles.appIcon} aria-hidden="true">
            <ShieldCheck size={22} strokeWidth={2} />
          </span>
          <span className={styles.brandName}>
            Duolink<span className={styles.brandAccent}>Admin</span>
          </span>
        </div>
        <nav className={styles.navArea}>
          <ul className={styles.nav}>
            {NAV.map(({ to, label, icon: Icon, key, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  className={({ isActive }) => (isActive ? styles.active : undefined)}
                >
                  <Icon className={styles.icon} size={20} strokeWidth={1.9} aria-hidden="true" />
                  <span className={styles.label}>{label}</span>
                  <kbd className={styles.kbd} aria-label={`Alt ${key}`}>
                    Alt {key}
                  </kbd>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className={styles.userCard}>
          <span className={styles.avatar} aria-hidden="true">
            {initials(admin.full_name)}
          </span>
          <span className={styles.userText}>
            <span className={styles.userName}>{admin.full_name}</span>
            <span className={styles.userRole}>Duolink admin</span>
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
        <div className={adminStyles.topRow}>
          <ThemeToggle />
        </div>
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
