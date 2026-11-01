import { Link } from "react-router";

import ledger from "@/components/Ledger.module.css";

import { useAdminTickets } from "../../api";
import { TicketTable } from "../../TicketTable";
import type { TenantDetail } from "../../types";

/** This company's tickets, newest activity first. Each opens the thread. */
export function SupportTab({ tenant }: { tenant: TenantDetail }) {
  const tickets = useAdminTickets({ tenant_id: tenant.id });
  if (tickets.isPending) return <p role="status">Loading tickets…</p>;
  if (tickets.isError) {
    return (
      <p role="alert" className={ledger.formError}>
        Tickets could not be loaded.
      </p>
    );
  }
  return (
    <>
      <div className={ledger.tableWrap}>
        <TicketTable
          rows={tickets.data.items}
          showCompany={false}
          empty="This company has not raised a ticket."
        />
        <p className={ledger.results}>
          {tickets.data.total} {tickets.data.total === 1 ? "ticket" : "tickets"}
        </p>
      </div>
      {tickets.data.total > tickets.data.items.length ? (
        <p className={ledger.note}>
          <Link to={`/admin/support?tenant_id=${tenant.id}`}>See all tickets of this company</Link>
        </p>
      ) : null}
    </>
  );
}
