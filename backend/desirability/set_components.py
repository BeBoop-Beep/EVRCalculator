from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.desirability.rarity_buckets import (
    ACCESSIBLE_HIT,
    BUCKET_PRIORITY,
    EXCLUDED,
    HIT_BUCKETS,
    MAJOR_HIT,
    PREMIUM_CHASE,
    PREMIUM_OR_MAJOR_BUCKETS,
    UNKNOWN,
    classify_rarity,
)
from backend.desirability.rarity_overrides import apply_card_rarity_override


SCORING_VERSION = "pokemon_set_desirability_components_v2_40_25_20_15"
DEPTH_POINT_CAP = 12.0
ACCESSIBLE_POINT_CAP = 12.0
FINAL_WEIGHTS = {
    "chase_subject_strength": 0.40,
    "chase_subject_depth": 0.25,
    "accessible_favorite_hits": 0.20,
    "special_pack_chase_appeal": 0.15,
}

EXPECTED_NON_POKEMON_HIT = "expected_non_pokemon_hit"
UNMATCHED_POKEMON_HIT = "unmatched_pokemon_hit"
UNSUPPORTED_SUBJECT_HIT = "unsupported_subject_hit"
TRUE_MISSING_LINK = "true_missing_link"
UNKNOWN_OR_UNCLASSIFIED_HIT = "unknown_or_unclassified"

HIT_LINK_CATEGORY_COUNT_KEYS = {
    EXPECTED_NON_POKEMON_HIT: "expected_non_pokemon_hit_count",
    UNMATCHED_POKEMON_HIT: "unmatched_pokemon_hit_count",
    UNSUPPORTED_SUBJECT_HIT: "unsupported_subject_hit_count",
    TRUE_MISSING_LINK: "true_missing_link_count",
    UNKNOWN_OR_UNCLASSIFIED_HIT: "unknown_or_unclassified_hit_count",
}


def build_card_facts(
    *,
    cards: Sequence[Dict[str, Any]],
    links: Sequence[Dict[str, Any]],
    scores_by_reference: Dict[int, Dict[str, Any]],
    references_by_pokedex: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    references_by_pokedex = references_by_pokedex or {}
    links_by_card: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for link in links:
        card_id = str(link.get("pokemon_canonical_card_id") or "")
        if card_id:
            links_by_card[card_id].append(link)

    facts: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for card in cards:
        card_id = str(card.get("id") or "")
        base_classification = classify_rarity(card.get("rarity"))
        classification, classification_override = apply_card_rarity_override(card, base_classification)
        card_links = links_by_card.get(card_id, [])
        if not card_links:
            card_links = _fallback_links_from_pokedex(card, references_by_pokedex)

        if not card_links and classification.bucket in HIT_BUCKETS:
            category = _missing_hit_link_category(card, classification)
            if category in {UNMATCHED_POKEMON_HIT, TRUE_MISSING_LINK}:
                warnings.append(f"Pokemon hit card has no desirability link: {card.get('name')}")
            elif category == UNKNOWN_OR_UNCLASSIFIED_HIT:
                warnings.append(f"Hit-like card could not be classified for desirability linking: {card.get('name')}")
            facts.append(_card_fact(card, None, None, classification, hit_link_category=category, classification_override=classification_override))
            continue

        if not card_links:
            facts.append(_card_fact(card, None, None, classification, classification_override=classification_override))
            continue

        for link in card_links:
            reference_id = _as_int(link.get("pokemon_reference_id"))
            score_row = scores_by_reference.get(reference_id or -1)
            if score_row is None and classification.bucket in HIT_BUCKETS:
                warnings.append(f"Linked hit-like card is missing composite score: {card.get('name')}")
            facts.append(_card_fact(card, link, score_row, classification, hit_link_category="linked_pokemon_hit", classification_override=classification_override))

    return facts, sorted(set(warnings))


def collapse_subject_rollups(card_facts: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for fact in card_facts:
        subject_key = fact.get("subject_key")
        if subject_key:
            grouped[str(subject_key)].append(fact)

    rollups: List[Dict[str, Any]] = []
    for facts in grouped.values():
        representative = sorted(facts, key=_representative_sort_key, reverse=True)[0]
        unique_card_ids = {fact.get("pokemon_canonical_card_id") for fact in facts if fact.get("pokemon_canonical_card_id")}
        bucket_counts = Counter(fact.get("rarity_bucket") for fact in facts if fact.get("rarity_bucket"))
        buckets_present = sorted(bucket_counts, key=lambda bucket: BUCKET_PRIORITY.get(bucket, -1), reverse=True)
        score_values = [_as_float(fact.get("desirability_score")) for fact in facts]
        fan_values = [_as_float(fact.get("fan_popularity_score")) for fact in facts]
        trend_values = [_as_float(fact.get("current_trend_score")) for fact in facts]
        all_cards = sorted(
            {
                (
                    str(fact.get("pokemon_canonical_card_id") or ""),
                    str(fact.get("card_name") or ""),
                    str(fact.get("printed_number") or fact.get("card_number") or ""),
                    str(fact.get("rarity") or ""),
                )
                for fact in facts
            },
            key=lambda item: (item[2], item[1], item[3], item[0]),
        )
        rollups.append(
            {
                "subject_key": representative.get("subject_key"),
                "subject_name": representative.get("subject_name"),
                "pokemon_reference_id": representative.get("pokemon_reference_id"),
                "pokedex_number": representative.get("pokedex_number"),
                "best_representative_card": representative.get("pokemon_canonical_card_id"),
                "representative_card_name": representative.get("card_name"),
                "representative_rarity": representative.get("rarity"),
                "representative_card_number": representative.get("card_number"),
                "representative_printed_number": representative.get("printed_number"),
                "best_rarity_bucket": representative.get("rarity_bucket"),
                "max_desirability_score": _round_metric(_max_present(score_values)),
                "max_fan_score": _round_metric(_max_present(fan_values)),
                "max_trend_score": _round_metric(_max_present(trend_values)),
                "card_count": len(unique_card_ids),
                "premium_chase_card_count": sum(1 for fact in facts if fact.get("rarity_bucket") == PREMIUM_CHASE),
                "major_hit_card_count": sum(1 for fact in facts if fact.get("rarity_bucket") == MAJOR_HIT),
                "accessible_hit_card_count": sum(1 for fact in facts if fact.get("rarity_bucket") == ACCESSIBLE_HIT),
                "rarity_buckets_present": buckets_present,
                "rarity_bucket_counts": dict(sorted(bucket_counts.items())),
                "all_card_names": [
                    {
                        "pokemon_canonical_card_id": card_id,
                        "name": name,
                        "printed_number": printed_number,
                        "rarity": rarity,
                    }
                    for card_id, name, printed_number, rarity in all_cards
                ],
            }
        )

    return sorted(rollups, key=_rollup_sort_key, reverse=True)


def compute_component_scores(
    *,
    subject_rollups: Sequence[Dict[str, Any]],
    card_facts: Sequence[Dict[str, Any]],
    set_config: Any = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    if not card_facts:
        warnings.append("No canonical card facts were available for V2 component scoring.")
    if not subject_rollups:
        warnings.append("No linked Pokemon subjects were available for V2 component scoring.")

    strength, strength_inputs = compute_chase_subject_strength(subject_rollups)
    depth, depth_inputs = compute_chase_subject_depth(subject_rollups)
    accessible, accessible_inputs = compute_accessible_favorite_hits(subject_rollups)
    special, special_summary = compute_special_pack_chase_appeal(
        set_config=set_config,
        subject_rollups=subject_rollups,
        card_facts=card_facts,
    )
    warnings.extend(special_summary.get("warnings") or [])
    hit_link_counts = compute_hit_link_category_counts(card_facts)
    hit_link_samples = _hit_link_category_samples(card_facts)
    rarity_override_summary = _rarity_override_summary(card_facts)
    if hit_link_counts.get("unsupported_subject_hit_count"):
        warnings.append(
            f"{hit_link_counts['unsupported_subject_hit_count']} unsupported non-Pokemon chase hit(s) were excluded from Pokemon-subject scoring."
        )

    final_score = (
        FINAL_WEIGHTS["chase_subject_strength"] * strength
        + FINAL_WEIGHTS["chase_subject_depth"] * depth
        + FINAL_WEIGHTS["accessible_favorite_hits"] * accessible
        + FINAL_WEIGHTS["special_pack_chase_appeal"] * special
    )

    return {
        "set_desirability_score": _round_metric(_bounded(final_score)),
        "chase_subject_strength": strength,
        "chase_subject_depth": depth,
        "accessible_favorite_hits": accessible,
        "special_pack_chase_appeal": special,
        "top_subjects_json": strength_inputs.get("top_subjects", []),
        "component_inputs_json": {
            "formula": "0.40 * chase_subject_strength + 0.25 * chase_subject_depth + 0.20 * accessible_favorite_hits + 0.15 * special_pack_chase_appeal",
            "weights": FINAL_WEIGHTS,
            "chase_subject_strength": strength_inputs,
            "chase_subject_depth": depth_inputs,
            "accessible_favorite_hits": accessible_inputs,
            "hit_link_category_counts": hit_link_counts,
            "rarity_override_summary": rarity_override_summary,
        },
        "special_pack_summary_json": special_summary,
        "diagnostics_json": {
            "component_bounds": "All component scores are bounded 0-100.",
            "duplicate_subject_policy": "Pokemon subjects are collapsed by pokemon_reference_id when available.",
            "missing_top_subject_policy": "Missing top chase slots contribute zero; existing subjects are not renormalized upward.",
            "hit_link_category_counts": hit_link_counts,
            "hit_link_category_samples": hit_link_samples,
            "rarity_override_summary": rarity_override_summary,
            "warning_policy": "Expected non-Pokemon hits are counted in diagnostics; warnings_json is reserved for actionable Pokemon-link or unsupported-subject issues.",
        },
        "warnings_json": sorted(set(warnings)),
    }


def compute_counts(
    *,
    card_facts: Sequence[Dict[str, Any]],
    subject_rollups: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    card_ids_by_bucket: Dict[str, set] = defaultdict(set)
    scored_card_ids: set = set()
    all_hit_card_ids: set = set()
    trainer_hit_ids: set = set()
    unmatched_hit_ids: set = set()
    pokemon_missing_link_ids: set = set()
    for fact in card_facts:
        bucket = str(fact.get("rarity_bucket") or "")
        card_id = fact.get("pokemon_canonical_card_id")
        if bucket in HIT_BUCKETS and card_id:
            all_hit_card_ids.add(card_id)
            card_ids_by_bucket[bucket].add(card_id)
            if _as_float(fact.get("desirability_score")) is not None:
                scored_card_ids.add(card_id)
            if not fact.get("subject_key"):
                unmatched_hit_ids.add(card_id)
            if fact.get("hit_link_category") in {UNMATCHED_POKEMON_HIT, TRUE_MISSING_LINK}:
                pokemon_missing_link_ids.add(card_id)
            if str(fact.get("supertype") or "").strip().lower() == "trainer":
                trainer_hit_ids.add(card_id)

    premium_subjects = [row for row in subject_rollups if int(row.get("premium_chase_card_count") or 0) > 0]
    major_subjects = [row for row in subject_rollups if int(row.get("major_hit_card_count") or 0) > 0]

    unique_subject_count = len(subject_rollups)
    linked_hit_subject_appearances = sum(
        1
        for fact in card_facts
        if fact.get("subject_key") and fact.get("rarity_bucket") in HIT_BUCKETS
    )

    return {
        "hit_eligible_card_count": len(all_hit_card_ids),
        "scored_hit_eligible_card_count": len(scored_card_ids),
        "unique_subject_count": unique_subject_count,
        "duplicate_subject_count": max(0, linked_hit_subject_appearances - unique_subject_count),
        "premium_chase_subject_count": len(premium_subjects),
        "major_hit_subject_count": len(major_subjects),
        "accessible_hit_count": len(card_ids_by_bucket.get(ACCESSIBLE_HIT, set())),
        "trainer_hit_count": len(trainer_hit_ids),
        "unmatched_hit_count": len(unmatched_hit_ids),
        "pokemon_missing_link_count": len(pokemon_missing_link_ids),
        **compute_hit_link_category_counts(card_facts),
        "rarity_bucket_counts_json": {
            bucket: len(card_ids)
            for bucket, card_ids in sorted(card_ids_by_bucket.items())
        },
    }


def compute_hit_link_category_counts(card_facts: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    ids_by_category: Dict[str, set] = defaultdict(set)
    for fact in card_facts:
        category = str(fact.get("hit_link_category") or "")
        key = HIT_LINK_CATEGORY_COUNT_KEYS.get(category)
        card_id = fact.get("pokemon_canonical_card_id")
        if key and card_id:
            ids_by_category[key].add(card_id)
    return {
        count_key: len(ids_by_category.get(count_key, set()))
        for count_key in HIT_LINK_CATEGORY_COUNT_KEYS.values()
    }


def build_set_coverage_audit(
    *,
    set_row: Dict[str, Any],
    cards: Sequence[Dict[str, Any]],
    card_facts: Sequence[Dict[str, Any]],
    limit: int = 10,
) -> Dict[str, Any]:
    unique_hit_ids = {
        fact.get("pokemon_canonical_card_id")
        for fact in card_facts
        if fact.get("pokemon_canonical_card_id") and fact.get("rarity_bucket") in HIT_BUCKETS
    }
    pokemon_linked_hit_ids = {
        fact.get("pokemon_canonical_card_id")
        for fact in card_facts
        if fact.get("pokemon_canonical_card_id")
        and fact.get("rarity_bucket") in HIT_BUCKETS
        and fact.get("subject_key")
    }
    non_pokemon_hit_ids = {
        fact.get("pokemon_canonical_card_id")
        for fact in card_facts
        if fact.get("pokemon_canonical_card_id")
        and fact.get("rarity_bucket") in HIT_BUCKETS
        and _is_clearly_non_pokemon_card(fact)
    }
    unknown_rarity_ids = {
        fact.get("pokemon_canonical_card_id")
        for fact in card_facts
        if fact.get("pokemon_canonical_card_id") and fact.get("rarity_bucket") == UNKNOWN
    }
    excluded_rarity_ids = {
        fact.get("pokemon_canonical_card_id")
        for fact in card_facts
        if fact.get("pokemon_canonical_card_id") and fact.get("rarity_bucket") == EXCLUDED
    }
    card_ids_by_bucket: Dict[str, set] = defaultdict(set)
    for fact in card_facts:
        card_id = fact.get("pokemon_canonical_card_id")
        bucket = fact.get("rarity_bucket")
        if card_id and bucket:
            card_ids_by_bucket[str(bucket)].add(card_id)
    rarity_override_summary = _rarity_override_summary(card_facts)

    hit_rows = sorted(
        [fact for fact in card_facts if fact.get("rarity_bucket") in HIT_BUCKETS],
        key=_representative_sort_key,
        reverse=True,
    )[:limit]

    return {
        "set_name": set_row.get("name"),
        "set_canonical_key": set_row.get("canonical_key"),
        "canonical_card_count": len(cards),
        "hit_like_card_count": len(unique_hit_ids),
        "pokemon_linked_hit_count": len(pokemon_linked_hit_ids),
        "non_pokemon_hit_count": len(non_pokemon_hit_ids),
        "unknown_rarity_count": len(unknown_rarity_ids),
        "excluded_rarity_count": len(excluded_rarity_ids),
        "premium_chase_count": len(card_ids_by_bucket.get(PREMIUM_CHASE, set())),
        "major_hit_count": len(card_ids_by_bucket.get(MAJOR_HIT, set())),
        "accessible_hit_count": len(card_ids_by_bucket.get(ACCESSIBLE_HIT, set())),
        "rarity_override_count": rarity_override_summary["rarity_override_count"],
        "rarity_override_counts_by_source": rarity_override_summary["rarity_override_counts_by_source"],
        "hit_link_category_counts": compute_hit_link_category_counts(card_facts),
        "rarity_bucket_counts": {
            bucket: len(card_ids)
            for bucket, card_ids in sorted(card_ids_by_bucket.items())
        },
        "top_hit_like_rows": [
            {
                "card_name": fact.get("card_name"),
                "rarity": fact.get("rarity"),
                "supertype": fact.get("supertype"),
                "bucket_classification": fact.get("rarity_bucket"),
                "base_bucket_classification": fact.get("base_rarity_bucket"),
                "rarity_override_source": fact.get("rarity_override_source"),
                "classification_override_reason": fact.get("classification_override_reason"),
                "has_pokemon_link": bool(fact.get("subject_key")),
                "matched_pokemon": fact.get("subject_name"),
                "reason_included_or_excluded": _audit_reason(fact),
            }
            for fact in hit_rows
        ],
    }


def compute_chase_subject_strength(subject_rollups: Sequence[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]]:
    candidates = [
        row for row in subject_rollups
        if row.get("best_rarity_bucket") in PREMIUM_OR_MAJOR_BUCKETS
        and _as_float(row.get("max_desirability_score")) is not None
    ]
    ranked = sorted(candidates, key=_rollup_score_sort_key, reverse=True)[:3]
    weights = [0.50, 0.30, 0.20]
    score = sum((_as_float(row.get("max_desirability_score")) or 0.0) * weights[index] for index, row in enumerate(ranked))
    return _round_metric(_bounded(score)), {
        "slot_weights": weights,
        "missing_slot_policy": "Missing top-subject slots contribute zero and are not renormalized.",
        "eligible_bucket_policy": sorted(PREMIUM_OR_MAJOR_BUCKETS),
        "top_subjects": [_top_subject_json(row, weight=weights[index]) for index, row in enumerate(ranked)],
    }


def compute_chase_subject_depth(subject_rollups: Sequence[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]]:
    rows = [
        row for row in subject_rollups
        if any(bucket in PREMIUM_OR_MAJOR_BUCKETS for bucket in row.get("rarity_buckets_present") or [])
    ]
    scored_rows = []
    total_points = 0.0
    for row in rows:
        score = _as_float(row.get("max_desirability_score"))
        points = _tier_points(score)
        if points > 0:
            total_points += points
            scored_rows.append({"subject_name": row.get("subject_name"), "score": _round_metric(score), "points": points})
    return _round_metric(_bounded((min(total_points, DEPTH_POINT_CAP) / DEPTH_POINT_CAP) * 100)), {
        "tier_thresholds": {"anchor": 85, "major": 70, "supporting": 55},
        "tier_points": {"anchor": 3, "major": 2, "supporting": 1},
        "point_cap": DEPTH_POINT_CAP,
        "raw_points": _round_metric(total_points),
        "counted_subjects": scored_rows,
    }


def compute_accessible_favorite_hits(subject_rollups: Sequence[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]]:
    rows = [
        row for row in subject_rollups
        if int(row.get("accessible_hit_card_count") or 0) > 0
    ]
    scored_rows = []
    total_points = 0.0
    for row in rows:
        score = _as_float(row.get("max_desirability_score"))
        points = _tier_points(score)
        if points > 0:
            total_points += points
            scored_rows.append({"subject_name": row.get("subject_name"), "score": _round_metric(score), "points": points})
    return _round_metric(_bounded((min(total_points, ACCESSIBLE_POINT_CAP) / ACCESSIBLE_POINT_CAP) * 100)), {
        "eligible_bucket_policy": [ACCESSIBLE_HIT],
        "tier_thresholds": {"anchor": 85, "major": 70, "supporting": 55},
        "tier_points": {"anchor": 3, "major": 2, "supporting": 1},
        "point_cap": ACCESSIBLE_POINT_CAP,
        "raw_points": _round_metric(total_points),
        "counted_subjects": scored_rows,
    }


def compute_special_pack_chase_appeal(
    *,
    set_config: Any,
    subject_rollups: Sequence[Dict[str, Any]],
    card_facts: Sequence[Dict[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    warnings: List[str] = []
    mechanics = []
    for attr, label, base_score in (
        ("GOD_PACK_CONFIG", "god", 90.0),
        ("DEMI_GOD_PACK_CONFIG", "demi_god", 60.0),
    ):
        config_map = _get_config_mapping(set_config, attr)
        enabled = bool(config_map.get("enabled")) if isinstance(config_map, dict) else False
        mechanic = {
            "type": label,
            "config_attr": attr,
            "enabled": enabled,
            "pull_rate": config_map.get("pull_rate") if isinstance(config_map, dict) else None,
            "strategy_type": ((config_map.get("strategy") or {}).get("type") if isinstance(config_map, dict) else None),
            "base_score": base_score,
            "rate_factor": 0.0,
            "subject_quality": 0.0,
            "score_contribution": 0.0,
        }
        if enabled:
            subjects, source = _special_pack_subjects(config_map, subject_rollups, card_facts)
            if source != "direct_special_pack_composition":
                warnings.append(f"{attr} direct subject composition unavailable; used set-level premium subject quality proxy.")
            subject_quality = _subject_quality_from_rollups(subjects)
            rate_factor = _pull_rate_factor(config_map.get("pull_rate"))
            mechanic.update(
                {
                    "rate_factor": _round_metric(rate_factor),
                    "subject_quality": subject_quality,
                    "subject_quality_source": source,
                    "subjects": [_top_subject_json(row) for row in sorted(subjects, key=_rollup_score_sort_key, reverse=True)[:10]],
                    "score_contribution": _round_metric(base_score * rate_factor * (subject_quality / 100.0)),
                }
            )
        mechanics.append(mechanic)

    score = _bounded(sum(_as_float(row.get("score_contribution")) or 0.0 for row in mechanics))
    return _round_metric(score), {
        "mechanics": mechanics,
        "scoring_note": "Scores only explicit enabled God/Demi-God-style mechanics from config; set_type, specialty status, and booster-box availability are ignored.",
        "warnings": sorted(set(warnings)),
    }


def _special_pack_subjects(
    config_map: Dict[str, Any],
    subject_rollups: Sequence[Dict[str, Any]],
    card_facts: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], str]:
    strategy = config_map.get("strategy") if isinstance(config_map, dict) else {}
    if not isinstance(strategy, dict):
        return _premium_proxy_subjects(subject_rollups), "set_level_premium_proxy"

    specs = list(strategy.get("cards") or [])
    for pack in strategy.get("packs") or []:
        if isinstance(pack, dict):
            specs.extend(pack.get("cards") or [])

    matched_subject_keys = set()
    if specs:
        for spec in specs:
            for fact in card_facts:
                if _fact_matches_card_spec(fact, spec) and fact.get("subject_key"):
                    matched_subject_keys.add(fact["subject_key"])
        if matched_subject_keys:
            return [row for row in subject_rollups if row.get("subject_key") in matched_subject_keys], "direct_special_pack_composition"

    rarity_rules = ((strategy.get("rules") or {}).get("rarities") or {})
    if isinstance(rarity_rules, dict) and rarity_rules:
        rarity_keys = {classify_rarity(rarity).normalized_key for rarity in rarity_rules.keys()}
        for fact in card_facts:
            if fact.get("normalized_rarity_key") in rarity_keys and fact.get("subject_key"):
                matched_subject_keys.add(fact["subject_key"])
        if matched_subject_keys:
            return [row for row in subject_rollups if row.get("subject_key") in matched_subject_keys], "direct_special_pack_composition"

    return _premium_proxy_subjects(subject_rollups), "set_level_premium_proxy"


def _premium_proxy_subjects(subject_rollups: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        row for row in subject_rollups
        if any(bucket in PREMIUM_OR_MAJOR_BUCKETS for bucket in row.get("rarity_buckets_present") or [])
    ]


def _subject_quality_from_rollups(subjects: Sequence[Dict[str, Any]]) -> float:
    ranked = sorted(
        [row for row in subjects if _as_float(row.get("max_desirability_score")) is not None],
        key=_rollup_score_sort_key,
        reverse=True,
    )[:3]
    weights = [0.50, 0.30, 0.20]
    score = sum((_as_float(row.get("max_desirability_score")) or 0.0) * weights[index] for index, row in enumerate(ranked))
    return _round_metric(_bounded(score))


def _fact_matches_card_spec(fact: Dict[str, Any], spec: object) -> bool:
    if isinstance(spec, dict):
        name = str(spec.get("name") or "").strip().lower()
        number = str(spec.get("number") or "").strip().lower()
        rarity = str(spec.get("rarity") or "").strip().lower()
    else:
        raw = str(spec or "").strip()
        name, number = (raw.rsplit(" - ", 1) + [""])[:2] if " - " in raw else (raw, "")
        name = name.strip().lower()
        number = number.strip().lower()
        rarity = ""
    if name and str(fact.get("card_name") or "").strip().lower() != name:
        return False
    if number and number not in {
        str(fact.get("printed_number") or "").strip().lower(),
        str(fact.get("card_number") or "").strip().lower(),
    }:
        return False
    if rarity and str(fact.get("rarity") or "").strip().lower() != rarity:
        return False
    return bool(name or number or rarity)


def _card_fact(
    card: Dict[str, Any],
    link: Optional[Dict[str, Any]],
    score_row: Optional[Dict[str, Any]],
    classification: Any,
    *,
    hit_link_category: Optional[str] = None,
    classification_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reference_id = _as_int((link or {}).get("pokemon_reference_id"))
    subject_name = (score_row or {}).get("pokemon_name") or (link or {}).get("pokemon_name")
    subject_key = f"ref:{reference_id}" if reference_id is not None else None
    base_classification = (classification_override or {}).get("base_rarity_classification") or {}
    fact = {
        "pokemon_canonical_card_id": card.get("id"),
        "pokemon_tcg_api_card_id": card.get("pokemon_tcg_api_card_id"),
        "set_canonical_key": card.get("set_canonical_key"),
        "card_name": card.get("name"),
        "card_number": card.get("number"),
        "printed_number": card.get("printed_number"),
        "rarity": card.get("rarity"),
        "supertype": card.get("supertype"),
        "subtypes": card.get("subtypes") if isinstance(card.get("subtypes"), list) else [],
        "national_pokedex_numbers": card.get("national_pokedex_numbers") if isinstance(card.get("national_pokedex_numbers"), list) else [],
        "pokemon_reference_id": reference_id,
        "pokedex_number": (score_row or {}).get("pokedex_number") or (link or {}).get("pokedex_number"),
        "subject_name": subject_name,
        "subject_key": subject_key,
        "desirability_score": _round_metric((score_row or {}).get("desirability_score")),
        "fan_popularity_score": _round_metric((score_row or {}).get("fan_popularity_score")),
        "current_trend_score": _round_metric((score_row or {}).get("current_trend_score")),
        "rarity_bucket": classification.bucket,
        "normalized_rarity_key": classification.normalized_key,
        "rarity_classification": asdict(classification),
        "base_rarity_classification": base_classification or asdict(classification),
        "base_rarity_bucket": base_classification.get("bucket", classification.bucket),
        "hit_link_category": hit_link_category,
        "hit_link_reason": _hit_link_reason(card, classification, hit_link_category),
    }
    if classification_override:
        fact.update(
            {
                "rarity_override_version": classification_override.get("rarity_override_version"),
                "rarity_override_source": classification_override.get("rarity_override_source"),
                "classification_override_reason": classification_override.get("classification_override_reason"),
                "rarity_override_match": classification_override.get("match"),
            }
        )
    return fact


def _fallback_links_from_pokedex(
    card: Dict[str, Any],
    references_by_pokedex: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not _looks_like_pokemon_card(card):
        return []
    links: List[Dict[str, Any]] = []
    for pokedex_number in _pokedex_numbers(card):
        reference = references_by_pokedex.get(pokedex_number)
        if not reference or reference.get("id") is None:
            continue
        links.append(
            {
                "pokemon_canonical_card_id": card.get("id"),
                "pokemon_reference_id": reference.get("id"),
                "pokedex_number": pokedex_number,
                "pokemon_name": reference.get("display_name") or reference.get("canonical_name"),
                "match_method": "v2_national_pokedex_fallback",
                "source": "pokemon_canonical_cards.national_pokedex_numbers",
            }
        )
    return links


def _missing_hit_link_category(card: Dict[str, Any], classification: Any) -> str:
    if _is_energy_card(card):
        return EXPECTED_NON_POKEMON_HIT
    if _looks_like_pokemon_card(card):
        return TRUE_MISSING_LINK if _pokedex_numbers(card) else UNMATCHED_POKEMON_HIT
    if _unsupported_subject_hit(card, classification):
        return UNSUPPORTED_SUBJECT_HIT
    if _is_clearly_non_pokemon_card(card):
        return EXPECTED_NON_POKEMON_HIT
    return UNKNOWN_OR_UNCLASSIFIED_HIT


def _unsupported_subject_hit(card: Dict[str, Any], classification: Any) -> bool:
    supertype = _normalized_text(card.get("supertype"))
    subtypes = {_normalized_text(item) for item in (card.get("subtypes") if isinstance(card.get("subtypes"), list) else [])}
    if supertype != "trainer" and not {"supporter", "item", "stadium", "tool"} & subtypes:
        return False
    return classification.bucket in PREMIUM_OR_MAJOR_BUCKETS


def _is_clearly_non_pokemon_card(card: Dict[str, Any]) -> bool:
    if _is_energy_card(card):
        return True
    supertype = _normalized_text(card.get("supertype"))
    subtypes = {_normalized_text(item) for item in (card.get("subtypes") if isinstance(card.get("subtypes"), list) else [])}
    if supertype in {"trainer", "energy"}:
        return True
    return bool({"supporter", "item", "stadium", "tool", "energy", "special_energy", "basic_energy"} & subtypes)


def _looks_like_pokemon_card(card: Dict[str, Any]) -> bool:
    if _is_energy_card(card):
        return False
    supertype = _normalized_text(card.get("supertype"))
    if supertype == "pokemon":
        return True
    if _pokedex_numbers(card):
        return True
    subtypes = {_normalized_text(item) for item in (card.get("subtypes") if isinstance(card.get("subtypes"), list) else [])}
    pokemon_subtypes = {
        "basic",
        "stage_1",
        "stage_2",
        "ex",
        "gx",
        "v",
        "vmax",
        "vstar",
        "break",
        "lv_x",
        "lv.x",
        "mega",
        "restored",
    }
    return bool(pokemon_subtypes & subtypes)


def _is_energy_card(card: Dict[str, Any]) -> bool:
    supertype = _normalized_text(card.get("supertype"))
    subtypes = {_normalized_text(item) for item in (card.get("subtypes") if isinstance(card.get("subtypes"), list) else [])}
    if supertype == "energy":
        return True
    return bool({"energy", "special_energy", "basic_energy"} & subtypes)


def _pokedex_numbers(card: Dict[str, Any]) -> List[int]:
    value = card.get("national_pokedex_numbers")
    if not isinstance(value, list):
        return []
    numbers: List[int] = []
    for item in value:
        parsed = _as_int(item)
        if parsed is not None and parsed not in numbers:
            numbers.append(parsed)
    return numbers


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _hit_link_reason(card: Dict[str, Any], classification: Any, category: Optional[str]) -> Optional[str]:
    if classification.bucket not in HIT_BUCKETS:
        return None
    if category == "linked_pokemon_hit":
        return "Hit-like Pokemon subject is linked and eligible for V2 Pokemon-subject scoring."
    if category == EXPECTED_NON_POKEMON_HIT:
        return "Hit-like non-Pokemon row is expected and counted only in diagnostics."
    if category == UNSUPPORTED_SUBJECT_HIT:
        return "Hit-like trainer/supporter chase is valid, but V2 currently scores only Pokemon subjects."
    if category == TRUE_MISSING_LINK:
        return "Pokemon hit has Pokédex data but no stored link; V2 could not resolve it."
    if category == UNMATCHED_POKEMON_HIT:
        return "Pokemon hit has no desirability link and no Pokédex fallback."
    if category == UNKNOWN_OR_UNCLASSIFIED_HIT:
        return "Hit-like row could not be confidently classified as Pokemon or non-Pokemon."
    return None


def _hit_link_category_samples(card_facts: Sequence[Dict[str, Any]], *, limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
    samples: Dict[str, List[Dict[str, Any]]] = {category: [] for category in HIT_LINK_CATEGORY_COUNT_KEYS}
    for fact in card_facts:
        category = fact.get("hit_link_category")
        if category not in samples or len(samples[category]) >= limit:
            continue
        samples[category].append(
            {
                "card_name": fact.get("card_name"),
                "rarity": fact.get("rarity"),
                "supertype": fact.get("supertype"),
                "rarity_bucket": fact.get("rarity_bucket"),
                "base_rarity_bucket": fact.get("base_rarity_bucket"),
                "rarity_override_source": fact.get("rarity_override_source"),
                "reason": fact.get("hit_link_reason"),
            }
        )
    return samples


def _rarity_override_summary(card_facts: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    ids_by_source: Dict[str, set] = defaultdict(set)
    samples: List[Dict[str, Any]] = []
    for fact in card_facts:
        source = fact.get("rarity_override_source")
        card_id = fact.get("pokemon_canonical_card_id")
        if not source or not card_id:
            continue
        ids_by_source[str(source)].add(card_id)
        if len(samples) < 10:
            samples.append(
                {
                    "card_name": fact.get("card_name"),
                    "printed_number": fact.get("printed_number"),
                    "pokemon_tcg_api_card_id": fact.get("pokemon_tcg_api_card_id"),
                    "rarity": fact.get("rarity"),
                    "base_rarity_bucket": fact.get("base_rarity_bucket"),
                    "effective_rarity_bucket": fact.get("rarity_bucket"),
                    "rarity_override_source": source,
                    "classification_override_reason": fact.get("classification_override_reason"),
                }
            )
    return {
        "rarity_override_count": len({card_id for ids in ids_by_source.values() for card_id in ids}),
        "rarity_override_counts_by_source": {
            source: len(ids)
            for source, ids in sorted(ids_by_source.items())
        },
        "samples": samples,
    }


def _audit_reason(fact: Dict[str, Any]) -> str:
    if fact.get("subject_key"):
        return "included: linked Pokemon hit contributes to subject rollups"
    reason = fact.get("hit_link_reason")
    if reason:
        return f"excluded: {reason}"
    if fact.get("rarity_bucket") == UNKNOWN:
        return "excluded: rarity is unknown to V2 bucket policy"
    if fact.get("rarity_bucket") == EXCLUDED:
        return "excluded: rarity is not hit-like under V2 bucket policy"
    return "excluded: no linked Pokemon subject"


def _representative_sort_key(fact: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        int(fact.get("rarity_classification", {}).get("bucket_priority") or 0),
        int(fact.get("rarity_classification", {}).get("rarity_priority") or 0),
        _as_float(fact.get("desirability_score")) or -1.0,
        _as_float(fact.get("fan_popularity_score")) or -1.0,
        _as_float(fact.get("current_trend_score")) or -1.0,
        _stable_card_number_value(fact.get("printed_number") or fact.get("card_number")),
        str(fact.get("card_name") or ""),
    )


def _rollup_sort_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        BUCKET_PRIORITY.get(str(row.get("best_rarity_bucket")), 0),
        _as_float(row.get("max_desirability_score")) or -1.0,
        _as_float(row.get("max_fan_score")) or -1.0,
        _as_float(row.get("max_trend_score")) or -1.0,
        str(row.get("subject_name") or ""),
    )


def _rollup_score_sort_key(row: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        _as_float(row.get("max_desirability_score")) or -1.0,
        BUCKET_PRIORITY.get(str(row.get("best_rarity_bucket")), 0),
        _as_float(row.get("max_fan_score")) or -1.0,
        str(row.get("subject_name") or ""),
    )


def _top_subject_json(row: Dict[str, Any], *, weight: Optional[float] = None) -> Dict[str, Any]:
    payload = {
        "subject_name": row.get("subject_name"),
        "pokemon_reference_id": row.get("pokemon_reference_id"),
        "representative_card_name": row.get("representative_card_name"),
        "representative_rarity": row.get("representative_rarity"),
        "representative_printed_number": row.get("representative_printed_number"),
        "best_rarity_bucket": row.get("best_rarity_bucket"),
        "desirability_score": row.get("max_desirability_score"),
        "fan_popularity_score": row.get("max_fan_score"),
        "current_trend_score": row.get("max_trend_score"),
    }
    if weight is not None:
        payload["component_weight"] = weight
        payload["weighted_contribution"] = _round_metric((_as_float(row.get("max_desirability_score")) or 0.0) * weight)
    return payload


def _tier_points(score: Optional[float]) -> int:
    if score is None:
        return 0
    if score >= 85:
        return 3
    if score >= 70:
        return 2
    if score >= 55:
        return 1
    return 0


def _pull_rate_factor(value: Any) -> float:
    rate = _as_float(value)
    if rate is None or rate <= 0:
        return 0.75
    if rate > 1:
        rate = 1 / rate
    denominator = 1 / rate if rate > 0 else 0
    if denominator >= 2000:
        return 1.0
    if denominator <= 50:
        return 0.35
    return max(0.35, min(1.0, denominator / 2000))


def _get_config_mapping(set_config: Any, attr: str) -> Dict[str, Any]:
    if set_config is None:
        return {}
    if isinstance(set_config, dict):
        value = set_config.get(attr, {})
    else:
        value = getattr(set_config, attr, {})
    return value if isinstance(value, dict) else {}


def _stable_card_number_value(value: Any) -> int:
    text = str(value or "").strip()
    digits = ""
    for char in text:
        if char.isdigit():
            digits += char
        elif digits:
            break
    return int(digits) if digits else -1


def _max_present(values: Sequence[Optional[float]]) -> Optional[float]:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _round_metric(value: Any, digits: int = 4) -> float:
    number = _as_float(value)
    if number is None:
        return 0.0
    return round(number, digits)


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
