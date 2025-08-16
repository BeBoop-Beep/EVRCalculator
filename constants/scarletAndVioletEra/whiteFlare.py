from .baseConfig import BaseSetConfig

class SetWhiteFlareConfig(BaseSetConfig):
    SET_NAME = "whiteFlare"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/24326/cards/?rows=5000&productTypeID=1" 

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/630699/detailed?range=quarter",
        "Mini Tin Price": None,
        "Booster Bundle Price": "",
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/630689/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/644835/detailed?range=quarter" ,
        "Booster Box Price": None,  # Specialty set, does not have one. 
        "Special Collection Price": ""
    }
    
    PULL_RATE_MAPPING = {
        'common' : 46, # 4/46 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 33, # 3/33 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 27, # 3/21 (there are 1.21 rares in each pack with 21 total rares in the set)
        'double rare': 57,
        'illustration rare': 848,
        'special illustration rare': 1120,
        'black white rare': 832,
        'ultra rare': 274,
        # Special cases (checked first)
        'poke ball pattern': 488,
        'master ball pattern': 2802,
        'god pack': 2000,
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.4349033
        "slot_1": {
            "poke ball pattern": 1/3,
            "master ball pattern": 1/19,
            "regular reverse": 1 - (1/3) - (1/19) # ≈ 0.61407
        },
        "slot_2": {
            'illustration rare': 1/6,
            "special illustration rare": 1/80,
            "regular reverse": 1 - (1/6) - (1 / 80)  # ≈ 0.820833
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 5,
        'ultra rare': 1 / 17,
        'black white rare': 1 / 416,
        'rare': 1 - (1 / 5) - (1 / 17) - (1 / 416),
    }
 
    GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 1 / 2000,
        "strategy": {
            "type": "random",  # or "fixed"
            "rules": {
                # Option A: unified pool
                # "count": 11,
                # "rarities": ["Illustration Rare", "Special Illustration Rare"]

                # Option B: split by slot
                "rarities": {
                    "illustration rare": 9,
                    "special illustration rare": 1,
                }
            }
        }
    }

    DEMI_GOD_PACK_CONFIG = {
        "enabled": False,
    }