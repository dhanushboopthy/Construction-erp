import { Download } from "lucide-react";
import { useState } from "react";

import { usePopover } from "@/components/usePopover";

import { isInstalled, promptInstall, useCanInstall } from "./install";
import styles from "./Pwa.module.css";

/**
 * "Install app" in the top bar, beside the shop and location. Shown until the app is installed.
 * When the browser has offered the install, one click opens its dialog. When it has not (Safari,
 * a browser that wants another visit first, or a page on plain HTTP), the click says how to
 * install from the browser's own menu instead of doing nothing.
 */
export function InstallButton() {
  const can = useCanInstall();
  const help = usePopover();
  const [installed, setInstalled] = useState(isInstalled);
  if (installed) return null;

  async function onClick() {
    if (!can) {
      help.toggle();
      return;
    }
    if ((await promptInstall()) === "accepted") setInstalled(true);
  }

  return (
    <div className={styles.installRoot} ref={help.rootRef}>
      <button
        ref={help.triggerRef}
        type="button"
        className={styles.install}
        onClick={() => void onClick()}
        aria-expanded={can ? undefined : help.open}
        title="Install this app on your device"
      >
        <Download size={16} strokeWidth={2} aria-hidden="true" />
        Install app
      </button>
      {help.open ? (
        <div className={styles.installHelp} role="dialog" aria-label="How to install">
          <p className={styles.installTitle}>Install from your browser</p>
          <p className={styles.installText}>
            Chrome, Edge or Brave: open the browser menu (⋮) and choose <b>Install app</b> or{" "}
            <b>Add to Home screen</b>. Safari on iPhone: tap Share, then <b>Add to Home Screen</b>.
          </p>
          <p className={styles.installText}>
            Nothing there? Reload the page once and try again. The browser offers it after a first
            visit.
          </p>
        </div>
      ) : null}
    </div>
  );
}
