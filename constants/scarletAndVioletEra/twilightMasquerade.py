from .baseConfig import BaseSetConfig

class SetTwilightMasqueradeConfig(BaseSetConfig):
    SET_NAME = "twilightMasquerade"

    PRICE_ENDPOINTS = {
        **BaseSetConfig.DEFAULT_PRICE_ENDPOINTS,
        "Pack Price": "https://example.com/pack",
        "Booster Bundle Price": "https://example.com/bundle",
    }

    PULL_RATE_MAPPING = {
        'common': 46,
        'uncommon': 33,
        'rare': 21,
        'double rare': 106,
        'special illustration rare': 1440,
        'ultra rare': 161,
        'hyper rare': 900,
        'poke ball pattern': 302,
        'master ball pattern': 1362,
        'ace spec': 128
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "ace_spec": 1/13,
            "pokeball_pattern": 1/3,
            "regular_reverse": 1 - (1/13) - (1/3)
        },
        "slot_2": {
            "masterball_pattern": 1/20,
            "special_illustration_rare": 1 / 45,
            "regular_reverse": 1 - (1 / 20) - (1 / 45)
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 13,
        'hyper rare': 1 / 180,
        'rare': 1 - (1 / 6) - (1 / 13) - (1 / 180),
    }
