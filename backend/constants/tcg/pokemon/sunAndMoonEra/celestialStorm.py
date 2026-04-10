from .baseConfig import BaseSetConfig

class SetCelestialStormConfig(BaseSetConfig):
    SET_NAME = 'Celestial Storm'
    SET_ABBREVIATION = 'CES'

    SET_ID = 'sm7'
    RELEASE_DATE = '2018/08/03'
    PRINTED_TOTAL = 168
    TOTAL = 187
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm7/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm7/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2278/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2278/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
