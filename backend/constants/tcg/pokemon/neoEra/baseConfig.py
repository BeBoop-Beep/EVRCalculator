from types import MappingProxyType

class BaseSetConfig:
    COLLECTION = "TCG"
    TCG = "Pokemon"
    ERA = "Neo"

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

    SLOTS_PER_RARITY = {
        "common": 4,
        "uncommon": 3,
        "reverse": 2,
        "rare": 1,
    }

    @classmethod
    def validate(cls):
        required_attrs = ["SET_NAME", "PULL_RATE_MAPPING", "SEALED_DETAILS_URL"]
        for attr in required_attrs:
            if not hasattr(cls, attr):
                raise ValueError(f"{cls.__name__} missing required attribute: {attr}")

