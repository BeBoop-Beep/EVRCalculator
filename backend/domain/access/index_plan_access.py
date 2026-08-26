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

from typing import Any, Mapping, Optional

INDEX_PLAN_PLUS = "plus"
INDEX_PLAN_PREMIUM = "premium"

#: The feature identity for Build a Market. Named for the CAPABILITY rather
#: than the plan, because commercial packaging is not final: if custom markets
#: later move to a differently-named tier, the seam is this constant's mapping
#: and not every call site.
FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS = "market_explorer_custom_markets"


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
