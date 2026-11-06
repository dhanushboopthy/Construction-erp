import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { PageHeader } from "@/components/PageHeader";
import { comboFromEvent, keysOf, usedBy, whyNot } from "@/shortcuts/combo";
import { useShortcuts } from "@/shortcuts/ShortcutsContext";

import styles from "./ShortcutsPage.module.css";

const MODIFIER_KEYS = new Set(["Alt", "Shift", "Control", "Meta", "AltGraph"]);

function Keys({ combo }: { combo: string }) {
  return (
    <span className={styles.keys} aria-label={combo.replaceAll("+", " plus ")}>
      {keysOf(combo).map((k, i) => (
        <kbd key={i} className={styles.key}>
          {k}
        </kbd>
      ))}
    </span>
  );
}

/**
 * Every shortcut the user has, and a way to change each one. Press "Change", then the new
 * combination (Alt plus a letter or a digit, optionally with Shift). Nothing is saved until
 * "Save"; "Restore defaults" clears every change. Opens from anywhere with Ctrl+Shift+Alt+1.
 */
export function ShortcutsPage() {
  const { actions, combos: current, saved, loading, save, pause } = useShortcuts();
  // The user's edits so far; null until they change something (then the saved ones are shown).
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [recording, setRecording] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const changes = draft ?? saved;
  const combos = useMemo(() => {
    const all: Record<string, string> = {};
    for (const a of actions) all[a.id] = changes[a.id] ?? a.default;
    return all;
  }, [actions, changes]);
  const dirty = draft !== null && !sameChanges(draft, saved);
  const labelOf = useCallback(
    (id: string) => actions.find((a) => a.id === id)?.label ?? id,
    [actions],
  );

  function setChange(id: string, combo: string | null) {
    const next = Object.fromEntries(Object.entries(changes).filter(([k]) => k !== id));
    const action = actions.find((a) => a.id === id);
    if (combo !== null && combo !== action?.default) next[id] = combo;
    setDraft(next);
    setMessage(null);
  }

  // While a new combination is awaited, the app's own shortcuts are off so pressing, say, Alt+2
  // is recorded instead of leaving the page.
  useEffect(() => {
    if (!recording) return;
    pause(true);
    const onKey = (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.key === "Escape") {
        setRecording(null);
        setProblem(null);
        return;
      }
      if (MODIFIER_KEYS.has(event.key)) return; // still holding the modifiers
      const combo = comboFromEvent(event);
      const bad = combo ? whyNot(combo) : "Use Alt plus a letter or a digit, for example Alt+N";
      if (!combo || bad) {
        setProblem(bad);
        return;
      }
      const owner = usedBy(combos, combo, recording);
      if (owner) {
        setProblem(`${combo} already runs "${labelOf(owner)}". Change that one first.`);
        return;
      }
      setChange(recording, combo);
      setRecording(null);
      setProblem(null);
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      pause(false);
    };
    // setChange reads the latest draft through `changes`, which is why it is listed by value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recording, combos, changes]);

  async function onSave() {
    if (!draft) return;
    setBusy(true);
    setMessage(null);
    try {
      await save(draft);
      setDraft(null);
      setMessage("Saved. These shortcuts now work on every device you sign in on.");
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : "Cannot reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const groups = [...new Set(actions.map((a) => a.group))];

  return (
    <section aria-labelledby="shortcuts-title" className={styles.page}>
      <PageHeader
        titleId="shortcuts-title"
        title="Keyboard shortcuts"
        subtitle="Change the keys that open screens and start new records. They are saved for you only. Press Ctrl + Shift + Alt + 1 anywhere to come back here."
        actions={
          <>
            <Button
              onClick={() => {
                setDraft({});
                setMessage(null);
              }}
              disabled={Object.keys(changes).length === 0 || recording !== null}
            >
              Restore defaults
            </Button>
            <Button
              variant="primary"
              onClick={() => void onSave()}
              disabled={!dirty || busy || recording !== null}
              aria-busy={busy}
            >
              {busy ? "Saving…" : "Save"}
            </Button>
          </>
        }
      />
      <p
        id="shortcuts-status"
        role={problem ? "alert" : "status"}
        className={problem ? styles.error : styles.note}
      >
        {problem ??
          (recording
            ? `Press the new shortcut for "${labelOf(recording)}" (Alt plus a letter or digit). Esc cancels.`
            : message)}
      </p>
      {loading ? <p role="status">Loading your shortcuts…</p> : null}
      {groups.map((group) => (
        <div key={group} className={styles.group}>
          <h2 className={styles.groupTitle}>{group}</h2>
          <ul className={styles.list}>
            {actions
              .filter((a) => a.group === group)
              .map((a) => {
                const now = combos[a.id] ?? a.default;
                const changed = now !== a.default;
                const listening = recording === a.id;
                return (
                  <li key={a.id} className={styles.row} data-changed={changed || undefined}>
                    <span className={styles.what}>
                      <strong>{a.label}</strong>
                      {a.hint ? <span className={styles.hint}>{a.hint}</span> : null}
                    </span>
                    <span className={styles.current}>
                      {listening ? (
                        <span className={styles.listening}>Press a shortcut…</span>
                      ) : (
                        <Keys combo={now} />
                      )}
                      {changed ? (
                        <span className={styles.was}>
                          was <Keys combo={a.default} />
                        </span>
                      ) : null}
                    </span>
                    <span className={styles.buttons}>
                      <Button
                        onClick={() => {
                          setProblem(null);
                          setMessage(null);
                          setRecording(listening ? null : a.id);
                        }}
                        aria-pressed={listening}
                        aria-label={`Change the shortcut for ${a.label}`}
                      >
                        {listening ? "Cancel" : "Change"}
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => setChange(a.id, null)}
                        disabled={!changed || recording !== null}
                        aria-label={`Use the default shortcut for ${a.label}`}
                      >
                        Default
                      </Button>
                    </span>
                  </li>
                );
              })}
          </ul>
        </div>
      ))}
      {Object.keys(current).length === 0 && !loading ? (
        <p className={styles.note}>You have no shortcuts yet.</p>
      ) : null}
    </section>
  );
}

function sameChanges(a: Record<string, string>, b: Record<string, string>): boolean {
  const ak = Object.keys(a);
  return ak.length === Object.keys(b).length && ak.every((k) => a[k] === b[k]);
}
