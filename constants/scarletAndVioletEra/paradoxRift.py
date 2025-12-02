from .baseConfig import BaseSetConfig

class SetParadoxRiftConfig(BaseSetConfig):
    SET_NAME = "paradoxRift"
    SET_ABBREVIATION = "PAR"
    SCRAPE_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23286/cards/?rows=5000&productTypeID=1" 

    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/512822/detailed?range=quarter",
        "Mini Tin Price": None, #TODO
        "Booster Bundle Price": "", #TODO
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/512813/detailed?range=quarter", #TODO: Has two need to average the prices between them or separate them. This is roaring moon
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/526656/detailed?range=quarter", #TODO: Has two need to average the prices between them or separate them. This is iron valiant 
        "Booster Box Price": None,  #TODO: RESEARCH
        "Special Collection Price": "" #TODO: RESEARCH
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Paradox-Rift-Pull-Rates/0b5fb648-38fc-4f61-a6af-57c2737b4a48/?srsltid=AfmBOooIZs-aYbeAuox63FWiJszuCo1ApHuG-4hpgLasna_YUZAXBWm1
        'common' : 77, # 4/77 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 58, # 3/58 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 27, 
        'double rare': 128,
        'illustration rare': 442,
        'special illustration rare': 712,
        'ultra rare': 421,
        'hyper rare': 576,
        # Special cases (checked first)
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.9018
        "slot_1": {
            "regular reverse": 1
        },
        "slot_2": {
            "illustration rare": 1 / 13,
            "special illustration rare": 1 / 47,
            'hyper rare': 1 / 82,
            "regular reverse": 1 - (1 / 13) - (1 / 47) - (1 / 82), # ≈ 0.9018
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 15,
        'rare': 1 - (1 / 6) - (1 / 15),
    }
 