import { useState } from "react";

import { toFormError } from "@/api/errors";
import { useCreateWritedown, useNrv, useWritedowns } from "@/api/inventory";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { Metric } from "@/components/Metric";
import { useShops } from "@/hooks/useShops";
import { formatMoney, trimDecimal } from "@/lib/format";
import tiles from "@/pages/reports/PnlPage.module.css";

const rupees = (value: string | null | undefined) =>
  value == null
    ? "—"
    : `${Number(value) < 0 ? "−" : ""}₹${formatMoney(String(Math.abs(Number(value))))}`;

/** Stock against today's market rate (FM6): what is worth less than it cost, and, for the owner,
 * the write-down that books the loss. Quantities never change and no input tax is reversed. */
export function StockValuePage() {
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const report = useNrv();
  const written = useWritedowns();
  const create = useCreateWritedown();
  const { shops } = useShops();
  const [picked, setPicked] = useState<number[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const r = report.data;
  const canWrite = owner && r?.writedown_enabled && shops.length > 0;

  async function writeDown() {
    setError(null);
    setDone(null);
    const shop = shops[0];
    if (!shop || picked.length === 0) return setError("Tick the items to write down.");
    try {
      const saved = await create.mutateAsync({
        location_id: shop.id,
        item_ids: picked,
        note: note.trim() || null,
      });
      setDone(`Written down: ${saved.number}, ${rupees(saved.total)}.`);
      setPicked([]);
      setNote("");
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.stack}>
      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The stock value could not be loaded.
        </p>
      ) : null}
      {r ? (
        <>
          <dl className={tiles.tiles}>
            <Metric
              code="nrv"
              label="Net realisable value"
              value={rupees(r.nrv_loss)}
              tone={Number(r.nrv_loss) > 0 ? "critical" : "good"}
              note={
                Number(r.nrv_loss) > 0
                  ? `Stock worth ${rupees(r.nrv_loss)} less than it cost, at today's market rate.`
                  : "Nothing is worth less than it cost."
              }
            />
            <Metric
              code="holding_gain_loss"
              label="Holding gain or loss"
              value={rupees(r.holding_gain_loss)}
            />
          </dl>
          {!r.writedown_enabled ? (
            <p className={styles.callout}>
              Writing stock down is switched off in Settings. The loss is shown here only.
            </p>
          ) : null}
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-label="Stock against the market">
              <thead>
                <tr>
                  {canWrite ? <th scope="col">Write down</th> : null}
                  <th scope="col">Item</th>
                  <th scope="col" className="num">
                    On hand
                  </th>
                  <th scope="col" className="num">
                    Cost
                  </th>
                  <th scope="col" className="num">
                    Market rate
                  </th>
                  <th scope="col" className="num">
                    Worth
                  </th>
                  <th scope="col" className="num">
                    Loss
                  </th>
                  <th scope="col" className="num">
                    Buy again at
                  </th>
                  <th scope="col" className="num">
                    Gain or loss
                  </th>
                </tr>
              </thead>
              <tbody>
                {r.rows.map((x) => (
                  <tr key={x.item_id}>
                    {canWrite ? (
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Write down ${x.item_name}`}
                          disabled={Number(x.nrv_loss) <= 0}
                          checked={picked.includes(x.item_id)}
                          onChange={(e) =>
                            setPicked((p) =>
                              e.target.checked
                                ? [...p, x.item_id]
                                : p.filter((id) => id !== x.item_id),
                            )
                          }
                        />
                      </td>
                    ) : null}
                    <th scope="row">{x.item_name}</th>
                    <td className="num">
                      {trimDecimal(x.on_hand)} {x.base_unit}
                    </td>
                    <td className="num">₹{trimDecimal(x.avg_cost)}</td>
                    <td className="num">
                      {x.market_rate ? `₹${trimDecimal(x.market_rate)}` : "No rate"}
                    </td>
                    <td className="num">{x.nrv ? `₹${trimDecimal(x.nrv)}` : "—"}</td>
                    <td className="num">{rupees(x.nrv_loss)}</td>
                    <td className="num">
                      {x.replacement_cost ? `₹${trimDecimal(x.replacement_cost)}` : "—"}
                    </td>
                    <td className="num">{rupees(x.holding_gain_loss)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={styles.note}>
            Worth is today&apos;s market rate less the cost of selling (Settings). It is never above
            cost: stock is not written up.
          </p>
          {canWrite ? (
            <form
              className={styles.panel}
              aria-label="Write stock down"
              onSubmit={(e) => {
                e.preventDefault();
                void writeDown();
              }}
            >
              <h2 style={{ margin: 0 }}>Write down to market value</h2>
              <p className={styles.note}>
                Lowers the cost of the ticked items to what they are worth now and books the loss in
                this month&apos;s net profit. No stock moves and no GST is reversed; the accountant
                should confirm this treatment.
              </p>
              <TextField label="Note" value={note} onChange={(e) => setNote(e.target.value)} />
              {error ? (
                <p role="alert" className={styles.formError}>
                  {error}
                </p>
              ) : null}
              {done ? <p role="status">{done}</p> : null}
              <div className={styles.inline}>
                <Button type="submit" disabled={create.isPending}>
                  Write down ticked items
                </Button>
              </div>
            </form>
          ) : null}
        </>
      ) : null}

      {written.data && written.data.length > 0 ? (
        <div className={styles.tableWrap}>
          <table className={styles.table} aria-label="Write-downs">
            <thead>
              <tr>
                <th scope="col">Number</th>
                <th scope="col">Date</th>
                <th scope="col">Items</th>
                <th scope="col" className="num">
                  Written off
                </th>
              </tr>
            </thead>
            <tbody>
              {written.data.map((w) => (
                <tr key={w.id}>
                  <th scope="row">{w.number}</th>
                  <td>{w.writedown_date}</td>
                  <td>{w.lines.map((l) => l.item_name).join(", ")}</td>
                  <td className="num">{rupees(w.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
