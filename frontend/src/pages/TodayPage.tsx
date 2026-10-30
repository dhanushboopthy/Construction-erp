import {
  AlertTriangle,
  ArrowRight,
  Boxes,
  CheckCircle2,
  Clock,
  HandCoins,
  Lightbulb,
  PiggyBank,
  Receipt,
  RotateCcw,
  TrendingUp,
  Truck,
  Wallet,
} from "lucide-react";
import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router";

import { usePendingEway } from "@/api/compliance";
import { useStockOverview } from "@/api/ledger";
import { useReceivables, useWorkingCapital } from "@/api/receivables";
import { useSegments, useToday } from "@/api/reports";
import { useAuth } from "@/auth/AuthContext";
import { KpiCard } from "@/components/KpiCard";
import { PageHeader } from "@/components/PageHeader";
import { formatMoney } from "@/lib/format";
import { modulesFor } from "@/modules";

import { DuesTable } from "./DuesTable";
import styles from "./TodayPage.module.css";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const money = (value: string) => (
  <>
    <span className={styles.rupee}>₹</span>
    <span className="num">{formatMoney(value)}</span>
  </>
);

/**
 * The owner's "10-second questions" (interview Q25): today's sales and profit, what customers
 * owe, what we owe, and what has run out. Counter staff see their own shop's sales and stock
 * only: they are never sent the receivables report or a profit figure.
 */
export function TodayPage() {
  const { user } = useAuth();
  const role = user?.role ?? "counter";
  const allowed = new Set(modulesFor(role).map((m) => m.path));
  const today = useToday();
  const stock = useStockOverview();
  const eway = usePendingEway();
  const receivables = useReceivables(role !== "counter");
  const t = today.data;
  const tied = useWorkingCapital((t?.as_of ?? "").slice(0, 7), {
    trend: false,
    enabled: role === "owner" && Boolean(t),
  });

  const stockRows = stock.data ?? [];
  const outOfStock = stockRows.filter((s) => Number(s.quantity) <= 0);
  const returns = t ? Number(t.returns_today) : 0;
  const rec = receivables.data;
  const loading = (ready: boolean) =>
    !ready && today.isLoading ? <span className={styles.skeleton} aria-label="Loading" /> : "—";

  const cards: ReactNode[] = [
    <KpiCard
      key="net"
      label="Net sales today"
      value={t ? money(t.net_sales_today) : loading(false)}
      icon={Receipt}
      tone="accent"
      href={allowed.has("/sales") ? "/sales" : undefined}
      note={
        t ? (
          returns > 0 ? (
            <span className={styles.kpiNote}>
              <RotateCcw size={14} aria-hidden="true" /> Returns ₹{formatMoney(t.returns_today)}
            </span>
          ) : (
            <span className={styles.kpiNote}>
              <TrendingUp size={14} aria-hidden="true" /> No returns
            </span>
          )
        ) : undefined
      }
    />,
  ];
  if (role === "owner") {
    cards.push(
      <KpiCard
        key="profit"
        label="Profit today"
        value={t ? money(t.profit_today ?? "0.00") : loading(false)}
        icon={TrendingUp}
        tone="good"
        href="/reports/profit"
        note="Owner only"
      />,
    );
  }
  if (role === "counter") {
    cards.push(
      <KpiCard
        key="eway"
        label="Waiting e-way bills"
        value={eway.data ? String(eway.data.length) : eway.isLoading ? loading(false) : "—"}
        icon={Truck}
        tone={eway.data?.length ? "warn" : "good"}
        href={allowed.has("/sales") ? "/sales" : undefined}
        note={eway.data ? (eway.data.length ? "Bills to move" : "None waiting") : undefined}
      />,
    );
  } else {
    const total = rec ? Number(rec.total) : 0;
    cards.push(
      <KpiCard
        key="owe"
        label="Customers owe"
        value={t ? money(t.customers_owe) : loading(false)}
        icon={Wallet}
        tone="warn"
        href="/reports/dues"
        note="To collect"
        progress={
          rec && total > 0
            ? {
                value: Number(rec.overdue),
                max: total,
                label: "Share of what customers owe that is overdue",
              }
            : undefined
        }
      />,
    );
    if (role === "accountant" && rec) {
      cards.push(
        <KpiCard
          key="overdue"
          label="Overdue"
          value={money(rec.overdue)}
          icon={Clock}
          tone={Number(rec.overdue) > 0 ? "critical" : "good"}
          href="/reports/receivables"
          note={Number(rec.overdue) > 0 ? "Past the due date" : "Nothing overdue"}
        />,
      );
    }
    cards.push(
      <KpiCard
        key="weowe"
        label="We owe suppliers"
        value={t ? money(t.we_owe ?? "0.00") : loading(false)}
        icon={HandCoins}
        tone="accent"
        href="/reports/dues"
        note="To pay"
      />,
    );
  }
  if (role === "owner" && tied.data) {
    cards.push(
      <KpiCard
        key="tied"
        label="Cash tied up"
        value={money(tied.data.cash_tied_up)}
        icon={PiggyBank}
        tone="accent"
        href="/reports/working-capital"
        note={
          tied.data.ccc_days == null
            ? "Cycle: not enough data yet"
            : `Cycle ${tied.data.ccc_days} days`
        }
      />,
    );
  }
  cards.push(
    <KpiCard
      key="stock"
      label="Items in stock"
      value={t ? String(t.items_in_stock) : loading(false)}
      icon={Boxes}
      tone={outOfStock.length ? "critical" : "good"}
      href="/stock"
      note={
        stock.data ? (
          outOfStock.length ? (
            <span className={styles.kpiNote}>
              <AlertTriangle size={14} aria-hidden="true" /> {outOfStock.length} out of stock
            </span>
          ) : (
            <span className={styles.kpiNote}>
              <CheckCircle2 size={14} aria-hidden="true" /> All in stock
            </span>
          )
        ) : undefined
      }
      progress={
        stockRows.length > 0
          ? {
              value: outOfStock.length,
              max: stockRows.length,
              label: "Share of items that are out of stock",
            }
          : undefined
      }
    />,
  );

  const date = t
    ? new Date(`${t.as_of}T00:00:00`).toLocaleDateString("en-IN", {
        weekday: "long",
        day: "numeric",
        month: "long",
      })
    : null;
  const shop = user?.locations[0]?.name;

  return (
    <section aria-labelledby="today-title" className={styles.page}>
      <PageHeader
        eyebrow={shop ?? "All shops"}
        title="Today"
        titleId="today-title"
        subtitle={`${date ? `${date}. ` : ""}Sales, dues and stock at a glance.`}
      />

      {today.isError ? (
        <p role="alert" className={styles.error}>
          Today&apos;s figures could not be loaded. Check the connection, then reload the page.
        </p>
      ) : null}

      <div className={styles.kpis}>{cards}</div>

      {role !== "counter" ? <DuesTable /> : null}

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
