class BaseSetConfig:
    COLLECTION = "TCG"
    TCG = "Pokemon"
    # Shared root base stays era-neutral; era identity is owned by era-specific base configs.
    ERA = ""

    GOD_PACK_CONFIG = {
        "enabled": False,
        "pull_rate": 0,
        "strategy": {},
    }

    DEMI_GOD_PACK_CONFIG = {
        "enabled": False,
        "pull_rate": 0,
        "strategy": {},
    }

    SLOTS_PER_RARITY = {
        "common": 4,
        "uncommon": 3,
        "reverse": 2,
        "rare": 1,
    }

    PRODUCT_VARIANT_RULES = {
        "etb": {
            "standard": {
                "packs_per_product": 9,
            },
        },
        "booster_box": {
            "standard": {
                "packs_per_product": 36,
            },
        },
    }

    # Optional per-set hook for excluding specific raw rarities from
    # chase/hit-derived metrics only. Simulation/state token handling remains
    # unchanged.
    CHASE_METRICS_EXCLUDED_RARITIES = frozenset()

    @classmethod
    def validate(cls):
        required_attrs = ["SET_NAME", "PULL_RATE_MAPPING", "SEALED_DETAILS_URL"]
        for attr in required_attrs:
            if not hasattr(cls, attr):
                raise ValueError(f"{cls.__name__} missing required attribute: {attr}")

    @classmethod
    def get_pack_state_overrides(cls):
        """Optional set-level delta over era defaults for V2 pack-state modeling."""
        return {}


def build_standard_pre_sv_pack_structure():
    """Return the standard English pre-SV modeled pack slot structure.

    TODO: This helper currently models standard English Sun & Moon / Sword &
    Shield packs only. Do not assume XY, Black & White, HGSS, or older eras
    share this shape without explicit verification.

    Modeled slots intentionally exclude non-value inserts such as basic Energy,
    code cards, and VSTAR markers.
    """
    return {
        "common_slots": 5,
        "uncommon_slots": 3,
        "rare_family_slots": [
            {
                "name": "rare_slot_1",
                "role": "reverse_parallel",
                "probability_attr": "REVERSE_SLOT_PROBABILITIES",
                "probability_key": "slot_1",
                "default_outcome": "regular reverse",
            },
            {
                "name": "rare_slot_2",
                "role": "rare_or_better",
                "probability_attr": "RARE_SLOT_PROBABILITY",
                "default_outcome": "rare",
            },
        ],
    }
