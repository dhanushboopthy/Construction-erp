import { useEffect, useRef, useState, type FormEvent } from "react";

import { toFormError } from "@/api/errors";
import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import styles from "@/components/Ledger.module.css";

import {
  previewBillDesign,
  useBillDesigns,
  useBillDiagnostics,
  useBillRegistry,
  useChangeBillDesign,
  useDeleteBillDesign,
  useRemoveSecondaryLogo,
  useSetSecondaryLogo,
  useUploadBillDesign,
} from "../../api";
import { useAdminAuth } from "../../AdminAuthContext";
import { Badge } from "../../Badge";
import type { BillSlot, BillTemplate, BillUpload, TenantDetail } from "../../types";
import design from "./BillDesignTab.module.css";

const SLOTS: { slot: BillSlot; label: string }[] = [
  { slot: "tax_invoice", label: "Tax invoice" },
  { slot: "proforma", label: "Proforma invoice" },
  { slot: "quotation", label: "Quotation" },
  { slot: "credit_note", label: "Credit note" },
  { slot: "debit_note", label: "Debit note" },
];
const SLOT_LABEL = Object.fromEntries(SLOTS.map((s) => [s.slot, s.label])) as Record<
  BillSlot,
  string
>;
const MAX_HTML_BYTES = 500 * 1024;
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

type Open = { id: number; label: string };

/**
 * A company's own bill designs (M28). One card per kind of document: the design new documents of
 * that kind use, and every version. Uploaded HTML is data, never a template engine: the checks
 * beside the preview say what was removed and which placeholders print blank.
 */
export function BillDesignTab({ tenant }: { tenant: TenantDetail }) {
  const { isSuperAdmin } = useAdminAuth();
  const designs = useBillDesigns(tenant.id);
  const [preview, setPreview] = useState<Open | null>(null);
  const [checking, setChecking] = useState<Open | null>(null);

  if (designs.isPending) return <p role="status">Loading bill designs…</p>;
  if (designs.isError) {
    return (
      <p role="alert" className={styles.formError}>
        Bill designs could not be loaded.
      </p>
    );
  }
  const { templates, secondary_logo: logo } = designs.data;
  return (
    <>
      <div className={design.slots}>
        {SLOTS.map(({ slot, label }) => (
          <SlotCard
            key={slot}
            tenant={tenant}
            label={label}
            versions={templates.filter((t) => t.slot === slot)}
            canChange={isSuperAdmin}
            onPreview={(t) => setPreview({ id: t.id, label: `${label}, version ${t.version}` })}
            onCheck={(t) => setChecking({ id: t.id, label: `${label}, version ${t.version}` })}
          />
        ))}
      </div>
      {preview || checking ? (
        <div className={design.review}>
          {preview ? <Preview tenantId={tenant.id} open={preview} /> : <div />}
          {checking ? <Checks tenantId={tenant.id} open={checking} /> : null}
        </div>
      ) : null}
      {isSuperAdmin ? <Upload tenantId={tenant.id} /> : null}
      <SecondaryLogo
        tenantId={tenant.id}
        present={logo !== null}
        canChange={isSuperAdmin}
        fingerprint={logo?.sha256.slice(0, 10) ?? null}
      />
      <Registry tenantId={tenant.id} />
    </>
  );
}

// ------------------------------------------------------------------ one slot

function SlotCard({
  tenant,
  label,
  versions,
  canChange,
  onPreview,
  onCheck,
}: {
  tenant: TenantDetail;
  label: string;
  versions: BillTemplate[];
  canChange: boolean;
  onPreview: (t: BillTemplate) => void;
  onCheck: (t: BillTemplate) => void;
}) {
  const change = useChangeBillDesign(tenant.id);
  const remove = useDeleteBillDesign(tenant.id);
  const [error, setError] = useState<string | null>(null);
  const active = versions.find((v) => v.is_active);
  const fail = (e: unknown) => setError(toFormError(e).message);
  return (
    <section className={design.slot} aria-label={label}>
      <h2 className={design.slotHead}>{label}</h2>
      <p className={design.inUse}>
        {active
          ? `New documents use ${active.name}, version ${active.version}.`
          : "Built-in layout."}
      </p>
      {versions.length === 0 ? (
        <p className={styles.note}>No design uploaded.</p>
      ) : (
        <ul className={design.versions}>
          {versions.map((v) => (
            <li key={v.id} className={design.version}>
              <span className={design.versionName}>
                {v.name} · v{v.version}
              </span>
              {v.is_active ? <Badge tone="good">In use</Badge> : null}
              {v.used ? <Badge tone="neutral">Printed on bills</Badge> : null}
              <span className={design.versionActions}>
                <Button
                  aria-label={`Preview ${label} version ${v.version}`}
                  onClick={() => onPreview(v)}
                >
                  Preview
                </Button>
                <Button
                  aria-label={`Check ${label} version ${v.version}`}
                  onClick={() => onCheck(v)}
                >
                  Check
                </Button>
                {canChange ? (
                  <>
                    <Button
                      aria-label={`${v.is_active ? "Deactivate" : "Activate"} ${label} version ${v.version}`}
                      disabled={change.isPending}
                      onClick={() => {
                        setError(null);
                        change.mutate(
                          { id: v.id, action: v.is_active ? "deactivate" : "activate" },
                          { onError: fail },
                        );
                      }}
                    >
                      {v.is_active ? "Deactivate" : "Activate"}
                    </Button>
                    {!v.used && !v.is_active ? (
                      <Button
                        aria-label={`Delete ${label} version ${v.version}`}
                        disabled={remove.isPending}
                        onClick={() => {
                          setError(null);
                          remove.mutate(v.id, { onError: fail });
                        }}
                      >
                        Delete
                      </Button>
                    ) : null}
                  </>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
    </section>
  );
}

// ------------------------------------------------------------------ preview and checks

function Preview({ tenantId, open }: { tenantId: number; open: Open }) {
  const [state, setState] = useState<{ url: string | null; failed: boolean }>({
    url: null,
    failed: false,
  });
  useEffect(() => {
    let url: string | null = null;
    let live = true;
    setState({ url: null, failed: false });
    previewBillDesign(tenantId, open.id).then(
      (blob) => {
        if (!live) return;
        url = URL.createObjectURL(blob);
        setState({ url, failed: false });
      },
      () => live && setState({ url: null, failed: true }),
    );
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [tenantId, open.id]);
  return (
    <div className={styles.panel}>
      <h2 className={styles.panelHead}>Preview: {open.label}</h2>
      {state.failed ? (
        <p role="alert" className={styles.formError}>
          The preview could not be drawn.
        </p>
      ) : state.url ? (
        <iframe className={design.frame} src={state.url} title={`Preview of ${open.label}`} />
      ) : (
        <p role="status">Drawing the preview…</p>
      )}
      <p className={styles.note}>Sample figures only, marked as a sample on every page.</p>
    </div>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <>
      <p className={design.checkHead}>{title}</p>
      <ul className={design.checks}>
        {items.map((item) => (
          <li key={item}>
            <code>{item}</code>
          </li>
        ))}
      </ul>
    </>
  );
}

function Checks({ tenantId, open }: { tenantId: number; open: Open }) {
  const report = useBillDiagnostics(tenantId, open.id);
  return (
    <div className={styles.panel}>
      <h2 className={styles.panelHead}>Checks: {open.label}</h2>
      {report.isPending ? <p role="status">Checking…</p> : null}
      {report.isError ? (
        <p role="alert" className={styles.formError}>
          The checks could not be run.
        </p>
      ) : null}
      {report.data ? <Report report={report.data} /> : null}
    </div>
  );
}

function Report({ report }: { report: BillUpload["diagnostics"] }) {
  const clean =
    report.warnings.length === 0 &&
    report.removed.length === 0 &&
    report.missing_fields.length === 0;
  return (
    <>
      <p className={styles.note}>
        {report.item_rows} item {report.item_rows === 1 ? "row" : "rows"}, {report.hsn_rows} HSN{" "}
        {report.hsn_rows === 1 ? "row" : "rows"}. Page size: {report.page_size ?? "A4 (default)"}.
      </p>
      {clean ? <p role="status">Nothing to fix.</p> : null}
      <List title="Missing, required on a GST document" items={report.missing_fields} />
      <List title="Printed blank: not a field" items={report.unknown} />
      <List title="Printed blank: another kind of document" items={report.other_slot} />
      <List title="Printed blank: outside a repeating row" items={report.outside_rows} />
      <List title="Never filled: inside a style" items={report.in_styles} />
      <List title="Images not included in the upload" items={report.missing_images} />
      <List title="Images uploaded but not used" items={report.unused_images} />
      <List title="Removed when the file was uploaded" items={report.removed} />
      <List title="Warnings" items={report.warnings} />
    </>
  );
}

// ------------------------------------------------------------------ upload

function Upload({ tenantId }: { tenantId: number }) {
  const upload = useUploadBillDesign(tenantId);
  const [slot, setSlot] = useState<BillSlot>("tax_invoice");
  const [name, setName] = useState("");
  const [html, setHtml] = useState<File | null>(null);
  const [images, setImages] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<BillUpload | null>(null);
  const htmlInput = useRef<HTMLInputElement>(null);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setDone(null);
    if (!name.trim()) return setError("Give the design a name.");
    if (!html) return setError("Choose the HTML file.");
    if (html.size > MAX_HTML_BYTES) return setError("The HTML file is larger than 500 KB.");
    if (images.some((i) => i.size > MAX_IMAGE_BYTES)) return setError("An image is over 2 MB.");
    setError(null);
    upload.mutate(
      { slot, name: name.trim(), html, images },
      {
        onSuccess: (made) => {
          setDone(made);
          setName("");
          setHtml(null);
          setImages([]);
          if (htmlInput.current) htmlInput.current.value = "";
        },
        onError: (err) => setError(toFormError(err).message),
      },
    );
  };

  return (
    <form className={styles.panel} onSubmit={onSubmit} noValidate>
      <h2 className={styles.panelHead}>Upload a design</h2>
      <p className={styles.note}>
        The HTML is used as written, with placeholders such as <code>{"{{invoice.number}}"}</code>{" "}
        filled in. Scripts and outside links are removed. It becomes the next version of the kind of
        document, and is used only once you activate it.
      </p>
      <div className={design.fileRow}>
        <SelectField
          label="Kind of document"
          value={slot}
          onChange={(e) => setSlot(e.target.value as BillSlot)}
        >
          {SLOTS.map((s) => (
            <option key={s.slot} value={s.slot}>
              {s.label}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Name of the design"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className={design.fileRow}>
        <TextField
          ref={htmlInput}
          label="HTML file"
          type="file"
          accept=".html,.htm,text/html"
          hint="Up to 500 KB."
          onChange={(e) => setHtml(e.target.files?.[0] ?? null)}
        />
        <TextField
          label="Images it uses"
          type="file"
          accept="image/png,image/jpeg"
          multiple
          hint="PNG or JPEG, up to 2 MB each, named as the HTML names them."
          onChange={(e) => setImages(Array.from(e.target.files ?? []))}
        />
      </div>
      {error ? (
        <p role="alert" className={styles.formError}>
          {error}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button variant="primary" type="submit" disabled={upload.isPending}>
          {upload.isPending ? "Uploading…" : "Upload design"}
        </Button>
      </div>
      {done ? (
        <div role="status">
          <p className={styles.saved}>
            Saved as {SLOT_LABEL[done.slot]}, version {done.version}. Not in use until activated.
          </p>
          <Report report={done.diagnostics} />
        </div>
      ) : null}
    </form>
  );
}

// ------------------------------------------------------------------ second logo

function SecondaryLogo({
  tenantId,
  present,
  canChange,
  fingerprint,
}: {
  tenantId: number;
  present: boolean;
  canChange: boolean;
  fingerprint: string | null;
}) {
  const set = useSetSecondaryLogo(tenantId);
  const remove = useRemoveSecondaryLogo(tenantId);
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const busy = set.isPending || remove.isPending;

  const onFile = (file: File | undefined) => {
    if (!file) return;
    if (file.size > MAX_IMAGE_BYTES) {
      setMessage({ text: "The logo is larger than 2 MB.", error: true });
    } else {
      set.mutate(file, {
        onSuccess: () => setMessage({ text: "Second logo saved.", error: false }),
        onError: (e) => setMessage({ text: toFormError(e).message, error: true }),
      });
    }
    if (input.current) input.current.value = "";
  };

  return (
    <div className={styles.panel}>
      <h2 className={styles.panelHead}>Second logo</h2>
      <p className={styles.note}>
        {present ? `Set (${fingerprint}). ` : "None set. "}
        Designs print it where they use <code>{"{{company.secondaryLogo}}"}</code>. Designs that
        bills were already issued with keep the logo they had.
      </p>
      {canChange ? (
        <div className={styles.actions}>
          <input
            ref={input}
            type="file"
            accept="image/png,image/jpeg"
            hidden
            aria-label="Second logo file"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
          <Button disabled={busy} onClick={() => input.current?.click()}>
            Choose second logo
          </Button>
          {present ? (
            <Button
              disabled={busy}
              onClick={() =>
                remove.mutate(undefined, {
                  onSuccess: () => setMessage({ text: "Second logo removed.", error: false }),
                  onError: (e) => setMessage({ text: toFormError(e).message, error: true }),
                })
              }
            >
              Remove second logo
            </Button>
          ) : null}
        </div>
      ) : null}
      {message ? (
        <p
          role={message.error ? "alert" : "status"}
          className={message.error ? styles.formError : styles.saved}
        >
          {message.text}
        </p>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ the field registry

function Registry({ tenantId }: { tenantId: number }) {
  const [shown, setShown] = useState(false);
  const registry = useBillRegistry(tenantId, shown);
  return (
    <details className={`${styles.panel} ${design.registry}`}>
      <summary onClick={() => setShown(true)}>Placeholders a design can use</summary>
      {registry.isPending && shown ? <p role="status">Loading placeholders…</p> : null}
      {registry.data ? (
        <>
          <p className={styles.note}>
            A placeholder with a format: <code>{"{{totals.grandTotal|symbol}}"}</code> (adds ₹) or{" "}
            <code>|upper</code>. The row holding <code>{"{{item.*}}"}</code> repeats per item; a
            section can also sit between <code>{"<!-- items:start -->"}</code> and{" "}
            <code>{"<!-- items:end -->"}</code>. Images:{" "}
            <code>{'<img src="{{company.logo}}">'}</code>.
          </p>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Placeholder</th>
                  <th scope="col">What it prints</th>
                  <th scope="col">Sample</th>
                </tr>
              </thead>
              <tbody>
                {registry.data.fields.map((f) => (
                  <tr key={f.key}>
                    <td className={design.placeholder}>{`{{${f.key}}}`}</td>
                    <td>{f.description}</td>
                    <td>{f.sample}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={styles.note}>
            Required on a tax invoice: {registry.data.required.tax_invoice.join("; ")}.
          </p>
        </>
      ) : null}
    </details>
  );
}
