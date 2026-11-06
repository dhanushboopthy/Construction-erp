import { useNavigate } from "react-router";

import { useAuth } from "@/auth/AuthContext";
import { formatClock } from "@/lib/format";

import styles from "./SupportBanner.module.css";

/**
 * "Duolink support · read-only · viewing <Company> · ends 16:40 · Exit". Shown on every screen
 * for as long as a support session is open (M23). The server enforces read-only; this only says so.
 */
export function SupportBanner() {
  const { support, exitSupport } = useAuth();
  const navigate = useNavigate();
  if (!support) return null;
  const ends = formatClock(
    support.expires_at < support.grant_ends_at ? support.expires_at : support.grant_ends_at,
  );
  return (
    <div className={styles.banner} role="status" aria-label="Duolink support session">
      <span className={styles.title}>Super Admin Mode</span>
      <span className={styles.facts}>
        Duolink support · read-only · viewing {support.company_name} · ends {ends}
        {support.include_costs ? " · cost and margin shown" : ""}
      </span>
      <button
        type="button"
        className={styles.exit}
        onClick={() => void exitSupport().then(() => navigate("/login", { replace: true }))}
      >
        Exit
      </button>
    </div>
  );
}
