"""Edge cases and guard clauses of app.domain, so every branch is covered (target: 100%).

Worked numbers are in the comments; each was calculated by hand.
"""

from datetime import date
from decimal import Decimal as D

import pytest

from app.domain import credit, fiscal, gst, landed_cost, pricing, stock_valuation
from app.domain.money import to_decimal
from app.domain.units import UnitConversion
from app.domain.weight_check import check_weight


class TestMoneyGuards:
    def test_rejects_bool(self):
        with pytest.raises(TypeError, match="bool"):
            to_decimal(True)


class TestFiscalEdges:
    def test_rejects_bad_start_month(self):
        with pytest.raises(ValueError, match="1-12"):
            fiscal.fy_start_year(date(2026, 10, 9), 13)

    def test_calendar_year_label(self):
        # A January-start year has one year in its label: 2026 -> "26".
        assert fiscal.fy_label(date(2026, 10, 9), start_month=1) == "26"

    def test_january_to_march_belongs_to_previous_fy(self):
        assert fiscal.fy_start_year(date(2027, 2, 1)) == 2026

    def test_sequence_and_series_guards(self):
        with pytest.raises(ValueError, match="starts at 1"):
            fiscal.format_doc_number("S1", "26-27", 0)
        with pytest.raises(ValueError, match="uppercase"):
            fiscal.format_doc_number("s1", "26-27", 1)


class TestGstEdges:
    def test_state_code_from_gstin(self):
        assert gst.state_code_of(" 33AAPFU0939F1ZV") == "33"

    def test_counter_pickup_is_intra_state(self):
        # No ship-to: place of supply is the shop's own state, so CGST + SGST.
        pos = gst.place_of_supply("33", None)
        assert gst.supply_kind("33", pos) is gst.SupplyKind.INTRA_STATE

    def test_line_tax_totals(self):
        # 1,000.00 at 18% intra-state: CGST 90.00 + SGST 90.00 = 180.00; total 1,180.00.
        tax = gst.line_tax(D("1000.00"), D("18"), gst.SupplyKind.INTRA_STATE)
        assert tax.tax == D("180.00") and tax.total == D("1180.00")

    def test_odd_paise_split_stays_equal(self):
        # 333.33 x 9% = 29.9997 -> 30.00 each half; CGST always equals SGST.
        tax = gst.line_tax(D("333.33"), D("18"), gst.SupplyKind.INTRA_STATE)
        assert tax.cgst == tax.sgst == D("30.00")

    def test_taxable_value_with_discount(self):
        # 12.5 bags x 380.40 = 4,755.00; less 55.00 discount = 4,700.00.
        assert gst.taxable_value("12.5", "380.40", "55") == D("4700.00")

    def test_discount_cannot_exceed_line(self):
        with pytest.raises(ValueError, match="discount"):
            gst.taxable_value("1", "100", "100.01")

    def test_negative_rate_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            gst.line_tax("100", "-5", gst.SupplyKind.INTER_STATE)


class TestLandedCostEdges:
    def _line(self, **overrides):
        values = {
            "billed_qty": D("100"),  # bags of cement
            "received_qty": D("100"),
            "rate": D("380"),
            "gst_rate": D("28"),
        }
        values.update(overrides)
        return landed_cost.PurchaseLine(**values)

    def test_per_bag_unloading(self):
        # 100 bags x 380 = 38,000.00; unloading 3.00 per bag x 100 = 300.00.
        # Cost 38,300.00 / 100 bags = 383.0000 per bag.
        line = self._line(
            charges=[landed_cost.Charge("Unloading", landed_cost.ChargeBasis.PER_BASE_UNIT, D("3"))]
        )
        result = landed_cost.landed_cost(line)
        assert result.charges_total == D("300.00") and result.unit_cost == D("383.0000")

    def test_negative_charge_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            landed_cost.Charge("Refund", landed_cost.ChargeBasis.FLAT, D("-1"))

    def test_per_ton_needs_weight(self):
        line = self._line(
            charges=[landed_cost.Charge("Unloading", landed_cost.ChargeBasis.PER_TON, D("250"))]
        )
        with pytest.raises(ValueError, match="received weight"):
            landed_cost.landed_cost(line)

    def test_quantities_must_be_positive(self):
        with pytest.raises(ValueError, match="received"):
            landed_cost.landed_cost(self._line(received_qty=D("0")))
        with pytest.raises(ValueError, match="billed"):
            landed_cost.landed_cost(self._line(billed_qty=D("0")))


class TestStockEdges:
    def test_value(self):
        # 200 kg at 55.0000 = 11,000.00.
        assert stock_valuation.StockPosition(D("200"), D("55")).value == D("11000.00")

    def test_receive_guards(self):
        with pytest.raises(ValueError, match="positive"):
            stock_valuation.receive(stock_valuation.EMPTY, "0", "50")
        with pytest.raises(ValueError, match="negative"):
            stock_valuation.receive(stock_valuation.EMPTY, "1", "-1")

    def test_issue_guard(self):
        pos = stock_valuation.receive(stock_valuation.EMPTY, "10", "50")
        with pytest.raises(ValueError, match="positive"):
            stock_valuation.issue(pos, "0")


class TestPricingEdges:
    def test_suggested_price(self):
        # Landed 55.6650/kg + margin 1.25/kg = 56.9150 -> 56.92 (paise, half up).
        assert pricing.suggested_price("55.6650", "1.25") == D("56.92")

    def test_expired_customer_rate_falls_back_to_market(self):
        special = [pricing.CustomerRate(D("58"), date(2026, 9, 1), date(2026, 9, 30))]
        market = [pricing.MarketRate(D("62"), date(2026, 10, 1))]
        resolved = pricing.resolve_price(date(2026, 10, 9), special, market)
        assert resolved == pricing.ResolvedPrice(D("62"), pricing.RateSource.MARKET)

    def test_margin_above_minimum(self):
        # Rate 57 - cost 55.6650 = 1.3350 margin, above the 1.00 minimum.
        check = pricing.check_margin("57", "55.6650", "1")
        assert check.margin_per_unit == D("1.3350")
        assert not check.below_cost and not check.below_min_margin


class TestCreditEdges:
    def test_credit_not_allowed(self):
        policy = credit.CreditPolicy(credit_allowed=False, limit=D("10000"), days=7)
        decision = credit.check_credit(policy, [], D("500"), today=date(2026, 10, 9))
        assert decision.violations == [credit.CreditViolation.CREDIT_NOT_ALLOWED]

    def test_within_limit_and_not_overdue(self):
        # Outstanding 4,000 + new 6,000 = 10,000: equal to the limit is allowed.
        policy = credit.CreditPolicy(credit_allowed=True, limit=D("10000"), days=7)
        invoices = [
            credit.OpenInvoice("S1/26-27/00002", date(2026, 10, 5), date(2026, 10, 12), D("4000"))
        ]
        decision = credit.check_credit(policy, invoices, D("6000"), today=date(2026, 10, 9))
        assert decision.allowed and decision.available == D("6000.00")


class TestUnitAndWeightGuards:
    def test_factor_must_be_positive(self):
        with pytest.raises(ValueError, match="positive"):
            UnitConversion("ton", D("0"))

    def test_weight_guards(self):
        with pytest.raises(ValueError, match="expected"):
            check_weight("0", "10", "0.5")
        with pytest.raises(ValueError, match="negative"):
            check_weight("10", "-1", "0.5")

    def test_excess_is_not_a_shortage(self):
        # 10,050 received against 10,000 billed: +0.50%, not above 0.50%, nothing short.
        result = check_weight("10000", "10050", "0.5")
        assert not result.flagged and result.shortage_value("55") == D("0.00")


class TestUnitConversionBetweenUnits:
    """Milestone 2: bag <-> ton and piece <-> kg conversions."""

    def test_ton_to_kg_and_back(self):
        from app.domain.units import UnitConversion, convert

        ton, kg = UnitConversion("ton", D("1000")), UnitConversion("kg", D("1"))
        # 2.5 ton x 1000 = 2,500 kg; 2,500 kg / 1000 = 2.5 ton.
        assert convert("2.5", ton, kg) == D("2500.000")
        assert convert("2500", kg, ton) == D("2.500")

    def test_cement_bag_to_ton(self):
        from app.domain.units import UnitConversion, convert

        # Cement base unit is the bag; 1 ton = 20 bags of 50 kg. 30 bags = 1.5 ton.
        bag, ton = UnitConversion("bag", D("1"), whole_only=True), UnitConversion("ton", D("20"))
        assert convert("30", bag, ton) == D("1.500")
        # 1.5 ton = 30 bags; 1.51 ton = 30.2 bags, which cannot be sold as a fraction.
        assert convert("1.5", ton, bag) == D("30.000")
        with pytest.raises(ValueError, match="whole"):
            convert("1.51", ton, bag)

    def test_pieces_to_kg_uses_theoretical_weight(self):
        from app.domain.units import pieces_to_kg

        # 12 mm TMT bar, 12 m long, 10.656 kg per piece: 25 pieces = 266.400 kg.
        assert pieces_to_kg("25", "10.656") == D("266.400")
        with pytest.raises(ValueError, match="weight per piece"):
            pieces_to_kg("25", "0")
