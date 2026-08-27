"""Index plan hierarchy — the server-side half of the entitlement authority.

THE PLAN NAMES AND THE HIERARCHY ARE DEFINED ONCE PER RUNTIME. The browser half
lives in ``frontend/lib/access/indexPlanAccess.mjs`` and this is its exact
mirror: same two plan strings, same normalization, same "Premium satisfies
Plus" rule. A second interpretation of the same plans is how a paid feature
quietly becomes free on one surface, so neither side may invent its own.

FRONTEND GATES ARE PRESENTATION. This module exists so the API can refuse a
request that the UI merely declined to offer.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Optional

INDEX_PLAN_PLUS = "plus"
INDEX_PLAN_PREMIUM = "premium"

#: The feature identity for Build a Market. Named for the CAPABILITY rather
#: than the plan, because commercial packaging is not final: if custom markets
#: later move to a differently-named tier, the seam is this constant's mapping
#: and not every call site.
FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS = "market_explorer_custom_markets"
FEATURE_CARD_CHASE_EFFICIENCY = "card_chase_efficiency"


def normalize_index_plan(plan: Any) -> Optional[str]:
    if not isinstance(plan, str):
        return None
    normalized = plan.strip().lower()
    return normalized if normalized in (INDEX_PLAN_PLUS, INDEX_PLAN_PREMIUM) else None


def has_index_plus_access(plan: Any) -> bool:
    """True for Index Plus AND Index Premium — Premium inherits Plus."""
    return normalize_index_plan(plan) in (INDEX_PLAN_PLUS, INDEX_PLAN_PREMIUM)


def has_index_premium_access(plan: Any) -> bool:
    return normalize_index_plan(plan) == INDEX_PLAN_PREMIUM


def has_index_feature_access(plan: Any, feature: str) -> bool:
    """Canonical capability-to-plan mapping; unknown capabilities fail closed."""
    if feature in (FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS, FEATURE_CARD_CHASE_EFFICIENCY):
        return has_index_premium_access(plan)
    return False


def filter_set_market_signal_access(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    """Redact prepared Plus-only Set Market signals after entitlement resolution.

    Market Index and all ordinary Set Value scopes remain Base.  Only the
    prepared breadth contract is removed here; Chase Concentration is computed
    in presentation from the independently public ``standard`` and ``top10``
    scopes and has no concentration-specific snapshot field to redact.
    """
    if has_index_plus_access(plan):
        return dict(payload)

    filtered = deepcopy(dict(payload))
    for market_key in ("cardsMarket", "cards_market"):
        cards_market = filtered.get(market_key)
        if not isinstance(cards_market, dict):
            continue
        cards_market.pop("marketBreadth", None)
        cards_market.pop("market_breadth", None)
    # Collector-path identity and raw exact-card odds are public. Cumulative
    # acquisition milestones are Plus analytics and must not cross the API
    # boundary for Basic users. Stored snapshots remain untouched.
    for contract_key in ("publicRipContractV10", "public_rip_contract_v10"):
        contract = filtered.get(contract_key)
        if not isinstance(contract, dict):
            continue
        collector = contract.get("collectorAppeal") or contract.get("collector_appeal")
        if not isinstance(collector, dict):
            continue
        subjects = collector.get("topSubjects") or collector.get("top_subjects")
        if not isinstance(subjects, list):
            continue
        for subject in subjects:
            if not isinstance(subject, dict):
                continue
            for path_key in ("elitePath", "elite_path", "accessiblePath", "accessible_path"):
                path = subject.get(path_key)
                if not isinstance(path, dict):
                    continue
                for field in (
                    "packsFor50PercentChance",
                    "packs_for_50_percent_chance",
                    "packsFor90PercentChance",
                    "packs_for_90_percent_chance",
                    "approximatePackSpend50",
                    "approximate_pack_spend_50",
                    "approximatePackSpend90",
                    "approximate_pack_spend_90",
                ):
                    path.pop(field, None)
    return filtered


def resolve_market_explorer_plan_access(user: Mapping[str, Any] | None) -> dict[str, Any]:
    """The Market Explorer access ladder for one user.

    ``accessMode`` is "basic" for both an anonymous visitor and an authenticated
    user with no paid plan: they have the same FEATURE access. Authentication
    and entitlement stay separate states everywhere they are user-visible (the
    upgrade path differs), but nothing about what the API will serve turns on
    being signed in alone.
    """
    plan = normalize_index_plan((user or {}).get("index_plan"))
    return {
        "accessMode": plan or "basic",
        "canUsePreparedMarketIntelligence": has_index_plus_access(plan),
        "canBuildCustomMarkets": has_index_premium_access(plan),
    }
