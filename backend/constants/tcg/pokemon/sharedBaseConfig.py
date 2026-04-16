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
