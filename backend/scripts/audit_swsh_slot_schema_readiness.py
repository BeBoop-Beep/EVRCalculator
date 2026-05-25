"""Read-only batch audit for Sword & Shield slot-schema readiness.

This script:
1) Discovers Sword & Shield set configs from SET_CONFIG_MAP.
2) Classifies sets as standard-main-set candidates vs special/blocked.
3) Audits cards/card_variants availability and optional near-mint price presence.
4) Attempts normalized bucket classification for standard SWSH sets.
5) Produces JSON + Markdown readiness matrix artifacts.

It does not mutate runtime config, probabilities, or database state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from backend.constants.tcg.pokemon.swordAndShieldEra.setMap import SET_CONFIG_MAP  # noqa: E402


DEFAULT_JSON_PATH = Path("logs/audits/swsh_slot_schema_readiness_matrix.json")
DEFAULT_MD_PATH = Path("backend/docs/audits/SWSH_SLOT_SCHEMA_READINESS_MATRIX.md")

STANDARD_SWSH_MAIN_SET_IDS = {
    "swsh1",
    "swsh2",
    "swsh3",
    "swsh4",
    "swsh5",
    "swsh6",
    "swsh7",
    "swsh8",
    "swsh9",
    "swsh10",
    "swsh11",
    "swsh12",
}

EXPLICIT_BLOCKED_SET_IDS = {
    "cel25",
    "cel25c",
    "swsh35",
    "swsh45",
    "swsh45sv",
    "swsh12pt5",
    "swsh12pt5gg",
    "pgo",
    "swshp",
}

BLOCKED_NAME_TOKENS = {
    "trainer gallery",
    "galarian gallery",
    "classic collection",
    "shiny vault",
    "black star promos",
}

SPECIAL_NAME_TOKENS = {
    "celebrations",
    "shining fates",
    "crown zenith",
    "pokemon go",
    "pokémon go",
    "champion's path",
}

RARE_FAMILY_RARITIES = {
    "rare",
    "holo rare",
    "rare holo",
    "ultra rare",
    "secret rare",
}

NORMALIZED_OUTCOME_ORDER = [
    "rare",
    "holo rare",
    "regular v",
    "regular vmax",
    "full art v",
    "full art trainer",
    "alternate art v",
    "alternate art vmax",
    "rainbow trainer",
    "rainbow vmax",
    "gold secret rare",
]

FINAL_ALLOWED_BUCKETS = set(NORMALIZED_OUTCOME_ORDER)


@dataclass(frozen=True)
class SetConfigMeta:
    set_key: str
    class_name: str
    set_name: str
    set_id: str
    printed_total: Optional[int]
    total: Optional[int]
    simulation_engine: str
    slot_schema_runtime_enabled: bool
    has_rare_slot_probability: bool
    has_reverse_slot_probabilities: bool
    reverse_slot_probability_shape: str
    standard_pack_shape: bool
    pack_shape_reason: str
    source_confidence_status: str
    source_confidence_runtime_ready: Optional[bool]
    source_confidence_probability_ready: Optional[bool]


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_name_for_tokens(value: str) -> str:
    lowered = _normalize_text(value)
    return lowered.replace("é", "e")


def _parse_card_number(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value:
            return None
        return int(value)

    text = str(value).strip()
    if not text:
        return None
    match = re.match(r"^(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_reverse_variant(variant: Mapping[str, Any]) -> bool:
    printing = _normalize_text(variant.get("printing_type"))
    special = _normalize_text(variant.get("special_type"))
    return "reverse" in printing or "reverse" in special


def _has_standard_swsh_pack_shape(config_cls: Any) -> Tuple[bool, str]:
    pack_structure = getattr(config_cls, "PACK_STRUCTURE", None)
    if not isinstance(pack_structure, Mapping):
        return False, "PACK_STRUCTURE missing"

    common_slots = pack_structure.get("common_slots")
    uncommon_slots = pack_structure.get("uncommon_slots")
    rare_family_slots = pack_structure.get("rare_family_slots")
    if common_slots != 5 or uncommon_slots != 3 or not isinstance(rare_family_slots, list):
        return False, "PACK_STRUCTURE not 5/3 with rare_family_slots"

    if len(rare_family_slots) != 2:
        return False, "PACK_STRUCTURE rare_family_slots length != 2"

    roles = {_normalize_text(slot.get("role")) for slot in rare_family_slots if isinstance(slot, Mapping)}
    if roles != {"reverse_parallel", "rare_or_better"}:
        return False, "PACK_STRUCTURE roles are not reverse_parallel + rare_or_better"

    slots_per_rarity = getattr(config_cls, "SLOTS_PER_RARITY", {})
    if not isinstance(slots_per_rarity, Mapping):
        return False, "SLOTS_PER_RARITY missing"

    if (
        _safe_int(slots_per_rarity.get("common")) != 5
        or _safe_int(slots_per_rarity.get("uncommon")) != 3
        or _safe_int(slots_per_rarity.get("reverse")) != 1
        or _safe_int(slots_per_rarity.get("rare")) != 1
    ):
        return False, "SLOTS_PER_RARITY not 5/3/1/1"

    return True, "standard pre-SV 5/3/1/1 structure"


def discover_swsh_set_configs() -> List[SetConfigMeta]:
    rows: List[SetConfigMeta] = []
    for set_key, config_cls in sorted(SET_CONFIG_MAP.items(), key=lambda item: item[0]):
        standard_pack_shape, pack_shape_reason = _has_standard_swsh_pack_shape(config_cls)
        reverse_table = getattr(config_cls, "REVERSE_SLOT_PROBABILITIES", None)
        source_confidence = getattr(config_cls, "SLOT_SCHEMA_SOURCE_CONFIDENCE", {})
        if not isinstance(source_confidence, Mapping):
            source_confidence = {}

        reverse_shape = "missing"
        if isinstance(reverse_table, Mapping):
            reverse_shape = f"slots={','.join(sorted(str(k) for k in reverse_table.keys()))}"

        rows.append(
            SetConfigMeta(
                set_key=set_key,
                class_name=config_cls.__name__,
                set_name=str(getattr(config_cls, "SET_NAME", set_key)),
                set_id=str(getattr(config_cls, "SET_ID", "")),
                printed_total=_safe_int(getattr(config_cls, "PRINTED_TOTAL", None)),
                total=_safe_int(getattr(config_cls, "TOTAL", None)),
                simulation_engine=str(getattr(config_cls, "SIMULATION_ENGINE", "v2")),
                slot_schema_runtime_enabled=bool(getattr(config_cls, "SLOT_SCHEMA_RUNTIME_ENABLED", False)),
                has_rare_slot_probability=hasattr(config_cls, "RARE_SLOT_PROBABILITY"),
                has_reverse_slot_probabilities=isinstance(reverse_table, Mapping),
                reverse_slot_probability_shape=reverse_shape,
                standard_pack_shape=standard_pack_shape,
                pack_shape_reason=pack_shape_reason,
                source_confidence_status=str(source_confidence.get("status", "")),
                source_confidence_runtime_ready=(
                    bool(source_confidence["runtime_ready"]) if "runtime_ready" in source_confidence else None
                ),
                source_confidence_probability_ready=(
                    bool(source_confidence["rare_slot_probability_ready"])
                    if "rare_slot_probability_ready" in source_confidence
                    else None
                ),
            )
        )
    return rows


def classify_set_scope(meta: SetConfigMeta) -> Tuple[str, str]:
    set_id = _normalize_text(meta.set_id)
    set_name = _normalize_name_for_tokens(meta.set_name)

    if set_id in STANDARD_SWSH_MAIN_SET_IDS:
        return "candidate_standard", "mainline Sword & Shield set id"

    if set_id in EXPLICIT_BLOCKED_SET_IDS:
        return "excluded_special", "explicitly blocked special/miniset/promos"

    for token in BLOCKED_NAME_TOKENS:
        if token in set_name:
            return "excluded_special", f"non-main-set token detected: {token}"

    for token in SPECIAL_NAME_TOKENS:
        if token in set_name:
            return "excluded_special", f"special-set token detected: {token}"

    if set_id.endswith("tg"):
        return "excluded_special", "trainer gallery subset"

    return "excluded_special", "not in standard SWSH main set id list"


def split_swsh_targets(configs: Sequence[SetConfigMeta]) -> Dict[str, List[Dict[str, Any]]]:
    included: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for meta in configs:
        scope, reason = classify_set_scope(meta)
        payload = {
            "set_key": meta.set_key,
            "set_name": meta.set_name,
            "set_id": meta.set_id,
            "class_name": meta.class_name,
            "scope": scope,
            "reason": reason,
        }
        if scope == "candidate_standard":
            included.append(payload)
        else:
            excluded.append(payload)

    return {
        "included": sorted(included, key=lambda row: row["set_id"]),
        "excluded": sorted(excluded, key=lambda row: (row["scope"], row["set_id"])),
    }


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def _get_supabase_client() -> Tuple[Optional[Any], Optional[str]]:
    try:
        from backend.db.clients.supabase_client import supabase  # noqa: WPS433

        return supabase, None
    except Exception as exc:  # pragma: no cover - environment-dependent
        return None, f"supabase unavailable: {type(exc).__name__}: {exc}"


def _resolve_set_row(supabase: Any, set_id: str, set_name: str) -> Optional[Dict[str, Any]]:
    by_api = (
        supabase.table("sets")
        .select("*")
        .eq("pokemon_api_set_id", set_id)
        .limit(5)
        .execute()
    )
    api_rows = by_api.data or []
    if api_rows:
        return api_rows[0]

    by_name = (
        supabase.table("sets")
        .select("*")
        .ilike("name", set_name)
        .limit(5)
        .execute()
    )
    name_rows = by_name.data or []
    if name_rows:
        return name_rows[0]
    return None


def _fetch_cards_for_set_row(supabase: Any, set_row_id: Any) -> List[Dict[str, Any]]:
    response = supabase.table("cards").select("*").eq("set_id", set_row_id).execute()
    return response.data or []


def _fetch_variants_for_card_ids(supabase: Any, card_ids: Sequence[Any]) -> List[Dict[str, Any]]:
    if not card_ids:
        return []
    rows: List[Dict[str, Any]] = []
    for chunk in _chunked(list(card_ids), 250):
        response = supabase.table("card_variants").select("*").in_("card_id", list(chunk)).execute()
        rows.extend(response.data or [])
    return rows


def _fetch_latest_market_for_variant_ids(supabase: Any, variant_ids: Sequence[Any]) -> List[Dict[str, Any]]:
    if not variant_ids:
        return []
    rows: List[Dict[str, Any]] = []
    for chunk in _chunked(list(variant_ids), 250):
        response = (
            supabase.table("card_market_usd_latest_by_condition")
            .select("*")
            .in_("variant_id", list(chunk))
            .execute()
        )
        rows.extend(response.data or [])
    return rows


def _market_condition_text(row: Mapping[str, Any]) -> str:
    for key in ("condition", "condition_name", "condition_label"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _is_near_mint_row(row: Mapping[str, Any]) -> bool:
    text = _normalize_text(_market_condition_text(row))
    return text in {"near mint", "nm", "near_mint"} or "near mint" in text


def _extract_price_value(row: Mapping[str, Any]) -> Optional[float]:
    for key in ("market_price", "price", "usd_market", "near_mint_price"):
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        return value
    return None


def _is_rare_family_non_reverse(card: Mapping[str, Any], variant: Mapping[str, Any]) -> bool:
    rarity = _normalize_text(card.get("rarity"))
    return rarity in RARE_FAMILY_RARITIES and not _is_reverse_variant(variant)


def _is_rare_family_reverse(card: Mapping[str, Any], variant: Mapping[str, Any]) -> bool:
    rarity = _normalize_text(card.get("rarity"))
    return rarity in RARE_FAMILY_RARITIES and _is_reverse_variant(variant)


def _contains_trainer_signal(card: Mapping[str, Any], name_lower: str) -> bool:
    supertype = _normalize_text(card.get("supertype"))
    if supertype == "trainer":
        return True

    subtypes = card.get("subtypes")
    tokens: List[str] = []
    if isinstance(subtypes, list):
        tokens = [_normalize_text(item) for item in subtypes]
    elif subtypes not in (None, ""):
        raw = str(subtypes)
        tokens = [_normalize_text(part) for part in raw.replace("[", "").replace("]", "").split(",")]

    if "trainer" in tokens or "supporter" in tokens or "item" in tokens or "stadium" in tokens:
        return True

    return "trainer" in name_lower


def _matches_bucket(bucket: str, card: Mapping[str, Any], variant: Mapping[str, Any], printed_total: Optional[int]) -> bool:
    rarity = _normalize_text(card.get("rarity"))
    name = str(card.get("name") or "")
    name_l = _normalize_text(name)
    card_number = _parse_card_number(card.get("card_number"))
    special = _normalize_text(variant.get("special_type"))
    printing = _normalize_text(variant.get("printing_type"))

    if _is_reverse_variant(variant):
        return False

    is_alt = "alternate" in name_l or "alternate" in special or " alt" in f" {name_l} "
    is_vmax = "vmax" in name_l
    is_v = name_l.endswith(" v") or " v " in f" {name_l} "
    is_rainbow = "rainbow" in name_l or "rainbow" in special or "rainbow" in printing
    is_gold = "gold" in name_l or "gold" in special or "gold" in printing
    is_full_art = "full art" in name_l or "full art" in special

    in_printed_range = True
    if printed_total is not None and card_number is not None:
        in_printed_range = card_number <= printed_total

    if bucket == "rare":
        return rarity == "rare" and printing != "holo"

    if bucket == "holo rare":
        return rarity in {"holo rare", "rare holo"} or ("holo" in rarity and "rare" in rarity)

    if bucket == "regular v":
        return rarity == "ultra rare" and is_v and not is_vmax and in_printed_range and not is_alt and not is_full_art

    if bucket == "regular vmax":
        return rarity == "ultra rare" and is_vmax and in_printed_range and not is_alt and not is_rainbow

    if bucket == "full art v":
        return rarity == "ultra rare" and is_v and not is_vmax and in_printed_range and not is_alt and is_full_art

    if bucket == "full art trainer":
        return (
            rarity == "ultra rare"
            and in_printed_range
            and not is_v
            and not is_vmax
            and _contains_trainer_signal(card, name_l)
        )

    if bucket == "alternate art v":
        return rarity == "ultra rare" and is_v and not is_vmax and is_alt

    if bucket == "alternate art vmax":
        return rarity == "secret rare" and is_vmax and is_alt

    if bucket == "rainbow trainer":
        return rarity == "secret rare" and is_rainbow and not is_vmax and _contains_trainer_signal(card, name_l)

    if bucket == "rainbow vmax":
        return rarity == "secret rare" and is_vmax and is_rainbow and not is_alt

    if bucket == "gold secret rare":
        if rarity != "secret rare":
            return False
        if is_gold:
            return True
        if printed_total is not None and card_number is not None:
            return card_number > printed_total
        return False

    return False


def classify_bucket_status(
    *,
    eligible_count: int,
    mapped_count: int,
    unmapped_count: int,
    overlap_count: int,
    missing_card_number_count: int,
) -> Tuple[str, str]:
    if eligible_count <= 0:
        return "db_label_blocked", "blocked"

    if overlap_count > 0 or unmapped_count > 0:
        if missing_card_number_count > 0:
            return "needs_card_number_boundary_review", "low"
        if unmapped_count + overlap_count <= max(3, int(eligible_count * 0.1)):
            return "needs_manual_name_rule_review", "medium"
        return "needs_manual_name_rule_review", "low"

    if mapped_count == eligible_count:
        return "bucket_classification_ready", "high"

    return "db_label_blocked", "blocked"


def classify_probability_readiness(meta: SetConfigMeta, bucket_status: str) -> str:
    status = _normalize_text(meta.source_confidence_status)
    probability_ready = bool(meta.source_confidence_probability_ready)

    if "best_available_empirical_draft" in status:
        return "probability_ready_candidate"

    if probability_ready:
        return "probability_ready_candidate"

    if status == "blocked_incomplete_probability_model":
        return "source_links_known_but_not_transcribed"

    if status:
        if "partial" in status:
            return "partial_high_rarity_rows_only"
        if "missing" in status:
            return "base_non_rare_rows_missing"

    if bucket_status == "bucket_classification_ready":
        return "no_source_rows_found"

    return "no_source_rows_found"


def _extract_complete_bucket_classification_audit(config_cls: Any) -> Optional[Dict[str, Any]]:
    if config_cls is None:
        return None

    preferred_attrs = [
        "CHILLING_REIGN_BUCKET_CLASSIFICATION_AUDIT",
        "EVOLVING_SKIES_BUCKET_CLASSIFICATION_AUDIT",
    ]

    discovered_attrs = [
        attr
        for attr in dir(config_cls)
        if attr.endswith("_BUCKET_CLASSIFICATION_AUDIT")
    ]

    ordered_attrs: List[str] = []
    for attr in preferred_attrs:
        if attr in discovered_attrs:
            ordered_attrs.append(attr)

    for attr in sorted(discovered_attrs):
        if attr not in ordered_attrs:
            ordered_attrs.append(attr)

    for attr in ordered_attrs:
        raw = getattr(config_cls, attr, None)
        if not isinstance(raw, Mapping):
            continue

        if _normalize_text(raw.get("status")) != "complete":
            continue

        eligible = _safe_int(raw.get("eligible_non_reverse_rare_family_variants"))
        mapped = _safe_int(raw.get("mapped_variants"))
        unmapped = _safe_int(raw.get("unmapped_variants"))
        overlapping = _safe_int(raw.get("overlapping_variants"))

        if None in {eligible, mapped, unmapped, overlapping}:
            continue

        return {
            "audit_attribute": attr,
            "eligible_non_reverse_rare_family_variants": int(eligible),
            "mapped_variants": int(mapped),
            "unmapped_variants": int(unmapped),
            "overlapping_variants": int(overlapping),
        }

    return None


def _summarize_counter(counter: Counter, max_items: int = 8) -> str:
    if not counter:
        return ""
    ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    trimmed = ordered[:max_items]
    return "; ".join(f"{key}:{value}" for key, value in trimmed)


def _empty_set_result(meta: SetConfigMeta, scope: str, reason: str, db_error: str = "") -> Dict[str, Any]:
    bucket_status = "special_structure_blocked" if scope != "candidate_standard" else "db_label_blocked"
    mapping_confidence = "blocked" if scope != "candidate_standard" else "low"
    probability = classify_probability_readiness(meta, bucket_status)

    if scope != "candidate_standard":
        next_action = "special_pack_structure_do_not_model_yet"
    elif db_error:
        next_action = "needs_supabase_data_fix"
    elif bucket_status == "bucket_classification_ready":
        next_action = "ready_for_pull_rate_research"
    else:
        next_action = "needs_manual_bucket_review"

    return {
        "set_key": meta.set_key,
        "set_name": meta.set_name,
        "set_id": meta.set_id,
        "class_name": meta.class_name,
        "printed_total": meta.printed_total,
        "total": meta.total,
        "config_exists": True,
        "standard_pack_shape": meta.standard_pack_shape,
        "simulation_engine": meta.simulation_engine,
        "slot_schema_runtime_enabled": meta.slot_schema_runtime_enabled,
        "has_rare_slot_probability": meta.has_rare_slot_probability,
        "has_reverse_slot_probabilities": meta.has_reverse_slot_probabilities,
        "reverse_slot_probability_shape": meta.reverse_slot_probability_shape,
        "scope": scope,
        "scope_reason": reason,
        "counts": {
            "card_count": 0,
            "variant_count": 0,
            "reverse_holo_count": 0,
            "eligible_non_reverse_rare_family_variants": 0,
            "mapped_variants": 0,
            "unmapped_variants": 0,
            "overlapping_variants": 0,
            "reverse_holo_in_rare_slot_count": 0,
            "near_mint_price_available_variants": 0,
            "missing_usable_price_variants": None,
        },
        "rarity_counts": {},
        "printing_type_counts": {},
        "special_type_counts": {},
        "edition_counts": {},
        "card_number_presence": {"present": 0, "missing": 0},
        "supertype_presence": {"present": 0, "missing": 0},
        "subtypes_presence": {"present": 0, "missing": 0},
        "set_name_presence": {"present": 0, "missing": 0},
        "bucket_counts": {},
        "bucket_classification_status": bucket_status,
        "mapping_confidence": mapping_confidence,
        "probability_readiness": probability,
        "runtime_ready_candidate": False,
        "recommended_next_action": next_action,
        "notes": "; ".join(filter(None, [reason, db_error]))[:500],
    }


def _analyze_set_rows(
    meta: SetConfigMeta,
    scope: str,
    reason: str,
    cards: Sequence[Mapping[str, Any]],
    variants: Sequence[Mapping[str, Any]],
    market_rows: Sequence[Mapping[str, Any]],
    dedicated_bucket_audit: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    cards_by_id = {row.get("id"): row for row in cards if row.get("id") is not None}

    rarity_counts = Counter(str(card.get("rarity") or "<NULL>") for card in cards)
    card_number_presence = Counter("present" if card.get("card_number") not in (None, "") else "missing" for card in cards)
    supertype_presence = Counter("present" if card.get("supertype") not in (None, "", []) else "missing" for card in cards)
    subtypes_presence = Counter("present" if card.get("subtypes") not in (None, "", []) else "missing" for card in cards)
    set_name_presence = Counter("present" if card.get("set_name") not in (None, "") else "missing" for card in cards)

    printing_counts = Counter(str(variant.get("printing_type") or "<NULL>") for variant in variants)
    special_counts = Counter(str(variant.get("special_type") or "<NULL>") for variant in variants)
    edition_counts = Counter(str(variant.get("edition") or "<NULL>") for variant in variants)

    reverse_holo_count = sum(1 for variant in variants if _is_reverse_variant(variant))

    variant_ids = [variant.get("id") for variant in variants if variant.get("id") is not None]
    nm_rows_by_variant: Dict[Any, List[Mapping[str, Any]]] = defaultdict(list)
    for row in market_rows:
        variant_id = row.get("variant_id")
        if variant_id is None:
            continue
        if _is_near_mint_row(row):
            nm_rows_by_variant[variant_id].append(row)

    near_mint_variants = set()
    missing_usable_price = 0
    for variant_id in variant_ids:
        nm_rows = nm_rows_by_variant.get(variant_id, [])
        if not nm_rows:
            continue
        near_mint_variants.add(variant_id)
        usable = any((price is not None and price > 0) for price in (_extract_price_value(row) for row in nm_rows))
        if not usable:
            missing_usable_price += 1

    eligible_variants: List[Mapping[str, Any]] = []
    reverse_in_rare_slot_count = 0
    missing_card_number_count = 0
    bucket_matches: Dict[Any, List[str]] = defaultdict(list)

    for variant in variants:
        card = cards_by_id.get(variant.get("card_id"), {})
        if _is_rare_family_reverse(card, variant):
            reverse_in_rare_slot_count += 1
        if not _is_rare_family_non_reverse(card, variant):
            continue

        eligible_variants.append(variant)
        if _parse_card_number(card.get("card_number")) is None:
            missing_card_number_count += 1

        for bucket in NORMALIZED_OUTCOME_ORDER:
            if _matches_bucket(bucket, card, variant, meta.printed_total):
                bucket_matches[variant.get("id")].append(bucket)

    mapped_variants = 0
    unmapped_variants = 0
    overlapping_variants = 0
    bucket_counts: Counter = Counter()

    for variant in eligible_variants:
        matches = bucket_matches.get(variant.get("id"), [])
        if len(matches) == 1:
            mapped_variants += 1
            bucket_counts[matches[0]] += 1
        elif len(matches) == 0:
            unmapped_variants += 1
        else:
            overlapping_variants += 1

    eligible_non_reverse_count = len(eligible_variants)
    mapped_non_reverse_count = mapped_variants
    unmapped_non_reverse_count = unmapped_variants
    overlapping_non_reverse_count = overlapping_variants

    bucket_status, mapping_confidence = classify_bucket_status(
        eligible_count=eligible_non_reverse_count,
        mapped_count=mapped_non_reverse_count,
        unmapped_count=unmapped_non_reverse_count,
        overlap_count=overlapping_non_reverse_count,
        missing_card_number_count=missing_card_number_count,
    )

    used_dedicated_audit = False
    if scope == "candidate_standard" and isinstance(dedicated_bucket_audit, Mapping):
        dedicated_eligible = _safe_int(dedicated_bucket_audit.get("eligible_non_reverse_rare_family_variants"))
        dedicated_mapped = _safe_int(dedicated_bucket_audit.get("mapped_variants"))
        dedicated_unmapped = _safe_int(dedicated_bucket_audit.get("unmapped_variants"))
        dedicated_overlapping = _safe_int(dedicated_bucket_audit.get("overlapping_variants"))

        if None not in {
            dedicated_eligible,
            dedicated_mapped,
            dedicated_unmapped,
            dedicated_overlapping,
        }:
            eligible_non_reverse_count = int(dedicated_eligible)
            mapped_non_reverse_count = int(dedicated_mapped)
            unmapped_non_reverse_count = int(dedicated_unmapped)
            overlapping_non_reverse_count = int(dedicated_overlapping)
            bucket_status = "bucket_classification_ready"
            mapping_confidence = "high"
            used_dedicated_audit = True

    if scope != "candidate_standard":
        bucket_status = "special_structure_blocked"
        mapping_confidence = "blocked"

    probability_readiness = classify_probability_readiness(meta, bucket_status)
    runtime_ready_candidate = (
        scope == "candidate_standard"
        and bucket_status == "bucket_classification_ready"
        and probability_readiness in {"candidate_probability_model_possible", "probability_ready_candidate"}
        and not meta.slot_schema_runtime_enabled
        and not meta.has_rare_slot_probability
    )

    if scope != "candidate_standard":
        next_action = "special_pack_structure_do_not_model_yet"
    elif bucket_status in {"needs_manual_name_rule_review", "needs_card_number_boundary_review"}:
        next_action = "needs_manual_bucket_review"
    elif bucket_status == "db_label_blocked":
        next_action = "needs_supabase_data_fix"
    elif probability_readiness == "no_source_rows_found":
        next_action = "ready_for_pull_rate_research"
    elif probability_readiness == "source_links_known_but_not_transcribed":
        next_action = "already_blocked_probability_only"
    else:
        next_action = "ready_for_probability_modeling_if_rates_provided"

    note_segments = [
        "rare is residual-capable",
        "reverse-holo variants excluded from rare-slot mapping",
        "Ultra Rare/Secret Rare are intermediate labels, not final outcomes",
    ]
    if used_dedicated_audit:
        note_segments.append(
            "dedicated completed bucket classification audit metadata used for mapping counts and readiness status"
        )

    return {
        "set_key": meta.set_key,
        "set_name": meta.set_name,
        "set_id": meta.set_id,
        "class_name": meta.class_name,
        "printed_total": meta.printed_total,
        "total": meta.total,
        "config_exists": True,
        "standard_pack_shape": meta.standard_pack_shape,
        "simulation_engine": meta.simulation_engine,
        "slot_schema_runtime_enabled": meta.slot_schema_runtime_enabled,
        "has_rare_slot_probability": meta.has_rare_slot_probability,
        "has_reverse_slot_probabilities": meta.has_reverse_slot_probabilities,
        "reverse_slot_probability_shape": meta.reverse_slot_probability_shape,
        "scope": scope,
        "scope_reason": reason,
        "counts": {
            "card_count": len(cards),
            "variant_count": len(variants),
            "reverse_holo_count": reverse_holo_count,
            "eligible_non_reverse_rare_family_variants": eligible_non_reverse_count,
            "mapped_variants": mapped_non_reverse_count,
            "unmapped_variants": unmapped_non_reverse_count,
            "overlapping_variants": overlapping_non_reverse_count,
            "reverse_holo_in_rare_slot_count": reverse_in_rare_slot_count,
            "near_mint_price_available_variants": len(near_mint_variants),
            "missing_usable_price_variants": missing_usable_price if near_mint_variants else None,
        },
        "rarity_counts": dict(sorted(rarity_counts.items(), key=lambda item: (-item[1], item[0]))),
        "printing_type_counts": dict(sorted(printing_counts.items(), key=lambda item: (-item[1], item[0]))),
        "special_type_counts": dict(sorted(special_counts.items(), key=lambda item: (-item[1], item[0]))),
        "edition_counts": dict(sorted(edition_counts.items(), key=lambda item: (-item[1], item[0]))),
        "card_number_presence": dict(card_number_presence),
        "supertype_presence": dict(supertype_presence),
        "subtypes_presence": dict(subtypes_presence),
        "set_name_presence": dict(set_name_presence),
        "bucket_counts": {bucket: int(bucket_counts.get(bucket, 0)) for bucket in NORMALIZED_OUTCOME_ORDER if bucket_counts.get(bucket, 0)},
        "bucket_classification_status": bucket_status,
        "mapping_confidence": mapping_confidence,
        "probability_readiness": probability_readiness,
        "runtime_ready_candidate": runtime_ready_candidate,
        "recommended_next_action": next_action,
        "dedicated_bucket_classification_audit_used": used_dedicated_audit,
        "dedicated_bucket_classification_audit_attribute": (
            str(dedicated_bucket_audit.get("audit_attribute"))
            if used_dedicated_audit and isinstance(dedicated_bucket_audit, Mapping)
            else ""
        ),
        "notes": "; ".join(note_segments) + ".",
    }


def _render_markdown_table(rows: Sequence[Mapping[str, Any]]) -> str:
    headers = [
        "set_name",
        "set_id",
        "printed_total",
        "total",
        "config_exists",
        "standard_pack_shape",
        "card_count",
        "variant_count",
        "reverse_holo_count",
        "rarity_counts_summary",
        "bucket_classification_status",
        "eligible_rare_family_variants",
        "mapped_variants",
        "unmapped_variants",
        "overlapping_variants",
        "mapping_confidence",
        "probability_readiness",
        "runtime_ready_candidate",
        "recommended_next_action",
        "notes",
    ]

    md_lines = [
        "# SWSH Slot Schema Readiness Matrix",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]

    for row in rows:
        counts = row.get("counts", {})
        values = [
            str(row.get("set_name", "")),
            str(row.get("set_id", "")),
            str(row.get("printed_total", "")),
            str(row.get("total", "")),
            str(row.get("config_exists", False)),
            str(row.get("standard_pack_shape", False)),
            str(counts.get("card_count", 0)),
            str(counts.get("variant_count", 0)),
            str(counts.get("reverse_holo_count", 0)),
            _summarize_counter(Counter(row.get("rarity_counts", {}))),
            str(row.get("bucket_classification_status", "")),
            str(counts.get("eligible_non_reverse_rare_family_variants", 0)),
            str(counts.get("mapped_variants", 0)),
            str(counts.get("unmapped_variants", 0)),
            str(counts.get("overlapping_variants", 0)),
            str(row.get("mapping_confidence", "")),
            str(row.get("probability_readiness", "")),
            str(row.get("runtime_ready_candidate", False)),
            str(row.get("recommended_next_action", "")),
            str(row.get("notes", ""))[:180].replace("|", "/"),
        ]
        md_lines.append("| " + " | ".join(values) + " |")

    return "\n".join(md_lines) + "\n"


def run_readiness_audit(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    markdown_output_path: Path = DEFAULT_MD_PATH,
) -> Dict[str, Any]:
    configs = discover_swsh_set_configs()
    split = split_swsh_targets(configs)

    by_key = {meta.set_key: meta for meta in configs}
    candidate_keys = {item["set_key"] for item in split["included"]}

    supabase, db_error = _get_supabase_client()

    rows: List[Dict[str, Any]] = []
    for meta in sorted(configs, key=lambda item: item.set_id):
        scope, reason = classify_set_scope(meta)
        config_cls = SET_CONFIG_MAP.get(meta.set_key)
        dedicated_bucket_audit = _extract_complete_bucket_classification_audit(config_cls)
        if supabase is None:
            rows.append(_empty_set_result(meta, scope, reason, db_error=db_error or ""))
            continue

        set_row = _resolve_set_row(supabase, meta.set_id, meta.set_name)
        if not set_row:
            rows.append(_empty_set_result(meta, scope, reason, db_error="set row not found"))
            continue

        cards = _fetch_cards_for_set_row(supabase, set_row.get("id"))
        card_ids = [row.get("id") for row in cards if row.get("id") is not None]
        variants = _fetch_variants_for_card_ids(supabase, card_ids)
        variant_ids = [row.get("id") for row in variants if row.get("id") is not None]
        market_rows = _fetch_latest_market_for_variant_ids(supabase, variant_ids)

        row = _analyze_set_rows(
            meta,
            scope,
            reason,
            cards,
            variants,
            market_rows,
            dedicated_bucket_audit=dedicated_bucket_audit,
        )
        row["resolved_set_row_id"] = set_row.get("id")
        row["resolved_set_row_name"] = set_row.get("name")
        rows.append(row)

    rows_sorted = sorted(rows, key=lambda item: item.get("set_id", ""))

    candidate_rows = [row for row in rows_sorted if row.get("set_key") in candidate_keys]
    excluded_rows = [row for row in rows_sorted if row.get("set_key") not in candidate_keys]

    runtime_enabled_sets = [
        row["set_id"]
        for row in rows_sorted
        if row.get("slot_schema_runtime_enabled")
    ]
    rare_slot_probability_sets = [
        row["set_id"]
        for row in rows_sorted
        if row.get("has_rare_slot_probability")
    ]

    summary = {
        "included_standard_sets": [row["set_id"] for row in candidate_rows],
        "excluded_or_special_sets": [row["set_id"] for row in excluded_rows],
        "runtime_enabled_sets": runtime_enabled_sets,
        "sets_with_rare_slot_probability": rare_slot_probability_sets,
        "mapping_ready_sets": [
            row["set_id"]
            for row in candidate_rows
            if row.get("bucket_classification_status") == "bucket_classification_ready"
        ],
        "manual_review_sets": [
            row["set_id"]
            for row in candidate_rows
            if row.get("bucket_classification_status")
            in {"needs_manual_name_rule_review", "needs_card_number_boundary_review"}
        ],
        "special_structure_blocked_sets": [
            row["set_id"]
            for row in excluded_rows
            if row.get("bucket_classification_status") == "special_structure_blocked"
        ],
    }

    payload = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "read_only": True,
            "project": "6.3-6.5",
            "cwd": os.getcwd(),
            "db_connected": supabase is not None,
            "db_error": db_error,
        },
        "discovery": {
            "total_configs": len(configs),
            "included": split["included"],
            "excluded": split["excluded"],
        },
        "summary": summary,
        "rows": rows_sorted,
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_output_path.write_text(_render_markdown_table(rows_sorted), encoding="utf-8")

    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only batch SWSH slot schema readiness audit")
    parser.add_argument(
        "--json-output",
        type=str,
        default=str(DEFAULT_JSON_PATH),
        help="JSON output path (default: logs/audits/swsh_slot_schema_readiness_matrix.json)",
    )
    parser.add_argument(
        "--markdown-output",
        type=str,
        default=str(DEFAULT_MD_PATH),
        help="Markdown matrix output path (default: backend/docs/audits/SWSH_SLOT_SCHEMA_READINESS_MATRIX.md)",
    )
    parser.add_argument("--stdout", action="store_true", help="Print summary JSON to stdout")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = run_readiness_audit(
        json_output_path=Path(args.json_output),
        markdown_output_path=Path(args.markdown_output),
    )

    summary = report["summary"]
    print(f"[audit] included_standard_sets={len(summary['included_standard_sets'])}")
    print(f"[audit] excluded_or_special_sets={len(summary['excluded_or_special_sets'])}")
    print(f"[audit] mapping_ready_sets={summary['mapping_ready_sets']}")
    print(f"[audit] runtime_enabled_sets={summary['runtime_enabled_sets']}")
    print(f"[audit] sets_with_rare_slot_probability={summary['sets_with_rare_slot_probability']}")
    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
