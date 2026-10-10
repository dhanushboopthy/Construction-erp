import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { currentTheme, savedTheme, setTheme, type Theme } from "@/theme";

import styles from "./ThemeToggle.module.css";

/** Sun/moon button that switches between light and dark and remembers the choice. */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setState] = useState<Theme>(currentTheme);

  // Until the user picks one, keep following the operating system.
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!query) return;
    const follow = (e: MediaQueryListEvent) => {
      if (savedTheme()) return;
      const next = e.matches ? "dark" : "light";
      document.documentElement.dataset.theme = next;
      setState(next);
    };
    query.addEventListener("change", follow);
    return () => query.removeEventListener("change", follow);
  }, []);

  const next: Theme = theme === "dark" ? "light" : "dark";
  const label = next === "dark" ? "Dark mode" : "Light mode";

  return (
    <button
      type="button"
      className={className ?? styles.toggle}
      onClick={() => {
        setTheme(next);
        setState(next);
      }}
      aria-label={`Switch to ${label.toLowerCase()}`}
      title={label}
    >
      {theme === "dark" ? (
        <Sun size={18} strokeWidth={2} aria-hidden="true" />
      ) : (
        <Moon size={18} strokeWidth={2} aria-hidden="true" />
      )}
    </button>
  );
}
