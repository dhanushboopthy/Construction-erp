"""Unit tests for app.domain. No database needed: `uv run pytest tests/unit`."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.domain import compliance, credit, fiscal, gst, landed_cost, pricing, stock_valuation
from app.domain.money import money, round_off, to_decimal
from app.domain.units import UnitConversion, from_base, to_base
from app.domain.weight_check import check_weight


class TestMoney:
    def test_rejects_float(self):
        with pytest.raises(TypeError):
            to_decimal(0.1)  # type: ignore[arg-type]

    def test_half_up(self):
        assert money("2.345") == D("2.35")

    def test_round_off(self):
        assert round_off("1180.49") == (D("1180.00"), D("-0.49"))
        assert round_off("1180.50") == (D("1181.00"), D("0.50"))


class TestFiscal:
    def test_fy_label(self):
        assert fiscal.fy_label(date(2026, 10, 9)) == "26-27"
        assert fiscal.fy_label(date(2027, 3, 31)) == "26-27"
        assert fiscal.fy_label(date(2027, 4, 1)) == "27-28"

    def test_bounds(self):
        assert fiscal.fy_bounds(date(2026, 10, 9)) == (date(2026, 4, 1), date(2027, 3, 31))

    def test_number_format_and_limit(self):
        assert fiscal.format_doc_number("S1", "26-27", 42) == "S1/26-27/00042"
        assert len(fiscal.format_doc_number("S1DC", "26-27", 99999)) == 16
        with pytest.raises(ValueError, match="16"):
            fiscal.format_doc_number("S1DC", "26-27", 100000)


class TestGst:
    def test_gstin_checksum(self):
        assert gst.is_valid_gstin("27AAPFU0939F1ZV")
        assert not gst.is_valid_gstin("27AAPFU0939F1ZA")

    def test_intra_state_split_is_even(self):
        tax = gst.line_tax(D("1000.00"), D("18"), gst.SupplyKind.INTRA_STATE)
        assert (tax.cgst, tax.sgst, tax.igst) == (D("90.00"), D("90.00"), D("0"))

    def test_inter_state(self):
        kind = gst.supply_kind("33", gst.place_of_supply("33", ship_to_state="29"))
        tax = gst.line_tax(D("1000.00"), D("18"), kind)
        assert kind is gst.SupplyKind.INTER_STATE and tax.igst == D("180.00")

    def test_invoice_totals_round_off(self):
        lines = [gst.line_tax(D("333.33"), D("18"), gst.SupplyKind.INTRA_STATE)]
        totals = gst.invoice_totals(lines)
        assert totals.before_round_off == D("393.33")
        assert totals.grand_total == D("393.00") and totals.round_off == D("-0.33")

    def test_taxable_from_inclusive(self):
        assert gst.taxable_from_inclusive("118", "18") == D("100.00")


class TestUnits:
    def test_ton_to_kg(self):
        assert to_base("1.5", UnitConversion("ton", D("1000"))) == D("1500.000")
        assert from_base("2500", UnitConversion("ton", D("1000"))) == D("2.500")

    def test_bags_whole_only(self):
        with pytest.raises(ValueError, match="whole"):
            to_base("2.5", UnitConversion("bag", D("1"), whole_only=True))


class TestLandedCost:
    def _line(self, received=D("10000")):
        return landed_cost.PurchaseLine(
            billed_qty=D("10000"),  # kg
            received_qty=received,
            rate=D("55.00"),  # per kg, excl. GST
            gst_rate=D("18"),
            received_weight_tons=received / 1000,
            charges=[
                landed_cost.Charge("Unloading", landed_cost.ChargeBasis.PER_TON, D("250")),
                landed_cost.Charge("Weighbridge", landed_cost.ChargeBasis.FLAT, D("150")),
                landed_cost.Charge("Transport", landed_cost.ChargeBasis.PER_TRIP, D("4000")),
            ],
        )

    def test_gst_excluded_by_default(self):
        result = landed_cost.landed_cost(self._line())
        assert result.goods_value == D("550000.00")
        assert result.charges_total == D("6650.00")  # 2500 + 150 + 4000
        assert result.total_cost == D("556650.00")
        assert result.unit_cost == D("55.6650")

    def test_gst_included_when_configured(self):
        result = landed_cost.landed_cost(self._line(), include_gst_in_cost=True)
        assert result.total_cost == D("655650.00")

    def test_shortage_raises_unit_cost(self):
        short = landed_cost.landed_cost(self._line(received=D("9900")))
        assert short.unit_cost > D("55.6650")


class TestStockValuation:
    def test_weighted_average(self):
        pos = stock_valuation.receive(stock_valuation.EMPTY, "100", "50")
        pos = stock_valuation.receive(pos, "100", "60")
        assert pos == stock_valuation.StockPosition(D("200.000"), D("55.0000"))

    def test_issue_keeps_average_and_blocks_negative(self):
        pos = stock_valuation.receive(stock_valuation.EMPTY, "10", "50")
        assert stock_valuation.issue(pos, "4").avg_cost == D("50.0000")
        with pytest.raises(stock_valuation.NegativeStockError):
            stock_valuation.issue(pos, "11")


class TestPricing:
    def test_customer_rate_wins_then_market(self):
        today = date(2026, 10, 9)
        market = [
            pricing.MarketRate(D("60"), date(2026, 10, 1)),
            pricing.MarketRate(D("62"), today),
        ]
        special = [pricing.CustomerRate(D("58"), date(2026, 9, 1), date(2026, 12, 31))]
        assert pricing.resolve_price(today, special, market) == pricing.ResolvedPrice(
            D("58"), pricing.RateSource.CUSTOMER
        )
        assert pricing.resolve_price(today, [], market).rate == D("62")

    def test_no_rate_blocks(self):
        with pytest.raises(pricing.PriceNotSetError):
            pricing.resolve_price(date(2026, 10, 9), [], [])

    def test_margin_check(self):
        check = pricing.check_margin("55", "55.6650", min_margin="1")
        assert check.below_cost and check.below_min_margin


class TestCredit:
    policy = credit.CreditPolicy(credit_allowed=True, limit=D("10000"), days=7)

    def test_due_date_from_invoice(self):
        assert credit.due_date(date(2026, 10, 1), 7) == date(2026, 10, 8)

    def test_limit_and_overdue(self):
        invoices = [
            credit.OpenInvoice("S1/26-27/00001", date(2026, 9, 20), date(2026, 9, 27), D("8000"))
        ]
        decision = credit.check_credit(self.policy, invoices, D("3000"), today=date(2026, 10, 9))
        assert not decision.allowed
        assert set(decision.violations) == {
            credit.CreditViolation.CREDIT_LIMIT_EXCEEDED,
            credit.CreditViolation.OVERDUE_INVOICES,
        }

    def test_fully_paid_bill_skips_checks(self):
        blocked = credit.CreditPolicy(credit_allowed=False, limit=D("0"), days=0)
        assert credit.check_credit(blocked, [], D("0"), today=date(2026, 10, 9)).allowed


class TestWeightAndCompliance:
    def test_weight_flag(self):
        result = check_weight("10000", "9940", "0.5")
        assert result.variance_pct == D("0.60") and result.flagged
        assert result.shortage_value("55") == D("3300.00")

    def test_eway_threshold(self):
        assert compliance.eway_bill_required("50000.01", True, "50000", "100000")
        assert not compliance.eway_bill_required("90000", False, "50000", "100000")

    def test_cash_receipt_limit(self):
        assert compliance.cash_receipt_blocked("150000", "50000", "200000")
        assert not compliance.cash_receipt_blocked("150000", "49999", "200000")

    def test_return_window(self):
        assert compliance.return_window_open(date(2026, 10, 7), date(2026, 10, 9), 2)
        assert not compliance.return_window_open(date(2026, 10, 6), date(2026, 10, 9), 2)
