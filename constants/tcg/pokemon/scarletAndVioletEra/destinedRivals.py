from .baseConfig import BaseSetConfig

class SetDestinedRivalsConfig(BaseSetConfig):
    SET_NAME = "Destined Rivals"
    SET_ABBREVIATION = "DRI"

    CARD_DETAILS_URL= "https://infinite-api.tcgplayer.com/priceguide/set/24269/cards/?rows=5000&productTypeID=1"
    SEALED_DETAILS_URL="https://infinite-api.tcgplayer.com/priceguide/set/24269/cards/?rows=5000&productTypeID=25"
    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/624683/detailed?range=quarter",
        "Mini Tin Price": None, #None exist atm
        "Booster Bundle Price": "https://infinite-api.tcgplayer.com/price/history/625670/detailed?range=quarter",
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/624676/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/635467/detailed?range=quarter" ,
        "Booster Box Price": "https://infinite-api.tcgplayer.com/price/history/624679/detailed?range=quarter",
        "Special Collection Price": "" #None exist atm
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Destined-Rivals-Pull-Rates/43ba832e-44c9-45a4-ae2e-594df2defdda/?srsltid=AfmBOor73ocuBTR49q2CsdlJV29wPtO2z4mu_MvTJq74mnHTu0G-iILg
        'common' : 85, # 4/85 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 62, # 3/62 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 18, 
        'double rare': 86,
        'illustration rare': 278,
        'special illustration rare': 1033,
        'ultra rare': 344,
        'hyper rare': 894,
        # Special cases (checked first)
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.906029
        "slot_1": {
            "regular reverse": 1  
        },
        "slot_2": {
            "illustration rare": 1/12,
            "special illustration rare": 1 / 94,
            'hyper rare': 1 / 149,
            "regular reverse": 1 - (1 / 12) - (1 / 94) - (1 / 149),  # ≈ 0.906029
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 5,
        'ultra rare': 1 / 16,
        'rare': 1 - (1 / 5) - (1 / 16),
    }
 