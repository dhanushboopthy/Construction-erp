import styles from "./Pwa.module.css";
import { useOnline } from "./updates";

/**
 * "No connection" (Milestone 29). The app shell opens offline, but there is no offline data and
 * no offline billing: every save goes to the server, which numbers the bill, so with no
 * connection nothing can be saved, and this says so on every screen.
 */
export function ConnectionNotice() {
  const online = useOnline();
  if (online) return null;
  return (
    <p className={styles.offline} role="alert">
      No connection. Bills and other changes cannot be saved until the network is back.
    </p>
  );
}
