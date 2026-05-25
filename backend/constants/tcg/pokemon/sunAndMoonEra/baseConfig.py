from types import MappingProxyType
from ..sharedBaseConfig import BaseSetConfig as SharedBaseSetConfig, build_standard_pre_sv_pack_structure

class BaseSetConfig(SharedBaseSetConfig):
    COLLECTION = "TCG"
    TCG = "Pokemon"
    ERA = "Sun and Moon"

    RARITY_MAPPING = MappingProxyType({
        "common": "common",
        "uncommon": "uncommon",
        "rare": "rare",
        "holo rare": "hits",
        "rare holo": "hits",
        "ultra rare": "hits",
        "double rare": "hits",
        "illustration rare": "hits",
        "special illustration rare": "hits",
        "secret rare": "hits",
    })

    GOD_PACK_CONFIG = {
        "enabled": False,
        "pull_rate": 0,
        "strategy": {}
    }

    DEMI_GOD_PACK_CONFIG = {
        "enabled": False,
        "pull_rate": 0,
        "strategy": {}
    }

    # Standard English SM-era packs are modeled as 5 commons, 3 uncommons,
    # 1 reverse/parallel slot, and 1 rare-or-better slot.
    # Basic Energy and code cards are intentionally excluded from modeled slots.
    # Pull-rate tables are still set-specific and intentionally not populated here.
    PACK_STRUCTURE = build_standard_pre_sv_pack_structure()

    SLOTS_PER_RARITY = {
        "common": 5,
        "uncommon": 3,
        "reverse": 1,
        "rare": 1,
    }

    @classmethod
    def get_reverse_eligible_rarities(cls):
        """Return raw rarity labels eligible for reverse foiling."""
        return [
            raw_rarity
            for raw_rarity, group in cls.RARITY_MAPPING.items()
            if group in {"common", "uncommon", "rare"}
        ]

    @classmethod
    def validate(cls):
        required_attrs = ["SET_NAME", "PULL_RATE_MAPPING", "SEALED_DETAILS_URL"]
        for attr in required_attrs:
            if not hasattr(cls, attr):
                raise ValueError(f"{cls.__name__} missing required attribute: {attr}")

