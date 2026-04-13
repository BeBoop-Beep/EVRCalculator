from .baseConfig import BaseSetConfig

class SetGymHeroesConfig(BaseSetConfig):
    SET_NAME = 'Gym Heroes'
    SET_ABBREVIATION = 'G1'

    SET_ID = 'gym1'
    RELEASE_DATE = '2000/08/14'
    PRINTED_TOTAL = 132
    TOTAL = 132
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/gym1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/gym1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1441/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1441/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
