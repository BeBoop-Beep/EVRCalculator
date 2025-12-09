from .baseConfig import BaseSetConfig

class Set151Config(BaseSetConfig):
    SET_NAME = "scarletAndViolet151"
    SET_ABBREVIATION = "MEW"

    CARD_DETAILS_URL = "https://infinite-api.tcgplayer.com/priceguide/set/23237/cards/?rows=5000&productTypeID=1"
    SEALED_DETAILS_URL="https://infinite-api.tcgplayer.com/priceguide/set/23237/cards/?rows=5000&productTypeID=25"   
    PRICE_ENDPOINTS = {
        "Pack Price": "https://infinite-api.tcgplayer.com/price/history/504467/detailed?range=quarter",
        "Mini Tin Price": None,
        "Booster Bundle Price": "https://infinite-api.tcgplayer.com/price/history/502000/detailed?range=quarter",
        "ETB Price": "https://infinite-api.tcgplayer.com/price/history/503313/detailed?range=quarter",
        "ETB Promo Price": "https://infinite-api.tcgplayer.com/price/history/517175/detailed?range=quarter" ,
        "Booster Box Price": None,  # Specialty set, does not have one. 
        "Special Collection Price": "https://infinite-api.tcgplayer.com/price/history/502005/detailed?range=quarter"
    }
    
    PULL_RATE_MAPPING = {
        # https://www.tcgplayer.com/content/article/Pok%C3%A9mon-TCG-Scarlet-Violet%E2%80%94151-Pull-Rates/b237df74-fbb0-40d0-9e13-d69ee6e804d9/?utm_campaign=18098386707&utm_source=google&utm_medium=cpc&utm_content=&utm_term=&adgroupid=&gad_source=1&gad_campaignid=20946811569&gbraid=0AAAAADHLWY3YDhh7a7GyxYkf06Aq5nXaz&gclid=Cj0KCQjw-4XFBhCBARIsAAdNOksXXvRKhxPzTkh5hXHFGAEgYw8nuamZol5PJSpB5pXiqlqRIcgBTgoaAhS7EALw_wcB
        'common': 66,
        'uncommon': 62,
        'rare': 26,
        'double rare': 90,
        'illustration rare': 188,
        'special illustration rare': 225,
        'ultra rare': 248,
        'hyper rare': 154,
    }

    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {
            "regular reverse": 1
        },
        "slot_2": {
            "illustration rare": 1/12,
            "special illustration rare": 1 / 32,
            'hyper rare': 1 / 51,
            "regular reverse": 1 - (1 / 12) - (1 / 32) - (1 / 51)  # ≈ 0.885417
        }
    }

    RARE_SLOT_PROBABILITY = {
        'double rare': 1 / 8,
        'ultra rare': 1 / 16,
        'rare': 1 - (1 / 8) - (1 / 16),
    }

    GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 1 / 2000,  # or whatever the real rate is
        "strategy": {
            "type": "fixed",
            "packs": [
                {
                    "name": "Charmander Line",
                    "cards": [
                        "Charmander - 168/165",
                        "Charmeleon - 169/165",
                        "Charizard ex - 199/165"
                    ]
                },
                {
                    "name": "Squirtle Line",
                    "cards": [
                        "Squirtle - 170/165",
                        "Wartortle - 171/165",
                        "Blastoise ex - 200/165"
                    ]
                },
                {
                    "name": "Bulbasaur Line",
                    "cards": [
                        "Bulbasaur - 166/165",
                        "Ivysaur - 167/165",
                        "Venusaur ex - 198/165"
                    ]
                }
            ]
        }
    }