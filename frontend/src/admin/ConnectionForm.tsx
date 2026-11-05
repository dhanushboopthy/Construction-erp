import { useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import { useConnectIntegration } from "./api";
import { FIELD_LABEL, PROVIDER } from "./labels";
import type { Integration, IntegrationProvider } from "./types";

const PROVIDERS: IntegrationProvider[] = ["sandbox", "live", "fake"];
const FIELDS = ["client_id", "client_secret", "username", "password", "api_key"] as const;

/**
 * Connect or update. The credentials are write-only: a saved key is never shown, only its last
 * four characters, and a field left empty keeps the saved value.
 */
export function ConnectionForm({
  integration,
  onClose,
}: {
  integration: Integration;
  onClose: () => void;
}) {
  const connect = useConnectIntegration(integration.kind);
  const [provider, setProvider] = useState<IntegrationProvider>(integration.provider ?? "sandbox");
  const [baseUrl, setBaseUrl] = useState(integration.base_url);
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<FormError | null>(null);
  const fieldError = (key: string) => (error?.field === key ? error.message : null);
  const pretend = provider === "fake";
  const wanted = FIELDS.filter((f) =>
    integration.kind === "gsp" ? f !== "api_key" : f === "api_key",
  );
  const saved = integration.provider !== null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await connect.mutateAsync({
        provider,
        base_url: pretend ? "" : baseUrl.trim(),
        ...(pretend ? {} : Object.fromEntries(wanted.map((f) => [f, values[f]?.trim() || null]))),
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
      aria-label={`Connect ${integration.kind}`}
      className={styles.stack}
    >
      <SelectField
        label="Provider"
        value={provider}
        onChange={(e) => setProvider(e.target.value as IntegrationProvider)}
        error={fieldError("provider")}
      >
        {PROVIDERS.map((p) => (
          <option key={p} value={p}>
            {PROVIDER[p]}
          </option>
        ))}
      </SelectField>
      {pretend ? (
        <p className={styles.note}>
          The pretend provider makes up answers and never reaches the government portal. The server
          refuses it in production.
        </p>
      ) : (
        <>
          <TextField
            label="Address (base URL)"
            value={baseUrl}
            placeholder="https://"
            onChange={(e) => setBaseUrl(e.target.value)}
            error={fieldError("base_url")}
          />
          {wanted.map((field) => (
            <TextField
              key={field}
              label={FIELD_LABEL[field] ?? field}
              type={field === "username" || field === "client_id" ? "text" : "password"}
              autoComplete="off"
              value={values[field] ?? ""}
              placeholder={saved ? "Leave empty to keep the saved value" : ""}
              onChange={(e) => setValues((v) => ({ ...v, [field]: e.target.value }))}
              error={fieldError(field)}
              hint={
                field === "client_secret" || field === "api_key"
                  ? integration.key_last4
                    ? `Saved key ends in ${integration.key_last4}. It is never shown again.`
                    : "Saved encrypted. Only its last 4 characters are shown afterwards."
                  : undefined
              }
            />
          ))}
        </>
      )}
      {error && !error.field ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" disabled={connect.isPending}>
          {connect.isPending ? "Saving…" : "Save connection"}
        </Button>
        <Button onClick={onClose}>Cancel</Button>
      </div>
    </form>
  );
}
