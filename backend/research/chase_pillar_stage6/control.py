"""Phase 1: OVERALL_CONTROL, reconstructed through production's own code.

RESEARCH ONLY.

WHAT THE AUDIT FOUND, AND WHY CONTROL IS BUILT THIS WAY
-------------------------------------------------------
The canonical Overall RIP is **V10**::

    overall_rip_v10_90_financial_v4_10_collector_appeal_v5
    = 0.90 * Financial RIP V4 (product-native)
    + 0.10 * Collector Appeal V5 (SET-level, projected unchanged onto every
      product of that set)

Financial RIP V4 is the canonical financial model
(``CANONICAL_FINANCIAL_RIP_VERSION``) and Collector Appeal V5 the canonical
appeal model (``canonical_collector_appeal_version()``).

The stored column ``overall_rip_v10_score`` is **NULL for every row** of the
Stage V-C cohort's run, because Collector Appeal was deferred when those rows
were finalized. There is therefore no stored production number to agree with to
a tolerance, and inventing one by reimplementing the arithmetic here would be
the weakest possible form of the Phase-1 gate.

CONTROL is instead built by calling ``compute_overall_rip_v10`` - the production
function itself - on the production Financial RIP V4 score and the production
Collector Appeal V5 score. Agreement with production is then exact by
construction rather than approximate by tolerance, and
:func:`verify_control_inputs` refuses to build a row whose inputs do not carry
the canonical version strings. What CONTROL cannot do is prove that production
*would have written* these numbers; that limitation is recorded on the artifact
rather than glossed.

ONE STALE COMMENT, RECORDED NOT ACTED ON
----------------------------------------
``compute_overall_rip_v10``'s docstring still says "NOT YET CANONICAL ...
resolves to V9". ``scoring_config.CANONICAL_OVERALL_RIP_VERSION`` is
``OVERALL_RIP_V10_VERSION``, so the constant contradicts the prose. The constant
is authoritative and the docstring is stale. Stage VI does not edit production
files, so this is reported, not fixed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence


def canonical_versions() -> Dict[str, str]:
    """The version strings production currently declares canonical."""
    from backend.desirability.scoring_config import (
        CANONICAL_FINANCIAL_RIP_VERSION,
        CANONICAL_OVERALL_RIP_VERSION,
        CANONICAL_OVERALL_RIP_WEIGHTS,
        canonical_collector_appeal_version,
        canonical_public_rip_contract_version,
    )

    return {
        "overallRip": CANONICAL_OVERALL_RIP_VERSION,
        "financialRip": CANONICAL_FINANCIAL_RIP_VERSION,
        "collectorAppeal": canonical_collector_appeal_version(),
        "publicRipContract": canonical_public_rip_contract_version(),
        "overallWeights": dict(CANONICAL_OVERALL_RIP_WEIGHTS),
    }


def verify_control_inputs(*, financial_version: Any, appeal_version: Any) -> Optional[str]:
    """None when both inputs are canonical, else the reason they are not.

    Resolved by DECLARED version, never by field position. The V9 and V10
    arithmetic are identical, so a Financial RIP V3 score passed into the V10
    function would silently produce V9 wearing the V10 name.
    """
    versions = canonical_versions()
    if str(financial_version) != versions["financialRip"]:
        return ("financial input declares %r, not the canonical %r"
                % (financial_version, versions["financialRip"]))
    if str(appeal_version) != versions["collectorAppeal"]:
        return ("appeal input declares %r, not the canonical %r"
                % (appeal_version, versions["collectorAppeal"]))
    return None


def control_score(*, financial_rip_v4_score: Any, collector_appeal_v5_score: Any,
                  financial_version: Any, appeal_version: Any) -> Dict[str, Any]:
    """One product's OVERALL_CONTROL, via the production function."""
    from backend.desirability.weighted_rip import compute_overall_rip_v10

    mismatch = verify_control_inputs(financial_version=financial_version,
                                     appeal_version=appeal_version)
    if mismatch is not None:
        return {"score": None, "supported": False, "reason": mismatch}
    result = compute_overall_rip_v10(financial_rip_v4_score, collector_appeal_v5_score)
    return {
        "score": result.get("score"),
        "supported": result.get("score") is not None,
        "reason": result.get("statusReason"),
        "version": result.get("version"),
        "weights": result.get("weights"),
        "financial": financial_rip_v4_score,
        "appeal": collector_appeal_v5_score,
    }


def with_chase(*, financial: Any, appeal: Any, chase: Any,
               weights: Mapping[str, float]) -> Optional[float]:
    """A three-pillar candidate on the SAME arithmetic shape as CONTROL.

    Deliberately the plain weighted sum production already uses. Stage VI tests
    whether a third pillar earns weight, not whether a different composition
    rule would be better; changing both at once would make the answer
    unattributable.
    """
    parts = (("financial_rip", financial), ("collector_appeal", appeal), ("chase", chase))
    total = 0.0
    for name, value in parts:
        weight = float(weights.get(name, 0.0))
        if weight == 0.0:
            continue
        if value is None:
            return None
        total += weight * float(value)
    return total


def donor_weights(chase_share: float, donor: str, *,
                  base: Optional[Mapping[str, float]] = None) -> Dict[str, float]:
    """Phase 18/19: fund a Chase share from a named donor.

    ``donor`` is one of ``financial``, ``collector`` or ``proportional``. The
    Collector donor is capped by what Collector actually has: with only a 0.10
    Collector share, a 15% or 20% Chase pillar cannot be funded from Collector
    at all, and this returns ``None`` for that combination rather than quietly
    borrowing the shortfall from Financial and mislabelling the result.
    """
    if base is None:
        base = canonical_versions()["overallWeights"]
    financial = float(base.get("financial_rip", 0.0))
    collector = float(base.get("collector_appeal", 0.0))
    share = float(chase_share)

    if donor == "financial":
        if share > financial:
            return {}
        return {"financial_rip": financial - share, "collector_appeal": collector,
                "chase": share}
    if donor == "collector":
        if share > collector:
            return {}
        return {"financial_rip": financial, "collector_appeal": collector - share,
                "chase": share}
    if donor == "proportional":
        total = financial + collector
        if total <= 0 or share > total:
            return {}
        return {"financial_rip": financial - share * financial / total,
                "collector_appeal": collector - share * collector / total,
                "chase": share}
    raise ValueError("unknown donor %r" % donor)
