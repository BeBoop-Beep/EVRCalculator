from .baseConfig import BaseSetConfig

class SetObsidianFlamesConfig(BaseSetConfig):
    SET_NAME = "obsidianFlames"
    SET_ABBREVIATION = "OBF"

    CARD_DETAILS_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23228/cards/?rows=5000&productTypeID=1" 
    SEALED_DETAILS_URL="https://infinite-api.tcgplayer.com/priceguide/set/23228/cards/?rows=5000&productTypeID=25"
    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/501256/detailed?range=quarter",
        "Mini Tin Price": None, #TODO
        "Booster Bundle Price": "", #TODO
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/501264/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/512035/detailed?range=quarter" ,
        "Booster Box Price": None,  #TODO: RESEARCH
        "Special Collection Price": "" #TODO: RESEARCH
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Obsidian-Flames-Pull-Rates/e2a66999-a7b5-4621-9765-c9a132e04bd2/?srsltid=AfmBOooUxe99pA9pdgKr9i-Ghul9Qf0klkrKAElnOkfYOcZ4hOh_Kbmg
        'common' : 92, # 4/92 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 74, # 3/74 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 10, 
        'illustration rare': 158,
        'special illustration rare': 192,
        'ultra rare': 181,
        'hyper rare': 156,
        # Special cases (checked first)
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.891827
        "slot_1": {
            "regular reverse": 1
        },
        "slot_2": {
            "illustration rare": 1/13,
            "special illustration rare": 1 / 32,
            'hyper rare': 1 / 52,
            "regular reverse": 1 - (1 / 13) - (1 / 32) - (1 / 52),  # ≈ 0.891827
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 7,
        'ultra rare': 1 / 15,
        'rare': 1 - (1 / 7) - (1 / 15),
    }
 