from .baseConfig import BaseSetConfig

class SetTemporalForcesConfig(BaseSetConfig):
    SET_NAME = "Temporal Forces"
    SET_ABBREVIATION = "TEF"

    CARD_DETAILS_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23381/cards/?rows=5000&productTypeID=1" 
    SEALED_DETAILS_URL="https://infinite-api.tcgplayer.com/priceguide/set/23381/cards/?rows=5000&productTypeID=25"
    SEALED_SPECIFIC_URL = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/532841/detailed?range=quarter",
        "Mini Tin Price": None, #TODO
        "Booster Bundle Price": "", #TODO
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/532845/detailed?range=quarter", #TODO: Has two need to average the prices between them or separate them. This is walking wake
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/543946/detailed?range=quarter" ,
        "Booster Box Price": None,  # TODO: RESEARCH
        "Special Collection Price": "" #TODO: RESEARCH
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Temporal-Forces-Pull-Rates/28c0ad22-00a4-428f-b22d-e7fee9ec50bc/?srsltid=AfmBOoq-Dq7eC8kdlnN-Awy5BcgTjuLCfNcQqriGWfbcodyaTLqXmKAU
        'common' : 71, # 4/71 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 55, # 3/55 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 14,
        'double rare': 89,
        'illustration rare': 285,
        'special illustration rare': 855,
        'ultra rare': 270,
        'hyper rare': 836,
        # Special cases (checked first)
        'ace spec': 140,
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.8543
        "slot_1": {
            "ace spec rare": 1 / 20,
            "regular reverse": 1 - (1 / 20) # ≈ 0.95
        },
        "slot_2": {
            "illustration rare": 1 / 13,
            "special illustration rare": 1 / 86,
            'hyper rare': 1 / 139,
            "regular reverse": 1 - (1 / 13) - (1 / 86) - (1 / 139)  # ≈ 0.9043
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 15,
        'rare': 1 - (1 / 6) - (1 / 15),
    }
 