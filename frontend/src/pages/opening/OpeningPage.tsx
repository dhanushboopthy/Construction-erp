import { useState } from "react";

import { toFormError } from "@/api/errors";
import { useDeleteOpening, useOpening, usePostOpening } from "@/api/ledger";
import type { OpeningKind, OpeningRow } from "@/api/types";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, plural, trimDecimal } from "@/lib/format";

import { BalanceEntry } from "./BalanceEntry";
import { StockEntry } from "./StockEntry";

type Step = "stock" | "customers" | "suppliers";

const STEPS: { id: Step; label: string; kinds: OpeningKind[]; help: string }[] = [
  {
    id: "stock",
    label: "1. Stock on hand",
    kinds: ["stock"],
    help: "Count each item at each shop and the godown on the day you start. Cost is what you paid per unit; use your last purchase rate if unsure.",
  },
  {
    id: "customers",
    label: "2. Customers owe us",
    kinds: ["receivable", "customer_advance"],
    help: "Unpaid bills from the paper books, per customer and site. Money a customer paid in advance goes in as an advance.",
  },
  {
    id: "suppliers",
    label: "3. We owe suppliers",
    kinds: ["payable", "supplier_advance"],
    help: "What you still owe each supplier, and advances you have paid that are not used up yet.",
  },
];

const KIND_LABEL: Record<OpeningKind, string> = {
  stock: "Stock",
  receivable: "Customer owes",
  customer_advance: "Customer advance",
  payable: "We owe",
  supplier_advance: "Our advance with supplier",
};

function todayISO(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function OpeningPage() {
  const query = useOpening();
  const remove = useDeleteOpening();
  const post = usePostOpening();
  const [step, setStep] = useState<Step>("stock");
  const [asOf, setAsOf] = useState(todayISO());
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const current = STEPS.find((s) => s.id === step);
  const kinds = current?.kinds ?? [];
  const rows = (query.data ?? []).filter((r) => kinds.includes(r.kind));
  const drafts = rows.filter((r) => r.status === "draft");
  const draftTotal = drafts
    .filter((r) => r.amount !== null)
    .reduce((sum, r) => sum + Math.round(Number(r.amount) * 100), 0);

  async function onPost() {
    setConfirming(false);
    try {
      const result = await post.mutateAsync(kinds);
      setMessage({
        ok: true,
        text: `Posted ${plural(result.posted, "entry", "entries")} to the ledger.`,
      });
    } catch (err) {
      setMessage({ ok: false, text: toFormError(err).message });
    }
  }

  return (
    <section aria-labelledby="opening-title" className={styles.stack}>
      <div className={styles.toolbar}>
        <h2 id="opening-title">Opening balances</h2>
        <p className={styles.keys}>Enter adds the row · Tab moves between boxes</p>
      </div>
      <p className={styles.sub}>
        Fill these in once, on the day you stop using paper. Entries stay as drafts you can edit or
        remove until you post them. Once posted they are part of the ledger and cannot be changed.
      </p>
      <ol className={styles.steps} aria-label="Steps">
        {STEPS.map((s) => (
          <li key={s.id}>
            <button
              type="button"
              className={s.id === step ? styles.stepActive : styles.step}
              aria-current={s.id === step ? "step" : undefined}
              onClick={() => {
                setStep(s.id);
                setMessage(null);
                setConfirming(false);
              }}
            >
              {s.label}
            </button>
          </li>
        ))}
      </ol>
      <p className={styles.sub}>{current?.help}</p>
      <div style={{ maxWidth: 240 }}>
        <TextField
          label="Opening date"
          type="date"
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
          hint="The day these figures are true. New rows use it."
        />
      </div>

      {step === "stock" ? <StockEntry asOf={asOf} /> : <BalanceEntry asOf={asOf} step={step} />}

      {query.isPending ? <p role="status">Loading…</p> : null}
      {rows.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Entry</th>
                <th scope="col">For</th>
                <th scope="col">Where</th>
                <th scope="col" className="num">
                  Quantity
                </th>
                <th scope="col" className="num">
                  Cost per unit (₹)
                </th>
                <th scope="col" className="num">
                  Amount (₹)
                </th>
                <th scope="col">Date</th>
                <th scope="col">Status</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: OpeningRow) => (
                <tr key={r.id}>
                  <td>{KIND_LABEL[r.kind]}</td>
                  <td>{r.item_name ?? r.party_name}</td>
                  <td>{r.location_code ?? r.site_name ?? "—"}</td>
                  <td className="num">
                    {r.quantity ? `${trimDecimal(r.quantity)} ${r.base_unit ?? ""}` : "—"}
                  </td>
                  <td className="num">{r.unit_cost ? trimDecimal(r.unit_cost) : "—"}</td>
                  <td className="num">{r.amount ? formatMoney(r.amount) : "—"}</td>
                  <td>{r.as_of}</td>
                  <td className={styles.status}>
                    <span
                      className={
                        r.status === "posted" ? styles.statusActive : styles.statusInactive
                      }
                    >
                      {r.status === "posted" ? "Posted" : "Draft"}
                    </span>
                  </td>
                  <td>
                    {r.status === "draft" ? (
                      <Button
                        variant="quiet"
                        aria-label={`Remove ${r.item_name ?? r.party_name ?? "entry"}`}
                        onClick={() => void remove.mutateAsync(r.id)}
                      >
                        Remove
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className={styles.empty}>Nothing entered for this step yet.</p>
      )}

      {drafts.length > 0 ? (
        <div className={styles.totalBand}>
          <span>
            {plural(drafts.length, "draft")} waiting
            {draftTotal > 0 ? `, ₹${formatMoney((draftTotal / 100).toFixed(2))} in all` : ""}
          </span>
          {confirming ? (
            <span className={styles.actions}>
              <span>Post to the ledger? This cannot be undone.</span>
              <Button variant="primary" onClick={() => void onPost()} disabled={post.isPending}>
                Yes, post {plural(drafts.length, "entry", "entries")}
              </Button>
              <Button onClick={() => setConfirming(false)}>Not yet</Button>
            </span>
          ) : (
            <Button variant="primary" onClick={() => setConfirming(true)}>
              Post {plural(drafts.length, "entry", "entries")}
            </Button>
          )}
        </div>
      ) : null}
      {message ? (
        <p
          role={message.ok ? "status" : "alert"}
          className={message.ok ? styles.saved : styles.formError}
        >
          {message.text}
        </p>
      ) : null}
    </section>
  );
}
