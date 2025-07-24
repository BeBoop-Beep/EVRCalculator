from .baseConfig import BaseSetConfig

class SetParadoxRiftConfig(BaseSetConfig):
    SET_NAME = "paradoxRift"
    SCRAPE_URL= "" 

    PRICE_ENDPOINTS = {
        "Pack Price": "",
        "Mini Tin Price": None,
        "Booster Bundle Price": "",
        "ETB Price": "",
        "ETB Promo Price": "" ,
        "Booster Box Price": None,  # Specialty set, does not have one. 
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
        'ace spec': 128,
        'god pack': 2000,
        'demi god pack': (1/3) * 2000
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.517547
        "slot_1": {
            "ace spec rare": 1/13,
            "poke ball pattern": 1/3,
            "regular reverse": 1 - (1/13) - (1/3) # ≈ 0.589747
        },
        "slot_2": {
            "master ball pattern": 1/20,
            "special illustration rare": 1 / 45,
            "regular reverse": 1 - (1 / 20) - (1 / 45)  # ≈ 0.9278
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 13,
        'hyper rare': 1 / 180,
        'rare': 1 - (1 / 6) - (1 / 13) - (1 / 180),
    }
 
    GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 1 / 2000,
        "strategy": {
            "type": "fixed",
            "cards": [
                "Eevee (Master Ball Pattern)",
                "Eevee ex - 167/131",
                "Vaporeon ex - 149/131",
                "Jolteon ex - 153/131",
                "Flareon ex - 146/131",
                "Espeon ex - 155/131",
                "Umbreon ex - 161/131",
                "Glaceon ex - 150/131",
                "Leafeon ex - 144/131",
                "Sylveon ex - 156/131"
            ]
        }
    }

    DEMI_GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 3 * (1/2000),
        "strategy": {
            "type": "random",
            "rules": {
                "count": 3,
                "rarities": ["special illustration rare"]
            }
        }
    }