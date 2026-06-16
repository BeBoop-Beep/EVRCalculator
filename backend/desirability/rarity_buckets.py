from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from backend.calculations.utils.rarity_classification import normalize_rarity_key


HIT_POLICY_VERSION = "pokemon_card_desirability_hit_policy_v2_coverage_cleanup"

PREMIUM_CHASE = "premium_chase"
MAJOR_HIT = "major_hit"
ACCESSIBLE_HIT = "accessible_hit"
REGULAR_HIT = "regular_hit"
EXCLUDED = "excluded"
UNKNOWN = "unknown"

HIT_BUCKETS = frozenset({PREMIUM_CHASE, MAJOR_HIT, ACCESSIBLE_HIT, REGULAR_HIT})
PREMIUM_OR_MAJOR_BUCKETS = frozenset({PREMIUM_CHASE, MAJOR_HIT})

BUCKET_PRIORITY: Dict[str, int] = {
    PREMIUM_CHASE: 5,
    MAJOR_HIT: 4,
    ACCESSIBLE_HIT: 3,
    REGULAR_HIT: 2,
    UNKNOWN: 1,
    EXCLUDED: 0,
}

PREMIUM_KEYS = frozenset(
    {
        "special_illustration_rare",
        "sir",
        "alternate_art",
        "alt_art",
        "rare_secret",
        "secret_rare",
        "hyper_rare",
        "gold",
        "gold_rare",
        "gold_star",
        "black_white_rare",
        "mega_hyper_rare",
        "rare_holo_star",
        "rare_shining",
        "shining",
        "rare_holo_crystal",
        "rare_crystal",
        "crystal_type",
    }
)

MAJOR_KEYS = frozenset(
    {
        "ultra_rare",
        "rare_ultra",
        "illustration_rare",
        "full_art",
        "rainbow_rare",
        "rare_rainbow",
        "trainer_gallery_rare_holo",
        "galarian_gallery_holo_rare",
        "shiny_ultra_rare",
        "rare_shiny_gx",
        "mega_attack_rare",
    }
)

ACCESSIBLE_KEYS = frozenset(
    {
        "double_rare",
        "rare_holo_ex",
        "rare_holo_v",
        "rare_holo_vmax",
        "rare_holo_vstar",
        "rare_holo_gx",
        "rare_holo_lv_x",
        "rare_holo_lv.x",
        "amazing_rare",
        "rare_break",
        "rare_prime",
        "radiant_rare",
        "rare_prism_star",
        "rare_shiny",
        "shiny_rare",
        "classic_collection",
        "rare_holo",
        "holo_rare",
        "rare_holo_pokemon",
    }
)

REGULAR_HIT_KEYS = frozenset()

EXCLUDED_KEYS = frozenset(
    {
        "",
        "common",
        "uncommon",
        "rare",
        "regular_rare",
        "regular_reverse",
        "reverse_holo",
        "reverse_holofoil",
        "poke_ball_pattern",
        "pokeball_pattern",
        "master_ball_pattern",
        "masterball_pattern",
        "ace_spec_rare",
    }
)

RARITY_PRIORITY: Dict[str, int] = {
    "special_illustration_rare": 100,
    "sir": 100,
    "alternate_art": 96,
    "alt_art": 96,
    "black_white_rare": 94,
    "mega_hyper_rare": 93,
    "hyper_rare": 92,
    "secret_rare": 91,
    "rare_secret": 91,
    "gold": 90,
    "gold_rare": 90,
    "gold_star": 90,
    "rare_holo_star": 90,
    "rare_shining": 89,
    "shining": 89,
    "rare_holo_crystal": 88,
    "rare_crystal": 88,
    "crystal_type": 88,
    "ultra_rare": 82,
    "rare_ultra": 82,
    "illustration_rare": 80,
    "full_art": 78,
    "rainbow_rare": 76,
    "rare_rainbow": 76,
    "trainer_gallery_rare_holo": 72,
    "galarian_gallery_holo_rare": 72,
    "mega_attack_rare": 70,
    "double_rare": 60,
    "rare_holo_vmax": 58,
    "rare_holo_vstar": 57,
    "rare_holo_ex": 56,
    "rare_holo_v": 55,
    "rare_holo_gx": 55,
    "amazing_rare": 52,
    "classic_collection": 50,
    "rare_holo": 40,
    "holo_rare": 40,
    "rare_holo_pokemon": 40,
}


@dataclass(frozen=True)
class RarityClassification:
    rarity: str
    normalized_key: str
    bucket: str
    bucket_priority: int
    rarity_priority: int


def classify_rarity(rarity: object) -> RarityClassification:
    raw = "" if rarity is None else str(rarity).strip()
    key = normalize_rarity_key(raw)

    if key in PREMIUM_KEYS:
        bucket = PREMIUM_CHASE
    elif key in MAJOR_KEYS:
        bucket = MAJOR_HIT
    elif key in ACCESSIBLE_KEYS:
        bucket = ACCESSIBLE_HIT
    elif key in REGULAR_HIT_KEYS:
        bucket = REGULAR_HIT
    elif key in EXCLUDED_KEYS:
        bucket = EXCLUDED
    else:
        bucket = UNKNOWN

    return RarityClassification(
        rarity=raw,
        normalized_key=key,
        bucket=bucket,
        bucket_priority=BUCKET_PRIORITY[bucket],
        rarity_priority=RARITY_PRIORITY.get(key, 0),
    )


def is_hit_bucket(bucket: str) -> bool:
    return bucket in HIT_BUCKETS
