"""Numbers stay gapless and stock never oversells when several bills are saved at once."""

import threading
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.clock import today_ist
from app.domain.gst import SupplyKind  # noqa: F401 - registers nothing; keeps imports honest
from app.models.enums import StockRef
from app.models.masters import Item, Party
from app.models.rates import MarketRate
from app.models.sales import SalesInvoice
from app.models.setup import Location
from app.schemas.sales import InvoiceCreate, InvoiceLineIn
from app.scripts.seed import seed
from app.services import ledgers, sales

pytestmark = pytest.mark.integration


def _reset(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE sales_line, sales_invoice, stock_ledger, party_ledger, "
                "market_rate, item_unit, item, party, document_sequence, "
                "opening_balance, audit_log, auth_session, user_location, app_user, "
                "cost_component, shop_settings, location RESTART IDENTITY CASCADE"
            )
        )


def test_concurrent_saves_get_gapless_numbers_and_never_oversell(engine):
    _reset(engine)
    try:
        with Session(engine) as db:
            seed(db, second_shop=True)
            s1 = db.execute(select(Location).where(Location.code == "S1")).scalar_one()
            item = Item(
                tenant_id=1,
                name="Cement",
                category="cement",
                hsn="25232930",
                gst_rate=28,
                base_unit="bag",
                base_whole_only=True,
            )
            customer = db.execute(
                select(Party).where(Party.name == "Walk-in customer")
            ).scalar_one()
            db.add(item)
            db.flush()
            db.add(
                MarketRate(
                    tenant_id=1,
                    item_id=item.id,
                    effective_date=today_ist() - timedelta(days=1),
                    rate=380,
                    entered_unit="bag",
                    entered_rate=380,
                )
            )
            # Exactly 30 bags in stock; 40 bills of 1 bag race for them: 30 may win, 10 must lose.
            ledgers.add_stock_move(
                db,
                item_id=item.id,
                location_id=s1.id,
                entry_date=today_ist() - timedelta(days=5),
                qty_in=30,
                unit_cost=350,
                ref_type=StockRef.OPENING,
                ref_id=None,
            )
            db.commit()
            ids = (s1.id, customer.id, item.id)

        results: list[str] = []
        failures: list[str] = []
        barrier = threading.Barrier(8)

        def worker(n: int) -> None:
            barrier.wait()
            for i in range(5):
                with Session(engine) as session:
                    try:
                        invoice, _ = sales.create(
                            session,
                            InvoiceCreate(
                                location_id=ids[0],
                                party_id=ids[1],
                                lines=[InvoiceLineIn(item_id=ids[2], quantity=1)],
                            ),
                            actor_id=1,
                            is_owner=True,
                            can_access=True,
                            idempotency_key=f"t{n}-{i}",
                        )
                        results.append(invoice.number)
                    except Exception as exc:
                        session.rollback()
                        failures.append(getattr(exc, "code", repr(exc)))

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 30, (len(results), failures[:3])
        assert failures == ["INSUFFICIENT_STOCK"] * 10
        numbers = sorted(int(n.rsplit("/", 1)[1]) for n in results)
        assert numbers == list(range(1, 31)), numbers  # gapless: no skips, no repeats
        with Session(engine) as db:
            assert db.execute(select(SalesInvoice.id)).all().__len__() == 30
            _, left = ledgers.stock_position(db, ids[2], ids[0])
            assert left == 0
    finally:
        _reset(engine)
