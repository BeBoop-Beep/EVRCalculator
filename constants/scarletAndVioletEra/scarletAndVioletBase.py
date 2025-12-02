from .baseConfig import BaseSetConfig

class SetScarletAndVioletBaseConfig(BaseSetConfig):
    SET_NAME = "scarletAndVioletBase"
    SET_ABBREVIATION = "SVI"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/22873/cards/?rows=5000&productTypeID=1" 

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/476451/detailed?range=quarter",
        "Mini Tin Price": None, #TODO
        "Booster Bundle Price": "", #TODO
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/478336/detailed?range=quarter", #TODO: Has two need to average the prices between them or separate them.
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/490719/detailed?range=quarter" , #TODO: Has two need to average the prices between them or separate them.
        "Booster Box Price": None,  # TODO: RESEARCH
        "Special Collection Price": "" #TODO: RESEARCH
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Scarlet-Violet-Pull-Rates/a7702fce-dd64-4a58-beb1-0f871c853215/?srsltid=AfmBOoo4eBSBCqZ2pBRf6KcsdcHYJH5e3pnctfWpRbYzD7tHFWNCAChw
        'common' : 121, # 4/121 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 60, # 3/60 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 21,
        'double rare': 87,
        'illustration rare': 313,
        'special illustration rare': 318,
        'ultra rare': 309,
        'hyper rare': 324,
        # Special cases (checked first)
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.517547
        "slot_1": {
            "regular reverse": 1
        },
        "slot_2": {
            "illustration rare": 1 / 13,
            "special illustration rare": 1 / 32,
            'hyper rare': 1 / 54,
            "regular reverse": 1 - (1 / 13) - (1 / 32) - (1 / 54), # ≈ 0.9278
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 7,
        'ultra rare': 1 / 15,
        'rare': 1 - (1 / 7) - (1 / 15),
    }
 