import { Bell, CheckCircle2, LayoutGrid, LogOut, PackageX, Truck } from "lucide-react";
import { Link } from "react-router";

import { actionsFor } from "@/actions";
import { usePendingEway } from "@/api/compliance";
import { useStockOverview } from "@/api/ledger";
import type { Role } from "@/api/types";
import { formatMoney } from "@/lib/format";

import { CommandSearch } from "./CommandSearch";
import { ThemeToggle } from "./ThemeToggle";
import styles from "./TopBar.module.css";
import { usePopover } from "./usePopover";

interface Props {
  role: Role;
  where: string;
  onSignOut: () => void;
}

export function TopBar({ role, where, onSignOut }: Props) {
  return (
    <header className={styles.topbar}>
      <CommandSearch role={role} />
      <div className={styles.tools}>
        <span className={styles.where} title={`Signed in for ${where}`}>
          <span className={styles.live} aria-hidden="true" />
          {where}
        </span>
        <Alerts />
        <QuickActions role={role} />
        <ThemeToggle className={styles.iconButton} />
        <button
          type="button"
          className={`${styles.iconButton} ${styles.phoneOnly}`}
          onClick={onSignOut}
          aria-label="Sign out"
        >
          <LogOut size={18} strokeWidth={2} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}

/** What needs attention now. Loads when opened; the dot shows once the figures are known. */
function Alerts() {
  const menu = usePopover();
  const stock = useStockOverview(menu.open);
  const eway = usePendingEway(menu.open);
  const outOfStock = (stock.data ?? []).filter((s) => Number(s.quantity) <= 0);
  const pending = eway.data ?? [];
  const count = outOfStock.length + pending.length;
  const loading = menu.open && (stock.isLoading || eway.isLoading);

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
          {!loading && stock.isError && eway.isError ? (
            <p className={styles.menuNote}>Alerts could not be loaded. Try again in a moment.</p>
          ) : null}
          {!loading && count === 0 && !(stock.isError && eway.isError) ? (
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
