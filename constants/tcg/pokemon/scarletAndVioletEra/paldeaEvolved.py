from .baseConfig import BaseSetConfig

class SetPaldeaEvolvedConfig(BaseSetConfig):
    SET_NAME = "Paldea Evolved"
    SET_ABBREVIATION = "PAL"

    CARD_DETAILS_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23120/cards/?rows=5000&productTypeID=1" 
    SEALED_DETAILS_URL="https://infinite-api.tcgplayer.com/priceguide/set/23120/cards/?rows=5000&productTypeID=25"
    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/493976/detailed?range=quarter",
        "Mini Tin Price": None, #TODO
        "Booster Bundle Price": "", #TODO
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/493974/detailed?range=quarter", 
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/500263/detailed?range=quarter" ,
        "Booster Box Price": None,  # TODO: RESEARCH
        "Special Collection Price": "", #TODO: RESEARCH
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Paldea-Evolved-Pull-Rates/1b7d3e70-9542-4a50-8692-1661e2316521/
        'common' : 81, # 4/81 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 70, # 3/70 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 25, 
        'double rare': 124,
        'illustration rare': 473,
        'special illustration rare': 468,
        'ultra rare': 391,
        'hyper rare': 512,
        # Special cases (checked first)
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.891827
        "slot_1": {
            "regular reverse": 1 
        },
        "slot_2": {
            "illustration rare": 1 / 13, 
            "special illustration rare": 1 / 32,
            'hyper rare': 1 / 57,
            "regular reverse": 1 - (1 / 13) - (1 / 32) - (1 / 57),  # ≈ 0.891827
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 7,
        'ultra rare': 1 / 15,
        'rare': 1 - (1 / 7) - (1 / 15),
    }
 