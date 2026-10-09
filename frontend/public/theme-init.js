// Runs before the app paints (a file, not inline, because of the CSP): apply the saved light or
// dark choice, otherwise follow the operating system. Keep the key in sync with src/theme.ts.
(function () {
  var theme = null;
  try {
    theme = localStorage.getItem("erp-theme");
  } catch (e) {
    // Storage blocked: fall back to the system setting.
  }
  if (theme !== "light" && theme !== "dark") {
    theme =
      window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.dataset.theme = theme;
})();
