from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional, Tuple

from backend.desirability.rarity_buckets import (
    BUCKET_PRIORITY,
    PREMIUM_CHASE,
    RarityClassification,
)
from backend.calculations.utils.rarity_classification import normalize_rarity_key


RARITY_OVERRIDE_VERSION = "pokemon_set_desirability_card_rarity_overrides_v1"

EVOLVING_SKIES_ALT_ART_OVERRIDES = {
    ("evolvingskies", "swsh7-167", "leafeon v", "167/203"),
    ("evolvingskies", "swsh7-205", "leafeon vmax", "205/203"),
    ("evolvingskies", "swsh7-175", "glaceon v", "175/203"),
    ("evolvingskies", "swsh7-209", "glaceon vmax", "209/203"),
    ("evolvingskies", "swsh7-184", "sylveon v", "184/203"),
    ("evolvingskies", "swsh7-212", "sylveon vmax", "212/203"),
    ("evolvingskies", "swsh7-189", "umbreon v", "189/203"),
    ("evolvingskies", "swsh7-215", "umbreon vmax", "215/203"),
    ("evolvingskies", "swsh7-194", "rayquaza v", "194/203"),
    ("evolvingskies", "swsh7-218", "rayquaza vmax", "218/203"),
    ("evolvingskies", "swsh7-192", "dragonite v", "192/203"),
    ("evolvingskies", "swsh7-180", "espeon v", "180/203"),
    ("evolvingskies", "swsh7-196", "noivern v", "196/203"),
    ("evolvingskies", "swsh7-186", "medicham v", "186/203"),
    ("evolvingskies", "swsh7-198", "duraludon v", "198/203"),
    ("evolvingskies", "swsh7-220", "duraludon vmax", "220/203"),
}


def apply_card_rarity_override(
    card: Dict[str, Any],
    base_classification: RarityClassification,
) -> Tuple[RarityClassification, Optional[Dict[str, Any]]]:
    match = _match_evolving_skies_alt_art(card)
    if not match:
        return base_classification, None

    classification = RarityClassification(
        rarity=base_classification.rarity,
        normalized_key=base_classification.normalized_key,
        bucket=PREMIUM_CHASE,
        bucket_priority=BUCKET_PRIORITY[PREMIUM_CHASE],
        rarity_priority=max(base_classification.rarity_priority, 96),
    )
    return classification, {
        "rarity_override_version": RARITY_OVERRIDE_VERSION,
        "rarity_override_source": "evolving_skies_alt_art_card_list",
        "classification_override_reason": (
            "Known Evolving Skies alternate-art chase card promoted to premium_chase "
            "by exact set, Pokemon TCG API card id, name, and printed number."
        ),
        "base_rarity_classification": asdict(base_classification),
        "match": match,
    }


def _match_evolving_skies_alt_art(card: Dict[str, Any]) -> Optional[Dict[str, str]]:
    set_key = _normalized_set_key(card.get("set_canonical_key"))
    api_id = _normalized_text(card.get("pokemon_tcg_api_card_id"))
    name = _normalized_text(card.get("name"))
    printed_number = _normalized_printed_number(card.get("printed_number") or card.get("number"))
    key = (set_key, api_id, name, printed_number)
    if key not in EVOLVING_SKIES_ALT_ART_OVERRIDES:
        return None
    return {
        "set_canonical_key": set_key,
        "pokemon_tcg_api_card_id": api_id,
        "name": name,
        "printed_number": printed_number,
    }


def _normalized_set_key(value: Any) -> str:
    return normalize_rarity_key(str(value or "")).replace("_", "")


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalized_printed_number(value: Any) -> str:
    return str(value or "").strip().lower()
