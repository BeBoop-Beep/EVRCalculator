from .baseConfig import BaseSetConfig

class SetJourneyTogetherConfig(BaseSetConfig):
    SET_NAME = "journeyTogether"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/24073/cards/?rows=5000&productTypeID=1" 

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/610935/detailed?range=quarter",
        "Sleeved Booster Pack Price": None,
        "Mini Tin Price": None,
        "3 Pack Blister Price": None,
        "Booster Bundle Price": "https://infinite-api.tcgplayer.com/price/history/610953/detailed?range=quarter",
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/610930/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/625181/detailed?range=quarter" ,
        "Booster Box Price": 'https://infinite-api.tcgplayer.com/price/history/610931/detailed?range=quarter',  #TODO: This isn't up to date, will need some research on how to handle
        "Special Collection Price": "" #None exist atm
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Journey-Together-Pull-Rates/1b9f379f-97cb-45cc-b6f6-a1a070a422cd/
        'common' : 85, # 4/85 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 42, # 3/42 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 16, 
        'double rare': 79,
        'illustration rare': 129,
        'special illustration rare': 518,
        'ultra rare': 168,
        'hyper rare': 411,
        # Special cases (checked first)
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.90504
        "slot_1": {
            "regular reverse": 1
        },
        "slot_2": {
            "illustration rare": 1 / 12,
            "special illustration rare": 1 / 86,
            'hyper rare': 1 / 137,
            "regular reverse": 1 - (1 / 12) - (1 / 86) - (1 / 137),  # ≈ 0.90504
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 5,
        'ultra rare': 1 / 15,
        'rare': 1 - (1 / 5) - (1 / 15),
    }
 