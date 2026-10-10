/** Light or dark look. The first choice is made before paint by public/theme-init.js. */
export type Theme = "light" | "dark";

const KEY = "erp-theme"; // keep in sync with public/theme-init.js

export function savedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

export function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function currentTheme(): Theme {
  const applied = document.documentElement.dataset.theme;
  return applied === "dark" || applied === "light" ? applied : (savedTheme() ?? systemTheme());
}

export function setTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Storage blocked: the choice lasts until the page is reloaded.
  }
}
