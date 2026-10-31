import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { toFormError, type FormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { CheckField, SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { GST_STATES } from "@/lib/gstStates";

import { useCreateTenant, usePlans } from "../api";
import { TRIAL_PLAN, companyAddress, limitsNote } from "../labels";

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
  const plans = usePlans(false).data ?? []; // archived plans are not offered
  const [chosenPlan, setPlan] = useState(TRIAL_PLAN);
  const picked = plans.find((p) => p.code === chosenPlan) ?? plans[0];
  const plan = picked?.code ?? chosenPlan;
  const [stateCode, setStateCode] = useState("33");
  const [city, setCity] = useState("");
  const [legalName, setLegalName] = useState("");
  const [gstin, setGstin] = useState("");
  const [shopName, setShopName] = useState("Shop 1");
  const [shopCode, setShopCode] = useState("S1");
  const [terms, setTerms] = useState<"trial" | "active">("trial");
  const [trialDays, setTrialDays] = useState("14");
  const [ownerName, setOwnerName] = useState("");
  const [username, setUsername] = useState("owner");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerMobile, setOwnerMobile] = useState("");
  const [password, setPassword] = useState("");
  const [mustChange, setMustChange] = useState(false);
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
      const onTrial = plan === TRIAL_PLAN && terms === "trial";
      const made = await create.mutateAsync({
        name: name.trim(),
        slug: shownSlug,
        plan,
        trial_days: onTrial ? Number(trialDays) : null,
        start_active: plan === TRIAL_PLAN && terms === "active",
        state_code: stateCode,
        city: city.trim() || null,
        legal_name: legalName.trim() || null,
        registration_no: gstin.trim().toUpperCase() || null,
        shop_name: shopName.trim() || "Shop 1",
        shop_code: shopCode.trim().toUpperCase() || "S1",
        owner_full_name: ownerName.trim(),
        owner_username: username.trim(),
        owner_email: ownerEmail.trim() || null,
        owner_mobile: ownerMobile.trim() || null,
        owner_password: password,
        require_owner_password_change: mustChange,
      });
      void navigate(`/admin/companies/${made.id}`, {
        state: { created: true, signInUrl: made.sign_in_url },
      });
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
            <TextField
              label="City"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              error={fieldError("city")}
            />
          </div>
        </fieldset>

        <fieldset className={styles.group}>
          <div className={styles.groupHead}>
            <h2>Seller details</h2>
            <p>Printed on every bill. The company can change them later in its own Settings.</p>
          </div>
          <div className={styles.grid}>
            <TextField
              label="Name on bills"
              value={legalName}
              onChange={(e) => setLegalName(e.target.value)}
              error={fieldError("legal_name")}
              hint="Blank: the company name above."
            />
            <TextField
              label="GSTIN"
              value={gstin}
              maxLength={15}
              onChange={(e) => setGstin(e.target.value.toUpperCase())}
              error={fieldError("registration_no")}
              hint="Blank if not registered yet. The first two digits are the state."
            />
          </div>
        </fieldset>

        <fieldset className={styles.group}>
          <div className={styles.groupHead}>
            <h2>First shop</h2>
            <p>A godown is added too. More shops are added in the company's Settings.</p>
          </div>
          <div className={styles.grid}>
            <TextField
              label="Shop name"
              value={shopName}
              onChange={(e) => setShopName(e.target.value)}
              error={fieldError("shop_name")}
            />
            <TextField
              label="Shop code"
              value={shopCode}
              maxLength={2}
              onChange={(e) => setShopCode(e.target.value.toUpperCase())}
              error={fieldError("shop_code")}
              hint="1 or 2 letters or digits. Printed at the start of every bill number."
            />
          </div>
        </fieldset>

        <fieldset className={styles.group}>
          <div className={styles.groupHead}>
            <h2>Plan</h2>
            <p>What the company can use, and how it starts.</p>
          </div>
          <div className={styles.grid}>
            <SelectField
              label="Plan"
              value={plan}
              onChange={(e) => setPlan(e.target.value)}
              hint={picked ? limitsNote(picked) : undefined}
              error={fieldError("plan")}
            >
              {plans.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.name}
                </option>
              ))}
            </SelectField>
            {plan === TRIAL_PLAN ? (
              <SelectField
                label="Start"
                value={terms}
                onChange={(e) => setTerms(e.target.value as "trial" | "active")}
              >
                <option value="trial">On a trial</option>
                <option value="active">Active, no trial</option>
              </SelectField>
            ) : null}
            {plan === TRIAL_PLAN && terms === "trial" ? (
              <TextField
                label="Trial length (days)"
                inputMode="numeric"
                value={trialDays}
                onChange={(e) => setTrialDays(e.target.value.replace(/\D/g, ""))}
                error={fieldError("trial_days")}
                hint="1 to 90 days."
              />
            ) : null}
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
              label="Email"
              type="email"
              value={ownerEmail}
              onChange={(e) => setOwnerEmail(e.target.value)}
              error={fieldError("owner_email")}
            />
            <TextField
              label="Mobile"
              inputMode="tel"
              value={ownerMobile}
              onChange={(e) => setOwnerMobile(e.target.value)}
              error={fieldError("owner_mobile")}
            />
            <TextField
              label="Password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={fieldError("owner_password")}
              hint={`At least ${MIN_PASSWORD} characters.`}
              required
            />
            <CheckField
              label="Make them choose a new password at first sign-in"
              hint="Off by default: an owner onboarded by Duolink gets a working password."
              checked={mustChange}
              onChange={(e) => setMustChange(e.target.checked)}
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
