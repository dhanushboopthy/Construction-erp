import { Bell } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import styles from "./Admin.module.css";
import { useNotifications } from "./api";
import { Badge } from "./Badge";
import { NOTIFICATION_LEVEL } from "./labels";

/**
 * The admin's bell (Milestone 24): what needs Duolink's attention, worked out by the server on
 * every read and asked again each minute. The count is read out ("3 notifications"); each item
 * names its level in words as well as in colour. Escape closes the panel and returns focus.
 */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const notifications = useNotifications();
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const count = notifications.data?.count ?? 0;

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    const onClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !button.current?.contains(target)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  return (
    <div className={styles.bell}>
      <button
        ref={button}
        type="button"
        className={styles.bellButton}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={count === 0 ? "Notifications" : `Notifications, ${count} to look at`}
        onClick={() => setOpen((v) => !v)}
      >
        <Bell size={20} strokeWidth={1.9} aria-hidden="true" />
        {count > 0 && (
          <span className={styles.bellCount} aria-hidden="true">
            {count}
          </span>
        )}
      </button>
      {open && (
        <div ref={panel} className={styles.bellPanel} role="dialog" aria-label="Notifications">
          {notifications.isError ? (
            <p className={styles.bellEmpty}>Notifications could not be loaded.</p>
          ) : count === 0 ? (
            <p className={styles.bellEmpty}>Nothing needs attention.</p>
          ) : (
            <ul className={styles.bellList}>
              {notifications.data?.items.map((n) => {
                const level = NOTIFICATION_LEVEL[n.level];
                return (
                  <li key={n.id} className={styles.bellItem}>
                    <Badge tone={level.tone}>{level.label}</Badge>
                    <Link to={n.link} onClick={() => setOpen(false)}>
                      {n.title}
                    </Link>
                    <span className={styles.bellBody}>{n.body}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
