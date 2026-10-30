import { Bell, CheckCircle2, LayoutGrid, PackageX, Truck } from "lucide-react";
import { Link } from "react-router";

import { actionsFor } from "@/actions";
import type { Role, User } from "@/api/types";
import type { Alerts } from "@/hooks/useAlerts";
import { formatMoney } from "@/lib/format";

import { CommandSearch } from "./CommandSearch";
import styles from "./TopBar.module.css";
import { UserMenu } from "./UserMenu";
import { usePopover, type Popover } from "./usePopover";

interface Props {
  user: User;
  where: string;
  onSignOut: () => void;
  /** The alerts panel is opened from here and from the sidebar, so the shell owns its state. */
  alerts: Alerts;
  alertsMenu: Popover;
}

export function TopBar({ user, where, onSignOut, alerts, alertsMenu }: Props) {
  return (
    <header className={styles.topbar}>
      <CommandSearch role={user.role} />
      <div className={styles.tools}>
        <span className={styles.where} title={`Signed in for ${where}`}>
          <span className={styles.live} aria-hidden="true" />
          {where}
        </span>
        <AlertsBell alerts={alerts} menu={alertsMenu} />
        <QuickActions role={user.role} />
        <span className={styles.divider} aria-hidden="true" />
        <UserMenu user={user} onSignOut={onSignOut} />
      </div>
    </header>
  );
}

/** The bell and its panel: out-of-stock items and e-way bills still to be made. */
function AlertsBell({ alerts, menu }: { alerts: Alerts; menu: Popover }) {
  const { outOfStock, pending, count, failed } = alerts;
  const loading = menu.open && alerts.loading;

  return (
    <div className={styles.menuRoot} ref={menu.rootRef}>
      <button
        ref={menu.triggerRef}
        type="button"
        className={styles.iconButton}
        aria-label={count ? `Alerts, ${count} need attention` : "Alerts"}
        aria-expanded={menu.open}
        onClick={menu.toggle}
      >
        <Bell size={18} strokeWidth={2} aria-hidden="true" />
        {count ? <span className={styles.dot} aria-hidden="true" /> : null}
      </button>
      {menu.open ? (
        <div className={styles.menu} role="dialog" aria-label="Alerts">
          <p className={styles.menuTitle}>Needs attention</p>
          {loading ? <p className={styles.menuNote}>Checking stock and e-way bills…</p> : null}
          {!loading && failed ? (
            <p className={styles.menuNote}>Alerts could not be loaded. Try again in a moment.</p>
          ) : null}
          {!loading && count === 0 && !failed ? (
            <p className={styles.allClear}>
              <CheckCircle2 size={18} aria-hidden="true" /> All clear: nothing is out of stock and
              no e-way bill is waiting.
            </p>
          ) : null}
          <ul className={styles.alertList}>
            {outOfStock.slice(0, 5).map((s) => (
              <li key={`s-${s.item_id}`}>
                <Link to="/stock" className={styles.alert} onClick={() => menu.close()}>
                  <span className={`${styles.alertIcon} ${styles.critical}`} aria-hidden="true">
                    <PackageX size={16} />
                  </span>
                  <span>
                    <strong>{s.name}</strong>
                    <span className={styles.alertSub}>Out of stock everywhere</span>
                  </span>
                </Link>
              </li>
            ))}
            {pending.slice(0, 5).map((p) => (
              <li key={`e-${p.invoice_id}`}>
                <Link to="/sales" className={styles.alert} onClick={() => menu.close()}>
                  <span className={`${styles.alertIcon} ${styles.warn}`} aria-hidden="true">
                    <Truck size={16} />
                  </span>
                  <span>
                    <strong>E-way bill for {p.number}</strong>
                    <span className={styles.alertSub}>
                      {p.party_name} · ₹{formatMoney(p.grand_total)}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function QuickActions({ role }: { role: Role }) {
  const menu = usePopover();
  const actions = actionsFor(role).slice(0, 6);
  if (actions.length === 0) return null;
  return (
    <div className={styles.menuRoot} ref={menu.rootRef}>
      <button
        ref={menu.triggerRef}
        type="button"
        className={styles.iconButton}
        aria-label="Quick actions"
        aria-expanded={menu.open}
        onClick={menu.toggle}
      >
        <LayoutGrid size={18} strokeWidth={2} aria-hidden="true" />
      </button>
      {menu.open ? (
        <nav className={`${styles.menu} ${styles.actionsMenu}`} aria-label="Quick actions">
          <p className={styles.menuTitle}>Quick actions</p>
          <ul className={styles.actionGrid}>
            {actions.map((a) => {
              const Icon = a.icon;
              return (
                <li key={a.id}>
                  <Link to={a.path} className={styles.action} onClick={() => menu.close()}>
                    <span className={styles.actionIcon} aria-hidden="true">
                      <Icon size={18} strokeWidth={2} />
                    </span>
                    {a.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      ) : null}
    </div>
  );
}
