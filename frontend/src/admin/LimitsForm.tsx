import { useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import { useIntegrationLimits } from "./api";
import type { Integration } from "./types";

/** The per-company limits, when to warn and (for the lookup) how long an answer is reused. */
export function LimitsForm({
  integration,
  onClose,
}: {
  integration: Integration;
  onClose: () => void;
}) {
  const save = useIntegrationLimits(integration.kind);
  const [daily, setDaily] = useState(String(integration.daily_limit));
  const [monthly, setMonthly] = useState(String(integration.monthly_limit));
  const [warn, setWarn] = useState(String(integration.warn_at_percent));
  const [hours, setHours] = useState(String(integration.cache_hours));
  const [error, setError] = useState<FormError | null>(null);
  const fieldError = (key: string) => (error?.field === key ? error.message : null);
  const lookup = integration.kind === "gstin_lookup";

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await save.mutateAsync({
        daily_limit: Number(daily),
        monthly_limit: Number(monthly),
        warn_at_percent: Number(warn),
        cache_hours: Number(hours),
      });
      onClose();
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <form
      onSubmit={(e) => void onSubmit(e)}
      noValidate
      aria-label={`Limits for ${integration.kind}`}
      className={styles.stack}
    >
      <div className={styles.grid}>
        <TextField
          label="Daily limit per company"
          inputMode="numeric"
          value={daily}
          onChange={(e) => setDaily(e.target.value)}
          error={fieldError("daily")}
        />
        <TextField
          label="Monthly limit per company"
          inputMode="numeric"
          value={monthly}
          onChange={(e) => setMonthly(e.target.value)}
          error={fieldError("monthly")}
        />
        <TextField
          label="Warn at (%)"
          inputMode="numeric"
          value={warn}
          onChange={(e) => setWarn(e.target.value)}
          error={fieldError("warn_at_percent")}
        />
        <TextField
          label="Keep lookups for (hours)"
          inputMode="numeric"
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          error={fieldError("cache_hours")}
          hint={lookup ? "0 turns the cache off." : "Only the GSTIN lookup uses the cache."}
        />
      </div>
      <p className={styles.note}>
        {lookup
          ? "A company over its limit is refused until the day or month turns."
          : "These only warn. A bill is never held back because the GSP limit is reached."}
      </p>
      {error && !error.field ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save limits"}
        </Button>
        <Button onClick={onClose}>Cancel</Button>
      </div>
    </form>
  );
}
