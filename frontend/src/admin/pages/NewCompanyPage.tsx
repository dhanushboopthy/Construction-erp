import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { toFormError, type FormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { GST_STATES } from "@/lib/gstStates";

import { useCreateTenant } from "../api";
import { PLAN, companyAddress } from "../labels";
import type { TenantPlan } from "../types";

const MIN_PASSWORD = 8; // backend app/core/security.py MIN_PASSWORD_LENGTH

/** "Shree Steels & Cement" -> "shree-steels-cement": a starting point for the company code. */
function suggestSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 30)
    .replace(/-+$/, "");
}

export function NewCompanyPage() {
  const navigate = useNavigate();
  const create = useCreateTenant();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [plan, setPlan] = useState<TenantPlan>("trial");
  const [stateCode, setStateCode] = useState("33");
  const [ownerName, setOwnerName] = useState("");
  const [username, setUsername] = useState("owner");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<FormError | null>(null);

  const fieldError = (key: string) => (error?.field === key ? error.message : null);
  const shownSlug = slugTouched ? slug : suggestSlug(name);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD) {
      setError({ field: "owner_password", message: `Use at least ${MIN_PASSWORD} characters.` });
      return;
    }
    try {
      const made = await create.mutateAsync({
        name: name.trim(),
        slug: shownSlug,
        plan,
        state_code: stateCode,
        owner_full_name: ownerName.trim(),
        owner_username: username.trim(),
        owner_password: password,
      });
      void navigate(`/admin/companies/${made.id}`, { state: { created: true } });
    } catch (err) {
      setError(toFormError(err));
    }
  }

  return (
    <section aria-labelledby="new-company-title" className={styles.page}>
      <p>
        <Link to="/admin/companies">Companies</Link>
      </p>
      <h1 id="new-company-title" className={styles.title}>
        Add company
      </h1>
      <form className={styles.sheet} onSubmit={(e) => void onSubmit(e)} noValidate>
        <fieldset className={styles.group}>
          <div className={styles.groupHead}>
            <h2>Company</h2>
            <p>Shop settings, a shop, a godown and the walk-in customer are set up for them.</p>
          </div>
          <div className={styles.grid}>
            <TextField
              label="Legal name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              error={fieldError("name")}
              required
            />
            <TextField
              label="Company code"
              value={shownSlug}
              onChange={(e) => {
                setSlugTouched(true);
                setSlug(e.target.value.toLowerCase());
              }}
              error={fieldError("slug")}
              hint={
                shownSlug
                  ? `They sign in at ${companyAddress(shownSlug)}`
                  : "3 to 30 lowercase letters, digits or hyphens."
              }
              required
            />
            <SelectField
              label="State (GST)"
              value={stateCode}
              onChange={(e) => setStateCode(e.target.value)}
              error={fieldError("state_code")}
            >
              {GST_STATES.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.code} {s.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Plan"
              value={plan}
              onChange={(e) => setPlan(e.target.value as TenantPlan)}
              hint={PLAN[plan].note}
            >
              {(Object.keys(PLAN) as TenantPlan[]).map((p) => (
                <option key={p} value={p}>
                  {PLAN[p].label}
                </option>
              ))}
            </SelectField>
          </div>
        </fieldset>

        <fieldset className={styles.group}>
          <div className={styles.groupHead}>
            <h2>First owner</h2>
            <p>They add their own staff in Settings. Share the password in person.</p>
          </div>
          <div className={styles.grid}>
            <TextField
              label="Full name"
              value={ownerName}
              onChange={(e) => setOwnerName(e.target.value)}
              error={fieldError("owner_full_name")}
              required
            />
            <TextField
              label="Username"
              value={username}
              autoComplete="off"
              onChange={(e) => setUsername(e.target.value.toLowerCase())}
              error={fieldError("owner_username")}
              required
            />
            <TextField
              label="Password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={fieldError("owner_password")}
              hint={`At least ${MIN_PASSWORD} characters. They can change it after signing in.`}
              required
            />
          </div>
        </fieldset>

        {error && !error.field ? (
          <p role="alert" className={styles.formError}>
            {error.message}
          </p>
        ) : null}
        <div className={styles.saveBar}>
          <Button type="submit" variant="primary" disabled={create.isPending}>
            {create.isPending ? "Creating…" : "Create company"}
          </Button>
          <Link to="/admin/companies">Cancel</Link>
        </div>
      </form>
    </section>
  );
}
