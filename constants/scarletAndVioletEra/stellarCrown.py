from .baseConfig import BaseSetConfig

class SetStellarCrownConfig(BaseSetConfig):
    SET_NAME = "stellarCrown"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23537/cards/?rows=5000&productTypeID=1" 

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/557331/detailed?range=quarter",
        "Mini Tin Price": None,
        "Booster Bundle Price": "", #TODO
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/557350/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/578811/detailed?range=quarter" ,
        "Booster Box Price": None,  # TODO
        "Special Collection Price": "" #TODO
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Stellar-Crown-Pull-Rates/2c0743dd-dbd0-4504-9ff8-be5a72dd04d1/
        'common' : 0, # 4/46 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 0, # 3/33 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 0,
        'double rare': 106,
        'illustration rare': 167,
        'special illustration rare': 540,
        'ultra rare': 163,
        'hyper rare': 411,
        # Special cases (checked first)
        'ace spec': 60,
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.8547
        "slot_1": {
            "ace spec rare": 1 / 20,
            "regular reverse": 1 - (1 / 20) # ≈ 0.95
        },
        "slot_2": {
            "illustration rare": 1 / 13,
            "special illustration rare": 1 / 90,
            'hyper rare': 1 / 137,
            "regular reverse": 1 - (1 / 13) - (1 / 90) - (1 / 137)  # ≈ 0.9047
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 15,
        'rare': 1 - (1 / 6) - (1 / 15),
    }