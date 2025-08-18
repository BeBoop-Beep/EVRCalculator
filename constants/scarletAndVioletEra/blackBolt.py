from .baseConfig import BaseSetConfig

class SetBlackBoltConfig(BaseSetConfig):
    SET_NAME = "blackBolt"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/24325/cards/?rows=5000&productTypeID=1" 

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/630434/detailed?range=quarter",
        "Mini Tin Price": "https://infinite-api.tcgplayer.com/price/history/630438/detailed?range=quarter", #TODO average out all mini tins
        "Booster Bundle Price": "https://infinite-api.tcgplayer.com/price/history/630431/detailed?range=quarter", 
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/630686/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/644833/detailed?range=quarter" ,
        "Booster Box Price": None,  # Specialty set, does not have one. 
        "Special Collection Price": "" #None exist atm
    }
    
    PULL_RATE_MAPPING = {
        # https://www.facebook.com/HKF3LIX/posts/pfbid02b9vQUSmnXbZECw8YsucAxEWLNJtZWQPRLvNjNi5WGKWkhtfGEm9jdkzqSt5mjj7cl/
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Black-Bolt-and-White-Flare-Pull-Rates/bac92199-a2a7-4668-b4a4-2647a111776f/
        'common' : 38, # 4/38 (there are 4 commons in each pack with 38 total commons is in the set)
        'uncommon': 32, # 3/32 (there are 3 uncommons in each pack with 32 total uncommons in the set)
        'rare': 10, 
        'double rare': 57,
        'illustration rare': 848,
        'special illustration rare': 1120,
        'black white rare': 1400,
        'ultra rare': 274,
        # Special cases (checked first)
        'poke ball pattern': 488,
        'master ball pattern': 2802,
        'god pack': 2000,
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.4349033
        "slot_1": {
            "poke ball pattern": 1/3,
            "master ball pattern": 1/19,
            "regular reverse": 1 - (1/3) - (1/19) # ≈ 0.61407
        },
        "slot_2": {
            'illustration rare': 1/6,
            "special illustration rare": 1/80,
            "regular reverse": 1 - (1/6) - (1 / 80)  # ≈ 0.820833
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 5,
        'ultra rare': 1 / 17,
        'black white rare': 1 / 496,
        'rare': 1 - (1 / 5) - (1 / 17) - (1 / 496),
    }
 
    GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 1 / 2000,
        "strategy": {
            "type": "random",  # or "fixed"
            "rules": {
                # Option A: unified pool
                # "count": 11,
                # "rarities": ["Illustration Rare", "Special Illustration Rare"]

                # Option B: split by slot
                "rarities": {
                    "illustration rare": 9,
                    "special illustration rare": 1,
                }
            }
        }
    }
