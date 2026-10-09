import { useState } from "react";

import { downloadFile } from "@/api/client";
import { toFormError } from "@/api/errors";
import { useGstr1, useGstr2b, useGstr3b, useUpload2b } from "@/api/gst";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney } from "@/lib/format";

function thisMonth(): string {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 7);
}

const STATUS = {
  matched: "Matched",
  mismatch: "Amounts differ",
  missing_in_2b: "In our books, not in 2B",
  missing_in_books: "In 2B, not in our books",
} as const;

/** GST return data for the accountant: GSTR-1 tables, GSTR-3B figures, GSTR-2B matching. */
export function GstPage() {
  const [period, setPeriod] = useState(thisMonth);
  const r1 = useGstr1(period);
  const r3 = useGstr3b(period);
  const r2 = useGstr2b(period);
  const upload = useUpload2b(period);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const d = r1.data;

  async function get(format: "json" | "xlsx") {
    setError(null);
    try {
      await downloadFile(
        `/gst/gstr1/export?period=${period}&format=${format}`,
        `GSTR1-${period}.${format}`,
      );
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    setNote(null);
    try {
      await upload.mutateAsync(file);
      setNote(`GSTR-2B file ${file.name} is loaded.`);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <TextField
          label="Month"
          type="month"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
        />
        <Button onClick={() => void get("xlsx")}>Download GSTR-1 Excel</Button>
        <Button onClick={() => void get("json")}>Download GSTR-1 JSON</Button>
      </div>
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      {d && !d.gstin ? (
        <p role="status" className={styles.callout}>
          The shop&apos;s GSTIN is not set. Enter it under Settings before filing.
        </p>
      ) : null}

      <h2 style={{ margin: 0 }}>GSTR-1</h2>
      {d ? (
        <>
          <span className={styles.kv}>
            <span>
              {d.totals.invoices} bills, {d.totals.notes} credit notes
            </span>
            <span>
              Taxable ₹{formatMoney(d.totals.taxable)} · IGST {formatMoney(d.totals.igst)} · CGST{" "}
              {formatMoney(d.totals.cgst)} · SGST {formatMoney(d.totals.sgst)}
            </span>
          </span>
          <Table
            title="B2B bills"
            head={["GSTIN", "Party", "Bill", "Date", "Value", "Taxable", "IGST", "CGST", "SGST"]}
            rows={d.b2b.map((i) => [
              i.ctin ?? "",
              i.party_name,
              i.number,
              i.invoice_date,
              formatMoney(i.value),
              formatMoney(i.taxable),
              formatMoney(i.igst),
              formatMoney(i.cgst),
              formatMoney(i.sgst),
            ])}
            numeric={4}
          />
          <Table
            title="B2C bills above ₹1,00,000 between states (B2CL)"
            head={["Party", "Bill", "Date", "Place of supply", "Value", "Taxable", "IGST"]}
            rows={d.b2cl.map((i) => [
              i.party_name,
              i.number,
              i.invoice_date,
              i.pos,
              formatMoney(i.value),
              formatMoney(i.taxable),
              formatMoney(i.igst),
            ])}
            numeric={4}
          />
          <Table
            title="Other B2C sales (B2CS), net of returns"
            head={["Supply", "Place of supply", "Rate %", "Taxable", "IGST", "CGST", "SGST"]}
            rows={d.b2cs.map((i) => [
              i.supply === "INTRA" ? "Within state" : "Between states",
              i.pos,
              i.rate,
              formatMoney(i.taxable),
              formatMoney(i.igst),
              formatMoney(i.cgst),
              formatMoney(i.sgst),
            ])}
            numeric={3}
          />
          <Table
            title="Credit notes (registered and large unregistered buyers)"
            head={[
              "GSTIN",
              "Party",
              "Note",
              "Date",
              "Against bill",
              "Taxable",
              "IGST",
              "CGST",
              "SGST",
            ]}
            rows={[...d.cdnr, ...d.cdnur].map((n) => [
              n.ctin ?? "",
              n.party_name,
              n.number,
              n.note_date,
              n.invoice_number,
              formatMoney(n.taxable),
              formatMoney(n.igst),
              formatMoney(n.cgst),
              formatMoney(n.sgst),
            ])}
            numeric={5}
          />
          <Table
            title="HSN summary"
            head={["HSN", "Item", "Unit", "Quantity", "Rate %", "Taxable", "IGST", "CGST", "SGST"]}
            rows={d.hsn.map((h) => [
              h.hsn,
              h.description,
              h.uqc,
              h.quantity,
              h.rate,
              formatMoney(h.taxable),
              formatMoney(h.igst),
              formatMoney(h.cgst),
              formatMoney(h.sgst),
            ])}
            numeric={3}
          />
          <Table
            title="Documents issued"
            head={["Kind", "Series", "From", "To", "Issued", "Missing numbers"]}
            rows={d.docs.map((x) => [
              x.nature,
              x.series,
              x.first,
              x.last,
              String(x.count),
              x.gaps.length ? x.gaps.join(", ") : "None",
            ])}
            numeric={4}
          />
        </>
      ) : null}

      <h2 style={{ margin: 0 }}>GSTR-3B</h2>
      {r3.data ? (
        <div className={styles.tableWrap}>
          <table className={styles.table} aria-label="GSTR-3B figures">
            <thead>
              <tr>
                <th scope="col">Row</th>
                <th scope="col" className="num">
                  Taxable (₹)
                </th>
                <th scope="col" className="num">
                  IGST
                </th>
                <th scope="col" className="num">
                  CGST
                </th>
                <th scope="col" className="num">
                  SGST
                </th>
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ["3.1(a) Sales at a GST rate, net of returns", r3.data.outward_taxable],
                  ["4(A) Input tax on purchases (our books)", r3.data.itc_books],
                  ["4(B) Input tax taken back (debit notes)", r3.data.itc_reversed],
                  ...(r3.data.itc_in_2b
                    ? [["Input tax shown in GSTR-2B", r3.data.itc_in_2b] as const]
                    : []),
                  ["Tax to pay (sales tax less net input tax)", r3.data.net_payable],
                ] as const
              ).map(([label, h]) => (
                <tr key={label}>
                  <th scope="row" style={{ fontWeight: 500, color: "inherit" }}>
                    {label}
                  </th>
                  <td className="num">{formatMoney(h.taxable)}</td>
                  <td className="num">{formatMoney(h.igst)}</td>
                  <td className="num">{formatMoney(h.cgst)}</td>
                  <td className="num">{formatMoney(h.sgst)}</td>
                </tr>
              ))}
              <tr>
                <th scope="row" style={{ fontWeight: 500, color: "inherit" }}>
                  3.1(c) Sales at 0%
                </th>
                <td className="num">{formatMoney(r3.data.outward_nil)}</td>
                <td colSpan={3} />
              </tr>
            </tbody>
          </table>
        </div>
      ) : null}

      <h2 style={{ margin: 0 }}>GSTR-2B matching</h2>
      <div className={styles.inline}>
        <label className={styles.sub}>
          Upload GSTR-2B for {period}
          <input
            type="file"
            accept=".json,.csv,application/json,text/csv"
            disabled={upload.isPending}
            onChange={(e) => void onFile(e.target.files?.[0])}
          />
        </label>
      </div>
      {note ? (
        <p role="status" className={styles.saved}>
          {note}
        </p>
      ) : null}
      {r2.data && r2.data.imported_rows === 0 ? (
        <p className={styles.empty}>
          No GSTR-2B file for this month yet. Download it from the GST portal and upload it here.
        </p>
      ) : null}
      {r2.data && r2.data.rows.length > 0 ? (
        <>
          <p className={styles.sub}>
            {r2.data.counts.matched} matched · {r2.data.counts.mismatch} differ ·{" "}
            {r2.data.counts.missing_in_2b} not in 2B · {r2.data.counts.missing_in_books} not in our
            books
          </p>
          <Table
            title="Supplier bills"
            head={["Result", "GSTIN", "Supplier", "Bill", "Books tax", "2B tax", "Difference"]}
            rows={r2.data.rows.map((m) => [
              STATUS[m.status],
              m.gstin,
              m.supplier ?? "",
              m.number,
              m.books_tax ? formatMoney(m.books_tax) : "—",
              m.portal_tax ? formatMoney(m.portal_tax) : "—",
              formatMoney(m.difference_tax),
            ])}
            numeric={4}
          />
        </>
      ) : null}
    </div>
  );
}

function Table({
  title,
  head,
  rows,
  numeric,
}: {
  title: string;
  head: string[];
  rows: string[][];
  numeric: number;
}) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table} aria-label={title}>
        <caption style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600 }}>
          {title}
        </caption>
        <thead>
          <tr>
            {head.map((h, i) => (
              <th key={h} scope="col" className={i >= numeric ? "num" : undefined}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={head.length}>None this month.</td>
            </tr>
          ) : (
            rows.map((r, n) => (
              <tr key={n}>
                {r.map((c, i) => (
                  <td key={i} className={i >= numeric ? "num" : undefined}>
                    {c}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
