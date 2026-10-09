import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type Ref,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import styles from "./Field.module.css";

interface Common {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  /** Spec rule this value controls, e.g. "B8". Shown so the owner knows what it changes. */
  rule?: string;
}

function useDescribedBy(hint: ReactNode, error: string | null | undefined) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return { id, hintId, errorId, describedBy };
}

function Frame({
  id,
  label,
  rule,
  hint,
  hintId,
  error,
  errorId,
  children,
}: Common & { id: string; hintId?: string; errorId?: string; children: ReactNode }) {
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
        {rule ? <span className={styles.rule}>Rule {rule}</span> : null}
      </label>
      {children}
      {hint ? (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className={styles.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function TextField({
  label,
  hint,
  error,
  rule,
  className,
  ref,
  ...input
}: Common & InputHTMLAttributes<HTMLInputElement> & { ref?: Ref<HTMLInputElement> }) {
  const { id, hintId, errorId, describedBy } = useDescribedBy(hint, error);
  return (
    <Frame {...{ id, label, rule, hint, hintId, error, errorId }}>
      <input
        ref={ref}
        id={id}
        className={[styles.control, className].filter(Boolean).join(" ")}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...input}
      />
    </Frame>
  );
}

export function SelectField({
  label,
  hint,
  error,
  rule,
  children,
  ...select
}: Common & SelectHTMLAttributes<HTMLSelectElement>) {
  const { id, hintId, errorId, describedBy } = useDescribedBy(hint, error);
  return (
    <Frame {...{ id, label, rule, hint, hintId, error, errorId }}>
      <select
        id={id}
        className={styles.control}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...select}
      >
        {children}
      </select>
    </Frame>
  );
}

export function TextAreaField({
  label,
  hint,
  error,
  rule,
  ...area
}: Common & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { id, hintId, errorId, describedBy } = useDescribedBy(hint, error);
  return (
    <Frame {...{ id, label, rule, hint, hintId, error, errorId }}>
      <textarea
        id={id}
        className={styles.control}
        rows={3}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...area}
      />
    </Frame>
  );
}

/** A checkbox whose label sits beside it; the hint explains what turning it on does. */
export function CheckField({
  label,
  hint,
  rule,
  ...input
}: Omit<Common, "error"> & Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const { id, hintId, describedBy } = useDescribedBy(hint, null);
  return (
    <div className={styles.check}>
      <input id={id} type="checkbox" aria-describedby={describedBy} {...input} />
      <div>
        <label htmlFor={id} className={styles.label}>
          {label}
          {rule ? <span className={styles.rule}>Rule {rule}</span> : null}
        </label>
        {hint ? (
          <p id={hintId} className={styles.hint}>
            {hint}
          </p>
        ) : null}
      </div>
    </div>
  );
}
