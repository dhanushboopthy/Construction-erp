import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { openFile } from "@/api/client";
import { toFormError } from "@/api/errors";
import { QUOTE_LABEL, useQuote, useQuotes } from "@/api/quotes";
import type { QuoteKind } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, plural, trimDecimal } from "@/lib/format";

function todayISO(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

/** Quotations (estimates) and proforma invoices. Neither is a tax invoice; each can become one
 * bill, priced again at that day's rates. */
export function QuotesPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const openId = params.get("open") ? Number(params.get("open")) : null;
  const [kind, setKind] = useState<QuoteKind | "">("");
  const [q, setQ] = useState("");
  const list = useQuotes(kind, q);
  const detail = useQuote(openId);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const canBill = user?.role === "owner" || user?.role === "counter";
  const rows = list.data?.items ?? [];
  const quote = detail.data;
  const expired = quote?.valid_until ? quote.valid_until < todayISO() : false;

  async function print(id: number) {
    setPdfError(null);
    try {
      await openFile(`/quotes/${id}/pdf`);
    } catch (err) {
      setPdfError(toFormError(err).message);
    }
  }

  return (
    <section aria-labelledby="quotes-title" className={styles.page}>
      <div className={styles.toolbar}>
        <h1 id="quotes-title" className={styles.title}>
          Quotations and proforma invoices
        </h1>
        {canBill ? (
          <>
            <Button variant="primary" onClick={() => void navigate("/sales/new?doc=quotation")}>
              New quotation
            </Button>
            <Button onClick={() => void navigate("/sales/new?doc=proforma")}>
              New proforma invoice
            </Button>
          </>
        ) : null}
        <Button variant="quiet" onClick={() => void navigate("/sales")}>
          Sales bills
        </Button>
      </div>
      <div className={styles.filters}>
        <SelectField
          label="Show"
          value={kind}
          onChange={(e) => setKind(e.target.value as QuoteKind | "")}
        >
          <option value="">Both</option>
          <option value="quotation">Quotations</option>
          <option value="proforma">Proforma invoices</option>
        </SelectField>
        <div className={styles.search}>
          <TextField
            label="Search"
            type="search"
            placeholder="Number or customer"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>
      <div className={styles.split}>
        <div className={styles.tableWrap}>
          {list.isPending ? (
            <p role="status" className={styles.empty}>
              Loading…
            </p>
          ) : null}
          {list.isSuccess && rows.length === 0 ? (
            <p className={styles.empty}>
              {q || kind ? "Nothing matches." : "No quotations or proforma invoices yet."}
            </p>
          ) : null}
          {rows.length > 0 ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Number</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Date</th>
                  <th scope="col">Customer</th>
                  <th scope="col">Billed as</th>
                  <th scope="col" className="num">
                    Total (₹)
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className={openId === r.id ? styles.selected : ""}>
                    <td>
                      <button
                        type="button"
                        className={styles.rowButton}
                        aria-current={openId === r.id ? "true" : undefined}
                        onClick={() => setParams({ open: String(r.id) })}
                      >
                        {r.number}
                      </button>
                    </td>
                    <td>{QUOTE_LABEL[r.kind]}</td>
                    <td>{r.quote_date}</td>
                    <td>{r.party_name}</td>
                    <td>{r.invoice_number ?? "—"}</td>
                    <td className="num">{formatMoney(r.grand_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {list.isSuccess ? (
            <p className={styles.results}>{plural(list.data.total, "document")}</p>
          ) : null}
        </div>
        {quote ? (
          <aside
            className={styles.panel}
            aria-labelledby="quote-title"
            onKeyDown={(e) => e.key === "Escape" && setParams({})}
          >
            <div className={styles.panelHead}>
              <h2 id="quote-title">{quote.number}</h2>
              <Button variant="quiet" onClick={() => setParams({})}>
                Close
              </Button>
            </div>
            <p className={styles.sub}>
              {QUOTE_LABEL[quote.kind]} · {quote.party_name} · {quote.quote_date}
              {quote.valid_until ? ` · valid until ${quote.valid_until}` : ""}
              {quote.ship_to_name ? ` · deliver to ${quote.ship_to_name}` : ""}
            </p>
            {quote.invoice_number ? (
              <p role="status" className={styles.callout}>
                Billed as{" "}
                <button
                  type="button"
                  className={styles.rowButton}
                  onClick={() => void navigate(`/sales?open=${quote.invoice_id}`)}
                >
                  {quote.invoice_number}
                </button>
                .
              </p>
            ) : expired ? (
              <p role="status" className={styles.callout}>
                Past its valid-until date. It can still be billed at today&apos;s rates.
              </p>
            ) : null}
            <div className={styles.actions}>
              <Button variant="primary" onClick={() => void print(quote.id)}>
                Print
              </Button>
              {canBill && !quote.invoice_id ? (
                <Button onClick={() => void navigate(`/sales/new?quote=${quote.id}`)}>
                  Make the bill
                </Button>
              ) : null}
            </div>
            {pdfError ? (
              <p role="alert" className={styles.formError}>
                {pdfError}
              </p>
            ) : null}
            {quote.lines.map((l) => (
              <span key={l.id} className={styles.kv}>
                <span>
                  {l.description} · {trimDecimal(l.quantity)} {l.unit}
                </span>
                <span>{formatMoney(l.line_total)}</span>
              </span>
            ))}
            <span className={styles.kv}>
              <span>Taxable</span>
              <span>{formatMoney(quote.taxable_value)}</span>
            </span>
            <span className={styles.kv}>
              <span>{quote.supply_kind === "intra_state" ? "CGST + SGST" : "IGST"}</span>
              <span>
                {formatMoney(String(Number(quote.cgst) + Number(quote.sgst) + Number(quote.igst)))}
              </span>
            </span>
            <div className={styles.billTotal}>
              <span>Total</span>
              <strong>₹{formatMoney(quote.grand_total)}</strong>
            </div>
            <p className={styles.sub}>
              Not a tax invoice. Nothing has left stock and the customer owes nothing for it.
            </p>
          </aside>
        ) : null}
      </div>
    </section>
  );
}
