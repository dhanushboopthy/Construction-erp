import { useKpiDefinitions } from "@/api/finance";
import styles from "@/components/Ledger.module.css";

const GOOD = {
  up: "Higher is better",
  down: "Lower is better",
  range: "Neither too low nor too high",
  none: "A fact, not a score",
} as const;

/** Every figure in the app, explained in plain words: its name, how it is worked out, what it
 * means and a worked example. Built from the same catalogue as the tooltips (GET
 * /kpis/definitions), so this page and the screens never disagree. */
export function MetricsPage() {
  const defs = useKpiDefinitions();
  return (
    <section aria-labelledby="metrics-title" className={styles.page}>
      <h1 id="metrics-title" className={styles.title}>
        Metrics explained
      </h1>
      <p className={styles.note}>
        What each figure means and how it is worked out, with an example from a shop like yours. The
        plain-words glossary is in{" "}
        <a
          href="https://github.com/dhanushboopthy/Construction-erp/blob/main/docs/GLOSSARY.md"
          target="_blank"
          rel="noreferrer"
        >
          docs/GLOSSARY.md
        </a>
        .
      </p>
      {defs.isError ? (
        <p role="alert" className={styles.formError}>
          The list of metrics could not be loaded.
        </p>
      ) : null}
      <div className={styles.stack}>
        {(defs.data ?? []).map((k) => (
          <article key={k.code} className={styles.panel} aria-labelledby={`metric-${k.code}`}>
            <h2 id={`metric-${k.code}`} style={{ margin: 0 }}>
              {k.name}
            </h2>
            <p style={{ margin: 0 }}>{k.meaning}</p>
            <dl style={{ margin: 0 }}>
              <dt>How it is worked out</dt>
              <dd>{k.formula}</dd>
              <dt>Example</dt>
              <dd>{k.example}</dd>
              <dt>Comes from</dt>
              <dd>{k.sources}</dd>
              <dt>Good is</dt>
              <dd>{GOOD[k.good as keyof typeof GOOD] ?? k.good}</dd>
              <dt>Updated</dt>
              <dd>
                {k.refresh}
                {k.owner_only ? " · owner only" : ""}
              </dd>
            </dl>
          </article>
        ))}
      </div>
    </section>
  );
}
