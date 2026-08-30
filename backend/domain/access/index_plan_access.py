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
FEATURE_MARKET_EXPLORER_SINGLE_AXIS = "market_explorer_single_axis"
FEATURE_MARKET_EXPLORER_COMPOUND = "market_explorer_compound"
FEATURE_MARKET_EXPLORER_CUSTOM_RANKED = "market_explorer_custom_ranked"
FEATURE_MARKET_EXPLORER_POKEMON = "market_explorer_pokemon"
FEATURE_CARD_CHASE_EFFICIENCY = "card_chase_efficiency"
FEATURE_MARKET_BREADTH = "market_breadth"
FEATURE_PRODUCT_RIP = "product_rip"
FEATURE_PACK_ECONOMICS = "pack_economics"
FEATURE_ACQUISITION_MILESTONES = "acquisition_milestones"
FEATURE_SET_RIP_ANALYTICS = "set_rip_analytics"

_PLUS_FEATURES = frozenset({
    FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS,
    FEATURE_MARKET_EXPLORER_SINGLE_AXIS,
    FEATURE_MARKET_BREADTH,
    FEATURE_PRODUCT_RIP,
    FEATURE_PACK_ECONOMICS,
    FEATURE_ACQUISITION_MILESTONES,
    FEATURE_SET_RIP_ANALYTICS,
})
_PREMIUM_FEATURES = frozenset({
    FEATURE_MARKET_EXPLORER_COMPOUND,
    FEATURE_MARKET_EXPLORER_CUSTOM_RANKED,
    FEATURE_MARKET_EXPLORER_POKEMON,
    FEATURE_CARD_CHASE_EFFICIENCY,
})


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
    if feature in _PREMIUM_FEATURES:
        return has_index_premium_access(plan)
    if feature in _PLUS_FEATURES:
        return has_index_plus_access(plan)
    return False


def evaluate_market_query_access(plan: Any, spec: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one normalized query definition against the plan hierarchy."""
    from backend.domain.pokemon.market_explorer_query import MODE_CHASE, active_filter_axes

    axes = active_filter_axes(spec)
    ranked = spec.get("mode") == MODE_CHASE
    if spec.get("pokemonIds"):
        required_plan, capability = INDEX_PLAN_PREMIUM, FEATURE_MARKET_EXPLORER_POKEMON
        reason = "Pokemon market research requires Index Premium"
    elif ranked:
        required_plan, capability = INDEX_PLAN_PREMIUM, FEATURE_MARKET_EXPLORER_CUSTOM_RANKED
        reason = "custom ranked composition requires Index Premium"
    elif len(axes) > 1:
        required_plan, capability = INDEX_PLAN_PREMIUM, FEATURE_MARKET_EXPLORER_COMPOUND
        reason = "compound market requires Index Premium"
    else:
        required_plan, capability = INDEX_PLAN_PLUS, FEATURE_MARKET_EXPLORER_SINGLE_AXIS
        reason = "custom market exploration requires Index Plus"
    allowed = (has_index_premium_access(plan) if required_plan == INDEX_PLAN_PREMIUM
               else has_index_plus_access(plan))
    return {
        "allowed": allowed,
        "requiredPlan": required_plan,
        "capability": capability,
        "reason": None if allowed else reason,
        "activeFilterAxes": list(axes),
    }


def _pick(source: Mapping[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    """Copy only fields classified for a response contract.

    This is intentionally not a redactor. New upstream fields are absent until
    somebody adds them to a tier allowlist.
    """
    return {key: source[key] for key in allowed if key in source}


_BASE_TARGET_FIELDS = frozenset({
    "id", "set_id", "target_id", "target_type", "name", "slug", "canonical_key",
    "pokemon_api_set_id", "era", "era_id", "hero_image_url", "logo_image_url",
    "symbol_image_url", "checklist_set_value", "checklist_set_value_as_of",
    "checklist_set_value_priced_card_count", "checklist_set_value_total_card_count",
    "checklistSetValue", "checklistSetValueAsOf", "checklistSetValuePricedCardCount",
    "checklistSetValueTotalCardCount", "current_checklist_set_value",
    "current_checklist_set_value_date", "currentChecklistSetValue",
    "currentChecklistSetValueDate", "publicAnalyticsStatus",
})
_PLUS_TARGET_FIELDS = _BASE_TARGET_FIELDS | frozenset({
    "calculation_run_id", "run_at", "pack_cost", "pack_score", "relative_pack_score",
    "pack_rank", "pack_tier", "profit_score", "relative_profit_score", "profit_rank",
    "profit_tier", "safety_score", "relative_safety_score", "safety_rank", "safety_tier",
    "stability_score", "relative_stability_score", "stability_rank", "stability_tier",
    "mean_value", "median_value", "prob_profit", "prob_big_hit", "roi_percent",
    "expected_loss_when_losing", "mean_value_to_cost_ratio", "mean_value_to_cost_rank",
    "mean_value_to_cost_tier", "p95_value_to_cost_ratio", "p95_value_to_cost_rank",
    "p95_value_to_cost_tier", "p99_value_to_cost_ratio", "p99_value_to_cost_rank",
    "p99_value_to_cost_tier", "rip", "ripCore", "financialRipV4", "overallRipV10",
    "publicRipContractV10", "setRipV1", "openingExperience", "rankingsChase",
    "collector_appeal_score", "collector_appeal_rank", "opening_desirability_score",
    "opening_desirability_rank", "opening_desirability_summary",
})
_RANKINGS_META_FIELDS = frozenset({"source", "updatedAt", "warnings", "snapshot", "limit"})
_PUBLIC_SET_RIP_FIELDS = frozenset({
    "score", "rank", "tier", "cohortSize", "rankable", "methodologyVersion",
    "participatingFamilyCount", "participatingFamilies", "skuEvidenceCount",
    "familyScores", "displayFamilyScores",
})


def _project_public_set_leaderboard_target(target: Mapping[str, Any]) -> dict[str, Any]:
    projected = _pick(target, _BASE_TARGET_FIELDS)
    set_rip = target.get("setRipV1")
    if isinstance(set_rip, Mapping):
        projected["setRipV1"] = _pick(set_rip, _PUBLIC_SET_RIP_FIELDS)
    return projected


def project_rankings_response(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    """Tier-safe `/explore/rip-statistics/targets` response."""
    plus = has_index_feature_access(plan, FEATURE_SET_RIP_ANALYTICS)
    target_fields = _PLUS_TARGET_FIELDS if plus else _BASE_TARGET_FIELDS
    targets = [
        _pick(target, target_fields) if plus else _project_public_set_leaderboard_target(target)
        for target in payload.get("targets", []) if isinstance(target, Mapping)
    ]
    result: dict[str, Any] = {
        "targets": targets,
        "meta": _pick(payload.get("meta") or {}, _RANKINGS_META_FIELDS),
        "access": {"rankingsIntelligence": plus, "requiredPlan": "plus"},
    }
    default_target = payload.get("default_target") or payload.get("defaultTarget")
    if isinstance(default_target, Mapping):
        result["default_target"] = (
            _pick(default_target, target_fields) if plus
            else _project_public_set_leaderboard_target(default_target)
        )
    if plus:
        for key in ("setRip", "productFamilyRankings"):
            if key in payload:
                result[key] = payload[key]
    return result


_PUBLIC_ERA_FIELDS = frozenset({
    "eraName", "eraId", "rank", "score", "tier", "cohortSize",
    "modeledSetCount", "strongestSet", "constituentSets",
})
_PUBLIC_ERA_SET_FIELDS = frozenset({"setId", "setName", "score"})


def project_public_era_rankings_response(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Expose only the prepared fields rendered by the public Era leaderboard."""
    source = payload.get("eraSetStrengthV1")
    if not isinstance(source, Mapping):
        return {"cohortSize": 0, "eras": []}
    eras = []
    for row in source.get("eras", []):
        if not isinstance(row, Mapping):
            continue
        projected = _pick(row, _PUBLIC_ERA_FIELDS)
        strongest = row.get("strongestSet")
        projected["strongestSet"] = _pick(strongest, _PUBLIC_ERA_SET_FIELDS) if isinstance(strongest, Mapping) else None
        projected["constituentSets"] = [
            _pick(item, _PUBLIC_ERA_SET_FIELDS)
            for item in row.get("constituentSets", []) if isinstance(item, Mapping)
        ]
        eras.append(projected)
    return {"cohortSize": source.get("cohortSize"), "eras": eras}


_BASE_PRODUCT_RANKING_FIELDS = frozenset({
    "sealedProductId", "setId", "productName", "setName", "productFamily",
    "productFamilyLabel", "productImageUrl", "setCanonicalKey", "unitPrice", "marketPrice",
})
_PLUS_PRODUCT_RANKING_FIELDS = _BASE_PRODUCT_RANKING_FIELDS | frozenset({
    "budgetRank", "budgetCohortSize", "budgetTier", "budgetModelTier", "publicTier",
    "quantity", "actualCommittedCapital", "unusedCapital", "overallRipScore",
    "financialRipScore", "overallRipAbsoluteScore", "overallRipRelativeScore",
    "overallRipLeaderScore", "financialRipAbsoluteScore", "financialRipRelativeScore",
    "financialRipLeaderScore", "collectorAppealScore", "expectedValue",
    "chanceToRecoverCost", "familyRank", "familySize", "familyTier",
})


def project_product_rankings_response(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    plus = has_index_feature_access(plan, FEATURE_PRODUCT_RIP)
    fields = _PLUS_PRODUCT_RANKING_FIELDS if plus else _BASE_PRODUCT_RANKING_FIELDS
    return {
        "available": bool(payload.get("available")),
        "reason": payload.get("reason"),
        "selectedBudget": payload.get("selectedBudget"),
        "availableBudgets": payload.get("availableBudgets") or [],
        "cohortSize": payload.get("cohortSize", 0),
        "rows": [_pick(row, fields) for row in payload.get("rows", []) if isinstance(row, Mapping)],
        **({"authority": payload.get("authority") or {}} if plus else {}),
    }


def project_product_family_rankings_response(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    """Tier-safe nested Product Family Rankings publication."""
    plus = has_index_feature_access(plan, FEATURE_PRODUCT_RIP)
    fields = _PLUS_PRODUCT_RANKING_FIELDS if plus else _BASE_PRODUCT_RANKING_FIELDS
    source_families = payload.get("families") or {}
    families: dict[str, Any] = {}
    if isinstance(source_families, Mapping):
        for family_id, block in source_families.items():
            if not isinstance(block, Mapping):
                continue
            products = block.get("products") or block.get("rows") or []
            projected = _pick(block, frozenset({"label", "count", "productFamily", "productFamilyLabel"}))
            projected["products"] = [
                _pick(row, fields) for row in products if isinstance(row, Mapping)
            ]
            families[str(family_id)] = projected
    result = {"families": families}
    if plus:
        result.update(_pick(payload, frozenset({"authority", "authorityTargetCount"})))
    return result


_OPENING_SCOPE_FIELDS = frozenset({
    "averageCostPerPack", "averageModelBreakEvenPerPack", "averageEntertainmentCostPerPack",
    "modeledReturnOnSpend", "entertainmentCostShare", "meanOutcomeRetention",
    "chanceToRecoverCost", "typicalOpeningPerPack", "typicalRetention",
    "valuePerPackPercentiles", "normalizedReturnPercentiles", "setCount",
    "productSkuCount", "productFamilyCount",
})
_BASE_OPENING_BREAKDOWN_FIELDS = frozenset({
    "eraId", "eraName", "setId", "setName", "setCanonicalKey",
    "setCount", "productSkuCount", "productFamilyCount", "averageCostPerPack",
})


def project_opening_economics_response(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    """Keep the global educational contract public; tier detailed breakdowns."""
    plus = has_index_feature_access(plan, FEATURE_PACK_ECONOMICS)
    result = _pick(payload, frozenset({
        "status", "reason", "contractVersion", "basis", "methodology", "marketDate", "population",
    }))
    if isinstance(payload.get("global"), Mapping):
        result["global"] = _pick(payload["global"], _OPENING_SCOPE_FIELDS)
    else:
        result["global"] = None
    for key in ("eras", "sets"):
        result[key] = []
        for row in payload.get(key, []):
            if not isinstance(row, Mapping):
                continue
            projected = _pick(
                row,
                _OPENING_SCOPE_FIELDS | _BASE_OPENING_BREAKDOWN_FIELDS
                if plus else _BASE_OPENING_BREAKDOWN_FIELDS,
            )
            if plus and key == "sets":
                projected["familyEconomics"] = [
                    _pick(family, _OPENING_SCOPE_FIELDS | frozenset({"family"}))
                    for family in row.get("familyEconomics", []) if isinstance(family, Mapping)
                ]
            result[key].append(projected)
    result["familyBenchmarks"] = [
        _pick(row, _OPENING_SCOPE_FIELDS | frozenset({"family"}))
        for row in payload.get("familyBenchmarks", []) if plus and isinstance(row, Mapping)
    ]
    return result


_BASE_MARKET_TOP_LEVEL = frozenset({
    "set", "window", "window_key", "days", "latestMarketDate", "latest_market_date",
    "availableScopes", "available_scopes", "setValueHistoriesByScope",
    "set_value_histories_by_scope", "performanceVsCostHistory",
    "performance_vs_cost_history", "topChaseCards", "top_chase_cards",
    "topChaseCardHistories", "top_chase_card_histories", "marketMovers",
    "market_movers", "marketMoversByWindow", "market_movers_by_window", "meta",
})


def project_set_market_response(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    result = _pick(payload, _BASE_MARKET_TOP_LEVEL)
    for key in ("cardsMarket", "cards_market"):
        block = payload.get(key)
        if not isinstance(block, Mapping):
            continue
        safe = _pick(block, frozenset({
            "available", "status", "marketIndex", "market_index", "setValue",
            "set_value", "history", "asOf", "as_of", "source",
        }))
        if has_index_feature_access(plan, FEATURE_MARKET_BREADTH):
            for breadth_key in ("marketBreadth", "market_breadth"):
                if breadth_key in block:
                    safe[breadth_key] = block[breadth_key]
        result[key] = safe
    for contract_key in ("publicRipContractV10", "public_rip_contract_v10"):
        contract = payload.get(contract_key)
        if not isinstance(contract, Mapping):
            continue
        collector = contract.get("collectorAppeal") or contract.get("collector_appeal")
        if not isinstance(collector, Mapping):
            continue
        projected_subjects = []
        for subject in collector.get("topSubjects") or collector.get("top_subjects") or []:
            if not isinstance(subject, Mapping):
                continue
            projected_subject = _pick(subject, frozenset({
                "subjectName", "subject_name", "subjectId", "subject_id", "imageUrl", "image_url",
            }))
            for path_key in ("elitePath", "elite_path", "accessiblePath", "accessible_path"):
                path = subject.get(path_key)
                if not isinstance(path, Mapping):
                    continue
                allowed = {
                    "canonicalCardId", "canonical_card_id", "cardName", "card_name",
                    "imageUrl", "image_url", "modeledProbability", "modeled_probability",
                    "impliedOdds", "implied_odds",
                }
                if has_index_feature_access(plan, FEATURE_ACQUISITION_MILESTONES):
                    allowed.update({
                        "packsFor50PercentChance", "packs_for_50_percent_chance",
                        "packsFor90PercentChance", "packs_for_90_percent_chance",
                        "approximatePackSpend50", "approximate_pack_spend_50",
                        "approximatePackSpend90", "approximate_pack_spend_90",
                    })
                projected_subject[path_key] = _pick(path, frozenset(allowed))
            projected_subjects.append(projected_subject)
        result[contract_key] = {
            "collectorAppeal": {"topSubjects": projected_subjects}
        }
    return result


_BASE_SET_PAGE_FIELDS = frozenset({"target", "set", "meta"})
_PLUS_SET_PAGE_FIELDS = _BASE_SET_PAGE_FIELDS | frozenset({
    "summary", "interpretation", "rankings", "ripDecision", "rip_statistics",
    "percentiles", "distribution_bins", "threshold_bins", "history_trend",
    "top_hits", "openingDesirability", "pull_rate_assumptions",
    "cardDesirabilityValidation", "card_desirability_validation",
    "cardAppealMarketPriceCorrelation", "card_appeal_market_price_correlation",
    "rip", "ripCore", "financialRipV4", "overallRipV10", "publicRipContractV10",
    "openingExperience", "publicAnalyticsCohort", "publicAnalyticsStatus",
})


def project_set_page_response(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    fields = _PLUS_SET_PAGE_FIELDS if has_index_feature_access(plan, FEATURE_SET_RIP_ANALYTICS) else _BASE_SET_PAGE_FIELDS
    return _pick(payload, fields)


def project_card_detail_response(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    result = _pick(payload, frozenset({
        "set", "card", "availableVariants", "selectedVariantId", "variantSelection",
        "market", "meta",
    }))
    if has_index_feature_access(plan, FEATURE_PRODUCT_RIP) and "intelligence" in payload:
        result["intelligence"] = payload["intelligence"]
    if has_index_feature_access(plan, FEATURE_PRODUCT_RIP) and "treatmentMarketPrestige" in payload:
        result["treatmentMarketPrestige"] = payload["treatmentMarketPrestige"]
    if has_index_feature_access(plan, FEATURE_CARD_CHASE_EFFICIENCY) and "chase" in payload:
        result["chase"] = payload["chase"]
    return result


def project_sealed_product_detail_response(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    result = _pick(payload, frozenset({"set", "product", "market", "meta"}))
    if has_index_feature_access(plan, FEATURE_PRODUCT_RIP):
        result.update(_pick(payload, frozenset({"rip", "comparisons"})))
    return result


def project_sealed_market_response(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    result = _pick(payload, frozenset({
        "set", "marketDate", "defaultProductId", "setPageConsumerMarket",
        "setPageConsumerTopProducts", "meta",
    }))
    if has_index_feature_access(plan, FEATURE_MARKET_BREADTH):
        result.update(_pick(payload, frozenset({"products", "setMarket"})))
    return result


def project_insights_critical_response(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    if has_index_feature_access(plan, FEATURE_SET_RIP_ANALYTICS):
        return _pick(payload, frozenset({
            "ripDecision", "set", "summary", "recommendation", "ripScore", "rip",
            "ripCore", "financialRipV4", "overallRipV10", "publicRipContractV10",
            "openingExperience", "publicAnalyticsCohort", "publicAnalyticsStatus",
            "interpretation", "meta",
        }))
    return _pick(payload, frozenset({
        "set", "recommendation", "ripScore", "publicAnalyticsStatus", "meta",
    }))


def filter_set_market_signal_access(payload: Mapping[str, Any], plan: Any) -> dict[str, Any]:
    """Compatibility name for the allowlist-based market projector."""
    return project_set_market_response(payload, plan)


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
        "canBuildCustomMarkets": has_index_plus_access(plan),
        "canBuildSingleAxisMarket": has_index_plus_access(plan),
        "canBuildCompoundMarket": has_index_premium_access(plan),
        "canUseCustomRankedComposition": has_index_premium_access(plan),
    }
