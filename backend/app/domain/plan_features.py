"""What a plan can list as included (Milestone 20).

The catalogue is code, not data: a feature is only worth listing once the product has it.
Gating features by plan is not built; the list is shown on the plan card and nothing else.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanFeature:
    code: str
    name: str
    description: str


FEATURES: tuple[PlanFeature, ...] = (
    PlanFeature("EWAY_BILL", "E-way bills", "Make e-way bills from a sales bill."),
    PlanFeature("GST_EXPORTS", "GST exports", "GSTR-1 and GSTR-2B reports for the accountant."),
    PlanFeature("TALLY_EXPORT", "Tally export", "Vouchers the accountant loads into Tally."),
    PlanFeature("MULTI_SHOP", "Several shops", "More than one shop and a godown."),
    PlanFeature("ATTACHMENTS", "Attachments", "Keep scanned bills and photos with a document."),
)

FEATURE_CODES: frozenset[str] = frozenset(f.code for f in FEATURES)


def unknown_features(codes: list[str]) -> list[str]:
    """The codes that are not in the catalogue, in the order given."""
    return [c for c in codes if c not in FEATURE_CODES]
