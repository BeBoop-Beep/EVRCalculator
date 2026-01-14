from .baseConfig import BaseSetConfig

class SetShroudedFableConfig(BaseSetConfig):
    SET_NAME = "Shrouded Fable"
    SET_ABBREVIATION = "SFA"

    CARD_DETAILS_URL= "https://infinite-api.tcgplayer.com/priceguide/set/23529/cards/?rows=5000&productTypeID=1" 
    SEALED_DETAILS_URL="https://infinite-api.tcgplayer.com/priceguide/set/23529/cards/?rows=5000&productTypeID=25"
    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/552997/detailed?range=quarter",
        "Mini Tin Price": None, #TODO
        "Booster Bundle Price": "", #TODO
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/552999/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/564137/detailed?range=quarter" ,
        "Booster Box Price": None,  # Specialty set, does not have one. 
        "Special Collection Price": "" #None exist atm
    }
    
    PULL_RATE_MAPPING = {
        # https://www.reddit.com/r/PokeInvesting/comments/1elpo0p/shrouded_fable_ultimate_release_guide_pull_rates/
        'common' : 28, # 4/28 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 20, # 3/20 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 7,
        'double rare': 36,
        'illustration rare': 180,
        'special illustration rare': 335,
        'ultra rare': 140,
        'hyper rare': 720,
        # Special cases (checked first)
        'ace spec': 51,
    }

    REVERSE_SLOT_PROBABILITIES = {
        # Total: ≈ 1.8429
        "slot_1": {
            "ace spec rare": 1 / 17,
            "regular reverse": 1 - (1 / 17) # ≈ 0.9412
        },
        "slot_2": {
            "illustration rare": 1 / 12,
            "special illustration rare": 1 / 67,
            'hyper rare': 1 / 144,
            "regular reverse": 1 - (1 / 12) - (1 / 67)  - (1 / 144), # ≈ 0.9017
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 6,
        'ultra rare': 1 / 14,
        'rare': 1 - (1 / 6) - (1 / 14),
    }
 