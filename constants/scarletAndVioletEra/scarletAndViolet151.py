from .baseConfig import BaseSetConfig

class Set151Config(BaseSetConfig):
    SET_NAME = "scarletAndViolet151"
    SCRAPE_URL = "https://infinite-api.tcgplayer.com/priceguide/set/23237/cards/?rows=5000&productTypeID=1"

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/504467/detailed?range=quarter",
        "Mini Tin Price": None,
        "Booster Bundle Price": "https://infinite-api.tcgplayer.com/price/history/502000/detailed?range=quarter",
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/503313/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/517175/detailed?range=quarter" ,
        "Booster Box Price": None,  # Specialty set, does not have one. 
        "Special Collection Price": "https://infinite-api.tcgplayer.com/price/history/502005/detailed?range=quarter"
    }
    
    PULL_RATE_MAPPING = {
        'common': 46,
        'uncommon': 33,
        'rare': 21,
        'double rare': 90,
        'illustration rare': 188,
        'special illustration rare': 225,
        'ultra rare': 248,
        'hyper rare': 154,
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1
        },
        "slot_2": {
            "illustration rare": 1/12,
            "special illustration rare": 1 / 32,
            "regular reverse": 1 - (1 / 12) - (1 / 32)  # ≈ 0.885417
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 8,
        'ultra rare': 1 / 16,
        'hyper rare': 1 / 51,
        'rare': 1 - (1 / 8) - (1 / 16) - (1 / 51),
    }