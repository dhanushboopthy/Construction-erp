"""A company's bill designs, as the company's own services see them (Milestone 28).

`pin_for` is called when a document is issued: it names the design the document will always
reprint on. Duolink's side (upload, activate, delete, preview) is `services/platform/
bill_templates.py`.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import current_tenant_id
from app.models.bill_templates import BillTemplate
from app.models.enums import BillSlot, QuoteKind
from app.models.returns import CreditNote, DebitNote
from app.models.sales import SalesInvoice, SalesQuote

QUOTE_SLOTS = {QuoteKind.QUOTATION: BillSlot.QUOTATION, QuoteKind.PROFORMA: BillSlot.PROFORMA}


def pin_for(db: Session, slot: BillSlot) -> int | None:
    """The company's active design for the slot, or None for the built-in layout. The company's
    own session sees only its own designs (row-level security, and the filter below)."""
    return db.scalar(
        select(BillTemplate.id).where(
            BillTemplate.tenant_id == current_tenant_id(db),
            BillTemplate.slot == slot,
            BillTemplate.is_active.is_(True),
        )
    )


def used_ids(db: Session) -> set[int]:
    """Designs at least one issued document points at: these are immutable and cannot be
    deleted."""
    tenant_id = current_tenant_id(db)
    found: set[int] = set()
    for model in (SalesInvoice, SalesQuote, CreditNote, DebitNote):
        found.update(
            db.scalars(
                select(model.bill_template_id)
                .where(model.tenant_id == tenant_id, model.bill_template_id.is_not(None))
                .distinct()
            )
        )
    return found
