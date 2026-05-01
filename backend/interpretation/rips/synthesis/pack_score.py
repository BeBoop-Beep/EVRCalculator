"""Pack Score synthesis from independent pillar interpretations."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..models import (
    EvidenceItem,
    PackScoreInterpretation,
    ProfitInterpretation,
    SafetyInterpretation,
    SectionInterpretation,
    StabilityInterpretation,
)
from ..thresholds import (
    IMBALANCE_GAP_POINTS,
    PILLAR_INTERPRETATION_WEIGHTS,
    build_pack_context,
    build_profit_context,
    build_safety_context,
    build_stability_context,
    classify_score_strength,
    get_numeric,
)

PILLAR_LABELS = {
    "profit": "Profit",
    "safety": "Safety",
    "stability": "Stability",
}

DECISION_LABELS = {
    "elite_open": "Elite rip profile",
    "strong_but_risky": "Strong, but risky",
    "good_open": "Solid rip profile",
    "above_average_but_flawed": "Better than average, with a catch",
    "good_value_shaky_path": "Good value, shaky path",
    "average_open": "Middle of the pack",
    "average_but_risky": "Average, but risky",
    "hit_dependent_open": "Needs the right hits",
    "below_average_open": "Below-average profile",
    "very_weak_open": "Very weak value profile",
    "bottom_tier_open": "Tough value profile",
    "okay_but_capped": "Safe, but not exciting",
    "safe_but_low_reward": "Low risk, low reward",
    "weak_open": "Weak value profile",
    "data_limited": "Not enough data",
}

DECISION_SEVERITY = {
    "elite_open": "positive",
    "strong_but_risky": "caution",
    "good_open": "positive",
    "above_average_but_flawed": "neutral",
    "good_value_shaky_path": "caution",
    "average_open": "neutral",
    "average_but_risky": "caution",
    "hit_dependent_open": "caution",
    "below_average_open": "negative",
    "very_weak_open": "negative",
    "bottom_tier_open": "negative",
    "okay_but_capped": "neutral",
    "safe_but_low_reward": "neutral",
    "weak_open": "negative",
    "data_limited": "data_limited",
}


def _pillar_scores(
    profit: ProfitInterpretation,
    safety: SafetyInterpretation,
    stability: StabilityInterpretation,
    data: Dict[str, Any],
) -> Dict[str, Optional[float]]:
    summary_data = data.get("summary") if isinstance(data.get("summary"), dict) else data
    return {
        "profit": profit.score if profit.score is not None else get_numeric(summary_data, "profit_score", "relative_profit_score"),
        "safety": safety.score if safety.score is not None else get_numeric(summary_data, "safety_score", "relative_safety_score"),
        "stability": stability.score if stability.score is not None else get_numeric(summary_data, "stability_score", "relative_stability_score"),
    }


def _strongest_weakest(scores: Dict[str, Optional[float]]) -> Tuple[str, str]:
    scored = [(pillar, score) for pillar, score in scores.items() if score is not None]
    if not scored:
        return ("profit", "safety")
    strongest = max(scored, key=lambda row: row[1])[0]
    weakest_candidates = sorted(scored, key=lambda row: row[1])
    weakest = weakest_candidates[0][0]
    if weakest == strongest and len(weakest_candidates) > 1:
        weakest = weakest_candidates[1][0]
    return strongest, weakest


def _format_rank(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"#{int(value)}"


def _strength_band(strength: Optional[int]) -> str:
    if strength is None:
        return "medium"
    if strength >= 4:
        return "high"
    if strength >= 2:
        return "medium"
    return "low"


def strength_to_band(strength: Optional[int]) -> str:
    if strength == 5:
        return "elite"
    if strength == 4:
        return "strong"
    if strength == 3:
        return "good"
    if strength == 2:
        return "average"
    if strength == 1:
        return "weak"
    return "dead"


def _is_dead(strength: Optional[int]) -> bool:
    return strength == 0


def _is_weak_or_dead(strength: Optional[int]) -> bool:
    return strength is not None and strength <= 1


def _is_average(strength: Optional[int]) -> bool:
    return strength == 2


def _is_good_plus(strength: Optional[int]) -> bool:
    return strength is not None and strength >= 3


def _is_strong_plus(strength: Optional[int]) -> bool:
    return strength is not None and strength >= 4


def _build_pillar_snapshot(
    pillar: str,
    score: Optional[float],
    summary_data: Dict[str, Any],
) -> Dict[str, Any]:
    if pillar == "profit":
        base = build_profit_context(summary_data)
    elif pillar == "safety":
        base = build_safety_context(summary_data)
    else:
        base = build_stability_context(summary_data)

    resolved_score = score if score is not None else base["score"]
    strength = base["strength"]
    weight = PILLAR_INTERPRETATION_WEIGHTS[pillar]
    weighted_impact = (strength * weight) if strength is not None else None
    drag_pressure = ((5 - strength) * weight) if strength is not None else None
    return {
        "score": resolved_score,
        "relative_score": base["relative_score"],
        "tier": base["tier"],
        "rank": base["rank"],
        "relative_rank": base["relative_rank"],
        "strength": strength,
        "weight": weight,
        "weighted_impact": weighted_impact,
        "drag_pressure": drag_pressure,
    }


def _pick_weighted_driver(pillars: Dict[str, Dict[str, Any]]) -> str:
    candidates = [
        (name, snapshot)
        for name, snapshot in pillars.items()
        if snapshot["weighted_impact"] is not None
    ]
    if not candidates:
        return "profit"
    return max(
        candidates,
        key=lambda item: (
            item[1]["weighted_impact"],
            item[1]["weight"],
            item[1]["strength"],
            -(item[1]["rank"] or 9999),
        ),
    )[0]


def _pick_weighted_drag(pillars: Dict[str, Dict[str, Any]]) -> str:
    candidates = [
        (name, snapshot)
        for name, snapshot in pillars.items()
        if snapshot["drag_pressure"] is not None
    ]
    if not candidates:
        return "safety"
    return max(
        candidates,
        key=lambda item: (
            item[1]["drag_pressure"],
            item[1]["weight"],
            -(item[1]["strength"] or 0),
            item[1]["rank"] or -1,
        ),
    )[0]


def _is_at_least(strength: Optional[int], threshold: int) -> bool:
    return strength is not None and strength >= threshold


def _is_at_most(strength: Optional[int], threshold: int) -> bool:
    return strength is not None and strength <= threshold


# ---------------------------------------------------------------------------
# Matrix classification helpers
# ---------------------------------------------------------------------------

_PROFIT_TIER_TO_LANE: Dict[str, str] = {
    "S": "elite_return",
    "A": "strong_return",
    "B": "good_return",
    "C": "average_return",
    "D": "weak_return",
    "F": "failing_return",
}


def classify_profit_lane(tier: Optional[str], strength: Optional[int]) -> str:
    """Map profit tier (preferred) or strength (fallback) to a profit_lane label."""
    if tier is not None:
        lane = _PROFIT_TIER_TO_LANE.get(str(tier).strip().upper())
        if lane:
            return lane
    if strength is None:
        return "average_return"
    if strength >= 5:
        return "elite_return"
    if strength >= 4:
        return "strong_return"
    if strength >= 3:
        return "good_return"
    if strength >= 2:
        return "average_return"
    if strength >= 1:
        return "weak_return"
    return "failing_return"


def classify_pillar_band(tier: Optional[str], strength: Optional[int]) -> str:
    """Map pillar tier (preferred) or strength (fallback) to high/medium/low band.

    Used for both safety_band and stability_band.
    S/A -> high, B/C -> medium, D/F -> low.
    """
    if tier is not None:
        normalized = str(tier).strip().upper()
        if normalized in {"S", "A"}:
            return "high"
        if normalized in {"B", "C"}:
            return "medium"
        if normalized in {"D", "F"}:
            return "low"
    if strength is None:
        return "medium"
    if strength >= 4:
        return "high"
    if strength >= 2:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Archetype matrix  (profit_lane : safety_band : stability_band -> archetype)
# ---------------------------------------------------------------------------

PACK_ARCHETYPE_MATRIX: Dict[str, Dict[str, str]] = {
    # ── ELITE RETURN ─────────────────────────────────────────────────────────
    "elite_return:high:high": {
        "label": "Elite rip profile",
        "summary": (
            "This is one of the strongest rip profiles in the current data. The cards pay back the pack price well, "
            "the misses are easier to handle than most sets, and value is spread across enough cards to avoid "
            "relying on one lucky pull."
        ),
        "reason_code": "elite_open",
    },
    "elite_return:high:medium": {
        "label": "Elite, some path risk",
        "summary": (
            "The return profile here is elite, and the misses are more manageable than most. "
            "The right hits still matter for the best outcomes, but the floor here is strong enough "
            "to keep the risk reasonable."
        ),
        "reason_code": "elite_open",
    },
    "elite_return:high:low": {
        "label": "Elite value, hit dependent",
        "summary": (
            "The return profile here is elite, and misses are easier to handle than most. "
            "The catch is that too much of that value depends on landing the right hits, "
            "so results can swing significantly from session to session."
        ),
        "reason_code": "elite_open",
    },
    "elite_return:medium:high": {
        "label": "Strong profile, watch misses",
        "summary": (
            "The return profile here is elite, and value is spread well across cards. "
            "Misses are about average, so bad packs are not painless, "
            "but the overall profile still stands out."
        ),
        "reason_code": "elite_open",
    },
    "elite_return:medium:medium": {
        "label": "Elite return, average risk",
        "summary": (
            "The return profile is elite for the price. "
            "Misses and value spread are both about average, which means the upside is real "
            "but results can vary meaningfully from session to session."
        ),
        "reason_code": "elite_open",
    },
    "elite_return:medium:low": {
        "label": "Good value, shaky path",
        "summary": (
            "The return profile is elite, but the path to it is fragile. "
            "Too much depends on landing the right hits, and missing them at this price point "
            "will leave the pack feeling thin."
        ),
        "reason_code": "good_value_shaky_path",
    },
    "elite_return:low:high": {
        "label": "Elite value, risky misses",
        "summary": (
            "This set has strong value for the price, and that value is spread well enough to avoid one-card dependence. "
            "The catch is that bad packs can still hurt, so a rough run of misses will add up quickly."
        ),
        "reason_code": "strong_but_risky",
    },
    "elite_return:low:medium": {
        "label": "Strong, but risky",
        "summary": (
            "This set has strong value for the price, and the value is spread well enough to avoid one-card dependence. "
            "The catch is that bad packs can still hurt, so this profile comes with real downside risk."
        ),
        "reason_code": "strong_but_risky",
    },
    "elite_return:low:low": {
        "label": "High upside, high risk",
        "summary": (
            "The return profile is elite, but it is a rough ride on both sides. "
            "Bad packs can hurt and too much of the value depends on landing the right hits. "
            "The ceiling is high, but so is the variance."
        ),
        "reason_code": "strong_but_risky",
    },
    # ── STRONG RETURN ─────────────────────────────────────────────────────────
    "strong_return:high:high": {
        "label": "Elite rip profile",
        "summary": (
            "This set has strong return potential for the price. "
            "Misses are easier to handle than most sets and value is spread across enough cards "
            "to avoid over-reliance on one pull. A genuinely strong profile."
        ),
        "reason_code": "elite_open",
    },
    "strong_return:high:medium": {
        "label": "Strong value, some path sensitivity",
        "summary": (
            "This set has strong return potential and the misses are more manageable than most. "
            "The right hits still help for the best outcomes, "
            "but the floor is solid enough to keep the overall profile worthwhile."
        ),
        "reason_code": "good_open",
    },
    "strong_return:high:low": {
        "label": "Strong, but hit dependent",
        "summary": (
            "This set has strong return potential and the misses are easier to handle. "
            "The catch is that too much depends on landing the right hits, "
            "so the experience swings more than the overall score suggests."
        ),
        "reason_code": "hit_dependent_open",
    },
    "strong_return:medium:high": {
        "label": "Strong value, solid spread",
        "summary": (
            "This set has strong return potential and value is spread well across cards. "
            "Misses are about average, which keeps the floor reasonable. "
            "This is a genuinely solid profile at the current pack price."
        ),
        "reason_code": "good_open",
    },
    "strong_return:medium:medium": {
        "label": "Solid rip profile",
        "summary": (
            "This is a solid rip profile. Return potential is strong, misses are about average, "
            "and value has decent spread. Not elite, but consistently strong value at the current pack price."
        ),
        "reason_code": "good_open",
    },
    "strong_return:medium:low": {
        "label": "Strong value, shaky path",
        "summary": (
            "This set has strong return potential, but the path to it is fragile. "
            "Value is concentrated on the right hits, "
            "and missing those makes the pack feel thin for the price."
        ),
        "reason_code": "good_value_shaky_path",
    },
    "strong_return:low:high": {
        "label": "Strong, but risky",
        "summary": (
            "This set has strong value for the price, and the value is spread well enough to avoid one-card dependence. "
            "The catch is that bad packs can still hurt, so a rough streak will add up."
        ),
        "reason_code": "strong_but_risky",
    },
    "strong_return:low:medium": {
        "label": "Strong value, rough misses",
        "summary": (
            "This set has strong return potential, but bad packs can hurt "
            "and the value path still depends on the right pulls. "
            "The upside is real, but the risk is real too."
        ),
        "reason_code": "strong_but_risky",
    },
    "strong_return:low:low": {
        "label": "Strong upside, high risk",
        "summary": (
            "This set has strong return potential, but it is fighting you on two fronts: "
            "the misses are rough and too much depends on landing the right hits. "
            "High ceiling, high variance."
        ),
        "reason_code": "strong_but_risky",
    },
    # ── GOOD RETURN ───────────────────────────────────────────────────────────
    "good_return:high:high": {
        "label": "Good, solid profile",
        "summary": (
            "This set has good value for the price. "
            "Misses are manageable and value is spread well enough to make this a consistent option, "
            "even if it is not in the elite tier."
        ),
        "reason_code": "good_open",
    },
    "good_return:high:medium": {
        "label": "Good value, easier misses",
        "summary": (
            "This set has good value for the price and the misses are more forgiving than most. "
            "The right hits still improve the outcome, "
            "but the floor is comfortable enough to keep opening reasonable."
        ),
        "reason_code": "good_open",
    },
    "good_return:high:low": {
        "label": "Good value, hit dependent",
        "summary": (
            "This set has good return potential and the misses are easier to handle. "
            "The catch is that too much of the upside depends on landing specific hits, "
            "so the experience is more variable than the overall score suggests."
        ),
        "reason_code": "hit_dependent_open",
    },
    "good_return:medium:high": {
        "label": "Good value, well spread",
        "summary": (
            "This set has good value for the price and spreads it well across cards. "
            "Misses are about average, which keeps the floor reasonable without being painless. "
            "A dependable profile."
        ),
        "reason_code": "good_open",
    },
    "good_return:medium:medium": {
        "label": "Solid rip profile",
        "summary": (
            "This is a solid rip profile. Value is good for the price, misses are about average, "
            "and value has some spread. Not elite, but a genuinely decent option at the current pack cost."
        ),
        "reason_code": "good_open",
    },
    "good_return:medium:low": {
        "label": "Good value, shaky path",
        "summary": (
            "This set has enough value to be interesting, but the value path is fragile. "
            "You need the right hits for the pack to feel worth it, "
            "and missing them leaves you feeling the price."
        ),
        "reason_code": "good_value_shaky_path",
    },
    "good_return:low:high": {
        "label": "Good value, risky misses",
        "summary": (
            "This set has good return potential and value is spread well. "
            "The weak point is that bad packs can still hurt, "
            "so the experience depends on your run of packs."
        ),
        "reason_code": "above_average_but_flawed",
    },
    "good_return:low:medium": {
        "label": "Good value, rough misses",
        "summary": (
            "This set has good value for the price, but bad packs can hurt "
            "and the right hits still matter. "
            "The upside is there, but the risk is real enough to factor in."
        ),
        "reason_code": "above_average_but_flawed",
    },
    "good_return:low:low": {
        "label": "Good value, real risk",
        "summary": (
            "This set has good return potential, but it is fighting you on two fronts: "
            "the misses are rough and too much depends on landing the right hits. "
            "The value is there if everything goes right."
        ),
        "reason_code": "above_average_but_flawed",
    },
    # ── AVERAGE RETURN ────────────────────────────────────────────────────────
    "average_return:high:high": {
        "label": "Safe, consistent, average",
        "summary": (
            "This set is around average for return. "
            "Misses are easier than most and value is spread well, "
            "but the rewards are not strong enough to make this set stand out from the pack."
        ),
        "reason_code": "okay_but_capped",
    },
    "average_return:high:medium": {
        "label": "Average, safer misses",
        "summary": (
            "This set is around average for return, but the misses are more forgiving than most. "
            "The value is not exciting, but you will not be punished hard for bad packs."
        ),
        "reason_code": "okay_but_capped",
    },
    "average_return:high:low": {
        "label": "Average, safer but hit dependent",
        "summary": (
            "This set is around average for return with easier misses, "
            "but too much of what value there is depends on landing specific hits. "
            "Manageable floor, but a ceiling that is hard to reach consistently."
        ),
        "reason_code": "okay_but_capped",
    },
    "average_return:medium:high": {
        "label": "Average, decent spread",
        "summary": (
            "This set is around average for return. "
            "Value is spread reasonably well, but the returns are not compelling enough "
            "to push it above the rest of the pack."
        ),
        "reason_code": "average_open",
    },
    "average_return:medium:medium": {
        "label": "Middle of the pack",
        "summary": (
            "This is an average value profile. "
            "There is some value, but it does not clearly stand out from other sets at this price point."
        ),
        "reason_code": "average_open",
    },
    "average_return:medium:low": {
        "label": "Average, shaky path",
        "summary": (
            "This set is around average for return, but the value path is fragile. "
            "You still need the right hits to get anywhere close to what the pack costs, "
            "which adds meaningful uncertainty."
        ),
        "reason_code": "average_open",
    },
    "average_return:low:high": {
        "label": "Average, but risky",
        "summary": (
            "This set is around average for return, but bad packs can hurt. "
            "The spread of value is reasonable, "
            "but the downside risk is higher than the value level justifies."
        ),
        "reason_code": "average_but_risky",
    },
    "average_return:low:medium": {
        "label": "Average, rough misses",
        "summary": (
            "This set has average return potential, but bad packs can hurt. "
            "The value is not strong enough to offset the downside pressure, "
            "making this harder to justify at the current price."
        ),
        "reason_code": "average_but_risky",
    },
    "average_return:low:low": {
        "label": "Average, but risky",
        "summary": (
            "This set has average return potential, but it comes with real risk on both fronts: "
            "the misses are rough and too much depends on the right hits. "
            "Average value with above-average downside."
        ),
        "reason_code": "average_but_risky",
    },
    # ── WEAK RETURN ───────────────────────────────────────────────────────────
    "weak_return:high:high": {
        "label": "Low risk, low reward",
        "summary": (
            "Misses are easier to handle and value is spread across enough cards. "
            "The problem is the wins are not big enough to make this an exciting open "
            "at the current pack price."
        ),
        "reason_code": "safe_but_low_reward",
    },
    "weak_return:high:medium": {
        "label": "Weak, safer misses",
        "summary": (
            "This set is weak on return because the cards are not paying back the pack price well enough. "
            "The saving grace is that misses are more manageable than most, "
            "which limits the damage from bad packs."
        ),
        "reason_code": "safe_but_low_reward",
    },
    "weak_return:high:low": {
        "label": "Weak, safer but hit dependent",
        "summary": (
            "This set is weak on return and what value it has depends too much on specific hits. "
            "At least the misses are more forgiving than most sets, "
            "but that does not fix the core return problem."
        ),
        "reason_code": "safe_but_low_reward",
    },
    "weak_return:medium:high": {
        "label": "Weak return, decent spread",
        "summary": (
            "This set is weak on return. The value is spread across cards, "
            "but there is not enough of it to justify the pack price consistently. "
            "Average misses do not change the overall weak picture."
        ),
        "reason_code": "below_average_open",
    },
    "weak_return:medium:medium": {
        "label": "Weak value profile",
        "summary": (
            "This is a weak value profile at the current pack price. The cards are not paying back the pack price well enough."
        ),
        "reason_code": "weak_open",
    },
    "weak_return:medium:low": {
        "label": "Weak, needs the right hits",
        "summary": (
            "This set is weak on return and the value is too dependent on landing specific hits. "
            "Average misses do not save it, and missing the key cards makes the price feel steep."
        ),
        "reason_code": "weak_open",
    },
    "weak_return:low:high": {
        "label": "Weak return, rough misses",
        "summary": (
            "This set is weak on return and the misses are rough. "
            "The spread of value is reasonable, but the overall package is not delivering enough "
            "for the current pack price."
        ),
        "reason_code": "very_weak_open",
    },
    "weak_return:low:medium": {
        "label": "Weak and risky",
        "summary": (
            "This set is weak on return and the misses are rough. "
            "The value is not paying back the pack price, "
            "and when you miss, the downside adds up quickly."
        ),
        "reason_code": "very_weak_open",
    },
    "weak_return:low:low": {
        "label": "Very weak value profile",
        "summary": (
            "This is a very weak value profile at the current pack price. "
            "The cards are not paying back the pack price, the misses are painful, "
            "and too much depends on landing the right hits."
        ),
        "reason_code": "very_weak_open",
    },
    # ── FAILING RETURN ────────────────────────────────────────────────────────
    "failing_return:high:high": {
        "label": "Low reward, safer misses",
        "summary": (
            "This set is failing on return, but it has an unusual quality: "
            "misses are more manageable than most and value is spread across cards. "
            "The issue is the cards are simply not coming close enough to the pack price."
        ),
        "reason_code": "safe_but_low_reward",
    },
    "failing_return:high:medium": {
        "label": "Low reward, safer misses",
        "summary": (
            "This set is failing on return because the cards are not coming close enough to the pack price. "
            "The misses are more forgiving than most, but that does not fix the core return problem."
        ),
        "reason_code": "safe_but_low_reward",
    },
    "failing_return:high:low": {
        "label": "Failing, safer but hit dependent",
        "summary": (
            "This set is failing on return and the little value it has depends too much on landing specific hits. "
            "At least the misses are more forgiving than most sets, "
            "but the return shortfall remains the main issue."
        ),
        "reason_code": "safe_but_low_reward",
    },
    "failing_return:medium:high": {
        "label": "Failing return, decent spread",
        "summary": (
            "This set is failing on return. The value is spread across cards, "
            "but there is not enough of it to justify the pack price. "
            "Average misses make an already tough profile harder to defend."
        ),
        "reason_code": "bottom_tier_open",
    },
    "failing_return:medium:medium": {
        "label": "Tough value profile",
        "summary": (
            "This set is failing on return because the cards are not coming close enough to the pack price. "
            "Misses are about average and value concentration adds more pressure on an already difficult profile."
        ),
        "reason_code": "bottom_tier_open",
    },
    "failing_return:medium:low": {
        "label": "Failing, shaky path",
        "summary": (
            "This set is failing on return and the value depends too much on the right hits. "
            "The combination of weak value and concentration risk makes this one of the harder profiles to justify at the current price."
        ),
        "reason_code": "bottom_tier_open",
    },
    "failing_return:low:high": {
        "label": "Failing return, rough misses",
        "summary": (
            "This set is failing on return and the misses are rough. "
            "The value is spread reasonably, but the overall package is not delivering enough for the price, "
            "and the downside is painful."
        ),
        "reason_code": "bottom_tier_open",
    },
    "failing_return:low:medium": {
        "label": "Failing return, rough misses",
        "summary": (
            "This set is failing on return and the misses are rough. "
            "The cards are not coming close to the pack price, "
            "and when you miss, the downside makes it worse."
        ),
        "reason_code": "bottom_tier_open",
    },
    "failing_return:low:low": {
        "label": "Tough value profile",
        "summary": (
            "This profile is fighting you on all three fronts: "
            "the cards are not paying back the pack price, the misses are brutal, "
            "and there is not enough value spread to help. "
            "One of the toughest value profiles in the current data."
        ),
        "reason_code": "bottom_tier_open",
    },
}

_FALLBACK_ARCHETYPE: Dict[str, str] = {
    "label": "Middle of the pack",
    "summary": "This is an average value profile. There is some value, but it does not clearly stand out.",
    "reason_code": "average_open",
}


def _resolve_archetype(matrix_key: str) -> Dict[str, str]:
    """Return the archetype dict for the given matrix_key, with a safe fallback."""
    return PACK_ARCHETYPE_MATRIX.get(matrix_key, _FALLBACK_ARCHETYPE)


def _decision_summary(category: str) -> str:
    summaries = {
        "elite_open": "This is one of the stronger rip profiles in the current data. The cards pay back the pack price well and the bad packs are not bad enough to ruin it.",
        "strong_but_risky": "This set has good hits for the price, but bad packs can still hurt. It ranks well because the winning pulls are strong enough to carry that risk.",
        "good_open": "This is a solid rip profile. The cards pay back better than many sets at the current pack price.",
        "above_average_but_flawed": "This is a better-than-average value profile, but it has a clear catch: either misses hurt or the value depends on specific hits.",
        "good_value_shaky_path": "This set has enough value to be interesting, but too much depends on landing the right hits.",
        "average_open": "This is an average value profile. There is some value, but it does not clearly stand out.",
        "average_but_risky": "This is an average value profile with real downside risk. The misses are rough enough to factor in.",
        "hit_dependent_open": "This set can pay off, but too much of the value depends on landing specific cards.",
        "below_average_open": "This is a below-average value profile. Either the return is weak or the misses are too harsh to offset it.",
        "weak_open": "This is a weak value profile at the current pack price. The cards are not paying back the pack price well enough.",
        "very_weak_open": "This is a very weak value profile at the current pack price. The cards are not paying back the price, and the misses are still painful.",
        "bottom_tier_open": "This is one of the toughest value profiles in the current data: the cards are not paying back the pack price, the misses are brutal, and there is not enough value spread to help.",
        "okay_but_capped": "This set has some protection when you miss, but the rewards are too limited to stand out.",
        "safe_but_low_reward": "The misses are more manageable than most sets, but the wins are not big enough to make the top end exciting.",
        "data_limited": "There is not enough data yet to evaluate this profile.",
    }
    return summaries[category]


def _primary_reason(weighted_driver: str) -> str:
    reasons = {
        "profit": "Cards are paying back well for the pack price.",
        "safety": "Bad packs are less painful than usual.",
        "stability": "Value is spread across enough cards.",
    }
    return reasons[weighted_driver]


def _main_catch(weighted_drag: str) -> str:
    if weighted_drag == "profit":
        return "The wins are not strong enough for the price."
    if weighted_drag == "safety":
        return "Bad packs can still hurt."
    if weighted_drag == "stability":
        return "Too much depends on landing the right hits."
    return "The overall read still has a meaningful weak spot."


def _resolve_reason_and_catch(category: str, weighted_driver: str, weighted_drag: str) -> tuple[str, str]:
    if category == "bottom_tier_open":
        return (
            "Too many parts of the rip look weak.",
            "This profile gets very little help from price, misses, or value spread.",
        )

    if category == "very_weak_open":
        return (
            "Cards are not paying back the pack price.",
            "Misses are still painful.",
        )

    if category == "good_value_shaky_path":
        return (
            "Cards can pay back well for the price.",
            "Too much depends on landing the right hits.",
        )

    if category == "above_average_but_flawed":
        return (
            "This set is better than average overall.",
            _main_catch(weighted_drag),
        )

    return _primary_reason(weighted_driver), _main_catch(weighted_drag)


def _determine_decision_category(
    pillars: Dict[str, Dict[str, Any]],
) -> tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Classify decision category using the profit-primary archetype matrix.

    Returns (decision_category, profit_lane, safety_band, stability_band, matrix_key).
    Returns ("data_limited", None, None, None, None) when profit data is missing.
    """
    profit_tier = pillars["profit"].get("tier")
    profit_strength = pillars["profit"]["strength"]
    safety_tier = pillars["safety"].get("tier")
    safety_strength = pillars["safety"]["strength"]
    stability_tier = pillars["stability"].get("tier")
    stability_strength = pillars["stability"]["strength"]

    # Require at least profit information to classify
    if profit_strength is None and profit_tier is None:
        return "data_limited", None, None, None, None

    profit_lane = classify_profit_lane(profit_tier, profit_strength)
    safety_band = classify_pillar_band(safety_tier, safety_strength)
    stability_band = classify_pillar_band(stability_tier, stability_strength)
    matrix_key = f"{profit_lane}:{safety_band}:{stability_band}"
    archetype = _resolve_archetype(matrix_key)
    return archetype["reason_code"], profit_lane, safety_band, stability_band, matrix_key


def interpret_pack_score(
    profit: ProfitInterpretation,
    safety: SafetyInterpretation,
    stability: StabilityInterpretation,
    data: Dict[str, Any] | None = None,
) -> PackScoreInterpretation:
    payload = data or {}
    scores = _pillar_scores(profit, safety, stability, payload)
    summary_data = payload.get("summary") if isinstance(payload.get("summary"), dict) else payload

    pillars = {
        "profit": _build_pillar_snapshot("profit", scores["profit"], summary_data),
        "safety": _build_pillar_snapshot("safety", scores["safety"], summary_data),
        "stability": _build_pillar_snapshot("stability", scores["stability"], summary_data),
    }
    pack_snapshot = build_pack_context(summary_data)

    strengths = {
        name: classify_score_strength(snapshot["score"])
        for name, snapshot in pillars.items()
    }

    strongest, weakest = _strongest_weakest(scores)

    numeric_scores = [s for s in scores.values() if s is not None]
    imbalance = False
    if len(numeric_scores) >= 2:
        imbalance = (max(numeric_scores) - min(numeric_scores)) >= IMBALANCE_GAP_POINTS

    unique_strengths = set(strengths.values())
    if unique_strengths == {"high"}:
        alignment = "all_strong"
    elif unique_strengths == {"low"}:
        alignment = "all_weak"
    elif len(unique_strengths) == 1:
        alignment = "uniform_mid"
    else:
        alignment = "mixed"

    profit_tail_driven = (
        profit.signals.get("upside_strength") == "high"
        and profit.signals.get("profit_frequency") in {"low", "medium"}
    )

    weighted_driver = _pick_weighted_driver(pillars)
    weighted_drag = _pick_weighted_drag(pillars)

    # Matrix-based classification: profit is the primary axis
    decision_category, profit_lane, safety_band_val, stability_band_val, matrix_key = (
        _determine_decision_category(pillars)
    )

    # Resolve archetype for label and summary
    if decision_category == "data_limited":
        archetype: Optional[Dict[str, str]] = None
        summary = _decision_summary("data_limited")
        label = DECISION_LABELS["data_limited"]
    else:
        archetype = _resolve_archetype(matrix_key)  # type: ignore[arg-type]
        summary = archetype["summary"]
        label = archetype["label"]

    p95_to_cost = get_numeric(summary_data, "p95_value_to_cost_ratio")
    if decision_category != "data_limited" and p95_to_cost is not None and p95_to_cost < 1.0:
        caveat = "High-end payoff is weak at the current pack price."
        if caveat not in summary:
            summary = f"{summary} {caveat}".strip()

    reason_code = decision_category
    severity = DECISION_SEVERITY[decision_category]

    # Weighted driver/drag corrections keyed on decision category
    if decision_category == "strong_but_risky" and weighted_driver != "profit" and profit_tail_driven:
        weighted_driver = "profit"
    if decision_category in {"okay_but_capped", "safe_but_low_reward", "weak_open", "very_weak_open", "bottom_tier_open"} and weighted_drag != "profit":
        weighted_drag = "profit"
    if decision_category in {"good_value_shaky_path", "hit_dependent_open"} and weighted_drag != "stability":
        weighted_drag = "stability"

    primary_reason, main_catch = _resolve_reason_and_catch(decision_category, weighted_driver, weighted_drag)

    evidence = [
        EvidenceItem("Main reason", primary_reason),
        EvidenceItem("Watch out for", main_catch),
    ]

    if pack_snapshot["tier"] is not None and pack_snapshot["rank"] is not None:
        evidence.append(
            EvidenceItem(
                "Compared with other sets",
                f"Pack tier {pack_snapshot['tier']}, rank {_format_rank(pack_snapshot['rank'])}",
            )
        )

    meta = SectionInterpretation(
        summary=summary,
        label=label,
        reason_code=reason_code,
        severity=severity,
        confidence="high" if len(numeric_scores) == 3 else ("medium" if numeric_scores else "low"),
        evidence=evidence,
        signals={
            "decision_category": decision_category,
            "alignment": alignment,
            "imbalance": imbalance,
            "strongest_pillar": strongest,
            "weakest_pillar": weakest,
            "weighted_driver": weighted_driver,
            "weighted_drag": weighted_drag,
            "primary_reason": primary_reason,
            "main_catch": main_catch,
            "interpretation_weights": dict(PILLAR_INTERPRETATION_WEIGHTS),
            # Matrix classification signals
            "profit_lane": profit_lane,
            "safety_band": safety_band_val,
            "stability_band": stability_band_val,
            "matrix_key": matrix_key,
            "pack_archetype": archetype["reason_code"] if archetype else None,
            # Legacy band signals
            "pack_band": strength_to_band(pack_snapshot["strength"]),
            "profit_band": strength_to_band(pillars["profit"]["strength"]),
            "safety_tier_band": strength_to_band(pillars["safety"]["strength"]),
            "stability_tier_band": strength_to_band(pillars["stability"]["strength"]),
            "pack": pack_snapshot,
            "pillars": pillars,
            **{f"{k}_strength": v for k, v in strengths.items()},
            **{f"{k}_tier_strength": _strength_band(snapshot["strength"]) for k, snapshot in pillars.items()},
        },
    )

    return PackScoreInterpretation(
        summary=summary,
        strongest_pillar=strongest,
        weakest_pillar=weakest,
        alignment=alignment,
        imbalance=imbalance,
        pillar_strengths=strengths,
        meta=meta,
    )
