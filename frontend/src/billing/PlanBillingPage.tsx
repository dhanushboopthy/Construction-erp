import { useState } from "react";

import { toFormError } from "@/api/errors";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import ledger from "@/components/Ledger.module.css";
import { formatDay, formatMoney, plural } from "@/lib/format";

import { useCreateOrder, useRenewalOverview, useVerifyPayment } from "./api";
import styles from "./Billing.module.css";
import { payWithCheckout } from "./checkout";
import type { RenewalOption, RenewalOverview } from "./types";

const STATUS_WORD: Record<RenewalOverview["status"], string> = {
  trial: "On trial",
  active: "Active",
  expired: "Ended",
  cancelled: "Cancelled",
};

const optionTerm = (o: RenewalOption) => plural(o.duration_value, o.duration_unit);

function PlanSummary({ plan }: { plan: RenewalOverview }) {
  return (
    <dl className={styles.summary}>
      <div>
        <dt>Plan</dt>
        <dd>{plan.plan_name}</dd>
      </div>
      <div>
        <dt>Status</dt>
        <dd data-tone={plan.access_state === "read_only" ? "critical" : undefined}>
          {STATUS_WORD[plan.status]}
          {plan.access_state === "read_only" ? " (read-only)" : ""}
        </dd>
      </div>
      <div>
        <dt>{plan.status === "expired" ? "Ended on" : "Runs until"}</dt>
        <dd>{plan.expires_at ? formatDay(plan.expires_at) : "No end date set"}</dd>
      </div>
    </dl>
  );
}

function Payment({ plan }: { plan: RenewalOverview }) {
  const [chosen, setChosen] = useState<number | null>(plan.options[0]?.price_id ?? null);
  const [message, setMessage] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const createOrder = useCreateOrder();
  const verify = useVerifyPayment();
  const busy = createOrder.isPending || verify.isPending;
  const option = plan.options.find((o) => o.price_id === chosen);

  async function pay() {
    if (!option) return;
    setMessage(null);
    try {
      const order = await createOrder.mutateAsync(option.price_id);
      const answer = await payWithCheckout(order);
      if (!answer) return; // closed without paying
      const done = await verify.mutateAsync(answer);
      setMessage({
        tone: "good",
        text: `Thank you. ${done.plan_name} now runs until ${formatDay(done.expires_at)}, and you can save changes again.`,
      });
    } catch (error) {
      setMessage({ tone: "bad", text: toFormError(error).message });
    }
  }

  return (
    <form
      className={styles.options}
      aria-label="Renew online"
      onSubmit={(event) => {
        event.preventDefault();
        void pay();
      }}
    >
      <fieldset className={styles.fieldset} disabled={busy}>
        <legend className={styles.legend}>Choose how long to renew for</legend>
        {plan.options.map((o) => (
          <label key={o.price_id} className={styles.option} data-chosen={o.price_id === chosen}>
            <input
              type="radio"
              name="price"
              value={o.price_id}
              checked={o.price_id === chosen}
              onChange={() => setChosen(o.price_id)}
            />
            <span className={styles.optionText}>
              <strong>
                {o.plan_name}, {optionTerm(o)}
              </strong>
              <span className={styles.optionSub}>
                Runs until {formatDay(o.would_run_until)}
                {o.is_current_plan ? "" : " · changes your plan"}
              </span>
            </span>
            <span className={styles.price}>₹{formatMoney(o.price)}</span>
          </label>
        ))}
      </fieldset>
      <div className={ledger.actions}>
        <Button type="submit" variant="primary" allowWhenReadOnly disabled={!option || busy}>
          {busy ? "Working…" : option ? `Pay ₹${formatMoney(option.price)} with Razorpay` : "Pay"}
        </Button>
        <span className={ledger.sub}>You pay Duolink on Razorpay&apos;s own secure page.</span>
      </div>
      {message ? (
        <p
          role={message.tone === "bad" ? "alert" : "status"}
          className={message.tone === "bad" ? ledger.formError : styles.thanks}
        >
          {message.text}
        </p>
      ) : null}
    </form>
  );
}

/**
 * Plan & billing. The owner sees the plan and pays online when Duolink has set that up; any
 * other role is told to ask the owner. Open while the company is read-only: that is when it is
 * needed. The server works out every amount; the browser only says which price.
 */
export function PlanBillingPage() {
  const { user } = useAuth();
  const isOwner = user?.role === "owner";
  const overview = useRenewalOverview(isOwner);
  const plan = overview.data;

  return (
    <section aria-labelledby="plan-title" className={ledger.page}>
      <div className={ledger.toolbar}>
        <h1 id="plan-title" className={ledger.title}>
          Plan &amp; billing
        </h1>
      </div>
      {!isOwner ? (
        <p className={ledger.note} role="status">
          Ask your owner to renew the Duolink plan.
        </p>
      ) : overview.isError ? (
        <p role="alert" className={ledger.formError}>
          {toFormError(overview.error).message}
        </p>
      ) : plan ? (
        <div className={styles.panel}>
          <PlanSummary plan={plan} />
          {plan.online_renewal && plan.options.length > 0 ? (
            <Payment plan={plan} />
          ) : (
            <p className={ledger.note} role="status">
              Contact Duolink to renew.
            </p>
          )}
        </div>
      ) : null}
    </section>
  );
}
