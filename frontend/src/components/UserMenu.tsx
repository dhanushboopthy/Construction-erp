import { ChevronDown, Keyboard, LifeBuoy, LogOut, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import type { User } from "@/api/types";
import { useUnreadTickets } from "@/support/api";
import { currentTheme, setTheme, type Theme } from "@/theme";

import { Avatar } from "./Avatar";
import styles from "./UserMenu.module.css";
import { usePopover } from "./usePopover";

export const ROLE_LABEL = { owner: "Owner", counter: "Counter", accountant: "Accountant" } as const;

/** Avatar, name and role in the top bar; the chevron opens the theme switch and Sign out. */
export function UserMenu({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const menu = usePopover();
  const [theme, setState] = useState<Theme>(currentTheme);
  const next: Theme = theme === "dark" ? "light" : "dark";
  const unread = useUnreadTickets().data?.unread ?? 0;

  return (
    <div className={styles.root} ref={menu.rootRef}>
      <button
        ref={menu.triggerRef}
        type="button"
        className={styles.trigger}
        aria-haspopup="dialog"
        aria-expanded={menu.open}
        aria-label={`Account menu, ${user.full_name}, ${ROLE_LABEL[user.role]}`}
        onClick={menu.toggle}
      >
        <Avatar name={user.full_name} size={32} />
        <span className={styles.text}>
          <span className={styles.name}>{user.full_name}</span>
          <span className={styles.role}>{ROLE_LABEL[user.role]}</span>
        </span>
        <ChevronDown size={16} strokeWidth={2.2} aria-hidden="true" />
        {unread > 0 ? <span className={styles.triggerDot} aria-hidden="true" /> : null}
      </button>
      {menu.open ? (
        <div className={styles.menu} role="dialog" aria-label="Account">
          <p className={styles.who}>
            <strong>{user.full_name}</strong>
            <span>
              {ROLE_LABEL[user.role]} · {user.username}
            </span>
          </p>
          <button
            type="button"
            className={styles.item}
            onClick={() => {
              setTheme(next);
              setState(next);
            }}
          >
            {theme === "dark" ? (
              <Sun size={18} strokeWidth={2} aria-hidden="true" />
            ) : (
              <Moon size={18} strokeWidth={2} aria-hidden="true" />
            )}
            {next === "dark" ? "Dark mode" : "Light mode"}
          </button>
          <Link to="/help" className={styles.item} onClick={() => menu.close()}>
            <LifeBuoy size={18} strokeWidth={2} aria-hidden="true" />
            Help
            {unread > 0 ? (
              <>
                <span className={styles.dot} aria-hidden="true" data-testid="help-dot" />
                <span className="visually-hidden">
                  {unread === 1 ? "1 new reply" : `${unread} new replies`}
                </span>
              </>
            ) : null}
          </Link>
          <Link to="/shortcuts" className={styles.item} onClick={() => menu.close()}>
            <Keyboard size={18} strokeWidth={2} aria-hidden="true" />
            Keyboard shortcuts
          </Link>
          <button type="button" className={styles.item} onClick={onSignOut}>
            <LogOut size={18} strokeWidth={2} aria-hidden="true" />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
