"""Stock dashboard figures (owner request R5), worked by hand."""

from decimal import Decimal as D

from app.domain.stock_dashboard import ItemStock, summarise


def test_counts_and_values_by_place_and_category() -> None:
    """TMT: 2,500 kg at S1 and 500 kg at G1, average ₹55.5 a kg -> S1 ₹1,38,750.00, G1
    ₹27,750.00. Cement: 40 bags at S1 at ₹341.25 -> ₹13,650.00. Wire: nothing left.
    Stock value 1,38,750 + 27,750 + 13,650 = ₹1,80,150.00."""
    items = [
        ItemStock(1, "TMT 12 mm", "tmt", D("55.5"), {"S1": D("2500"), "G1": D("500")}),
        ItemStock(2, "Cement PPC", "cement", D("341.25"), {"S1": D("40"), "G1": D("0")}),
        ItemStock(3, "Binding wire", "wire", D("80"), {}),
    ]
    s = summarise(items)
    assert s.items_in_stock == 2
    assert [x.item_id for x in s.out_of_stock] == [3]
    assert s.stock_value == D("180150.00")
    assert [(p.code, p.items, p.value) for p in s.places] == [
        ("G1", 1, D("27750.00")),
        ("S1", 2, D("152400.00")),
    ]
    assert [(c.code, c.items, c.value) for c in s.categories] == [
        ("cement", 1, D("13650.00")),
        ("tmt", 1, D("166500.00")),
    ]


def test_negative_or_zero_stock_counts_as_out_and_names_can_repeat() -> None:
    s = summarise(
        [
            ItemStock(7, "Pipe", "pipe", D("10"), {"S1": D("0")}),
            ItemStock(5, "Pipe", "pipe", D("10"), {"S1": D("-1")}),
        ]
    )
    assert (s.items_in_stock, s.stock_value) == (0, D("0.00"))
    assert [x.item_id for x in s.out_of_stock] == [5, 7]
    assert s.places == [] and s.categories == []
    assert summarise([]).out_of_stock == []
