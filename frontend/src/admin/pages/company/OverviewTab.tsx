import { useRef, useState, type FormEvent } from "react";

import { toFormError, type FormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { SelectField, TextAreaField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatDateTime } from "@/lib/format";
import { GST_STATES } from "@/lib/gstStates";

import {
  useCancelTenant,
  useReactivateTenant,
  useRemoveCompanyLogo,
  useSellerDetails,
  useSetCompanyLogo,
  useSuspendTenant,
  useUpdateSellerDetails,
  useUpdateTenant,
} from "../../api";
import adminStyles from "../../Admin.module.css";
import { useAdminAuth } from "../../AdminAuthContext";
import { Usage } from "../../Badge";
import type { SellerDetails, TenantDetail, TenantUpdate } from "../../types";

const MAX_LOGO_BYTES = 200 * 1024;

/** Who the company is, what it uses, what prints on its bills, and its status. */
export function OverviewTab({ tenant }: { tenant: TenantDetail }) {
  const { isSuperAdmin } = useAdminAuth();
  return (
    <>
      <div className={adminStyles.twoColumns}>
        <InUse tenant={tenant} />
        <Contact tenant={tenant} />
      </div>
      <Seller tenant={tenant} />
      {isSuperAdmin ? (
        <>
          <Logo tenant={tenant} />
          <Status tenant={tenant} />
        </>
      ) : null}
    </>
  );
}

function InUse({ tenant: t }: { tenant: TenantDetail }) {
  return (
    <div className={styles.panel}>
      <h2 className={styles.panelHead}>In use</h2>
      <dl className={adminStyles.facts}>
        <dt>Active users</dt>
        <dd>
          <Usage used={t.users} limit={t.max_users} label="active users" />
        </dd>
        <dt>Shops and godowns</dt>
        <dd>
          <Usage used={t.locations} limit={t.max_locations} label="shops and godowns" />
        </dd>
        <dt>Bills, last 30 days</dt>
        <dd>{t.bills_30d}</dd>
        <dt>Signed in now</dt>
        <dd>{t.open_sessions}</dd>
        <dt>Last sign-in</dt>
        <dd>{formatDateTime(t.last_sign_in_at)}</dd>
        <dt>Last activity</dt>
        <dd>{formatDateTime(t.last_activity_at)}</dd>
        <dt>Joined</dt>
        <dd>{formatDateTime(t.created_at)}</dd>
      </dl>
    </div>
  );
}

// ------------------------------------------------------------------ contact

function Contact({ tenant }: { tenant: TenantDetail }) {
  const { isSuperAdmin } = useAdminAuth();
  const update = useUpdateTenant(tenant.id);
  const [ownerName, setOwnerName] = useState(tenant.owner_name ?? "");
  const [email, setEmail] = useState(tenant.owner_email ?? "");
  const [mobile, setMobile] = useState(tenant.owner_mobile ?? "");
  const [city, setCity] = useState(tenant.city ?? "");
  const [stateCode, setStateCode] = useState(tenant.state_code ?? "");
  const [notes, setNotes] = useState(tenant.notes ?? "");
  const [error, setError] = useState<FormError | null>(null);
  const [saved, setSaved] = useState(false);
  const fieldError = (key: string) => (error?.field === key ? error.message : null);

  if (!isSuperAdmin) {
    return (
      <div className={styles.panel}>
        <h2 className={styles.panelHead}>Contact</h2>
        <dl className={adminStyles.facts}>
          <dt>Owner</dt>
          <dd>{tenant.owner_name ?? "Not recorded"}</dd>
          <dt>Email</dt>
          <dd>{tenant.owner_email ?? "Not recorded"}</dd>
          <dt>Mobile</dt>
          <dd>{tenant.owner_mobile ?? "Not recorded"}</dd>
          <dt>City</dt>
          <dd>{tenant.city ?? "Not recorded"}</dd>
          <dt>Internal notes</dt>
          <dd>{tenant.notes ?? "None"}</dd>
        </dl>
      </div>
    );
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    const body: TenantUpdate = {
      owner_name: ownerName.trim() || null,
      owner_email: email.trim() || null,
      owner_mobile: mobile.trim() || null,
      city: city.trim() || null,
      state_code: stateCode || null,
      notes: notes.trim() || null,
    };
    try {
      await update.mutateAsync(body);
      setSaved(true);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <form className={styles.panel} onSubmit={(e) => void onSubmit(e)} noValidate>
      <h2 className={styles.panelHead}>Contact</h2>
      <TextField
        label="Owner"
        value={ownerName}
        onChange={(e) => setOwnerName(e.target.value)}
        error={fieldError("owner_name")}
      />
      <TextField
        label="Owner email"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={fieldError("owner_email")}
      />
      <TextField
        label="Owner mobile"
        inputMode="tel"
        value={mobile}
        onChange={(e) => setMobile(e.target.value)}
        error={fieldError("owner_mobile")}
      />
      <TextField
        label="City"
        value={city}
        onChange={(e) => setCity(e.target.value)}
        error={fieldError("city")}
      />
      <SelectField
        label="State"
        value={stateCode}
        onChange={(e) => setStateCode(e.target.value)}
        error={fieldError("state_code")}
      >
        <option value="">Not recorded</option>
        {GST_STATES.map((s) => (
          <option key={s.code} value={s.code}>
            {s.code} {s.name}
          </option>
        ))}
      </SelectField>
      <TextAreaField
        label="Internal notes"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        hint="Only Duolink staff see these. The company never does."
        error={fieldError("notes")}
      />
      {error && !error.field ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" disabled={update.isPending}>
          {update.isPending ? "Saving…" : "Save contact"}
        </Button>
        {saved ? (
          <p role="status" className={styles.saved}>
            Contact saved.
          </p>
        ) : null}
      </div>
    </form>
  );
}

// ------------------------------------------------------------------ seller details

function Seller({ tenant }: { tenant: TenantDetail }) {
  const { isSuperAdmin } = useAdminAuth();
  const seller = useSellerDetails(tenant.id);
  if (seller.isPending) return <p role="status">Loading seller details…</p>;
  if (seller.isError) {
    return <p className={styles.formError}>Seller details could not be loaded.</p>;
  }
  const s = seller.data;
  if (!isSuperAdmin) {
    return (
      <div className={styles.panel}>
        <h2 className={styles.panelHead}>Seller details on bills</h2>
        <dl className={adminStyles.facts}>
          <dt>Legal name</dt>
          <dd>{s.legal_name}</dd>
          <dt>GSTIN</dt>
          <dd>{s.registration_no ?? "Not registered"}</dd>
          <dt>PAN</dt>
          <dd>{s.pan ?? "From the GSTIN"}</dd>
          <dt>CIN</dt>
          <dd>{s.cin ?? "None"}</dd>
          <dt>State</dt>
          <dd>{s.state_code}</dd>
          <dt>Address</dt>
          <dd>{s.address || "Not set"}</dd>
        </dl>
      </div>
    );
  }
  // Keyed by the saved values, so the form starts again from what the server now holds.
  return <SellerForm key={JSON.stringify(s)} tenant={tenant} seller={s} />;
}

function SellerForm({ tenant, seller }: { tenant: TenantDetail; seller: SellerDetails }) {
  const update = useUpdateSellerDetails(tenant.id);
  const [legalName, setLegalName] = useState(seller.legal_name);
  const [gstin, setGstin] = useState(seller.registration_no ?? "");
  const [pan, setPan] = useState(seller.pan ?? "");
  const [cin, setCin] = useState(seller.cin ?? "");
  const [address, setAddress] = useState(seller.address);
  const [stateCode, setStateCode] = useState(seller.state_code);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<FormError | null>(null);
  const [saved, setSaved] = useState(false);
  const fieldError = (key: string) => (error?.field === key ? error.message : null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    if (reason.trim().length < 3) {
      setError({ field: "reason", message: "Write why, in a few words." });
      return;
    }
    // Only what changed is sent; a blank GSTIN, PAN or CIN clears it.
    const body: Partial<Parameters<typeof update.mutateAsync>[0]> & { reason: string } = {
      reason: reason.trim(),
    };
    if (legalName.trim() !== seller.legal_name) body.legal_name = legalName.trim();
    if ((gstin.trim() || null) !== seller.registration_no) {
      body.registration_no = gstin.trim().toUpperCase() || null;
    }
    if ((pan.trim() || null) !== seller.pan) body.pan = pan.trim().toUpperCase() || null;
    if ((cin.trim() || null) !== seller.cin) body.cin = cin.trim().toUpperCase() || null;
    if (address !== seller.address) body.address = address;
    if (stateCode !== seller.state_code) body.state_code = stateCode;
    try {
      await update.mutateAsync(body);
      setReason("");
      setSaved(true);
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <form className={styles.panel} onSubmit={(e) => void onSubmit(e)} noValidate>
      <h2 className={styles.panelHead}>Seller details on bills</h2>
      <p className={styles.note}>
        For a company that cannot reach its own Settings. The change shows in its audit log as done
        by Duolink.
      </p>
      <TextField
        label="Legal name"
        value={legalName}
        onChange={(e) => setLegalName(e.target.value)}
        error={fieldError("legal_name")}
      />
      <TextField
        label="GSTIN"
        value={gstin}
        maxLength={15}
        onChange={(e) => setGstin(e.target.value.toUpperCase())}
        error={fieldError("registration_no")}
      />
      <TextField
        label="PAN"
        value={pan}
        maxLength={10}
        onChange={(e) => setPan(e.target.value.toUpperCase())}
        hint="Blank: taken from the GSTIN."
        error={fieldError("pan")}
      />
      <TextField
        label="CIN"
        value={cin}
        maxLength={21}
        onChange={(e) => setCin(e.target.value.toUpperCase())}
        error={fieldError("cin")}
      />
      <SelectField
        label="State (GST)"
        value={stateCode}
        onChange={(e) => setStateCode(e.target.value)}
        error={fieldError("state_code")}
      >
        {GST_STATES.map((st) => (
          <option key={st.code} value={st.code}>
            {st.code} {st.name}
          </option>
        ))}
      </SelectField>
      <TextAreaField
        label="Address"
        value={address}
        onChange={(e) => setAddress(e.target.value)}
        error={fieldError("address")}
      />
      <TextField
        label="Reason for the change"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        hint="Kept in the audit logs. For example: the owner sent the new certificate."
        error={fieldError("reason")}
      />
      {error && !error.field ? (
        <p role="alert" className={styles.formError}>
          {error.message}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" disabled={update.isPending}>
          {update.isPending ? "Saving…" : "Save seller details"}
        </Button>
        {saved ? (
          <p role="status" className={styles.saved}>
            Seller details saved.
          </p>
        ) : null}
      </div>
    </form>
  );
}

// ------------------------------------------------------------------ logo

function Logo({ tenant }: { tenant: TenantDetail }) {
  const set = useSetCompanyLogo(tenant.id);
  const remove = useRemoveCompanyLogo(tenant.id);
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const busy = set.isPending || remove.isPending;

  const onFile = (file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_LOGO_BYTES) {
      setMessage({ text: "The logo is larger than 200 KB. Use a smaller file.", error: true });
    } else {
      set.mutate(file, {
        onSuccess: () => setMessage({ text: "Logo saved.", error: false }),
        onError: (e) => setMessage({ text: toFormError(e).message, error: true }),
      });
    }
    if (input.current) input.current.value = ""; // so choosing the same file again still fires
  };

  return (
    <div className={styles.panel}>
      <h2 className={styles.panelHead}>Logo</h2>
      <p className={styles.note}>
        A square PNG or plain SVG, up to 200 KB. The company can also set its own in Settings.
      </p>
      <div className={styles.actions}>
        <input
          ref={input}
          type="file"
          accept="image/png,image/svg+xml"
          hidden
          aria-label="Logo file"
          onChange={(e) => onFile(e.target.files?.[0])}
        />
        <Button disabled={busy} onClick={() => input.current?.click()}>
          Choose logo
        </Button>
        <Button
          disabled={busy}
          onClick={() =>
            remove.mutate(undefined, {
              onSuccess: () => setMessage({ text: "Logo removed.", error: false }),
              onError: (e) => setMessage({ text: toFormError(e).message, error: true }),
            })
          }
        >
          Remove logo
        </Button>
      </div>
      {message ? (
        <p
          role={message.error ? "alert" : "status"}
          className={message.error ? styles.formError : styles.saved}
        >
          {message.text}
        </p>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ status

type Pending = "suspend" | "cancel" | null;

function Status({ tenant }: { tenant: TenantDetail }) {
  const suspend = useSuspendTenant(tenant.id);
  const cancel = useCancelTenant(tenant.id);
  const reactivate = useReactivateTenant(tenant.id);
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState<Pending>(null);
  const [error, setError] = useState<string | null>(null);
  const closed = tenant.status === "cancelled";
  const suspended = tenant.status === "suspended";

  function ask(kind: Exclude<Pending, null>) {
    if (reason.trim().length < 3) {
      setError("Write why, in a few words. The company's owner may ask.");
      return;
    }
    setError(null);
    setConfirming(kind);
  }

  const people = `${tenant.open_sessions} signed-in ${tenant.open_sessions === 1 ? "person is" : "people are"}`;

  return (
    <form
      className={styles.panel}
      onSubmit={(e) => {
        e.preventDefault();
        if (closed) {
          if (reason.trim().length < 3) {
            setError("Say why this company is being reopened.");
            return;
          }
          reactivate.mutate(reason.trim(), {
            onSuccess: () => setReason(""),
            onError: (err) => setError(toFormError(err).message),
          });
        } else {
          ask("suspend");
        }
      }}
      noValidate
    >
      <h2 className={styles.panelHead}>
        {closed ? "Closed" : suspended ? "Suspended" : "Suspend or close company"}
      </h2>
      {suspended || closed ? (
        <dl className={adminStyles.facts}>
          <dt>Since</dt>
          <dd>{formatDateTime(closed ? tenant.cancelled_at : tenant.suspended_at)}</dd>
          <dt>Reason</dt>
          <dd>{closed ? tenant.cancelled_reason : tenant.suspended_reason}</dd>
        </dl>
      ) : null}
      {closed ? (
        <p className={styles.note}>
          Nobody at {tenant.name} can sign in. Their books are kept. Reopening needs a reason.
        </p>
      ) : suspended ? (
        <p className={styles.note}>Nobody at {tenant.name} can sign in. Their books are kept.</p>
      ) : null}

      {suspended ? (
        <div className={styles.actions}>
          <Button
            variant="primary"
            disabled={reactivate.isPending}
            onClick={() => {
              setError(null);
              reactivate.mutate(undefined, { onError: (e) => setError(toFormError(e).message) });
            }}
          >
            Reactivate company
          </Button>
        </div>
      ) : null}

      <TextAreaField
        label="Reason"
        value={reason}
        onChange={(e) => {
          setReason(e.target.value);
          setConfirming(null);
        }}
        hint={
          closed
            ? "For example: they paid the pending invoice."
            : "For example: Invoice for October unpaid."
        }
        error={error}
      />

      {confirming ? (
        <div className={adminStyles.confirm} role="alertdialog" aria-labelledby="status-confirm">
          <p id="status-confirm">
            {confirming === "suspend"
              ? `Suspend ${tenant.name}? ${people} signed out now, and nobody can sign in until you reactivate it.`
              : `Close ${tenant.name}? ${people} signed out now, and nobody can sign in. Their books are kept, and you can reopen it with a reason.`}
          </p>
          <div className={styles.actions}>
            <Button
              variant="primary"
              className={adminStyles.danger}
              disabled={suspend.isPending || cancel.isPending}
              autoFocus
              onClick={() => {
                const done = {
                  onSuccess: () => {
                    setConfirming(null);
                    setReason("");
                  },
                  onError: (e: unknown) => setError(toFormError(e).message),
                };
                if (confirming === "suspend") suspend.mutate(reason.trim(), done);
                else cancel.mutate(reason.trim(), done);
              }}
            >
              {confirming === "suspend" ? "Suspend now" : "Close now"}
            </Button>
            <Button onClick={() => setConfirming(null)}>Keep it running</Button>
          </div>
        </div>
      ) : closed ? (
        <div className={styles.actions}>
          <Button type="submit" variant="primary" disabled={reactivate.isPending}>
            Reopen company
          </Button>
        </div>
      ) : (
        <div className={styles.actions}>
          {suspended ? null : <Button type="submit">Suspend company</Button>}
          <Button onClick={() => ask("cancel")}>Close company</Button>
        </div>
      )}
    </form>
  );
}
