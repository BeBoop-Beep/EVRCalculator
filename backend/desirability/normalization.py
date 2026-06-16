from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple


TIER_BANDS = (
    ("S", 90, 100),
    ("A", 75, 89),
    ("B", 55, 74),
    ("C", 35, 54),
    ("D", 15, 34),
    ("F", 0, 14),
)

TIER_STATUS_SCORE = {
    "s": 95.0,
    "top": 95.0,
    "favorite": 90.0,
    "a": 82.0,
    "popular": 82.0,
    "b": 65.0,
    "notable": 65.0,
    "c": 45.0,
    "average": 45.0,
    "d": 25.0,
    "low": 25.0,
    "f": 8.0,
}

SCORING_VERSION = "pokemon_desirability_source_v1"

FORM_SUFFIXES_TO_STRIP = (
    "disguised",
    "altered",
    "shield",
    "amped",
    "land",
    "midday",
    "normal",
    "male",
    "female",
    "average",
    "red meteor",
    "aria",
    "50",
    "family of four",
    "standard",
    "curly",
    "ice",
    "solo",
    "ordinary",
    "full belly",
    "baile",
    "single strike",
    "two segment",
    "incarnate",
    "zero",
    "plant",
    "green plumage",
    "red striped",
)

KNOWN_NAME_ALIASES = {
    "nidoran female": {"nidoran f"},
    "nidoran male": {"nidoran m"},
    "type null": {"type null"},
}


def normalize_pokemon_name_key(value: Optional[str]) -> str:
    """Return a stable matching key for Pokemon names from mixed public sources."""
    if value is None:
        return ""

    text = str(value).strip().casefold()
    text = text.replace("♀", " f ").replace("♂", " m ")
    text = text.replace("’", "").replace("‘", "").replace("'", "").replace("`", "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def assign_desirability_tier(score: float) -> str:
    bounded = max(0.0, min(100.0, float(score)))
    for tier, low, high in TIER_BANDS:
        if low <= bounded <= high:
            return tier
    return "F"


def normalize_from_vote_counts(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    vote_rows = [
        row
        for row in rows
        if row.get("raw_vote_count") is not None and _as_float(row.get("raw_vote_count")) is not None
    ]
    if not vote_rows:
        return []

    max_vote_count = max(_as_float(row["raw_vote_count"]) or 0.0 for row in vote_rows)
    if max_vote_count <= 0:
        return []

    normalized: List[Dict[str, Any]] = []
    ranked_rows = sorted(vote_rows, key=lambda row: _as_float(row["raw_vote_count"]) or 0.0, reverse=True)
    for index, row in enumerate(ranked_rows, start=1):
        vote_count = _as_float(row["raw_vote_count"]) or 0.0
        score = 100.0 * math.log1p(vote_count) / math.log1p(max_vote_count)
        normalized.append(_score_payload(row, score, normalized_rank=index, confidence="high", signal="vote_count"))
    return normalized


def normalize_from_ranks(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rank_rows = [
        row
        for row in rows
        if row.get("raw_rank") is not None and _as_int(row.get("raw_rank")) is not None
    ]
    if not rank_rows:
        return []

    ranked_rows = sorted(rank_rows, key=lambda row: _as_int(row["raw_rank"]) or 0)
    total_ranked = len(ranked_rows)
    normalized: List[Dict[str, Any]] = []

    for row in ranked_rows:
        rank = _as_int(row["raw_rank"]) or total_ranked
        if total_ranked <= 1:
            score = 100.0
        else:
            score = 100.0 * (1.0 - ((rank - 1) / (total_ranked - 1)))
        normalized.append(_score_payload(row, score, normalized_rank=rank, confidence="medium", signal="rank"))
    return normalized


def normalize_from_tiers(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        raw_tier = str(row.get("raw_tier") or "").strip()
        if not raw_tier:
            continue
        key = normalize_pokemon_name_key(raw_tier)
        score = TIER_STATUS_SCORE.get(key)
        if score is None:
            score = TIER_STATUS_SCORE.get(raw_tier[:1].casefold())
        if score is None:
            continue
        normalized.append(_score_payload(row, score, normalized_rank=None, confidence="low", signal="tier"))
    return normalized


def normalize_source_rows(rows: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Normalize extracted source rows using the strongest available signal."""
    row_list = list(rows)
    vote_scores = normalize_from_vote_counts(row_list)
    if vote_scores:
        return vote_scores, _summary("vote_count", vote_scores, row_list)

    rank_scores = normalize_from_ranks(row_list)
    if rank_scores:
        return rank_scores, _summary("rank", rank_scores, row_list)

    tier_scores = normalize_from_tiers(row_list)
    if tier_scores:
        return tier_scores, _summary("tier", tier_scores, row_list)

    return [], {
        "signal": "none",
        "confidence": "insufficient",
        "input_rows": len(row_list),
        "normalized_rows": 0,
        "reason": "No vote counts, ranks, or mappable tiers were extracted.",
    }


def match_source_row_to_reference(
    source_row: Dict[str, Any],
    references: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    pokedex_number = _as_int(source_row.get("pokedex_number"))
    reference_list = list(references)
    if pokedex_number is not None:
        for reference in reference_list:
            if _as_int(reference.get("pokedex_number")) == pokedex_number:
                return reference

    source_key = normalize_pokemon_name_key(source_row.get("pokemon_name"))
    if not source_key:
        return None

    source_keys = _expanded_name_keys(source_key)
    for reference in reference_list:
        if source_keys.intersection(_reference_name_keys(reference)):
            return reference
    return None


def _expanded_name_keys(name_key: str) -> set[str]:
    return {name_key, *KNOWN_NAME_ALIASES.get(name_key, set())}


def _reference_name_keys(reference: Dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for name in (reference.get("canonical_name"), reference.get("display_name")):
        key = normalize_pokemon_name_key(name)
        if not key:
            continue
        keys.add(key)
        keys.update(_form_stripped_name_keys(key))
        for alias_key, target_keys in KNOWN_NAME_ALIASES.items():
            if key in target_keys:
                keys.add(alias_key)
    return keys


def _form_stripped_name_keys(name_key: str) -> set[str]:
    keys: set[str] = set()
    for suffix in FORM_SUFFIXES_TO_STRIP:
        suffix_text = f" {suffix}"
        if name_key.endswith(suffix_text):
            stripped = name_key[: -len(suffix_text)].strip()
            if stripped:
                keys.add(stripped)
    return keys


def _score_payload(
    row: Dict[str, Any],
    score: float,
    normalized_rank: Optional[int],
    confidence: str,
    signal: str,
) -> Dict[str, Any]:
    bounded_score = round(max(0.0, min(100.0, float(score))), 4)
    return {
        "pokemon_reference_id": row.get("pokemon_reference_id"),
        "pokedex_number": row.get("pokedex_number"),
        "pokemon_name": row.get("pokemon_name"),
        "source_name": row.get("source_name"),
        "snapshot_id": row.get("snapshot_id"),
        "normalized_score": bounded_score,
        "normalized_rank": normalized_rank,
        "desirability_tier": assign_desirability_tier(bounded_score),
        "confidence": confidence,
        "scoring_version": SCORING_VERSION,
        "source_signal": signal,
    }


def _summary(signal: str, scores: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    confidence_counts: Dict[str, int] = {}
    for score in scores:
        confidence = str(score.get("confidence") or "unknown")
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1

    primary_confidence = max(confidence_counts.items(), key=lambda item: item[1])[0]
    return {
        "signal": signal,
        "confidence": primary_confidence,
        "input_rows": len(rows),
        "normalized_rows": len(scores),
        "coverage_ratio": round(len(scores) / len(rows), 4) if rows else 0.0,
    }


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
