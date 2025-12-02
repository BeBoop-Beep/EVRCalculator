from .baseConfig import BaseSetConfig

class SetSurgingSparksConfig(BaseSetConfig):
    SET_NAME = "surgingSparks"
    SET_ABBREVIATION = "SSP"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23651/cards/?rows=5000&productTypeID=1" 

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/565604/detailed?range=quarter",
        "Mini Tin Price": None, #TODO
        "Booster Bundle Price": "", #TODO
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/565630/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/594386/detailed?range=quarter" ,
        "Booster Box Price": None,  # TODO: RESEARCH
        "Special Collection Price": "" #TODO: RESEARCH
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Surging-Sparks-Pull-Rates/6ccfb6ab-f26a-4ce8-bab5-5f91c85ec70e/
        'common' : 88, # 4/88 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 61, # 3/61 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 16, 
        'double rare': 106,
        'illustration rare': 300,
        'special illustration rare': 960,
        'ultra rare': 312,
        'hyper rare': 1127,
        # Special cases (checked first)
        'ace spec': 159,
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.8563
        "slot_1": {
            "ace spec rare": 1 / 20,
            "regular reverse": 1 - (1 / 20) # ≈ 0.95
        },
        "slot_2": {
            "illustration rare":  1 / 13,
            "special illustration rare": 1 / 87,
            'hyper rare': 1 / 188,
            "regular reverse": 1 - (1 / 13) - (1 / 87) - (1 / 188)  # ≈ 0.9063
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 15,
        'rare': 1 - (1 / 6) - (1 / 15),
    }
 