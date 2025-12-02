from .baseConfig import BaseSetConfig

class SetPaldeanFatesConfig(BaseSetConfig):
    SET_NAME = "paldeanFates"
    SET_ABBREVIATION = "PAF"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23353/cards/?rows=5000&productTypeID=1" 

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/528038/detailed?range=quarter",
        "Mini Tin Price": None, #TODO
        "Booster Bundle Price": "", #TODO
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/532845/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/535952/detailed?range=quarter" ,
        "Booster Box Price": None,  #TODO: RESEARCH
        "Special Collection Price": "" #TODO: RESEARCH
    }
    
    PULL_RATE_MAPPING = {
        #https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Paldean-Fates-Pull-Rates/23de3e93-0d0f-4ae0-abc4-13664f3001a3/
        'common' : 40, # 4/40 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 25, # 3/25 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 16,
        'double rare': 63,
        'illustration rare': 42,
        'special illustration rare': 465,
        'ultra rare': 76,
        'hyper rare': 372,
        # Special cases (checked first)
        'shiny rare': 472,
        'shiny ultra rare': 155,
    }
#TODO: RESEARCH
    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.5683
        "slot_1": {
            "shiny rare": 1 / 4, 
            "shiny ultra rare": 1 / 13 ,
            "regular reverse": 1 - (1 / 4) - (1 / 13) # ≈ 0.6731
        },
        "slot_2": {
            "illustration rare": 1 / 14,
            "special illustration rare": 1 / 58,
            'hyper rare': 1 / 62,
            "regular reverse": 1 - (1 / 14) - (1 / 58)  - (1 / 62), # ≈ 0.8952
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 15,
        'rare': 1 - (1 / 6) - (1 / 15),
    }
 
