import { ChevronDown, LogOut, Moon, Sun } from "lucide-react";
import { useState } from "react";

import type { User } from "@/api/types";
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
          <button type="button" className={styles.item} onClick={onSignOut}>
            <LogOut size={18} strokeWidth={2} aria-hidden="true" />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
