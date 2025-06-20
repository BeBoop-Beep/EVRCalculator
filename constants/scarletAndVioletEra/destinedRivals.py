from .baseConfig import BaseSetConfig

class SetDestinedRivalsConfig(BaseSetConfig):
    SET_NAME = "destinedRivals"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/24269/cards/?rows=5000&productTypeID=1"

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/624683/detailed?range=quarter",
        "Mini Tin Price": None,
        "Booster Bundle Price": "https://infinite-api.tcgplayer.com/price/history/625670/detailed?range=quarter",
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/624676/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/635467/detailed?range=quarter" ,
        "Booster Box Price": "https://infinite-api.tcgplayer.com/price/history/624679/detailed?range=quarter",  # Specialty set, does not have one. 
        "Special Collection Price": ""
    }
    
    PULL_RATE_MAPPING = {
        'common' : 46, # 4/46 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 33, # 3/33 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 21, # 3/21 (there are 1.21 rares in each pack with 21 total rares in the set)
        'double rare': 106,
        # 'illustration rare': 188,
        'special illustration rare': 1440,
        'ultra rare': 161,
        'hyper rare': 900,
        # Special cases (checked first)
        'poke ball pattern': 302,
        'master ball pattern': 1362,
        'ace spec': 128
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "ace_spec": 1/13,
            "pokeball_pattern": 1/3,
            "regular_reverse": 1 - (1/13) - (1/3) # ≈ 0.589747
        },
        "slot_2": {
            "masterball_pattern": 1/20,
            "special_illustration_rare": 1 / 45,
            "regular_reverse": 1 - (1 / 20) - (1 / 45)  # ≈ 0.9278
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 13,
        'hyper rare': 1 / 180,
        'rare': 1 - (1 / 6) - (1 / 13) - (1 / 180),
    }
