"""RIP interpretation engine orchestrating pillar + synthesis layers."""

from __future__ import annotations

import dataclasses
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from .models import SectionInterpretation
from .pillars.profit import interpret_profit
from .pillars.safety import interpret_safety
from .pillars.stability import interpret_stability
from .sections.advanced_metrics import interpret_advanced_metrics
from .sections.historical_trend import interpret_historical_trend
from .sections.outcome_distribution import interpret_outcome_distribution
from .sections.pack_breakdown import interpret_pack_breakdown
from .sections.rarity_contribution import interpret_rarity_contribution
from .sections.top_ev_drivers import interpret_top_ev_drivers
from .synthesis.pack_score import interpret_pack_score
from .thresholds import format_percent, format_ratio, get_numeric, get_summary_data, get_tier


BIG_HIT_UPSIDE_LABEL = "Big Hit Upside"
GOD_PULL_UPSIDE_LABEL = "God Pull Upside"
BIG_HIT_UPSIDE_HELPER = "P95 outcome vs pack cost"
GOD_PULL_UPSIDE_HELPER = "P99 outcome vs pack cost"

_RARITY_BUCKET_MERGE_MAP = {
    "ultra rare": "ultra_ex",
    "ex": "ultra_ex",
}

_RARITY_BUCKET_LABELS = {
    "special illustration rare": "Special Illustration Rare",
    "illustration rare": "Illustration Rare",
    "ultra_ex": "Ultra Rare / ex",
    "double rare": "Double Rare",
    "hyper rare": "Hyper Rare",
}

_CARD_FAMILY_REMOVE_PATTERNS = [
    r"\bspecial\s+illustration\s+rare\b",
    r"\billustration\s+rare\b",
    r"\bfull\s+art\b",
    r"\bultra\s+rare\b",
    r"\bdouble\s+rare\b",
    r"\bhyper\s+rare\b",
    r"\bsecret\s+rare\b",
    r"\balternate\s+art\b",
    r"\balt\s+art\b",
    r"\bpromo\b",
    r"\bsir\b",
    r"\bir\b",
    r"\bfa\b",
    r"\bar\b",
    r"\bsar\b",
    r"\bur\b",
]

_EXPLICIT_CLUSTER_MIN_COUNT = 3
_EXPLICIT_CLUSTER_MIN_SHARE = 0.22
_EXPLICIT_PAIR_MIN_SHARE = 0.32
_EXPLICIT_TOP5_PAIR_MIN_SHARE = 0.25

_ENTITY_CLUSTER_MIN_COUNT = 3
_ENTITY_CLUSTER_MIN_SHARE = 0.25
_ENTITY_PAIR_MIN_SHARE = 0.35

_SINGLE_OUTLIER_SHARE_MIN = 0.28
_SINGLE_OUTLIER_RATIO_HARD = 1.75
_SINGLE_OUTLIER_RATIO_CLEAR = 1.35


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_rarity_bucket_for_signal(rarity: Any) -> str:
    from .thresholds import normalize_rarity_name

    normalized = normalize_rarity_name(rarity)
    if normalized == "unknown":
        return "unknown"
    return _RARITY_BUCKET_MERGE_MAP.get(normalized, normalized)


def _rarity_bucket_label_for_signal(bucket: str) -> str:
    return _RARITY_BUCKET_LABELS.get(bucket, bucket.replace("_", " ").title())


def _normalize_card_family_name(card_name: Any) -> str:
    text = str(card_name or "").strip().lower()
    if not text:
        return ""

    # Remove collector/set numbers like "#123", "123/197", "sv2 145".
    text = re.sub(r"\b#?\d+\s*/\s*\d+\b", " ", text)
    text = re.sub(r"\bsv\d+[a-z]*\s*\d+\b", " ", text)
    text = re.sub(r"\b#\d+\b", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)

    for pattern in _CARD_FAMILY_REMOVE_PATTERNS:
        text = re.sub(pattern, " ", text)

    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text


def _normalize_explicit_card_name(card_name: Any) -> str:
    text = str(card_name or "").strip().lower()
    if not text:
        return ""

    text = text.replace("’", "'")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\b#?\d+\s*/\s*\d+\b", " ", text)
    text = re.sub(r"\bsv\d+[a-z]*\s*\d+\b", " ", text)
    text = re.sub(r"\b[a-z]{1,4}\d{1,4}\b", " ", text)
    text = re.sub(r"\b#\d+\b", " ", text)

    for pattern in _CARD_FAMILY_REMOVE_PATTERNS:
        text = re.sub(pattern, " ", text)

    text = re.sub(r"\b(alt|alternate)\b", " ", text)
    text = re.sub(r"\b(art|rare|holo|foil|promo)\b", " ", text)
    text = re.sub(r"[^a-z0-9'\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text


def _derive_entity_name(explicit_name: str) -> str:
    text = str(explicit_name or "").strip().lower()
    if not text:
        return ""

    text = re.sub(r"\b(vmax|vstar|gx|ex|v)\b", " ", text)
    # Broad entity fallback can drop ownership prefix to merge related cards when explicit clusters do not dominate.
    text = re.sub(r"^(team\s+rocket's)\s+", "", text)
    text = re.sub(r"^[a-z]+'s\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text


def _display_name_from_normalized(normalized_name: str) -> str:
    token_map = {
        "ex": "ex",
        "v": "V",
        "vmax": "VMAX",
        "vstar": "VSTAR",
        "gx": "GX",
    }

    def _cap_token(token: str) -> str:
        if "'" in token:
            left, right = token.split("'", 1)
            return f"{left.capitalize()}'{right}"
        return token.capitalize()

    tokens: List[str] = []
    for token in str(normalized_name or "").split():
        if token in token_map:
            tokens.append(token_map[token])
        else:
            tokens.append(_cap_token(token))
    return " ".join(tokens).strip()


def _display_card_family_name(normalized_family: str) -> str:
    token_map = {
        "ex": "ex",
        "v": "V",
        "vmax": "VMAX",
        "vstar": "VSTAR",
        "gx": "GX",
        "lv": "Lv",
    }
    tokens = []
    for token in normalized_family.split():
        tokens.append(token_map.get(token, token.capitalize()))
    return " ".join(tokens).strip()


def _build_single_card_outlier_signal(top_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not top_rows:
        return {
            "type": "none",
            "card_name": None,
            "top_card_ev_contribution": None,
            "second_card_ev_contribution": None,
            "lead_ratio": None,
            "top_card_share_of_top_hits": None,
            "reason_code": "insufficient_top_hits",
        }

    total_top_ev = sum(row["ev_contribution"] for row in top_rows)
    top = top_rows[0]
    second = top_rows[1] if len(top_rows) > 1 else None

    top_ev = top["ev_contribution"]
    second_ev = second["ev_contribution"] if second else None
    lead_ratio = (top_ev / second_ev) if second_ev and second_ev > 0 else None
    top_share = (top_ev / total_top_ev) if total_top_ev > 0 else None

    top_pack_share = _to_float(top.get("pack_value_share"))
    second_pack_share = _to_float(second.get("pack_value_share")) if second else None
    pack_share_ratio = (
        top_pack_share / second_pack_share
        if top_pack_share is not None and second_pack_share is not None and second_pack_share > 0
        else None
    )

    hard_outlier = bool(
        (
            top_share is not None
            and top_share >= _SINGLE_OUTLIER_SHARE_MIN
            and lead_ratio is not None
            and lead_ratio >= _SINGLE_OUTLIER_RATIO_CLEAR
        )
        or (lead_ratio is not None and lead_ratio >= _SINGLE_OUTLIER_RATIO_HARD)
        or (pack_share_ratio is not None and pack_share_ratio >= _SINGLE_OUTLIER_RATIO_HARD)
    )
    clear_leader = bool(lead_ratio is not None and lead_ratio >= _SINGLE_OUTLIER_RATIO_CLEAR)

    if hard_outlier:
        signal_type = "hard_single_card_outlier"
        reason_code = "single_card_outlier"
    elif clear_leader:
        signal_type = "clear_single_card_leader"
        reason_code = "clear_top_card"
    else:
        signal_type = "none"
        reason_code = "no_clear_top_card"

    return {
        "type": signal_type,
        "card_name": top.get("card_name"),
        "top_card_ev_contribution": top_ev,
        "second_card_ev_contribution": second_ev,
        "lead_ratio": lead_ratio,
        "top_card_share_of_top_hits": top_share,
        "top_card_pack_value_share": top_pack_share,
        "second_card_pack_value_share": second_pack_share,
        "pack_share_ratio": pack_share_ratio,
        "reason_code": reason_code,
    }


def _build_name_pattern_signal(top_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not top_rows:
        return {
            "exact_family": {"type": "none"},
            "entity_cluster": {"type": "none"},
            "primary_name_pattern": {
                "type": "none",
                "name": None,
                "summary_phrase": None,
                "confidence": "low",
            },
        }

    total_top_ev = sum(row["ev_contribution"] for row in top_rows)
    explicit_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    entity_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for idx, row in enumerate(top_rows, start=1):
        explicit_key = _normalize_explicit_card_name(row.get("card_name"))
        if explicit_key:
            explicit_rows[explicit_key].append({**row, "rank": idx})
            entity_key = _derive_entity_name(explicit_key)
            if entity_key:
                entity_rows[entity_key].append({**row, "rank": idx})

    def _rank_cluster(rows_by_key: Dict[str, List[Dict[str, Any]]]) -> tuple[Optional[str], List[Dict[str, Any]], Optional[float]]:
        ranked = sorted(
            rows_by_key.items(),
            key=lambda item: (
                sum(r["ev_contribution"] for r in item[1]),
                len(item[1]),
                -min(r["rank"] for r in item[1]),
            ),
            reverse=True,
        )
        if not ranked:
            return None, [], None
        key, rows = ranked[0]
        share = (sum(r["ev_contribution"] for r in rows) / total_top_ev) if total_top_ev > 0 else None
        return key, rows, share

    exact_key, exact_rows, exact_share = _rank_cluster(explicit_rows)
    entity_key, entity_rows_list, entity_share = _rank_cluster(entity_rows)

    def _rows_to_examples(rows: List[Dict[str, Any]], limit: int = 4) -> List[str]:
        return [str(r.get("card_name") or "") for r in rows[:limit] if str(r.get("card_name") or "").strip()]

    exact_positions = [int(r["rank"]) for r in exact_rows]
    exact_top5_count = sum(1 for pos in exact_positions if pos <= 5)
    exact_dominant = bool(
        exact_key
        and exact_share is not None
        and (
            (len(exact_rows) >= _EXPLICIT_CLUSTER_MIN_COUNT and exact_share >= _EXPLICIT_CLUSTER_MIN_SHARE)
            or (len(exact_rows) >= 2 and exact_share >= _EXPLICIT_PAIR_MIN_SHARE)
            or (len(exact_rows) >= 2 and exact_top5_count >= 2 and exact_share >= _EXPLICIT_TOP5_PAIR_MIN_SHARE)
        )
    )

    entity_positions = [int(r["rank"]) for r in entity_rows_list]
    entity_top6_count = sum(1 for pos in entity_positions if pos <= 6)
    entity_dominant = bool(
        entity_key
        and entity_share is not None
        and (
            (len(entity_rows_list) >= _ENTITY_CLUSTER_MIN_COUNT and entity_share >= _ENTITY_CLUSTER_MIN_SHARE)
            or (len(entity_rows_list) >= 2 and entity_share >= _ENTITY_PAIR_MIN_SHARE)
            or (len(entity_rows_list) >= _ENTITY_CLUSTER_MIN_COUNT and entity_top6_count >= 2)
        )
    )

    exact_signal = {
        "type": "dominant_exact_family" if exact_dominant else ("mixed_exact_families" if exact_key else "none"),
        "family_name": _display_name_from_normalized(exact_key or "") if exact_key else None,
        "family_count": len(exact_rows),
        "family_ev_share_of_top_hits": exact_share,
        "family_rank_positions": exact_positions,
        "example_cards": _rows_to_examples(exact_rows),
        "reason_code": "explicit_family_dominant" if exact_dominant else "explicit_family_not_dominant",
    }

    entity_signal = {
        "type": "dominant_entity_cluster" if (entity_dominant and not exact_dominant) else ("mixed_entities" if entity_key else "none"),
        "entity_name": _display_name_from_normalized(entity_key or "") if entity_key else None,
        "entity_count": len(entity_rows_list),
        "entity_ev_share_of_top_hits": entity_share,
        "entity_rank_positions": entity_positions,
        "example_cards": _rows_to_examples(entity_rows_list),
        "reason_code": "entity_cluster_dominant" if (entity_dominant and not exact_dominant) else "entity_cluster_not_dominant",
    }

    if exact_dominant:
        primary = {
            "type": "explicit_name_cluster",
            "name": exact_signal["family_name"],
            "summary_phrase": f"{exact_signal['family_name']} variants carry a meaningful share of the value.",
            "confidence": "high",
        }
    elif entity_dominant:
        primary = {
            "type": "generic_entity_cluster",
            "name": entity_signal["entity_name"],
            "summary_phrase": f"{entity_signal['entity_name']} cards carry a meaningful share of the value.",
            "confidence": "medium",
        }
    else:
        primary = {
            "type": "none",
            "name": None,
            "summary_phrase": None,
            "confidence": "low",
        }

    return {
        "exact_family": exact_signal,
        "entity_cluster": entity_signal,
        "primary_name_pattern": primary,
    }


def _build_value_concentration_signal(
    single_card_signal: Dict[str, Any],
    value_source_signal: Dict[str, Any],
    name_pattern_signal: Dict[str, Any],
) -> Dict[str, Any]:
    exact = name_pattern_signal.get("exact_family") if isinstance(name_pattern_signal, dict) else {}
    entity = name_pattern_signal.get("entity_cluster") if isinstance(name_pattern_signal, dict) else {}

    single_type = str(single_card_signal.get("type") or "none")
    if single_type == "hard_single_card_outlier":
        card_name = str(single_card_signal.get("card_name") or "").strip()
        return {
            "type": "hard_single_card_outlier",
            "label": "Top card carries value",
            "short_phrase": f"carried heavily by {card_name}" if card_name else "carried heavily by one top card",
            "summary_phrase": f"{card_name} carries a large share of the upside." if card_name else "One top card carries a large share of the upside.",
            "risk_phrase": "Missing that top card can make sessions feel thin.",
            "tone": "caution",
            "card_name": card_name or None,
            "metrics": {
                "lead_ratio": single_card_signal.get("lead_ratio"),
                "top_card_share_of_top_hits": single_card_signal.get("top_card_share_of_top_hits"),
            },
            "confidence": "high",
        }

    if single_type == "clear_single_card_leader":
        card_name = str(single_card_signal.get("card_name") or "").strip()
        return {
            "type": "clear_single_card_leader",
            "label": "Top card leads value",
            "short_phrase": f"driven largely by {card_name}" if card_name else "driven largely by one top card",
            "summary_phrase": f"{card_name} does a lot of the heavy lifting." if card_name else "One top card does a lot of the heavy lifting.",
            "risk_phrase": "The value path still depends on landing that lead card.",
            "tone": "caution",
            "card_name": card_name or None,
            "metrics": {
                "lead_ratio": single_card_signal.get("lead_ratio"),
                "top_card_share_of_top_hits": single_card_signal.get("top_card_share_of_top_hits"),
            },
            "confidence": "medium",
        }

    if isinstance(exact, dict) and str(exact.get("type") or "") == "dominant_exact_family":
        family_name = str(exact.get("family_name") or "").strip()
        return {
            "type": "dominant_exact_family",
            "label": "Exact family carries value",
            "short_phrase": f"concentrated in {family_name} variants" if family_name else "concentrated in one exact card family",
            "summary_phrase": f"{family_name} variants carry much of the value." if family_name else "One exact card family carries much of the value.",
            "risk_phrase": "The score depends on landing that specific cluster of chase cards.",
            "tone": "caution",
            "family_name": family_name or None,
            "metrics": {
                "family_count": exact.get("family_count"),
                "family_ev_share_of_top_hits": exact.get("family_ev_share_of_top_hits"),
            },
            "confidence": "high",
        }

    if isinstance(entity, dict) and str(entity.get("type") or "") == "dominant_entity_cluster":
        entity_name = str(entity.get("entity_name") or "").strip()
        return {
            "type": "dominant_entity_cluster",
            "label": "Entity cluster carries value",
            "short_phrase": f"concentrated in {entity_name} cards" if entity_name else "concentrated in one character cluster",
            "summary_phrase": f"{entity_name} cards carry much of the value." if entity_name else "One character cluster carries much of the value.",
            "risk_phrase": "The value story is narrower than a fully broad spread.",
            "tone": "caution",
            "entity_name": entity_name or None,
            "metrics": {
                "entity_count": entity.get("entity_count"),
                "entity_ev_share_of_top_hits": entity.get("entity_ev_share_of_top_hits"),
            },
            "confidence": "medium",
        }

    signal_type = str(value_source_signal.get("type") or "")
    dominant_bucket = str(value_source_signal.get("dominant_rarity_bucket") or "")
    if signal_type == "dominant_rarity" and dominant_bucket == "special illustration rare":
        return {
            "type": "sir_driven",
            "label": "SIR-driven value",
            "short_phrase": "tied to harder-to-pull Special Illustration Rares",
            "summary_phrase": "Much of the upside sits in harder-to-pull Special Illustration Rares.",
            "risk_phrase": "The path depends more on premium chase outcomes.",
            "tone": "caution",
            "rarity_bucket": dominant_bucket,
            "metrics": {
                "dominant_share": value_source_signal.get("dominant_share"),
            },
            "confidence": "high",
        }
    if signal_type == "dominant_rarity" and dominant_bucket == "illustration rare":
        return {
            "type": "ir_driven",
            "label": "IR-supported value",
            "short_phrase": "supported broadly by Illustration Rares",
            "summary_phrase": "Illustration Rares provide broad support across several meaningful hits.",
            "risk_phrase": "Value is less tied to one single card than top-heavy profiles.",
            "tone": "positive",
            "rarity_bucket": dominant_bucket,
            "metrics": {
                "dominant_share": value_source_signal.get("dominant_share"),
            },
            "confidence": "high",
        }
    if signal_type == "dominant_rarity":
        rarity_label = _rarity_bucket_label_for_signal(dominant_bucket) if dominant_bucket else "one rarity group"
        return {
            "type": "dominant_rarity_group",
            "label": "Rarity-led value",
            "short_phrase": f"carried mostly by {rarity_label} cards",
            "summary_phrase": f"Much of the value is carried by {rarity_label} cards.",
            "risk_phrase": "The path depends more on that rarity lane than on broad spread.",
            "tone": "caution",
            "rarity_bucket": dominant_bucket or None,
            "metrics": {
                "dominant_share": value_source_signal.get("dominant_share"),
            },
            "confidence": "medium",
        }
    if signal_type == "broad_spread":
        return {
            "type": "broad_value_spread",
            "label": "Broad value spread",
            "short_phrase": "spread across several meaningful cards and rarity groups",
            "summary_phrase": "Value is spread across several meaningful cards and rarity groups.",
            "risk_phrase": "This lowers dependence on one perfect pull.",
            "tone": "positive",
            "metrics": {
                "dominant_share": value_source_signal.get("dominant_share"),
                "diversity": value_source_signal.get("diversity"),
            },
            "confidence": "medium",
        }

    return {
        "type": "mixed_chase_value",
        "label": "Mixed value base",
        "short_phrase": "value comes from a mixed set of hits",
        "summary_phrase": "Value comes from a mixed set of hits.",
        "risk_phrase": None,
        "tone": "neutral",
        "metrics": {
            "dominant_share": value_source_signal.get("dominant_share"),
            "diversity": value_source_signal.get("diversity"),
        },
        "confidence": "low",
    }


def _build_value_source_signals(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    top_hits = data.get("top_hits") if isinstance(data.get("top_hits"), list) else []
    rankings = data.get("rankings") if isinstance(data.get("rankings"), list) else []

    top_rows: List[Dict[str, Any]] = []
    for hit in top_hits:
        if not isinstance(hit, dict):
            continue
        ev = _to_float(hit.get("ev_contribution"))
        if ev is None or ev <= 0:
            continue
        rarity_bucket = _normalize_rarity_bucket_for_signal(hit.get("rarity_bucket"))
        top_rows.append(
            {
                "card_name": str(hit.get("card_name") or "").strip(),
                "rarity_bucket": rarity_bucket,
                "ev_contribution": ev,
                "pack_value_share": _to_float(hit.get("pack_value_share") or hit.get("value_share")),
            }
        )

    top_rows.sort(key=lambda row: row["ev_contribution"], reverse=True)

    rarity_totals: Dict[str, float] = defaultdict(float)
    rarity_cards: Dict[str, List[str]] = defaultdict(list)
    for row in top_rows:
        rarity = row["rarity_bucket"]
        if rarity == "unknown":
            continue
        rarity_totals[rarity] += row["ev_contribution"]
        if row["card_name"]:
            rarity_cards[rarity].append(row["card_name"])

    rarity_source = "top_hits"
    if not rarity_totals:
        for row in rankings:
            if not isinstance(row, dict):
                continue
            rarity = _normalize_rarity_bucket_for_signal(
                row.get("rarity_bucket") or row.get("rarity") or row.get("card_rarity")
            )
            total_value = _to_float(row.get("total_sampled_value"))
            if rarity == "unknown" or total_value is None or total_value <= 0:
                continue
            rarity_totals[rarity] += total_value
        if rarity_totals:
            rarity_source = "rankings"

    value_source_signal: Dict[str, Any] = {
        "type": "unknown",
        "dominant_rarity_bucket": None,
        "label": "Limited value-source clarity",
        "short_phrase": "value-source mix is still unclear",
    }

    if rarity_totals:
        sorted_buckets = sorted(rarity_totals.items(), key=lambda item: item[1], reverse=True)
        rarity_total = sum(value for _, value in sorted_buckets)
        lead_bucket, lead_value = sorted_buckets[0]
        lead_share = (lead_value / rarity_total) if rarity_total > 0 else 0.0
        second_share = (sorted_buckets[1][1] / rarity_total) if len(sorted_buckets) > 1 and rarity_total > 0 else 0.0
        top2_share = (
            ((sorted_buckets[0][1] + sorted_buckets[1][1]) / rarity_total)
            if len(sorted_buckets) > 1 and rarity_total > 0
            else lead_share
        )
        diversity = len(sorted_buckets)

        lead_label = _rarity_bucket_label_for_signal(lead_bucket)
        supporting_cards = rarity_cards.get(lead_bucket, [])[:3]

        if lead_share >= 0.5 and (lead_share - second_share) >= 0.12:
            phrase_prefix = "driven heavily by"
            if lead_bucket == "special illustration rare":
                phrase_prefix = "led by"
            value_source_signal = {
                "type": "dominant_rarity",
                "dominant_rarity_bucket": lead_bucket,
                "label": f"{lead_label}-driven value",
                "short_phrase": f"{phrase_prefix} {lead_label} cards",
                "supporting_cards": supporting_cards,
                "dominant_share": lead_share,
                "top2_share": top2_share,
                "diversity": diversity,
                "source": rarity_source,
            }
        elif diversity >= 4 and lead_share < 0.35:
            value_source_signal = {
                "type": "broad_spread",
                "dominant_rarity_bucket": None,
                "label": "Broad rarity spread",
                "short_phrase": "spread across several rarity groups",
                "dominant_share": lead_share,
                "top2_share": top2_share,
                "diversity": diversity,
                "source": rarity_source,
            }
        else:
            value_source_signal = {
                "type": "mixed_rarity",
                "dominant_rarity_bucket": lead_bucket if lead_share >= 0.35 else None,
                "label": "Mixed rarity value",
                "short_phrase": "supported by a mix of chase cards rather than one rarity",
                "dominant_share": lead_share,
                "top2_share": top2_share,
                "diversity": diversity,
                "source": rarity_source,
            }

    name_pattern_signal = _build_name_pattern_signal(top_rows)
    exact_signal = name_pattern_signal.get("exact_family") if isinstance(name_pattern_signal, dict) else {}
    entity_signal = name_pattern_signal.get("entity_cluster") if isinstance(name_pattern_signal, dict) else {}

    card_family_signal: Dict[str, Any] = {
        "type": "unknown",
        "family_name": None,
        "family_count": 0,
        "family_ev_share_of_top_hits": None,
        "example_cards": [],
    }

    if isinstance(exact_signal, dict):
        exact_type = str(exact_signal.get("type") or "")
        if exact_type == "dominant_exact_family":
            card_family_signal = {
                "type": "dominant_card_family",
                "family_name": exact_signal.get("family_name"),
                "family_count": exact_signal.get("family_count") or 0,
                "family_ev_share_of_top_hits": exact_signal.get("family_ev_share_of_top_hits"),
                "example_cards": exact_signal.get("example_cards") or [],
                "family_rank_positions": exact_signal.get("family_rank_positions") or [],
                "reason_code": exact_signal.get("reason_code") or "explicit_family_dominant",
            }
        elif exact_type == "mixed_exact_families":
            card_family_signal = {
                "type": "mixed_card_families",
                "family_name": None,
                "family_count": exact_signal.get("family_count") or 0,
                "family_ev_share_of_top_hits": exact_signal.get("family_ev_share_of_top_hits"),
                "example_cards": exact_signal.get("example_cards") or [],
                "family_rank_positions": exact_signal.get("family_rank_positions") or [],
                "reason_code": exact_signal.get("reason_code") or "explicit_family_not_dominant",
            }

    single_card_signal = _build_single_card_outlier_signal(top_rows)
    value_concentration_signal = _build_value_concentration_signal(
        single_card_signal=single_card_signal,
        value_source_signal=value_source_signal,
        name_pattern_signal=name_pattern_signal,
    )

    return {
        "value_source_signal": value_source_signal,
        "card_family_signal": card_family_signal,
        "single_card_signal": single_card_signal,
        "value_name_pattern_signal": {
            "exact_family": exact_signal,
            "entity_cluster": entity_signal,
            "primary_name_pattern": (name_pattern_signal or {}).get("primary_name_pattern") if isinstance(name_pattern_signal, dict) else None,
        },
        "value_concentration_signal": value_concentration_signal,
    }


def _value_source_pack_phrase(
    value_source_signal: Dict[str, Any],
    card_family_signal: Dict[str, Any],
    value_concentration_signal: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    concentration = value_concentration_signal if isinstance(value_concentration_signal, dict) else {}
    concentration_type = str(concentration.get("type") or "")
    strong_types = {
        "hard_single_card_outlier",
        "clear_single_card_leader",
        "dominant_exact_family",
        "dominant_entity_cluster",
        "sir_driven",
        "ir_driven",
        "dominant_rarity_group",
        "broad_value_spread",
    }
    if concentration_type in strong_types:
        short_phrase = str(concentration.get("short_phrase") or "").strip()
        if short_phrase:
            return short_phrase
    if concentration_type:
        return None

    family_type = str(card_family_signal.get("type") or "")
    if family_type == "dominant_card_family":
        family_name = str(card_family_signal.get("family_name") or "").strip()
        if family_name:
            return f"a lot of the value story is carried by {family_name} variants"

    signal_type = str(value_source_signal.get("type") or "")
    if signal_type == "dominant_rarity":
        phrase = str(value_source_signal.get("short_phrase") or "").strip()
        if phrase:
            return phrase
    if signal_type == "mixed_rarity":
        return "value is spread across multiple chase cards instead of one single card"
    if signal_type == "broad_spread":
        return "value is spread across several rarity groups"
    return None


def _inject_specific_value_source_copy(
    summary: str,
    value_source_signal: Dict[str, Any],
    card_family_signal: Dict[str, Any],
    value_concentration_signal: Optional[Dict[str, Any]] = None,
) -> str:
    text = str(summary or "")
    phrase = _value_source_pack_phrase(value_source_signal, card_family_signal, value_concentration_signal)
    if not phrase:
        return text

    replacements = {
        "value is spread well across cards": phrase,
        "value is spread across cards": phrase,
        "spreads it well across cards": phrase,
        "value is spread well enough to avoid one-card dependence": phrase,
        "value is spread reasonably": phrase,
        "value has some spread": phrase,
        "value is spread across enough cards": phrase,
    }

    lowered = text.lower()
    for old, new in replacements.items():
        idx = lowered.find(old)
        if idx >= 0:
            return f"{text[:idx]}{new}{text[idx + len(old):]}"
    return text


def _append_value_source_context(
    long_summary: str,
    value_source_signal: Dict[str, Any],
    card_family_signal: Dict[str, Any],
    *,
    lens_key: str,
) -> str:
    base = (long_summary or "").strip()

    family_type = str(card_family_signal.get("type") or "")
    family_name = str(card_family_signal.get("family_name") or "").strip()
    signal_type = str(value_source_signal.get("type") or "")
    dominant_bucket = str(value_source_signal.get("dominant_rarity_bucket") or "")

    extra = None
    if lens_key == "chase_potential":
        if family_type == "dominant_card_family" and family_name:
            extra = f"The chase is more focused than it first looks because multiple {family_name} variants are carrying the set."
        elif signal_type == "dominant_rarity" and dominant_bucket == "special illustration rare":
            extra = "The chase is strong because Special Illustration Rares carry much of the top-end value."
        elif signal_type == "dominant_rarity" and dominant_bucket == "illustration rare":
            extra = "The chase is supported heavily by Illustration Rare cards at the top end."
        elif signal_type == "dominant_rarity":
            rarity_label = _rarity_bucket_label_for_signal(dominant_bucket)
            extra = f"The chase leans most on {rarity_label} cards."
        elif signal_type in {"mixed_rarity", "broad_spread"}:
            extra = "The chase is broad because value is spread across several meaningful cards."

    elif lens_key == "biggest_upside":
        if family_type == "dominant_card_family" and family_name:
            extra = f"The very top is exciting, but a lot of that ceiling is tied to {family_name} variants."
        elif signal_type == "dominant_rarity" and dominant_bucket == "special illustration rare":
            extra = "The best outcomes can go far above pack price, especially when the main Special Illustration Rare chase lands."
        elif signal_type == "dominant_rarity" and dominant_bucket == "illustration rare":
            extra = "The ceiling is helped by several strong Illustration Rare outcomes."
        elif signal_type == "mixed_rarity":
            extra = "Top outcomes come from a mix of chase cards rather than one narrow rarity lane."

    elif lens_key == "opening_experience":
        if family_type == "dominant_card_family" and family_name:
            extra = f"This can feel swingy because outcomes depend heavily on landing {family_name} variants."
        elif signal_type == "dominant_rarity" and dominant_bucket in {"special illustration rare", "illustration rare", "ultra_ex"}:
            extra = "This can feel swingy because the set depends on landing the right chase cards."

    if not extra:
        return base
    if extra in base:
        return base
    return f"{base} {extra}".strip()


def _section_to_dict(section: SectionInterpretation) -> Dict[str, Any]:
    """Serialize a SectionInterpretation (and its nested EvidenceItems) to a plain dict."""
    return dataclasses.asdict(section)


def _is_high_tier(tier: Any) -> bool:
    return str(tier or "").strip().upper() in {"S", "A"}


def _is_safety_guardrail_tier(tier: Any) -> bool:
    return str(tier or "").strip().upper() in {"S", "A", "B"}


def _contains_word(value: str, needle: str) -> bool:
    return needle.lower() in (value or "").lower()


def _replace_punishing_label(section: SectionInterpretation, replacement: str) -> None:
    if _contains_word(section.label, "punishing"):
        section.label = replacement


def _map_severity_to_tone(severity: Any) -> str:
    severity_key = str(severity or "").strip().lower()
    if severity_key == "positive":
        return "positive"
    if severity_key == "negative":
        return "negative"
    if severity_key == "caution":
        return "mixed"
    return "neutral"


def _friendly_pillar_supporting_signals(key: str, section: Dict[str, Any]) -> List[str]:
    signals = section.get("signals") if isinstance(section, dict) else {}
    if not isinstance(signals, dict):
        signals = {}

    if key == "profit":
        probability_band = str(signals.get("probability_band") or "")
        impact_band = str(signals.get("impact_band") or "")
        items = []
        if probability_band in {"strong", "moderate"}:
            items.append("Win-rate support")
        if impact_band in {"strong", "huge", "solid"}:
            items.append("High-end upside")
        if not items:
            items = ["Mixed average pack results"]
        return items

    if key == "safety":
        reason_code = str(section.get("reason_code") or "")
        if any(token in reason_code for token in ("elite_downside_control", "strong_downside_control")):
            return ["Strong downside support"]
        if "controlled_misses" in reason_code:
            return ["Misses are more manageable"]
        if "average_safety_profile" in reason_code:
            return ["Downside is around category average"]
        if any(token in reason_code for token in ("rough", "brutal", "harsh", "punishing", "weak")):
            return ["Misses can be punishing"]
        return ["Downside is around category average"]

    if key == "stability":
        profile = str(signals.get("profile") or "")
        if profile in {"well_spread", "decent_spread", "high_tier_relative"}:
            return ["Value spread across more hits"]
        if profile in {"single_card_dependent", "top_heavy"}:
            return ["One card carries too much value"]
        return ["Concentration vs spread balance"]

    return []


def _build_pillar_contract(key: str, label: str, section: Optional[Dict[str, Any]], tier: Optional[str]) -> Dict[str, Any]:
    section_data = section if isinstance(section, dict) else {}
    short_summary = str(section_data.get("summary") or "").strip()
    return {
        "key": key,
        "label": label,
        "tier": tier,
        "state": section_data.get("reason_code"),
        "tone": _map_severity_to_tone(section_data.get("severity")),
        "short_summary": short_summary,
        "long_summary": None,
        "supporting_signals": _friendly_pillar_supporting_signals(key, section_data),
    }


def _build_opening_experience_lens(
    summary_data: Dict[str, Any],
    safety_tier: Optional[str],
    stability_tier: Optional[str],
    value_source_signal: Dict[str, Any],
    card_family_signal: Dict[str, Any],
) -> Dict[str, Any]:
    prob_profit = get_numeric(summary_data, "prob_profit")
    median_to_cost = get_numeric(summary_data, "median_value_to_cost_ratio")
    expected_loss_fraction = get_numeric(summary_data, "expected_loss_when_losing_fraction")
    cv = get_numeric(summary_data, "coefficient_of_variation")

    state = "balanced"
    tone = "neutral"
    short_summary = "This set can feel mixed to open, with both decent packs and dry packs."
    long_summary = "Most runs land in the middle: you get some help from good packs, but misses can still show up in streaks."

    if prob_profit is None or median_to_cost is None or expected_loss_fraction is None:
        state = "balanced"
        tone = "neutral"
        short_summary = "Opening feel is still forming because key signals are limited."
        long_summary = "Early data points to a mixed opening feel, but this read will sharpen as more runs come in."
    elif prob_profit >= 0.55 and median_to_cost >= 0.9 and expected_loss_fraction <= 0.55 and (cv is None or cv <= 1.15):
        state = "forgiving"
        tone = "positive"
        short_summary = "This set feels more forgiving than most. Misses still happen, but they hurt less."
        long_summary = "Average packs hold up better than most sets, so rough stretches are usually less painful than normal."
    elif expected_loss_fraction >= 0.82 and prob_profit < 0.30:
        state = "punishing"
        tone = "negative"
        short_summary = "This set can feel rough to open because bad packs give back very little."
        long_summary = "Misses can hurt in a hurry, so opening sessions lean heavily on landing better pulls to recover value."
    elif (cv is not None and cv >= 1.6) and prob_profit < 0.45:
        state = "boom_or_bust"
        tone = "mixed"
        short_summary = "This set feels swingy. Some packs hit hard, but dry packs still happen."
        long_summary = "The best pulls can carry a session, but misses can stack up, so opening results can jump around a lot."
    elif prob_profit >= 0.45 and median_to_cost >= 0.7 and expected_loss_fraction <= 0.72:
        state = "balanced"
        tone = "positive"
        short_summary = "This set feels fairly balanced compared with most."
        long_summary = "Misses still happen, but average packs are steadier than the more volatile chase-heavy sets."
    else:
        state = "swingy"
        tone = "mixed"
        short_summary = "This set can feel swingy, with noticeable gaps between average packs and hit packs."
        long_summary = "The opening experience can change quickly from pack to pack, so misses can feel rough when the top pulls do not show."

    if state in {"swingy", "boom_or_bust", "punishing"}:
        long_summary = _append_value_source_context(
            long_summary,
            value_source_signal,
            card_family_signal,
            lens_key="opening_experience",
        )

    simple_short_summary = short_summary
    simple_long_summary = long_summary
    expert_short_summary = short_summary
    expert_long_summary = long_summary

    evidence = [
        {"label": "Chance to beat cost", "value": format_percent(prob_profit)},
        {"label": "Typical outcome vs cost", "value": format_ratio(median_to_cost)},
        {"label": "Loss on misses", "value": format_percent(expected_loss_fraction)},
    ]

    return {
        "key": "opening_experience",
        "label": "Opening Experience",
        "variant": "composite_lens",
        "state": state,
        "tone": tone,
        "tier": summary_data.get("experience_tier") or safety_tier or stability_tier,
        "short_summary": short_summary,
        "long_summary": long_summary,
        "simple_summary": simple_short_summary,
        "simple_long_summary": simple_long_summary,
        "expert_summary": expert_short_summary,
        "expert_long_summary": expert_long_summary,
        "supporting_signals": [
            "Typical pack outcomes",
            "Miss recovery profile",
            "Outcome consistency",
        ],
        "evidence": evidence,
    }


def _format_optional_number(value: Optional[float], decimals: int = 1) -> str:
    return f"{value:.{decimals}f}" if value is not None else "N/A"


def _tail_gap_ratio(p95_to_cost: Optional[float], p99_to_cost: Optional[float]) -> Optional[float]:
    if p95_to_cost is None or p99_to_cost is None or p95_to_cost <= 0:
        return None
    return p99_to_cost / p95_to_cost


def _append_unique(items: List[str], candidate: Optional[str]) -> None:
    if not candidate:
        return
    if candidate not in items:
        items.append(candidate)


def _compose_chase_long_summary(
    *,
    state: str,
    top_heavy: bool,
    extreme_tail: bool,
    decent_depth: bool,
    weak_profit_support: bool,
    strong_frequency: bool,
) -> str:
    if state == "elite_chase":
        parts = [
            "The chase is strong because it is not only about one spike; there are enough meaningful pulls behind the top end.",
        ]
        if top_heavy:
            parts.append("One card still carries more weight than ideal, but there is enough behind it to avoid a pure lottery feel.")
        elif decent_depth:
            parts.append("The chase has enough depth that the best pulls matter a lot without everything resting on one card.")
        return " ".join(parts)

    if state == "strong_chase":
        parts = [
            "There is a real chase here, and it is not carried by only one far-tail outcome.",
        ]
        if weak_profit_support:
            parts.append("You still rely on the chase more than the average pack return.")
        elif strong_frequency:
            parts.append("Hit frequency gives this chase setup more backbone than thinner profiles.")
        return " ".join(parts)

    if state == "top_heavy_chase":
        parts = [
            "The ceiling is exciting, but the chase is top-heavy and missing the right cards can make packs feel much weaker.",
        ]
        if extreme_tail:
            parts.append("A lot of that excitement sits in rarer outcomes, not in a broad chase band.")
        return " ".join(parts)

    if state == "extreme_tail_chase":
        parts = [
            "The very top is exciting, but most of that excitement lives in rare outcomes.",
        ]
        if not decent_depth:
            parts.append("There are not enough meaningful pulls behind that tail to match deeper chase sets.")
        if weak_profit_support:
            parts.append("So the chase appeal depends more on rare spikes than on the average pack.")
        return " ".join(parts)

    if state == "low_chase":
        return "There are fewer outcomes where top pulls separate clearly from pack cost."

    parts = [
        "There is real upside here, but consistency depends on how much value sits at the very top.",
    ]
    if top_heavy:
        parts.append("The chase leans on a narrower set of cards than broad-depth sets do.")
    elif decent_depth:
        parts.append("There is useful depth behind the best outcomes, even if this is not a top-tier chase setup.")
    return " ".join(parts)


def _build_chase_potential_lens(
    summary_data: Dict[str, Any],
    value_source_signal: Dict[str, Any],
    card_family_signal: Dict[str, Any],
) -> Dict[str, Any]:
    p95_to_cost = get_numeric(summary_data, "p95_value_to_cost_ratio")
    p99_to_cost = get_numeric(summary_data, "p99_value_to_cost_ratio")
    effective_chase_count = get_numeric(summary_data, "effective_chase_count")
    hhi = get_numeric(summary_data, "hhi_ev_concentration")
    top1 = get_numeric(summary_data, "top1_ev_share")
    prob_big_hit = get_numeric(summary_data, "prob_big_hit")
    mean_to_cost = get_numeric(summary_data, "mean_value_to_cost_ratio")
    pack_cost = get_numeric(summary_data, "pack_cost")

    top_heavy = bool(
        (top1 is not None and top1 >= 0.35)
        or (hhi is not None and hhi >= 0.22)
    )
    decent_depth = effective_chase_count is None or effective_chase_count >= 8.0
    thin_depth = effective_chase_count is not None and effective_chase_count < 6.0
    strong_frequency = prob_big_hit is not None and prob_big_hit >= 0.12
    moderate_frequency = prob_big_hit is not None and prob_big_hit >= 0.07
    weak_profit_support = mean_to_cost is not None and mean_to_cost < 0.85
    tail_gap = _tail_gap_ratio(p95_to_cost, p99_to_cost)
    extreme_tail = bool(
        p99_to_cost is not None
        and p99_to_cost >= 6.0
        and (
            p95_to_cost is None
            or p95_to_cost < 3.0
            or (tail_gap is not None and tail_gap >= 2.2)
        )
    )

    state = "moderate_chase"
    tone = "neutral"
    short_summary = "The chase is real, but it is not one of the strongest setups."
    long_summary = _compose_chase_long_summary(
        state=state,
        top_heavy=top_heavy,
        extreme_tail=extreme_tail,
        decent_depth=decent_depth,
        weak_profit_support=weak_profit_support,
        strong_frequency=strong_frequency,
    )

    if p95_to_cost is None:
        state = "moderate_chase"
        tone = "neutral"
        short_summary = "Chase read is still forming because high-end context is limited."
        long_summary = "Early samples show some upside, but more data is needed to lock in how strong this chase setup really is."
    elif top_heavy and (p95_to_cost >= 2.0 or (p99_to_cost is not None and p99_to_cost >= 5.0)):
        state = "top_heavy_chase"
        tone = "mixed"
        short_summary = "The chase is exciting, but it is top-heavy and relies on a narrower hit set."
        long_summary = _compose_chase_long_summary(
            state=state,
            top_heavy=top_heavy,
            extreme_tail=extreme_tail,
            decent_depth=decent_depth,
            weak_profit_support=weak_profit_support,
            strong_frequency=strong_frequency,
        )
    elif p95_to_cost >= 3.0 and ((p99_to_cost is not None and p99_to_cost >= 6.0) or strong_frequency) and decent_depth and not top_heavy:
        state = "elite_chase"
        tone = "positive"
        short_summary = "The chase is strong, with a real ceiling and enough depth behind it."
        long_summary = _compose_chase_long_summary(
            state=state,
            top_heavy=top_heavy,
            extreme_tail=extreme_tail,
            decent_depth=decent_depth,
            weak_profit_support=weak_profit_support,
            strong_frequency=strong_frequency,
        )
    elif extreme_tail and not top_heavy and (
        p95_to_cost < 3.0 or not decent_depth or not moderate_frequency
    ):
        state = "extreme_tail_chase"
        tone = "mixed"
        short_summary = "The chase is real, but most of the excitement sits at the very top and is rare."
        long_summary = _compose_chase_long_summary(
            state=state,
            top_heavy=top_heavy,
            extreme_tail=extreme_tail,
            decent_depth=decent_depth,
            weak_profit_support=weak_profit_support,
            strong_frequency=strong_frequency,
        )
    elif p95_to_cost >= 2.0 and decent_depth and not top_heavy:
        state = "strong_chase"
        tone = "positive"
        short_summary = "There is a strong chase here, with meaningful upside and enough depth behind the hits."
        long_summary = _compose_chase_long_summary(
            state=state,
            top_heavy=top_heavy,
            extreme_tail=extreme_tail,
            decent_depth=decent_depth,
            weak_profit_support=weak_profit_support,
            strong_frequency=strong_frequency,
        )
    elif p95_to_cost < 1.3 and (p99_to_cost is None or p99_to_cost < 3.0):
        state = "low_chase"
        tone = "negative"
        short_summary = "Chase potential is limited because the top end looks capped."
        long_summary = _compose_chase_long_summary(
            state=state,
            top_heavy=top_heavy,
            extreme_tail=extreme_tail,
            decent_depth=decent_depth,
            weak_profit_support=weak_profit_support,
            strong_frequency=strong_frequency,
        )
    else:
        long_summary = _compose_chase_long_summary(
            state=state,
            top_heavy=top_heavy,
            extreme_tail=extreme_tail,
            decent_depth=decent_depth,
            weak_profit_support=weak_profit_support,
            strong_frequency=strong_frequency,
        )

    long_summary = _append_value_source_context(
        long_summary,
        value_source_signal,
        card_family_signal,
        lens_key="chase_potential",
    )

    supporting_signals: List[str] = []
    if p95_to_cost is not None and p95_to_cost >= 2.0:
        _append_unique(supporting_signals, "High-end upside")
    if extreme_tail:
        _append_unique(supporting_signals, "Extreme tail present")
    if decent_depth and not thin_depth:
        _append_unique(supporting_signals, "Broad chase depth")
    if top_heavy:
        _append_unique(supporting_signals, "Top-heavy value")
    if pack_cost is not None and pack_cost <= 10.0:
        _append_unique(supporting_signals, "Accessible pack cost")
    elif pack_cost is not None and pack_cost >= 18.0:
        _append_unique(supporting_signals, "Higher entry cost")
    if weak_profit_support:
        _append_unique(supporting_signals, "Profit support is limited")

    evidence = [
        {"label": BIG_HIT_UPSIDE_LABEL, "value": format_ratio(p95_to_cost), "detail": BIG_HIT_UPSIDE_HELPER},
        {"label": GOD_PULL_UPSIDE_LABEL, "value": format_ratio(p99_to_cost), "detail": GOD_PULL_UPSIDE_HELPER},
        {"label": "Big hit chance", "value": format_percent(prob_big_hit)},
        {"label": "Chase depth", "value": _format_optional_number(effective_chase_count)},
        {"label": "Top card concentration", "value": format_percent(top1)},
    ]

    return {
        "key": "chase_potential",
        "label": "Chase Potential",
        "variant": "composite_lens",
        "state": state,
        "tone": tone,
        "tier": summary_data.get("chase_potential_tier"),
        "short_summary": short_summary,
        "long_summary": long_summary,
        "simple_summary": short_summary,
        "simple_long_summary": long_summary,
        "expert_summary": short_summary,
        "expert_long_summary": long_summary,
        "supporting_signals": supporting_signals,
        "evidence": evidence,
    }


def _build_biggest_upside_lens(
    summary_data: Dict[str, Any],
    value_source_signal: Dict[str, Any],
    card_family_signal: Dict[str, Any],
) -> Dict[str, Any]:

    # Blended Biggest Upside Score (P95 primary, P99 secondary, capped)
    p95 = get_numeric(summary_data, "p95_value_to_cost_ratio")
    p99 = get_numeric(summary_data, "p99_value_to_cost_ratio")
    max_value = get_numeric(summary_data, "max_value")
    gap_ratio = _tail_gap_ratio(p95, p99)

    # Normalization and capping for blending
    def _norm(val, cap):
        if val is None:
            return 0.0
        return min(max(val, 0.0), cap) / cap

    norm_p95 = _norm(p95, 5.0)  # 5x cost is a practical cap for P95
    norm_p99 = _norm(p99, 10.0) # 10x cost is a practical cap for P99
    # Blend: 70% P95, 30% P99
    biggest_upside_score = 0.7 * norm_p95 + 0.3 * norm_p99

    # State/summary logic
    state = "moderate_upside"
    tone = "neutral"
    short_summary = "The best outcomes can go well above pack price when this set hits."
    long_summary = "The ceiling is real, but this is more about occasional spikes than constant top-end outcomes."

    if p95 is None:
        state = "moderate_upside"
        tone = "neutral"
        short_summary = "Upside context is limited for this run."
        long_summary = "There is not enough upper-tail context yet to pin down the full ceiling profile with confidence."
    elif p99 is not None and p99 >= 6.0 and (p95 < 3.0 or (gap_ratio is not None and gap_ratio >= 2.2)):
        state = "extreme_tail_upside"
        tone = "mixed"
        short_summary = "The very top can spike far above pack cost, but that is a rare outcome."
        long_summary = "The ceiling is exciting, but it shows up more as rare spikes than as a normal high-end result."
    elif p95 >= 3.0:
        state = "high_upside"
        tone = "positive"
        short_summary = "The best outcomes can go far above the pack price."
        long_summary = "When this set hits, the top pulls create real separation above cost."
    elif p95 >= 1.6 or (p99 is not None and p99 >= 4.0):
        state = "moderate_upside"
        tone = "positive"
        short_summary = "Top outcomes can still push above cost, but the ceiling is more moderate."
        long_summary = "There is upside here, just not the same top-end power as stronger chase sets."
    elif p95 < 1.2:
        state = "limited_upside"
        tone = "negative"
        short_summary = "The ceiling is limited compared with stronger chase sets."
        long_summary = "Even the best outcomes do not separate enough from current pack cost to carry the opening case."

    long_summary = _append_value_source_context(
        long_summary,
        value_source_signal,
        card_family_signal,
        lens_key="biggest_upside",
    )

    evidence = [
        {"label": BIG_HIT_UPSIDE_LABEL, "value": format_ratio(p95), "detail": BIG_HIT_UPSIDE_HELPER},
        {"label": GOD_PULL_UPSIDE_LABEL, "value": format_ratio(p99), "detail": GOD_PULL_UPSIDE_HELPER},
    ]
    if max_value is not None:
        evidence.append({"label": "Best simulated pull", "value": f"${max_value:,.2f}"})

    # Attach blended score for frontend/Explore ranking (not exposed in Profit Score)
    return {
        "key": "biggest_upside",
        "label": "Biggest Upside",
        "variant": "metric_lens",
        "state": state,
        "tone": tone,
        "tier": summary_data.get("p95_value_to_cost_tier"),
        "short_summary": short_summary,
        "long_summary": long_summary,
        "simple_summary": short_summary,
        "simple_long_summary": long_summary,
        "expert_summary": short_summary,
        "expert_long_summary": long_summary,
        "supporting_signals": [
            BIG_HIT_UPSIDE_LABEL,
            "P99 tail context" if p99 is not None else None,
            "Best pull context" if max_value is not None else None,
        ],
        "evidence": evidence,
        "biggest_upside_score": biggest_upside_score,
        "p95_value_to_cost_ratio": p95,
        "p99_value_to_cost_ratio": p99,
    }


def _build_average_return_lens(summary_data: Dict[str, Any]) -> Dict[str, Any]:
    mean_to_cost = get_numeric(summary_data, "mean_value_to_cost_ratio")

    state = "near_cost"
    tone = "neutral"
    short_summary = "The average pack is close to the current pack price."
    long_summary = "When average return is near cost, the opening feel and chase setup matter more."

    if mean_to_cost is None:
        state = "near_cost"
        tone = "neutral"
        short_summary = "Average return context is limited for this run."
        long_summary = None
    elif mean_to_cost >= 1.05:
        state = "above_cost"
        tone = "positive"
        short_summary = "The average pack gives back more than the current pack price."
        long_summary = "Compared with most sets, average packs are doing better here, even though misses still happen."
    elif mean_to_cost >= 0.9:
        state = "near_cost"
        tone = "neutral"
        short_summary = "The average pack is close to the price, so chase quality matters more."
        long_summary = "You are near break-even on average, which means opening feel and top-end pulls decide most of the appeal."
    elif mean_to_cost >= 0.75:
        state = "below_cost"
        tone = "mixed"
        short_summary = "The average pack gives back less than the current price."
        long_summary = "The average pack trails cost, so you need chase excitement or collector reasons to justify opening."
    else:
        state = "deeply_below_cost"
        tone = "negative"
        short_summary = "The average pack does not give enough back for the current price."
        long_summary = "The misses hurt more than the average pack gives back, so this is hard to justify on value alone."

    return {
        "key": "average_return",
        "label": "Average Return",
        "variant": "metric_lens",
        "state": state,
        "tone": tone,
        "tier": summary_data.get("mean_value_to_cost_tier"),
        "short_summary": short_summary,
        "long_summary": long_summary,
        "simple_summary": short_summary,
        "simple_long_summary": long_summary,
        "expert_summary": short_summary,
        "expert_long_summary": long_summary,
        "supporting_signals": ["Mean value vs cost"],
        "evidence": [
            {"label": "Average return vs cost", "value": format_ratio(mean_to_cost)},
        ],
    }


def _build_set_intelligence(
    summary_data: Dict[str, Any],
    safety_tier: Optional[str],
    stability_tier: Optional[str],
    value_source_signal: Dict[str, Any],
    card_family_signal: Dict[str, Any],
) -> List[Dict[str, Any]]:
    lenses = [
        _build_opening_experience_lens(summary_data, safety_tier, stability_tier, value_source_signal, card_family_signal),
        _build_chase_potential_lens(summary_data, value_source_signal, card_family_signal),
        _build_biggest_upside_lens(summary_data, value_source_signal, card_family_signal),
        _build_average_return_lens(summary_data),
    ]

    for lens in lenses:
        signals = lens.get("supporting_signals")
        if isinstance(signals, list):
            lens["supporting_signals"] = [item for item in signals if item]

    return lenses


def _append_modifier(base_summary: str, modifier: Optional[str]) -> str:
    summary = (base_summary or "").strip()
    extra = (modifier or "").strip()
    if not extra:
        return summary
    if extra in summary:
        return summary
    return f"{summary} {extra}".strip()


def _index_lenses_by_key(set_intelligence: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        str(lens.get("key")): lens
        for lens in set_intelligence
        if isinstance(lens, dict) and lens.get("key")
    }


def _pack_score_identity_modifier(
    pack_meta: Optional[Dict[str, Any]],
    set_intelligence: List[Dict[str, Any]],
    value_source_signal: Dict[str, Any],
    card_family_signal: Dict[str, Any],
    value_concentration_signal: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    if not isinstance(pack_meta, dict):
        return None

    lens_by_key = _index_lenses_by_key(set_intelligence)
    chase = lens_by_key.get("chase_potential") or {}
    upside = lens_by_key.get("biggest_upside") or {}
    experience = lens_by_key.get("opening_experience") or {}

    reason_code = str(pack_meta.get("reason_code") or "")
    severity = str(pack_meta.get("severity") or "")
    chase_state = str(chase.get("state") or "")
    upside_state = str(upside.get("state") or "")
    experience_state = str(experience.get("state") or "")
    signals = pack_meta.get("signals") if isinstance(pack_meta.get("signals"), dict) else {}
    pack_tier = str(((signals.get("pack") or {}).get("tier") if isinstance(signals.get("pack"), dict) else "") or "").strip().upper()
    safety_band = str(signals.get("safety_band") or "")

    weak_reasons = {
        "weak_open",
        "very_weak_open",
        "bottom_tier_open",
        "below_average_open",
        "safe_but_low_reward",
    }
    average_reasons = {
        "average_open",
        "average_but_risky",
        "okay_but_capped",
        "above_average_but_flawed",
    }

    if chase_state == "top_heavy_chase":
        if pack_tier == "S":
            return "This is an elite rip, but the value is more chase-driven than steady."
        if severity == "positive":
            return "This set grades well, but the value case is more chase-driven than steady."
        if reason_code in average_reasons:
            return "The overall profile is decent, but more of the value case depends on a narrower chase band."
        return "There is still chase appeal here, but much of it sits in a narrower hit set."

    if chase_state == "extreme_tail_chase":
        if reason_code in weak_reasons or severity == "negative":
            return "The ceiling exists, but most openings still do not hold up well enough."
        if reason_code in average_reasons or severity in {"neutral", "caution"}:
            return "The overall case is mixed, but there is still a real chase at the very top."
        return "There is a real chase at the very top here, even if the rest of the chase setup is less steady than top-tier sets."

    if chase_state == "low_chase" and experience_state in {"forgiving", "balanced"}:
        return "This set may feel safer to open, but it does not have the big ceiling stronger chase sets have."

    if upside_state == "extreme_tail_upside" and reason_code in weak_reasons:
        return "There is real ceiling in the far tail, but it does not change the weaker broader value profile."

    if experience_state in {"boom_or_bust", "swingy"} and severity == "positive":
        pack_phrase = _value_source_pack_phrase(value_source_signal, card_family_signal, value_concentration_signal)
        if pack_tier == "S":
            base = "This is an elite rip, but not a free win. Bad packs can still happen."
            if pack_phrase:
                return f"{base} A lot of the value is {pack_phrase}."
            return base
        base = "It can still feel swingy even with a strong overall score."
        if pack_phrase:
            return f"{base} A lot of the value is {pack_phrase}."
        return base

    if pack_tier == "S" and reason_code == "strong_but_risky" and safety_band in {"low", "medium"}:
        base = "This is an elite rip, but not a free win. Bad packs can still happen."
        pack_phrase = _value_source_pack_phrase(value_source_signal, card_family_signal, value_concentration_signal)
        if pack_phrase:
            return f"{base} A lot of the value is {pack_phrase}."
        return base

    pack_phrase = _value_source_pack_phrase(value_source_signal, card_family_signal, value_concentration_signal)
    if pack_phrase and reason_code in {"elite_open", "good_open", "strong_but_risky", "good_value_shaky_path"}:
        return f"A lot of the value is {pack_phrase}."

    return None


def _enforce_elite_label_for_s_tier(
    *,
    pack_meta: Dict[str, Any],
    set_intelligence: List[Dict[str, Any]],
    summary_data: Dict[str, Any],
) -> None:
    pack_tier = get_tier(summary_data, "pack_tier")
    if pack_tier != "S":
        return
    current_label = str(pack_meta.get("label") or "")
    if "elite" in current_label.lower():
        return

    lens_by_key = _index_lenses_by_key(set_intelligence)
    chase_state = str((lens_by_key.get("chase_potential") or {}).get("state") or "")
    experience_state = str((lens_by_key.get("opening_experience") or {}).get("state") or "")
    reason_code = str(pack_meta.get("reason_code") or "")

    if reason_code == "strong_but_risky":
        if chase_state == "top_heavy_chase":
            pack_meta["label"] = "Elite but top-heavy"
            return
        if experience_state in {"boom_or_bust", "swingy"}:
            pack_meta["label"] = "Elite but swingy"
            return
        pack_meta["label"] = "Elite rip, watch misses"
        return

    if chase_state == "top_heavy_chase":
        pack_meta["label"] = "Elite chase rip"
        return

    if experience_state in {"boom_or_bust", "swingy"}:
        pack_meta["label"] = "Elite but swingy"
        return

    if reason_code == "elite_open":
        pack_meta["label"] = "Elite rip"
        return

    pack_meta["label"] = "Elite profile"


def validate_interpretation_consistency(
    data: Dict[str, Any],
    pack_score: Any,
    profit: Any,
    safety: Any,
    stability: Any,
    advanced_metrics: SectionInterpretation,
) -> None:
    summary_data = get_summary_data(data)
    decision_category = None
    if pack_score.meta and isinstance(pack_score.meta.signals, dict):
        decision_category = pack_score.meta.signals.get("decision_category")

    profit_tier = get_tier(summary_data, "profit_tier")
    safety_tier = get_tier(summary_data, "safety_tier")
    stability_tier = get_tier(summary_data, "stability_tier")

    if safety.meta and _is_safety_guardrail_tier(safety_tier):
        if safety.meta.severity in {"negative", "caution"}:
            safety.meta.severity = "neutral"
        replacement = "Controlled misses" if str(safety_tier or "").strip().upper() == "B" else "Safer misses"
        _replace_punishing_label(safety.meta, replacement)

    if profit.meta and _is_high_tier(profit_tier) and profit.meta.severity in {"negative", "caution"}:
        profit.meta.severity = "neutral"

    if stability.meta and _is_high_tier(stability_tier) and stability.meta.severity in {"negative", "caution"}:
        if "better than most" not in stability.meta.summary.lower():
            stability.meta.summary = f"{stability.meta.summary} It is still better than most sets in this category."
        stability.meta.severity = "neutral"

    if decision_category in {"elite_open", "strong_but_risky"}:
        advanced_metrics.summary = (
            "The deeper numbers support the main read, with a catch: weaker packs can still hurt."
            if advanced_metrics.severity in {"negative", "caution"}
            else advanced_metrics.summary
        )
        if advanced_metrics.severity == "negative":
            advanced_metrics.severity = "caution"

    if decision_category == "weak_open":
        for pillar in (profit.meta, safety.meta, stability.meta):
            if pillar and pillar.severity == "positive":
                pillar.severity = "neutral"
                pillar.summary = f"{pillar.summary} This helps, but it is not enough to offset the weak overall open profile."


def build_rip_interpretation(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the full RIP interpretation payload.

    Returns all existing string keys unchanged (backwards-compatible contract),
    plus a ``meta`` key containing structured section outputs.
    """
    profit = interpret_profit(data)
    safety = interpret_safety(data)
    stability = interpret_stability(data)

    pack_score = interpret_pack_score(profit, safety, stability, data)

    outcome_dist = interpret_outcome_distribution(data)
    hist_trend = interpret_historical_trend(data)
    pack_bdown = interpret_pack_breakdown(data)
    top_ev = interpret_top_ev_drivers(data)
    rarity_contrib = interpret_rarity_contribution(data)
    adv_metrics = interpret_advanced_metrics(data, _section_to_dict(pack_score.meta) if pack_score.meta else None)
    validate_interpretation_consistency(data, pack_score, profit, safety, stability, adv_metrics)

    summary_data = get_summary_data(data)
    profit_tier = get_tier(summary_data, "profit_tier")
    safety_tier = get_tier(summary_data, "safety_tier")
    stability_tier = get_tier(summary_data, "stability_tier")

    value_source_signals = _build_value_source_signals(data)
    value_source_signal = value_source_signals["value_source_signal"]
    card_family_signal = value_source_signals["card_family_signal"]
    value_concentration_signal = value_source_signals.get("value_concentration_signal")

    set_intelligence = _build_set_intelligence(
        summary_data,
        safety_tier,
        stability_tier,
        value_source_signal,
        card_family_signal,
    )

    pack_score_summary = pack_score.summary
    pack_meta = _section_to_dict(pack_score.meta) if pack_score.meta else None
    if pack_meta:
        _enforce_elite_label_for_s_tier(
            pack_meta=pack_meta,
            set_intelligence=set_intelligence,
            summary_data=summary_data,
        )
        modifier = _pack_score_identity_modifier(
            pack_meta,
            set_intelligence,
            value_source_signal,
            card_family_signal,
            value_concentration_signal,
        )
        if modifier:
            pack_meta["summary"] = _append_modifier(pack_meta.get("summary") or "", modifier)
        pack_meta["summary"] = _inject_specific_value_source_copy(
            pack_meta.get("summary") or "",
            value_source_signal,
            card_family_signal,
            value_concentration_signal,
        )
        pack_score_summary = str(pack_meta.get("summary") or pack_score_summary)
    profit_meta = _section_to_dict(profit.meta) if profit.meta else None
    safety_meta = _section_to_dict(safety.meta) if safety.meta else None
    stability_meta = _section_to_dict(stability.meta) if stability.meta else None

    # Build meta — structured dicts for every section and pillar.
    meta: Dict[str, Any] = {
        "packScore": pack_meta,
        "profit": profit_meta,
        "safety": safety_meta,
        "stability": stability_meta,
        "outcomeDistribution": _section_to_dict(outcome_dist),
        "historicalTrend": _section_to_dict(hist_trend),
        "packBreakdown": _section_to_dict(pack_bdown),
        "topEvDrivers": _section_to_dict(top_ev),
        "rarityContribution": _section_to_dict(rarity_contrib),
        "advancedMetrics": _section_to_dict(adv_metrics),
        "value_source_signals": {
            "value_source_signal": value_source_signal,
            "card_family_signal": card_family_signal,
            "single_card_signal": value_source_signals.get("single_card_signal"),
            "value_name_pattern_signal": value_source_signals.get("value_name_pattern_signal"),
            "value_concentration_signal": value_concentration_signal,
        },
        "pillars": [
            _build_pillar_contract("profit", "Profit", profit_meta, profit_tier),
            _build_pillar_contract("safety", "Safety", safety_meta, safety_tier),
            _build_pillar_contract("stability", "Stability", stability_meta, stability_tier),
        ],
        "set_intelligence": set_intelligence,
    }

    return {
        # Existing string keys — unchanged contract
        "packScore": pack_score_summary,
        "outcomeDistribution": outcome_dist.summary,
        "historicalTrend": hist_trend.summary,
        "packBreakdown": pack_bdown.summary,
        "topEvDrivers": top_ev.summary,
        "rarityContribution": rarity_contrib.summary,
        "advancedMetrics": adv_metrics.summary,
        # New structured metadata
        "meta": meta,
        "interpretation_version": "2.0",
        "schema_version": "rip_interpretation_v2",
    }
