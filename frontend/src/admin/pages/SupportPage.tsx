import { useSearchParams } from "react-router";

import { Button } from "@/components/Button";
import { SelectField, TextField } from "@/components/Field";
import ledger from "@/components/Ledger.module.css";
import { PRIORITY, PRIORITY_ORDER, TICKET_STATUS, TICKET_STATUS_ORDER } from "@/support/labels";

import { TICKET_PAGE_SIZE, useAdminTickets, useTenants } from "../api";
import adminStyles from "../Admin.module.css";
import { TicketTable } from "../TicketTable";

/** Every company's tickets in one queue. Any admin, Support included, may work them. */
export function SupportPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const priority = params.get("priority") ?? "";
  const tenantId = params.get("tenant_id") ?? "";
  const assigned = params.get("assigned") ?? "";
  const q = params.get("q") ?? "";
  const page = Math.max(0, Number(params.get("page") ?? 0) || 0);
  const companies = useTenants({ limit: 200 });
  const tickets = useAdminTickets({
    status,
    priority,
    tenant_id: tenantId,
    assigned,
    q,
    offset: page * TICKET_PAGE_SIZE,
  });

  const setFilter = (key: string, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== "page") next.delete("page");
        return next;
      },
      { replace: true },
    );

  const counts = tickets.data?.counts;
  const tiles: { label: string; value: number | undefined; tone?: string }[] = [
    { label: "Open", value: counts?.open },
    { label: "In progress", value: counts?.in_progress },
    { label: "Waiting on company", value: counts?.waiting_on_company },
    { label: "Urgent open", value: counts?.urgent_open, tone: "critical" },
    { label: "Unassigned", value: counts?.unassigned, tone: "warn" },
  ];

  return (
    <section aria-labelledby="support-title" className={ledger.page}>
      <div className={ledger.toolbar}>
        <h1 id="support-title" className={ledger.title}>
          Support
        </h1>
        <p className={ledger.keys}>↑↓ move · Enter open</p>
      </div>

      <dl className={adminStyles.stats} aria-label="Ticket counts">
        {tiles.map((t) => (
          <div key={t.label} className={adminStyles.stat} data-tone={t.value ? t.tone : undefined}>
            <dt>{t.label}</dt>
            <dd className={adminStyles.statValue}>{t.value ?? "—"}</dd>
          </div>
        ))}
      </dl>

      <form className={ledger.filters} role="search" onSubmit={(e) => e.preventDefault()}>
        <div className={ledger.search}>
          <TextField
            label="Search"
            type="search"
            value={q}
            placeholder="Number or subject"
            onChange={(e) => setFilter("q", e.target.value)}
          />
        </div>
        <SelectField
          label="Status"
          value={status}
          onChange={(e) => setFilter("status", e.target.value)}
        >
          <option value="">Any status</option>
          {TICKET_STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {TICKET_STATUS[s].label}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Priority"
          value={priority}
          onChange={(e) => setFilter("priority", e.target.value)}
        >
          <option value="">Any priority</option>
          {PRIORITY_ORDER.map((p) => (
            <option key={p} value={p}>
              {PRIORITY[p].label}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Company"
          value={tenantId}
          onChange={(e) => setFilter("tenant_id", e.target.value)}
        >
          <option value="">Any company</option>
          {(companies.data?.items ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Assigned"
          value={assigned}
          onChange={(e) => setFilter("assigned", e.target.value)}
        >
          <option value="">Anyone</option>
          <option value="me">Assigned to me</option>
          <option value="unassigned">Unassigned</option>
        </SelectField>
      </form>

      {tickets.isPending ? (
        <p role="status">Loading tickets…</p>
      ) : tickets.isError ? (
        <p role="alert" className={ledger.formError}>
          Tickets could not be loaded. Reload the page.
        </p>
      ) : (
        <div className={ledger.tableWrap}>
          <TicketTable
            rows={tickets.data.items}
            empty={params.toString() ? "No ticket matches. Clear the filters." : "No tickets yet."}
          />
          <p className={ledger.results}>
            {tickets.data.total} {tickets.data.total === 1 ? "ticket" : "tickets"}
          </p>
          {tickets.data.total > TICKET_PAGE_SIZE ? (
            <nav aria-label="Pages" className={ledger.actions}>
              <Button disabled={page === 0} onClick={() => setFilter("page", String(page - 1))}>
                Previous
              </Button>
              <Button
                disabled={(page + 1) * TICKET_PAGE_SIZE >= tickets.data.total}
                onClick={() => setFilter("page", String(page + 1))}
              >
                Next
              </Button>
            </nav>
          ) : null}
        </div>
      )}
    </section>
  );
}
