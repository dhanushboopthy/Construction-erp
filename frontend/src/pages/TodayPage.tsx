import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Lightbulb,
  Lock,
  RotateCcw,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState, type CSSProperties } from "react";
import { Link } from "react-router";

import { useStockOverview } from "@/api/ledger";
import { useSegments, useToday } from "@/api/reports";
import { useAuth } from "@/auth/AuthContext";
import { formatMoney } from "@/lib/format";
import { modulesFor } from "@/modules";

import styles from "./TodayPage.module.css";

type Tone = "accent" | "good" | "warn" | "critical";

interface Kpi {
  label: string;
  value: string | null;
  money: boolean;
  tone: Tone;
  badge: { text: string; tone: Tone; icon: LucideIcon } | null;
  to: string | null;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * The owner's "10-second questions" (interview Q25): today's sales and profit, what customers
 * owe, what we owe, and what has run out. Counter staff see their own shop's sales.
 */
export function TodayPage() {
  const { user } = useAuth();
  const role = user?.role ?? "counter";
  const allowed = new Set(modulesFor(role).map((m) => m.path));
  const today = useToday();
  const stock = useStockOverview();
  const t = today.data;

  const outOfStock = (stock.data ?? []).filter((s) => Number(s.quantity) <= 0);
  const returns = t ? Number(t.returns_today) : 0;

  const kpis: Kpi[] = [
    {
      label: "Sales today",
      value: t?.sales_today ?? null,
      money: true,
      tone: "accent",
      badge: t
        ? returns > 0
          ? { text: `Returns ₹${formatMoney(t.returns_today)}`, tone: "warn", icon: RotateCcw }
          : { text: "No returns", tone: "good", icon: TrendingUp }
        : null,
      to: allowed.has("/sales") ? "/sales" : null,
    },
    ...(role === "owner"
      ? [
          {
            label: "Profit today",
            value: t?.profit_today ?? null,
            money: true,
            tone: "good" as const,
            badge: { text: "Owner only", tone: "accent" as const, icon: Lock },
            to: "/reports/profit",
          },
        ]
      : []),
    {
      label: "Customers owe",
      value: t?.customers_owe ?? null,
      money: true,
      tone: "warn",
      badge: { text: "To collect", tone: "accent", icon: ArrowRight },
      to: role !== "counter" ? "/reports/dues" : null,
    },
    ...(role !== "counter"
      ? [
          {
            label: "We owe suppliers",
            value: t?.we_owe ?? null,
            money: true,
            tone: "accent" as const,
            badge: { text: "To pay", tone: "accent" as const, icon: ArrowRight },
            to: "/reports/dues",
          },
        ]
      : []),
    {
      label: "Items in stock",
      value: t ? String(t.items_in_stock) : null,
      money: false,
      tone: outOfStock.length ? "critical" : "good",
      badge: stock.data
        ? outOfStock.length
          ? { text: `${outOfStock.length} out of stock`, tone: "critical", icon: AlertTriangle }
          : { text: "All in stock", tone: "good", icon: CheckCircle2 }
        : null,
      to: "/stock",
    },
  ];

  const date = t
    ? new Date(`${t.as_of}T00:00:00`).toLocaleDateString("en-IN", {
        weekday: "long",
        day: "numeric",
        month: "long",
      })
    : null;

  return (
    <section aria-labelledby="today-title" className={styles.page}>
      <header className={styles.head}>
        <h1 id="today-title" className={styles.title}>
          Today
        </h1>
        {date ? <p className={styles.date}>{date}</p> : null}
      </header>

      {today.isError ? (
        <p role="alert" className={styles.error}>
          Today&apos;s figures could not be loaded. Check the connection, then reload the page.
        </p>
      ) : null}

      <dl className={styles.kpis}>
        {kpis.map((k) => (
          <KpiCard key={k.label} kpi={k} loading={today.isLoading} />
        ))}
      </dl>

      <div className={styles.panels}>
        <StockLevels
          rows={stock.data}
          loading={stock.isLoading}
          failed={stock.isError}
          canPurchase={allowed.has("/purchases")}
        />
        {role !== "counter" ? <SalesChart /> : null}
      </div>
    </section>
  );
}

function KpiCard({ kpi, loading }: { kpi: Kpi; loading: boolean }) {
  const Badge = kpi.badge?.icon;
  return (
    <div className={styles.kpi} data-tone={kpi.tone} data-link={kpi.to ? true : undefined}>
      <dt className={styles.kpiLabel}>
        {kpi.to ? (
          <Link to={kpi.to} className={styles.kpiLink}>
            {kpi.label}
          </Link>
        ) : (
          kpi.label
        )}
      </dt>
      <dd className={styles.kpiValue}>
        {kpi.value === null ? (
          loading ? (
            <span className={styles.skeleton} aria-label="Loading" />
          ) : (
            "—"
          )
        ) : (
          <>
            {kpi.money ? <span className={styles.rupee}>₹</span> : null}
            <span className="num">{kpi.money ? formatMoney(kpi.value) : kpi.value}</span>
          </>
        )}
      </dd>
      {kpi.badge && Badge ? (
        <dd className={styles.badge} data-tone={kpi.badge.tone}>
          <Badge size={13} strokeWidth={2.4} aria-hidden="true" />
          {kpi.badge.text}
        </dd>
      ) : null}
      {kpi.to ? (
        <dd className={styles.kpiArrow} aria-hidden="true">
          <ArrowRight size={16} />
        </dd>
      ) : null}
    </div>
  );
}

interface StockRowLike {
  item_id: number;
  name: string;
  base_unit: string;
  quantity: string;
}

function StockLevels({
  rows,
  loading,
  failed,
  canPurchase,
}: {
  rows: StockRowLike[] | undefined;
  loading: boolean;
  failed: boolean;
  canPurchase: boolean;
}) {
  const { shown, max, out } = useMemo(() => {
    const all = rows ?? [];
    const out = all.filter((r) => Number(r.quantity) <= 0);
    const inStock = all
      .filter((r) => Number(r.quantity) > 0)
      .sort((a, b) => Number(b.quantity) - Number(a.quantity));
    const shown = [...inStock.slice(0, 6 - Math.min(out.length, 2)), ...out.slice(0, 2)];
    const max = Math.max(1, ...inStock.map((r) => Number(r.quantity)));
    return { shown, max, out };
  }, [rows]);

  return (
    <article className={styles.card} aria-labelledby="stock-levels-title">
      <header className={styles.cardHead}>
        <div>
          <h2 id="stock-levels-title">Stock levels</h2>
          <p className={styles.cardSub}>All shops and the godown</p>
        </div>
        <Link to="/stock" className={styles.cardLink}>
          Details <ArrowRight size={14} aria-hidden="true" />
        </Link>
      </header>

      {failed ? <p className={styles.note}>Stock could not be loaded.</p> : null}
      {loading ? (
        <ul className={styles.levels} aria-label="Loading stock">
          {[0, 1, 2, 3].map((i) => (
            <li key={i} className={styles.levelSkeleton} />
          ))}
        </ul>
      ) : null}
      {!loading && !failed && shown.length === 0 ? (
        <p className={styles.note}>
          No stock yet. Post the opening stock or enter a purchase, and levels appear here.
        </p>
      ) : null}

      {shown.length ? (
        <ul className={styles.levels}>
          {shown.map((r, i) => {
            const qty = Number(r.quantity);
            const empty = qty <= 0;
            const pct = empty ? 4 : Math.max(4, Math.round((qty / max) * 100));
            return (
              <li key={r.item_id} className={styles.level} data-empty={empty || undefined}>
                <div className={styles.levelHead}>
                  <span className={styles.levelName}>{r.name}</span>
                  <span className={`${styles.levelQty} num`}>
                    {formatQty(r.quantity)} {r.base_unit}
                  </span>
                </div>
                <div
                  className={styles.track}
                  role="meter"
                  aria-label={`${r.name} stock`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={empty ? 0 : pct}
                  aria-valuetext={empty ? "Out of stock" : `${pct}% of the largest holding`}
                >
                  <span
                    className={styles.fill}
                    style={{ "--pct": `${pct}%`, "--i": i } as CSSProperties}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}

      {!loading && rows?.length ? (
        <div className={styles.tip} data-tone={out.length ? "critical" : "good"}>
          <Lightbulb size={20} strokeWidth={2} aria-hidden="true" />
          <p>
            {out.length ? (
              <>
                <strong>Reorder soon:</strong> {out.map((o) => o.name).join(", ")}{" "}
                {out.length === 1 ? "is" : "are"} out of stock in every shop and the godown.
                {canPurchase ? (
                  <>
                    {" "}
                    <Link to="/purchases/new">Enter a purchase</Link>
                  </>
                ) : null}
              </>
            ) : (
              <>
                <strong>Nothing has run out.</strong> Bars compare each item with the largest
                holding.
              </>
            )}
          </p>
        </div>
      ) : null}
    </article>
  );
}

function SalesChart() {
  const report = useSegments(null);
  const [active, setActive] = useState<number | null>(null);
  const r = report.data;

  const months = useMemo(
    () =>
      (r?.months ?? []).map((m) => {
        const [y, mo] = m.month.split("-");
        return {
          key: m.month,
          label: MONTHS[Number(mo) - 1] ?? m.month,
          year: y,
          total: Number(m.total),
        };
      }),
    [r],
  );
  const thisMonth = new Date().toISOString().slice(0, 7);
  const currentIndex = months.findIndex((m) => m.key === thisMonth);
  const max = Math.max(1, ...months.map((m) => m.total));
  const best = months.reduce<(typeof months)[number] | null>(
    (b, m) => (m.total > (b?.total ?? 0) ? m : b),
    null,
  );
  const cur = currentIndex >= 0 ? months[currentIndex] : undefined;
  const prev = currentIndex > 0 ? months[currentIndex - 1] : undefined;
  const change =
    cur && prev && prev.total > 0 ? ((cur.total - prev.total) / prev.total) * 100 : null;
  const shown = active ?? (currentIndex >= 0 ? currentIndex : null);

  return (
    <article className={`${styles.card} ${styles.chartCard}`} aria-labelledby="sales-chart-title">
      <header className={styles.cardHead}>
        <h2 id="sales-chart-title">
          Sales by month{r ? <span className={styles.fy}> FY {r.financial_year}</span> : null}
        </h2>
        <ul className={styles.legend} aria-label="Legend">
          <li data-series="sales">Sales</li>
          <li data-series="now">This month</li>
        </ul>
      </header>

      {report.isError ? <p className={styles.note}>The sales chart could not be loaded.</p> : null}
      {report.isLoading ? (
        <div className={styles.chartSkeleton} aria-label="Loading chart" />
      ) : null}

      {r ? (
        <>
          <ol className={styles.chart} aria-label="Sales by month, excluding GST">
            {months.map((m, i) => {
              const h = m.total > 0 ? Math.max(6, (m.total / max) * 100) : 2;
              const isNow = i === currentIndex;
              const future = currentIndex >= 0 && i > currentIndex;
              return (
                <li key={m.key} className={styles.col}>
                  <button
                    type="button"
                    className={styles.bar}
                    data-now={isNow || undefined}
                    data-future={future || undefined}
                    data-active={shown === i || undefined}
                    style={{ "--h": `${h}%`, "--i": i } as CSSProperties}
                    aria-label={`${m.label} ${m.year}: ₹${formatMoney(String(m.total))}`}
                    onPointerEnter={() => setActive(i)}
                    onPointerLeave={() => setActive(null)}
                    onFocus={() => setActive(i)}
                    onBlur={() => setActive(null)}
                  >
                    {shown === i ? (
                      <span className={styles.tooltip} aria-hidden="true">
                        ₹{formatMoney(String(m.total))}
                      </span>
                    ) : null}
                  </button>
                  <span className={styles.month} aria-hidden="true">
                    {m.label}
                  </span>
                </li>
              );
            })}
          </ol>

          <dl className={styles.stats}>
            <div>
              <dt>This year</dt>
              <dd>₹{formatMoney(r.total)}</dd>
            </div>
            <div>
              <dt>Best month</dt>
              <dd>{best ? `${best.label} · ₹${formatMoney(String(best.total))}` : "—"}</dd>
            </div>
            <div>
              <dt>vs last month</dt>
              <dd data-tone={change === null ? undefined : change >= 0 ? "good" : "critical"}>
                {change === null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(1)}%`}
              </dd>
            </div>
          </dl>
        </>
      ) : null}
    </article>
  );
}

function formatQty(value: string) {
  const n = Number(value);
  return Number.isInteger(n)
    ? n.toLocaleString("en-IN")
    : n.toLocaleString("en-IN", { maximumFractionDigits: 3 });
}
