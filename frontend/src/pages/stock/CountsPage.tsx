import { useState } from "react";

import { toFormError } from "@/api/errors";
import {
  useCounts,
  useEnterCounts,
  useOpenCount,
  usePostCount,
  type CountRow,
} from "@/api/purchasing";
import { useLocations } from "@/api/setup";
import type { StockCountOwner } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/Button";
import { SelectField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { formatMoney, trimDecimal } from "@/lib/format";

const isOwnerCount = (c: CountRow): c is StockCountOwner => "total_variance_value" in c;

function CountSheet({ count, canPost }: { count: CountRow; canPost: boolean }) {
  const enter = useEnterCounts();
  const post = usePostCount();
  const [values, setValues] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      count.lines.map((l) => [l.item_id, l.counted_qty ? trimDecimal(l.counted_qty) : ""]),
    ),
  );
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const posted = count.status === "posted";

  const payload = () =>
    count.lines
      .filter((l) => values[l.item_id] !== "")
      .map((l) => ({ item_id: l.item_id, counted_qty: values[l.item_id] ?? null }));

  async function save() {
    const bad = count.lines.find(
      (l) => values[l.item_id] && !/^\d+(\.\d{1,3})?$/.test(values[l.item_id] ?? ""),
    );
    if (bad)
      return setMessage({
        ok: false,
        text: `${bad.item_name}: enter a quantity like 120 or 120.5.`,
      });
    if (payload().length === 0)
      return setMessage({ ok: false, text: "Enter at least one counted quantity." });
    try {
      await enter.mutateAsync({ id: count.id, lines: payload() });
      setMessage({ ok: true, text: "Counts saved." });
    } catch (err) {
      setMessage({ ok: false, text: toFormError(err).message });
    }
  }

  async function onPost() {
    setConfirming(false);
    try {
      await enter.mutateAsync({ id: count.id, lines: payload() });
      await post.mutateAsync(count.id);
      setMessage({ ok: true, text: "Posted. Stock now matches the count." });
    } catch (err) {
      setMessage({ ok: false, text: toFormError(err).message });
    }
  }

  return (
    <div className={styles.stack}>
      <h3 style={{ margin: 0 }}>
        Count of {count.location_code} · {count.count_date} · {posted ? "Posted" : "Draft"}
      </h3>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col" className="num">
                In the books
              </th>
              <th scope="col" className="num">
                Counted
              </th>
              <th scope="col" className="num">
                Difference
              </th>
              {isOwnerCount(count) ? (
                <th scope="col" className="num">
                  Worth (₹)
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {count.lines.map((l) => (
              <tr key={l.item_id}>
                <th scope="row" style={{ fontWeight: 500, color: "inherit" }}>
                  {l.item_name}
                </th>
                <td className="num">
                  {trimDecimal(l.system_qty)} {l.base_unit}
                </td>
                <td className="num">
                  {posted ? (
                    l.counted_qty ? (
                      trimDecimal(l.counted_qty)
                    ) : (
                      "—"
                    )
                  ) : (
                    <input
                      aria-label={`Counted ${l.item_name}`}
                      inputMode="decimal"
                      value={values[l.item_id] ?? ""}
                      onChange={(e) => setValues((v) => ({ ...v, [l.item_id]: e.target.value }))}
                      style={{
                        width: 110,
                        textAlign: "right",
                        padding: "4px 8px",
                        border: "1px solid var(--color-rule-strong)",
                        borderRadius: 4,
                      }}
                    />
                  )}
                </td>
                <td className="num">{l.variance ? trimDecimal(l.variance) : "—"}</td>
                {isOwnerCount(count) && "variance_value" in l ? (
                  <td className="num">{l.variance_value ? formatMoney(l.variance_value) : "—"}</td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {isOwnerCount(count) && posted ? (
        <div className={styles.totalBand}>
          <span>Stock written {Number(count.total_variance_value) < 0 ? "off" : "on"}</span>
          <strong>₹{formatMoney(count.total_variance_value)}</strong>
        </div>
      ) : null}
      {!posted ? (
        <div className={styles.actions}>
          <Button onClick={() => void save()} disabled={enter.isPending}>
            Save counts
          </Button>
          {canPost ? (
            confirming ? (
              <>
                <span>Adjust stock to the counted quantities? This cannot be undone.</span>
                <Button variant="primary" onClick={() => void onPost()}>
                  Yes, post the count
                </Button>
                <Button onClick={() => setConfirming(false)}>Not yet</Button>
              </>
            ) : (
              <Button variant="primary" onClick={() => setConfirming(true)}>
                Post count
              </Button>
            )
          ) : (
            <span className={styles.sub}>The owner posts the count once you have saved it.</span>
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
    </div>
  );
}

/** Physical stock counts: staff enter what is on the shelf, the owner posts the difference. */
export function CountsPage() {
  const { user } = useAuth();
  const list = useCounts();
  const open = useOpenCount();
  const locations = useLocations();
  const [locationId, setLocationId] = useState(
    user?.locations[0] ? String(user.locations[0].id) : "",
  );
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const owner = user?.role === "owner";
  const counts = list.data ?? [];
  const selected = counts.find((c) => c.id === selectedId);

  async function start() {
    if (!locationId) return setError("Pick the shop or godown you are counting.");
    setError(null);
    try {
      const made = await open.mutateAsync({ location_id: Number(locationId) });
      setSelectedId(made.id);
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.stack}>
      <div className={styles.filters}>
        <SelectField
          label="Count which place"
          value={locationId}
          onChange={(e) => setLocationId(e.target.value)}
        >
          <option value="">Choose a place</option>
          {(locations.data ?? [])
            .filter((l) => owner || user?.locations.some((x) => x.id === l.id))
            .map((l) => (
              <option key={l.id} value={l.id}>
                {l.code} {l.name}
              </option>
            ))}
        </SelectField>
        <Button variant="primary" onClick={() => void start()} disabled={open.isPending}>
          Start a count
        </Button>
      </div>
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      {counts.length > 0 ? (
        <ul className={styles.pillRow} aria-label="Counts">
          {counts.map((c) => (
            <li key={c.id}>
              <Button
                variant={c.id === selectedId ? "primary" : "secondary"}
                onClick={() => setSelectedId(c.id)}
              >
                {c.location_code} · {c.count_date} · {c.status === "posted" ? "Posted" : "Draft"}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.empty}>
          No counts yet. Pick a place and start one; each item in it is listed for you to count.
        </p>
      )}
      {selected ? (
        <CountSheet key={`${selected.id}-${selected.status}`} count={selected} canPost={owner} />
      ) : null}
    </div>
  );
}
