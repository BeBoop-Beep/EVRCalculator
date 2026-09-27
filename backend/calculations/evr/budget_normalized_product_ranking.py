"""Budget-Constrained Whole-Unit Product Ranking — the internal, cross-format
budget-ceiling ranking engine.

WHAT THIS IS
------------
The validated answer to "if I have UP TO $X to spend, which eligible sealed
product opening strategy performs best" — using the maximum number of WHOLE
purchasable retail units that fit under a budget CEILING, never a
natural-unit cross-format sort of ``overall_rip_v10_score`` (that comparison
remains invalid; see
``backend.domain.pokemon.sealed_product_comparison_scope``).

THIS IS NOT EQUAL COMMITTED CAPITAL
-----------------------------------
Two strategies at the same budget generally commit DIFFERENT amounts of
capital: a $1,339 product commits $1,339 of a $1,350 budget, while a $450
product commits $1,350 exactly. Both are valid answers to "what can I open
for up to $1,350"; neither is an equal-spend comparison.

The methodology validation measured both semantics against each other and
found them NOT interchangeable — they agree globally (Spearman ~0.95) but
disagree on the podium (top-5 overlap 1-3 of 5). Budget-constrained was
approved (``BUDGET_CONSTRAINED_WHOLE_UNIT_RANKING_V1_APPROVED``) because it
is the only one of the two that answers the actual user question, and
because matched capital cannot represent the most expensive SKU at all under
the preregistered 5% / $1,000 pairwise bound.

Do NOT describe this engine as equal spend, equal committed capital, matched
capital, "the best use of your money", or total-wealth optimisation. It
ranks OPENING STRATEGIES under a spending ceiling. See
``docs/research/BUDGET_NORMALIZED_PRODUCT_RANKING_v1.md``.

This is NOT a context-free universal "Overall Product Rank". Research
(``docs/research/OVERALL_PRODUCT_RANK_DECISION_2026-08-22_v2.md``) found no
single budget gives 100% cohort coverage, so every rank produced here is
explicitly budget-qualified — the budget is part of the rank's identity, not
an implementation detail. This module is INTERNAL infrastructure for a future
higher-tier "given my budget, what should I open" capability. It is not wired
to any current customer-facing surface.

RANKING METHOD VERSION
-----------------------
``BUDGET_NORMALIZED_RANKING_METHOD_VERSION`` below. Bump it (and add a new
constant, never mutate the meaning of an existing one — matching the
project's convention for every other RIP model version) if the allocation
rule, scoring chain, or comparator change.

ALLOCATION RULE (validated in this task; see decision record)
---------------------------------------------------------------
``quantity = floor(target_budget / product_market_price)``, i.e. the largest
whole number of retail units purchasable without exceeding the target. This
is Candidate A from the research phase ("simple floor quantity") — chosen
over a nearest-whole-unit-within-tolerance search because floor quantity is:
simpler to explain to a user ("as many as $X buys"), deterministic with no
search/tolerance parameter to tune, and the SAME rule the existing validated
equal-spend research already used for its `fixed_budget_quantity` bands
(preserving continuity with the already-validated $25-$500 research). A
product priced above the target budget is simply ineligible (quantity 0),
recorded as such rather than silently dropped.

Leftover ("unused") capital is recorded explicitly and NEVER treated as
spent, invested, or folded into the outcome distribution.

SCORING CHAIN (mirrors production exactly)
-------------------------------------------
For a strategy of quantity Q of one SKU: build the REAL Q-unit outcome
distribution (reusing ``build_stage1_product_distributions`` — the same
machinery Stage 1/2 production scoring and the equal-spend research use, so
no approximation of "single-unit metrics x Q"), add guaranteed-component
value once per unit purchased, then score via
``build_financial_rip_v3`` -> ``project_financial_rip_v4_from_v3_payload``
(the same V3-then-project-to-V4 chain production uses — verified by exact
reconstruction in the equal-spend V4 research), then
``compute_overall_rip_v10(financial_v4_score, collector_appeal_score)`` using
the SAME Collector Appeal score the SKU's set already carries (Collector
Appeal describes the set's desirability, not purchase quantity, and is never
recomputed here).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v4 import (
    project_financial_rip_v4_from_v3_payload,
)
from backend.calculations.evr.guaranteed_component_value import (
    add_guaranteed_components,
)
from backend.calculations.evr.sealed_product_distribution import (
    build_stage1_product_distributions,
)
from backend.desirability.composite import assign_composite_tier
from backend.desirability.weighted_rip import compute_overall_rip_v10, compute_overall_rip_v12

#: Bump on any change to allocation rule, scoring chain, or comparator.
#: Never mutate the meaning of an already-published version string.
BUDGET_NORMALIZED_RANKING_METHOD_VERSION = "budget_product_ranking_v1"
ALLOCATION_METHOD_VERSION = "budget_allocation_floor_quantity_v1"

#: Comparison-scope identity for THIS ranking — deliberately distinct from
#: the natural-unit `within_product_family_only` scope, which is untouched.
#:
#: V1 FINAL. The name states the four properties that define the scope:
#: budget-CONSTRAINED (a ceiling, not a match), WHOLE-UNIT (indivisible
#: retail units), CROSS-FORMAT (families compared against each other), V1.
BUDGET_COMPARISON_SCOPE_VERSION = "budget_constrained_whole_unit_cross_format_v1"

#: HISTORICAL ONLY — never emitted by this engine again.
#:
#: The pre-freeze scope string. It described the implementation as
#: equal-committed-capital when the implementation was in fact
#: floor-to-budget; the methodology validation proved the two produce
#: materially different rankings, so the name was wrong rather than loose.
#:
#: Retained (not deleted, not redefined) so that any artifact carrying this
#: string keeps its original meaning and can be identified as pre-freeze.
#: No production publication ever used it: the storage migration was authored
#: but never applied, so zero rows exist under this scope.
LEGACY_BUDGET_COMPARISON_SCOPE_VERSION_PRE_FREEZE = "equal_committed_capital_cross_format_v1"

#: Validated in research (docs/research/OVERALL_PRODUCT_RANK_DECISION_2026-08-22_v2.md):
#: near-perfect (median Spearman 1.0) cross-budget rank stability, zero
#: dominance inversions. Preserved as the canonical standard bands.
CANONICAL_BUDGET_BANDS: tuple[float, ...] = (
    25.0, 50.0, 100.0, 150.0, 250.0, 500.0, 750.0, 1000.0, 1250.0,
)

#: FULL_MARKET is a sentinel budget_type, not a fixed dollar figure — its
#: dollar value is resolved dynamically per publication (see
#: `resolve_full_market_budget`) and stored alongside every record built at
#: it, so a future price movement crossing the rounding boundary is
#: reproducible and auditable rather than silently inconsistent.
BUDGET_TYPE_STANDARD = "standard_band"
BUDGET_TYPE_FULL_MARKET = "full_market"
BUDGET_TYPE_CUSTOM = "custom"

#: The Full Market anchor rounds the current maximum eligible SKU price UP to
#: the next $50 increment. Chosen over $25 (same anchor value on the current
#: cohort — no coverage/inflation benefit, but a smaller boundary means MORE
#: frequent anchor changes as prices drift) and over $100 (needlessly
#: inflates committed capital ~4.5x more than necessary on the current
#: cohort, with no stability benefit measured). See decision record for the
#: comparison.
FULL_MARKET_ROUNDING_INCREMENT = 50.0

#: Frozen identity of the Full Market rounding rule, persisted per publication
#: so a historical anchor stays auditable if the increment ever changes.
#:
#: EVIDENCE for $50 (methodology validation, replicated on two cohorts):
#:   * $25 resolves to the SAME anchor on the current cohort ($1,350) but
#:     churns twice as often across a price sweep (4 changes vs 2).
#:   * $100 inflates committed capital 4.54% above the max SKU vs 0.81% for
#:     $50 — 5.6x the excess — and buys no measured stability, because ranks
#:     are near-invariant from $1,350 to $1,600 (Spearman >= 0.993, top-20
#:     overlap 20/20).
#:   * Confirmed by real drift: the max SKU price moved $1,339.19 -> $1,331.19
#:     during validation and the $50 anchor held at $1,350.
FULL_MARKET_ROUNDING_RULE_VERSION = "full_market_next_50_above_max_eligible_sku_v1"


def resolve_full_market_budget(eligible_market_prices: Sequence[float]) -> Dict[str, Any]:
    """The lowest standardized committed-capital level admitting every eligible SKU.

    Deliberately NOT the raw maximum price: rounds up to the nearest
    ``FULL_MARKET_ROUNDING_INCREMENT`` so the anchor does not move every time
    the single most expensive SKU's price changes by a few dollars, while a
    price change that does NOT cross the rounding boundary produces the
    identical anchor (reproducible, low-sensitivity).
    """
    prices = [float(p) for p in eligible_market_prices if p is not None and float(p) > 0]
    if not prices:
        raise ValueError("cannot resolve a Full Market budget with no eligible priced products")
    max_price = max(prices)
    increment = FULL_MARKET_ROUNDING_INCREMENT
    anchor = math.ceil(max_price / increment) * increment
    # A max price that lands exactly on a boundary must still admit that SKU
    # (floor-quantity needs budget >= price to buy 1 unit).
    if anchor < max_price:
        anchor += increment
    return {
        "budget": float(anchor),
        "maxEligibleSkuPrice": max_price,
        "roundingIncrement": increment,
        "roundingRule": f"ceil(maxEligibleSkuPrice / {increment:g}) * {increment:g}",
        "roundingRuleVersion": FULL_MARKET_ROUNDING_RULE_VERSION,
    }


def whole_unit_allocation(target_budget: float, product_market_price: float) -> Dict[str, Any]:
    """Whole-unit floor allocation. See module docstring for why floor, not nearest-search."""
    price = float(product_market_price)
    if price <= 0:
        raise ValueError("product_market_price must be positive")
    budget = float(target_budget)
    if budget <= 0:
        raise ValueError("target_budget must be positive")
    quantity = int(math.floor(budget / price))
    actual_committed_capital = quantity * price
    unused_capital = budget - actual_committed_capital
    # `capitalUtilization` and `unusedCapitalPercent` are exact complements by
    # construction (they sum to 1.0 up to float error), and BOTH are persisted:
    # utilization is the diagnostic the methodology validation correlates
    # against rank to prove the absence of budget-divisibility bias, while
    # unused percent is the disclosure that stops leftover cash from being
    # read as opening value.
    unused_capital_percent = (unused_capital / budget) if budget > 0 else None
    capital_utilization = (actual_committed_capital / budget) if budget > 0 else None
    return {
        "eligible": quantity >= 1,
        "quantity": quantity,
        "targetBudget": budget,
        "actualCommittedCapital": actual_committed_capital,
        "unusedCapital": unused_capital,
        "unusedCapitalPercent": unused_capital_percent,
        "capitalUtilization": capital_utilization,
    }


def build_budget_strategy_values(
    *,
    base_random_pack_values: np.ndarray,
    quantity: int,
    guaranteed_component_market_value: Optional[float],
    canonical_set_key: Any,
    run_fingerprint: Optional[str] = None,
) -> np.ndarray:
    """The REAL quantity-Q outcome vector: not `single_unit_metric * Q`.

    ``base_random_pack_values`` is the single-unit random-component
    distribution (already built once per set/pack-count by the caller and
    reused across every candidate budget/product, exactly like the
    equal-spend research's `StrategyEngine` cache). Guaranteed-component
    value is added once PER UNIT purchased, matching how a real multi-unit
    purchase accumulates guaranteed contents.
    """
    if quantity < 1:
        raise ValueError("quantity must be a positive whole retail unit")
    if quantity == 1:
        values = base_random_pack_values
    else:
        built = build_stage1_product_distributions(
            base_random_pack_values,
            pack_counts=[quantity],
            canonical_set_key=canonical_set_key,
            run_fingerprint=run_fingerprint,
        )
        values = built["distributions"][quantity]
    if guaranteed_component_market_value:
        values = add_guaranteed_components(values, float(guaranteed_component_market_value) * quantity)
    return values


def score_budget_strategy(
    values: np.ndarray,
    actual_committed_capital: float,
    collector_appeal_score: Optional[float],
    *,
    min_simulation_count: int = 0,
    chase_accessibility_raw: Optional[float] = None,
) -> Dict[str, Any]:
    """Financial RIP V4 (projected from V3, exactly as production computes it),
    then Overall RIP V10 from that V4 score and the SAME Collector Appeal
    score the set already carries (never recomputed per quantity).

    ``chase_accessibility_raw`` (optional, additive) is the SAME set-level raw
    Chase Accessibility value used elsewhere for this product's set - a
    structural, quantity-independent reachability metric, never recomputed
    per budget/quantity, exactly like ``collector_appeal_score`` above. When
    provided, an ADDITIVE, non-canonical ``overallRipV12*`` triple is also
    computed via the one canonical :func:`compute_overall_rip_v12` transform.
    This NEVER changes `_tier_sort_key`'s V10-only sort order or any existing
    output field - callers that omit the new keyword see byte-identical
    behavior. Promotion of this shadow field to the sort key is a separate,
    later, explicit cutover (matching how V10 itself was promoted)."""
    v3_kwargs = {} if not min_simulation_count else {"min_simulation_count": min_simulation_count}
    v3_payload = build_financial_rip_v3(values, actual_committed_capital, **v3_kwargs)
    # Top 1% Value Share MUST come from the outcome-distribution disclosure
    # (`distributionDisclosures.jackpotValueShare`) of THIS SAME q-unit
    # strategy's simulated values — never the unrelated card-attribution
    # metric `depthAndRobustness.top1EvShare`, which shares only the "top1"
    # naming pattern and answers a different question.
    top1_outcome_value_share = (v3_payload.get("distributionDisclosures") or {}).get("jackpotValueShare")
    v4_payload = project_financial_rip_v4_from_v3_payload(v3_payload)
    # `chance_to_recover_capital` is the canonical `true_win_probability` raw
    # input. It MUST be read from the V3 payload: the V4 projection carries an
    # EMPTY `audit.normalizedInputs`, so sourcing it from V4 silently yields
    # None. That exact mistake made the prior research's four-metric dominance
    # test vacuous ("0 comparable pairs" reported as "zero inversions").
    v3_raw = {
        key: record.get("raw")
        for key, record in ((v3_payload.get("audit") or {}).get("normalizedInputs") or {}).items()
    }
    chance_to_recover_capital = v3_raw.get("true_win_probability")
    typical_retention_ratio = v3_raw.get("typical_retention_ratio")
    financial_v4_score = v4_payload.get("score")
    financial_v4_status = v4_payload.get("status")
    financial_v4_rankable = bool(v4_payload.get("rankable"))
    overall_v10 = None
    if financial_v4_rankable and financial_v4_score is not None and collector_appeal_score is not None:
        overall_v10 = compute_overall_rip_v10(financial_v4_score, collector_appeal_score)
    overall_v12 = None
    if (
        financial_v4_rankable and financial_v4_score is not None
        and collector_appeal_score is not None and chase_accessibility_raw is not None
    ):
        overall_v12 = compute_overall_rip_v12(
            financial_v4_score, chase_accessibility_raw, collector_appeal_score
        )
    return {
        "financialRipV4Score": financial_v4_score,
        "financialRipV4Status": financial_v4_status,
        "financialRipV4Rankable": financial_v4_rankable,
        "financialRipV4Payload": v4_payload,
        "overallRipV10Score": overall_v10.get("score") if overall_v10 else None,
        "overallRipV10Rankable": bool(overall_v10.get("rankable")) if overall_v10 else False,
        "overallRipV10Version": overall_v10.get("version") if overall_v10 else None,
        # SHADOW/ADDITIVE ONLY: never consumed by `_tier_sort_key`. See the
        # docstring above - the same non-recomputation discipline applied to
        # `collector_appeal_score` applies to `chase_accessibility_raw`.
        "overallRipV12Score": overall_v12.get("score") if overall_v12 else None,
        "overallRipV12Rankable": bool(overall_v12.get("rankable")) if overall_v12 else False,
        "overallRipV12Version": overall_v12.get("version") if overall_v12 else None,
        "overallRipV12Payload": overall_v12,
        "expectedValue": float(np.mean(values)),
        "medianValue": float(np.median(values)),
        "topOneOutcomeValueShare": top1_outcome_value_share,
        # Average Return for a budget strategy is ALWAYS expected value over
        # the actual committed capital for this exact q-unit allocation —
        # never the cohort's target budget band, never a single-unit price.
        "averageReturn": (
            float(np.mean(values)) / actual_committed_capital
            if actual_committed_capital else None
        ),
        "chanceToRecoverCapital": chance_to_recover_capital,
        "typicalRetentionRatio": typical_retention_ratio,
        "lossResilience": (v4_payload.get("components") or {}).get("loss_resilience", {}).get("score"),
    }


#: Sort-authority selector for :func:`rank_budget_cohort` (Gate F, Phase 7;
#: UI-5B, Phase 3/7/8 promotes the *default* below to resolve dynamically).
SORT_AUTHORITY_V10 = "overall_rip_v10"
SORT_AUTHORITY_V12 = "overall_rip_v12"


def resolve_default_budget_sort_authority() -> str:
    """The generic/current Budget sort authority: whatever Overall RIP model
    is canonical program-wide (`scoring_config.CANONICAL_OVERALL_RIP_VERSION`),
    resolved fresh on every call rather than cached at import time.

    UI-5B cutover: prior to this, `rank_budget_cohort`'s default was the
    literal constant `SORT_AUTHORITY_V10`, hardcoded independently of the
    program's canonical-version switch — the exact defect
    (`BUDGET_V12_BLOCKED_PIPELINE_NOT_CUTOVER`) recorded in
    docs/research/OVERALL_RIP_V12_UI_STANDARDIZATION.md. A caller that wants a
    specific, explicit authority regardless of what is canonical (e.g. the
    offline V10 rollback/compat path) must keep passing `sort_authority=`
    explicitly — this resolver is consulted ONLY when the caller omits the
    argument entirely.
    """
    from backend.desirability.scoring_config import canonical_overall_rip_is_v12

    return SORT_AUTHORITY_V12 if canonical_overall_rip_is_v12() else SORT_AUTHORITY_V10


def _tier_sort_key(entry: Mapping[str, Any]) -> tuple:
    """Overall RIP V10 (desc) -> Financial RIP V4 (desc) -> chance-to-recover
    (desc, when present) -> committed-capital closeness to target (asc) ->
    sealed_product_id (deterministic final tie-break). Mirrors the validated
    Family Rank comparator's structure so the two ranking systems read
    consistently, adapted with a budget-utilisation tie-break specific to a
    spending ceiling: among strategies that are otherwise indistinguishable,
    the one using MORE of the available budget ranks first. This is a
    tie-break on utilisation, NOT a capital-matching requirement — nothing
    here forces or rewards equal committed capital."""
    overall = entry.get("overallRipV10Score")
    financial = entry.get("financialRipV4Score")
    # Tie-break 3 is the canonical chance-to-recover-capital. It was
    # historically read from `chanceToRecoverCost`, which the builder always
    # set to None, leaving this position inert. `chanceToRecoverCapital` is
    # now populated from the V3 raw inputs; the legacy key is still honoured
    # so existing callers keep working. The comparator's SHAPE is unchanged
    # (validated semantics preserved) — the slot simply carries a real value
    # now. Verified non-binding on the current cohort: exact (V10, V4) ties
    # number 0 at every tested budget, so ordering is unaffected.
    recover = entry.get("chanceToRecoverCapital")
    if recover is None:
        recover = entry.get("chanceToRecoverCost")
    mismatch = abs(entry.get("actualCommittedCapital", 0.0) - entry.get("targetBudget", 0.0))
    return (
        -(overall if overall is not None else float("-inf")),
        -(financial if financial is not None else float("-inf")),
        -(recover if recover is not None else float("-inf")),
        mismatch,
        str(entry.get("sealedProductId") or ""),
    )


def _tier_sort_key_v12(entry: Mapping[str, Any]) -> tuple:
    """V12-authority ordering: Overall RIP V12 (desc) in the position V10
    occupies in :func:`_tier_sort_key`, everything else identical (same
    Financial V4 / chance-to-recover / utilisation tie-breaks). A row whose
    ``overallRipV12Rankable`` is not True must never reach this comparator -
    :func:`rank_budget_cohort` filters those out before sorting, so there is
    no path by which an unavailable V12 row can be silently ordered (let
    alone ordered using its V10 score under the V12 label)."""
    overall = entry.get("overallRipV12Score")
    financial = entry.get("financialRipV4Score")
    recover = entry.get("chanceToRecoverCapital")
    if recover is None:
        recover = entry.get("chanceToRecoverCost")
    mismatch = abs(entry.get("actualCommittedCapital", 0.0) - entry.get("targetBudget", 0.0))
    return (
        -(overall if overall is not None else float("-inf")),
        -(financial if financial is not None else float("-inf")),
        -(recover if recover is not None else float("-inf")),
        mismatch,
        str(entry.get("sealedProductId") or ""),
    )


def financial_only_comparator_key(entry: Mapping[str, Any]) -> tuple:
    """Financial RIP V4 (desc) -> sealed_product_id (deterministic tie-break).

    The comparator behind rank_by_financial_only(): the same sort key
    rank_budget_cohort() has always used for its internal financialOnlyRank
    audit lens, extracted so Best-Open Price V2's FINANCIAL_V4 comparison
    authority can reuse it directly instead of reimplementing the sort.
    """
    financial = entry.get("financialRipV4Score")
    return (
        -(financial if financial is not None else float("-inf")),
        str(entry.get("sealedProductId") or ""),
    )


def rank_by_financial_only(strategies: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Canonical Financial-only comparator.

    Orders the GIVEN strategies by financial_only_comparator_key and assigns
    1-based ranks. Callers control cohort membership -- this function applies
    no rankability filter of its own, matching how rank_budget_cohort() has
    always called this ordering only on its own pre-filtered `rankable` list.
    Used both by rank_budget_cohort() (for its internal financialOnlyRank
    audit lens) and by Best-Open Price V2's FINANCIAL_V4 comparison authority
    for pairwise candidate-vs-benchmark winner determination.
    """
    ordered = sorted(strategies, key=financial_only_comparator_key)
    return [
        {**entry, "financialOnlyRank": index}
        for index, entry in enumerate(ordered, start=1)
    ]


def rank_budget_cohort(
    strategies: Sequence[Mapping[str, Any]],
    *,
    sort_authority: str = SORT_AUTHORITY_V10,
) -> List[Dict[str, Any]]:
    """Rank only the RANKABLE strategies under the requested sort authority.

    ``sort_authority`` defaults to V10 and MUST be passed explicitly to get
    V12 ordering - there is no implicit/inferred cutover AT THIS FUNCTION.
    (UI-5B note: the engine stays a dumb, explicit-only comparator on purpose
    - many existing callers/tests build V10-only strategy fixtures with no
    V12 fields populated at all, so resolving a canonical default HERE would
    silently empty their rankable set under V12. The generic/current-vs-V10
    decision belongs one layer up, at the orchestration layer that actually
    has the data to populate V12 fields in the first place - see
    `resolve_default_budget_sort_authority` and
    `backend.scripts.build_budget_normalized_product_rankings`.)
    Ineligible/unrankable strategies (for V10:
    ``overallRipV10Score`` is None; for V12: ``overallRipV12Rankable`` is not
    True) are never assigned a rank; callers must keep them out of this list's
    cohort-size accounting and report them as excluded with a reason, never as
    a fabricated rank. A V12-unavailable row can never "fall back" to being
    ranked by its V10 score while the result is labelled V12 - it is simply
    excluded from this list.
    """
    if sort_authority == SORT_AUTHORITY_V12:
        rankable = [s for s in strategies if s.get("overallRipV12Rankable") is True and s.get("overallRipV12Score") is not None]
        sort_key = _tier_sort_key_v12
        score_field = "overallRipV12Score"
    elif sort_authority == SORT_AUTHORITY_V10:
        rankable = [s for s in strategies if s.get("overallRipV10Score") is not None]
        sort_key = _tier_sort_key
        score_field = "overallRipV10Score"
    else:
        raise ValueError("unknown sort_authority %r" % (sort_authority,))

    ordered = sorted(rankable, key=sort_key)
    size = len(ordered)

    # INTERNAL AUDIT LENS (never surfaced publicly): the SAME cohort ordered by
    # Financial RIP V4 alone. Overall RIP V10 is 0.90 financial + 0.10
    # Collector Appeal, so a financially dominated SKU can legitimately outrank
    # its dominator on desirability. Dominance diagnostics are financial, so
    # they need an ordering with appeal removed — validation measured 1.06%
    # inversions under V10 versus 0.044% under this financial-only lens, and
    # confirmed ~98-100% of the V10 inversions are Collector Appeal by design.
    financial_only_rank = {
        str(entry.get("sealedProductId")): entry["financialOnlyRank"]
        for entry in rank_by_financial_only(rankable)
    }

    out = []
    for index, entry in enumerate(ordered, start=1):
        out.append(
            {
                **entry,
                "budgetRank": index,
                "budgetCohortSize": size,
                # SCORE tier, not a rank-percentile tier: derived from the
                # Overall RIP V10 score via the shared composite thresholds.
                # Rank #1 does not imply tier S, and tier S does not imply
                # rank #1 — see the decision record's tier semantics section.
                "budgetTier": assign_composite_tier(entry[score_field]),
                "financialOnlyRank": financial_only_rank[str(entry.get("sealedProductId"))],
            }
        )
    return out


# ---------------------------------------------------------------------------
# Ranking V2 - Financial RIP V5 + Overall RIP V14 (EXPLICIT, NON-CANONICAL)
# ---------------------------------------------------------------------------
# V2 changes the scoring authority ONLY: Financial V4 -> V5 and Overall V12 ->
# V14. Allocation (``budget_allocation_floor_quantity_v1``), Full Market anchor,
# $50 rounding, comparison scope and the comparator SHAPE are unchanged. Nothing
# above this line is modified and no default resolves to V2; selecting it is an
# explicit act, and the canonical switch is a separate cutover.

#: Never mutate the meaning of V1 (``BUDGET_NORMALIZED_RANKING_METHOD_VERSION``).
BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2 = "budget_product_ranking_v2"
SORT_AUTHORITY_V14 = "overall_rip_v14"


def score_budget_strategy_v2(
    values: np.ndarray,
    actual_committed_capital: float,
    collector_appeal_score: Optional[float],
    *,
    chase_accessibility_raw: Optional[float] = None,
    min_simulation_count: int = 0,
    prepared: Any = None,
) -> Dict[str, Any]:
    """Financial RIP V5 then Overall RIP V14 for one exact q-unit strategy.

    Uses the production ``build_financial_rip_v5`` (never the research
    candidate). The V3 payload supplies the V4 control (exactly the V3-then-
    project chain V1 uses) so V4 is not recomputed. Chase Accessibility and
    Collector Appeal are the SAME set-level values V1 uses. Every emitted field
    is V5/V14-named; nothing here is written to a V4/V12 field.
    """
    from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
    from backend.calculations.evr.financial_rip_v5 import build_financial_rip_v5
    from backend.desirability.overall_rip_v14 import compute_overall_rip_v14
    from backend.desirability.scoring_config import (
        FINANCIAL_RIP_V5_VERSION,
        overall_rip_v14_required_chase_accessibility_version,
        overall_rip_v14_required_collector_appeal_version,
    )

    prepared = prepared or PreparedFinancialRipDistribution.prepare(values)
    kwargs = {} if not min_simulation_count else {"min_simulation_count": min_simulation_count}
    v3_payload = prepared.score(actual_committed_capital, **kwargs)
    control = project_financial_rip_v4_from_v3_payload(v3_payload)
    v5 = build_financial_rip_v5(prepared, actual_committed_capital, control_payload=control)
    v3_raw = {
        key: record.get("raw")
        for key, record in ((v3_payload.get("audit") or {}).get("normalizedInputs") or {}).items()
    }
    v5_rankable = bool(v5.get("rankable")) and v5.get("score") is not None
    overall = None
    if v5_rankable and collector_appeal_score is not None and chase_accessibility_raw is not None:
        overall = compute_overall_rip_v14(
            v5.get("score"), chase_accessibility_raw, collector_appeal_score,
            financial_version=FINANCIAL_RIP_V5_VERSION,
            chase_accessibility_version=overall_rip_v14_required_chase_accessibility_version(),
            collector_appeal_version=overall_rip_v14_required_collector_appeal_version(),
        )
    return {
        "financialRipV5Score": v5.get("score"),
        "financialRipV5Status": v5.get("status"),
        "financialRipV5Rankable": v5_rankable,
        "financialRipV5Version": v5.get("scoreVersion"),
        "financialRipV5Payload": v5,
        "overallRipV14Score": overall.get("score") if overall else None,
        "overallRipV14Status": overall.get("status") if overall else "unavailable_missing_input",
        "overallRipV14Rankable": bool(overall.get("rankable")) if overall else False,
        "overallRipV14Version": overall.get("version") if overall else None,
        "overallRipV14Payload": overall,
        "expectedValue": float(np.mean(values)) if values is not None else None,
        "medianValue": float(np.median(values)) if values is not None else None,
        "topOneOutcomeValueShare": (v3_payload.get("distributionDisclosures") or {}).get("jackpotValueShare"),
        "averageReturn": (
            float(np.mean(values)) / actual_committed_capital
            if values is not None and actual_committed_capital else None
        ),
        "chanceToRecoverCapital": v3_raw.get("true_win_probability"),
        "typicalRetentionRatio": v3_raw.get("typical_retention_ratio"),
        "shortfallResilience": (v5.get("components") or {}).get("shortfall_resilience", {}).get("score"),
    }


def _tier_sort_key_v14(entry: Mapping[str, Any]) -> tuple:
    """Overall V14 (desc) -> Financial V5 (desc) -> chance-to-recover (desc) ->
    committed-capital mismatch (asc) -> sealed_product_id. Same shape as
    :func:`_tier_sort_key_v12` with the versioned fields substituted."""
    overall = entry.get("overallRipV14Score")
    financial = entry.get("financialRipV5Score")
    recover = entry.get("chanceToRecoverCapital")
    mismatch = abs(entry.get("actualCommittedCapital", 0.0) - entry.get("targetBudget", 0.0))
    return (
        -(overall if overall is not None else float("-inf")),
        -(financial if financial is not None else float("-inf")),
        -(recover if recover is not None else float("-inf")),
        mismatch,
        str(entry.get("sealedProductId") or ""),
    )


def financial_only_comparator_key_v5(entry: Mapping[str, Any]) -> tuple:
    """Financial RIP V5 (desc) -> sealed_product_id."""
    financial = entry.get("financialRipV5Score")
    return (
        -(financial if financial is not None else float("-inf")),
        str(entry.get("sealedProductId") or ""),
    )


def rank_by_financial_only_v5(strategies: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Financial-V5-only ordering; emits ``financialOnlyRankV5`` (never V4's key)."""
    ordered = sorted(strategies, key=financial_only_comparator_key_v5)
    return [{**entry, "financialOnlyRankV5": i} for i, entry in enumerate(ordered, start=1)]


def rank_budget_cohort_v2(strategies: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Rank only strategies whose V14 result is rankable. There is deliberately
    no ``sort_authority`` argument and no fallback to V10/V12 or V4 fields: a
    row without V14 evidence is excluded, never ordered by another model."""
    rankable = [
        s for s in strategies
        if s.get("overallRipV14Rankable") is True and s.get("overallRipV14Score") is not None
        and s.get("financialRipV5Rankable") is True
    ]
    ordered = sorted(rankable, key=_tier_sort_key_v14)
    size = len(ordered)
    financial_only_rank = {
        str(e.get("sealedProductId")): e["financialOnlyRankV5"]
        for e in rank_by_financial_only_v5(rankable)
    }
    return [
        {
            **entry,
            "budgetRankV14": index,
            "budgetCohortSizeV14": size,
            "budgetTierV14": assign_composite_tier(entry["overallRipV14Score"]),
            "financialOnlyRankV5": financial_only_rank[str(entry.get("sealedProductId"))],
        }
        for index, entry in enumerate(ordered, start=1)
    ]
