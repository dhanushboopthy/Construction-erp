import { useEffect, useState } from "react";

import { downloadFile } from "@/api/client";
import { toFormError } from "@/api/errors";
import { useSaveTallyLedgers, useTallyLedgers, useTallyPreview } from "@/api/tally";
import { useToday } from "@/api/reports";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney } from "@/lib/format";

function monthBounds(asOf: string): { from: string; to: string } {
  const [y, m] = asOf.split("-").map(Number);
  if (!y || !m) return { from: "", to: "" };
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const mm = String(m).padStart(2, "0");
  return { from: `${y}-${mm}-01`, to: `${y}-${mm}-${String(last).padStart(2, "0")}` };
}

/** Tally export (FM4): the day book for a date range as an XML file the accountant imports,
 * checked against GSTR-1, GSTR-3B and the dues reports, plus the ledger names it uses. */
export function TallyPage() {
  const asOf = useToday().data?.as_of ?? "";
  const month = monthBounds(asOf);
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState<string | null>(null);
  const dateFrom = from ?? month.from;
  const dateTo = to ?? month.to;
  const preview = useTallyPreview(dateFrom, dateTo);
  const ledgers = useTallyLedgers();
  const save = useSaveTallyLedgers();
  const [company, setCompany] = useState("");
  const [names, setNames] = useState<Record<string, string>>({});
  const [masters, setMasters] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const p = preview.data;
  const l = ledgers.data;

  useEffect(() => {
    if (!l) return;
    setCompany(l.company);
    setNames(Object.fromEntries(l.ledgers.map((x) => [x.purpose, x.name])));
  }, [l]);

  async function download() {
    setError(null);
    try {
      await downloadFile(
        `/tally/export?date_from=${dateFrom}&date_to=${dateTo}&masters=${masters}`,
        `tally-${dateFrom}-to-${dateTo}.xml`,
      );
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  async function saveNames() {
    setError(null);
    setSaved(false);
    try {
      await save.mutateAsync({
        company: company.trim() && company !== l?.default_company ? company.trim() : null,
        names,
      });
      setSaved(true);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  const allOk = p ? p.checks.every((c) => c.ok) : false;

  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <TextField
          label="From"
          type="date"
          value={dateFrom}
          onChange={(e) => setFrom(e.target.value)}
        />
        <TextField label="To" type="date" value={dateTo} onChange={(e) => setTo(e.target.value)} />
        <label className={styles.sub}>
          <input type="checkbox" checked={masters} onChange={(e) => setMasters(e.target.checked)} />{" "}
          Include ledger names for Tally to create
        </label>
        <Button onClick={() => void download()} disabled={!p || !allOk || p.voucher_count === 0}>
          Download Tally file
        </Button>
      </div>

      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      {preview.isError ? (
        <p role="alert" className={styles.formError}>
          The export could not be prepared for these dates.
        </p>
      ) : null}

      {p ? (
        <>
          <p className={allOk ? styles.note : styles.callout} role="status">
            {p.voucher_count === 0
              ? "Nothing to export in these dates."
              : allOk
                ? `${p.voucher_count} vouchers for ${p.company}. Every check below agrees, so the file is ready.`
                : "A check below does not agree with the books, so the file cannot be downloaded. Run the integrity check under System and tell your accountant."}
          </p>
          {p.note ? <p className={styles.note}>{p.note}</p> : null}

          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Vouchers in the file">
              <thead>
                <tr>
                  <th scope="col">Voucher type</th>
                  <th scope="col" className="num">
                    Count
                  </th>
                  <th scope="col" className="num">
                    Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {p.kinds.map((k) => (
                  <tr key={k.kind}>
                    <th scope="row">{k.kind}</th>
                    <td className="num">{k.count}</td>
                    <td className="num">₹{formatMoney(k.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Checks against the books">
              <thead>
                <tr>
                  <th scope="col">Check</th>
                  <th scope="col" className="num">
                    In the file
                  </th>
                  <th scope="col" className="num">
                    In the report
                  </th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {p.checks.map((c) => (
                  <tr key={c.code}>
                    <th scope="row">{c.label}</th>
                    <td className="num">₹{formatMoney(c.vouchers)}</td>
                    <td className="num">₹{formatMoney(c.report)}</td>
                    <td>{c.ok ? "Agrees" : "Differs"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      <h2 style={{ margin: 0 }}>Ledger names in Tally</h2>
      <p className={styles.note}>
        The export posts to these ledgers. Use the names already in your Tally company; the defaults
        are only a starting point. Your accountant should confirm them before the first import.
      </p>
      {l ? (
        <form
          className={styles.panel}
          onSubmit={(e) => {
            e.preventDefault();
            void saveNames();
          }}
        >
          <TextField
            label="Tally company name"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
          {l.ledgers.map((x) => (
            <TextField
              key={x.purpose}
              label={x.label}
              value={names[x.purpose] ?? ""}
              onChange={(e) => setNames((n) => ({ ...n, [x.purpose]: e.target.value }))}
            />
          ))}
          <div className={styles.inline}>
            <Button type="submit" disabled={save.isPending}>
              Save ledger names
            </Button>
            {saved ? <span role="status">Saved.</span> : null}
          </div>
        </form>
      ) : null}
    </div>
  );
}
