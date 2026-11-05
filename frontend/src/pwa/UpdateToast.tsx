import { useState } from "react";

import { Button } from "@/components/Button";

import styles from "./Pwa.module.css";
import { applyUpdate, dismissUpdate, usePwa } from "./updates";

/**
 * "A new version is ready. Update now" (Milestone 29). Shown when a new build has been
 * installed; nothing reloads until the person presses Update now, and not even then while a
 * form has changes not yet saved.
 */
export function UpdateToast() {
  const pwa = usePwa();
  const [blocked, setBlocked] = useState(false);
  if (!pwa.updateWaiting || pwa.dismissed) return null;
  return (
    <div className={styles.toast} role="status" aria-live="polite" aria-label="App update">
      <p className={styles.toastText}>
        <span className={styles.toastTitle}>A new version is ready.</span>
        {blocked ? (
          <span className={styles.toastNote} data-tone="warn">
            Save or cancel the open form first. Nothing is reloaded until you do.
          </span>
        ) : (
          <span className={styles.toastNote}>Updating reloads this page.</span>
        )}
      </p>
      <div className={styles.toastActions}>
        <Button
          variant="primary"
          allowWhenReadOnly
          onClick={() => setBlocked(applyUpdate() === "unsaved")}
        >
          Update now
        </Button>
        <Button variant="ghost" allowWhenReadOnly onClick={dismissUpdate}>
          Later
        </Button>
      </div>
    </div>
  );
}
