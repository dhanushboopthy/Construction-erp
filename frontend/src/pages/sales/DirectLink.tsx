import { useState } from "react";

import { toFormError } from "@/api/errors";
import { useLinkDropShip, useOpenDirectLines } from "@/api/transport";
import { Button } from "@/components/Button";
import { SelectField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";
import { trimDecimal } from "@/lib/format";

/** Owner: tie a direct sale line to the supplier purchase that sent the goods, so profit is known. */
export function DirectLink({ lineId, itemId }: { lineId: number; itemId: number }) {
  const open = useOpenDirectLines(itemId);
  const link = useLinkDropShip();
  const [pick, setPick] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    if (!pick) return setError("Choose the supplier purchase.");
    setError(null);
    try {
      await link.mutateAsync({ sales_line_id: lineId, purchase_line_id: Number(pick) });
    } catch (err) {
      setError(toFormError(err).message);
    }
  }

  return (
    <div className={styles.inline}>
      <SelectField
        label="Supplier purchase for this line"
        value={pick}
        onChange={(e) => setPick(e.target.value)}
      >
        <option value="">Choose</option>
        {(open.data ?? []).map((p) => (
          <option key={p.purchase_line_id} value={p.purchase_line_id}>
            {p.purchase_number} · {p.supplier_name} · {trimDecimal(p.free_qty)} {p.base_unit} free
          </option>
        ))}
      </SelectField>
      <Button onClick={() => void save()} disabled={link.isPending}>
        Link purchase
      </Button>
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
