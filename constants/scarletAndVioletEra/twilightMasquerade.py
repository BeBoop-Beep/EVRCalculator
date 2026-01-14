from .baseConfig import BaseSetConfig

class SetTwilightMasqueradeConfig(BaseSetConfig):
    SET_NAME = "twilightMasquerade"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23473/cards/?rows=5000&productTypeID=1"

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/543843/detailed?range=quarter",
        "Mini Tin Price": None, #TODO
        "Booster Bundle Price": "", #TODO
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/543845/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/552785/detailed?range=quarter" ,
        "Booster Box Price": None,  # TODO
        "Special Collection Price": "" #TODO
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Twilight-Masquerade-Pull-Rates/f3eea967-e5fb-4108-8655-bb1c89587628/
        'common' : 76, # 4/76 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 55, # 3/55 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 16,
        'double rare': 83,
        'illustration rare': 272,
        'special illustration rare': 941,
        'ultra rare': 318,
        'hyper rare': 879,
        # Special cases (checked first)
        'ace spec': 119,
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.517547
        "slot_1": {
            "ace spec rare": 1 / 20,
            "regular reverse": 1 - (1 / 20) # ≈ 0.95
        },
        "slot_2": {
            "illustration rare": 1 / 13,
            "special illustration rare": 1 / 86,
            'hyper rare': 1 / 146,
            "regular reverse": 1 - (1 / 13) - (1 / 86) - (1 / 146)  # ≈ 0.9278
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 15,
        'rare': 1 - (1 / 6) - (1 / 15),
    }
 