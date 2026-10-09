import { useRef, useState } from "react";

import { openFile } from "@/api/client";
import { useAttachments, useUploadAttachment } from "@/api/documents";
import { toFormError } from "@/api/errors";
import type { AttachmentKind, AttachmentRef } from "@/api/types";
import { Button } from "./Button";
import { SelectField } from "./Field";
import styles from "./Ledger.module.css";

const KIND_LABEL: Record<AttachmentKind, string> = {
  weighbridge: "Weighbridge slip",
  delivery: "Delivery proof",
  other: "Other paper",
};

/** Photos and PDFs kept with a document. Files are never deleted; a wrong one is explained by a
 * newer one. `canAdd` is false for people who may look but not upload. */
export function Attachments({
  refType,
  refId,
  canAdd,
}: {
  refType: AttachmentRef;
  refId: number;
  canAdd: boolean;
}) {
  const list = useAttachments(refType, refId);
  const upload = useUploadAttachment(refType, refId);
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<AttachmentKind>("weighbridge");
  const [error, setError] = useState<string | null>(null);

  async function onPick(file: File | undefined) {
    if (!file) return;
    setError(null);
    try {
      await upload.mutateAsync({ file, kind, note: "" });
    } catch (err) {
      setError(toFormError(err).message);
    } finally {
      if (input.current) input.current.value = "";
    }
  }

  const rows = list.data ?? [];
  return (
    <div className={styles.stack} role="group" aria-label="Papers">
      <h3 style={{ margin: 0 }}>Papers</h3>
      {list.isSuccess && rows.length === 0 ? (
        <p className={styles.sub}>No slips or delivery proof added yet.</p>
      ) : null}
      {rows.map((a) => (
        <span key={a.id} className={styles.kv}>
          <span>
            {KIND_LABEL[a.kind]} · {a.file_name}
          </span>
          <Button variant="quiet" onClick={() => void openFile(`/attachments/${a.id}/file`)}>
            Open {a.file_name}
          </Button>
        </span>
      ))}
      {canAdd ? (
        <div className={styles.inline}>
          <SelectField
            label="Kind of paper"
            value={kind}
            onChange={(e) => setKind(e.target.value as AttachmentKind)}
          >
            {(Object.keys(KIND_LABEL) as AttachmentKind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </SelectField>
          <label className={styles.sub}>
            Add photo or PDF
            <input
              ref={input}
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              capture="environment"
              disabled={upload.isPending}
              onChange={(e) => void onPick(e.target.files?.[0])}
            />
          </label>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
