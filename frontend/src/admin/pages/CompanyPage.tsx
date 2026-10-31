import { Link, useLocation, useParams, useSearchParams } from "react-router";

import styles from "@/components/Ledger.module.css";

import { useTenant } from "../api";
import adminStyles from "../Admin.module.css";
import { useAdminAuth } from "../AdminAuthContext";
import { Badge } from "../Badge";
import { COMPANY_TABS } from "../companyTabs";
import { STATUS, TRIAL, companyAddress } from "../labels";

/** One company on one page, with tabs (the list is in companyTabs.tsx). */
export function CompanyPage() {
  const id = Number(useParams().id);
  const location = useLocation();
  const [params] = useSearchParams();
  const { isSuperAdmin } = useAdminAuth();
  const tenant = useTenant(id);
  const created = (location.state as { signInUrl?: string; created?: boolean } | null) ?? null;

  if (tenant.isPending) return <p role="status">Loading the company…</p>;
  if (tenant.isError) {
    return (
      <p className={styles.formError}>
        This company could not be loaded. <Link to="/admin/companies">Back to companies</Link>
      </p>
    );
  }
  const t = tenant.data;
  const trial = TRIAL[t.trial_state];
  const address = created?.signInUrl ?? companyAddress(t.slug);
  const tabs = COMPANY_TABS.filter((tab) => isSuperAdmin || !tab.superAdminOnly);
  const active = tabs.find((tab) => tab.key === params.get("tab")) ?? tabs[0];

  return (
    <section aria-labelledby="company-title" className={styles.page}>
      <p>
        <Link to="/admin/companies">Companies</Link>
      </p>
      <div className={adminStyles.heading}>
        <h1 id="company-title" className={styles.title}>
          {t.name}
        </h1>
        <Badge tone={STATUS[t.status].tone}>{STATUS[t.status].label}</Badge>
        {trial && t.status === "trial" ? <Badge tone={trial.tone}>{trial.label}</Badge> : null}
        <a className={adminStyles.address} href={address} target="_blank" rel="noreferrer">
          {address.replace(/^https?:\/\//, "")}
        </a>
      </div>
      {created?.created ? (
        <p role="status" className={styles.saved}>
          Company created. Its owner can sign in at {address} now.
        </p>
      ) : null}

      <nav aria-label="Company sections">
        <ul className={styles.tabs}>
          {tabs.map((tab) => (
            <li key={tab.key}>
              <Link
                to={`/admin/companies/${t.id}?tab=${tab.key}`}
                replace
                state={created}
                className={tab.key === active?.key ? styles.tabActive : styles.tab}
                aria-current={tab.key === active?.key ? "page" : undefined}
              >
                {tab.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      {active?.render(t)}
    </section>
  );
}
