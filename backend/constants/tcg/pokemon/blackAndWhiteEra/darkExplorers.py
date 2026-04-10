from .baseConfig import BaseSetConfig

class SetDarkExplorersConfig(BaseSetConfig):
    SET_NAME = 'Dark Explorers'
    SET_ABBREVIATION = 'DEX'

    SET_ID = 'bw5'
    RELEASE_DATE = '2012/05/09'
    PRINTED_TOTAL = 108
    TOTAL = 111
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/bw5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/bw5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1386/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1386/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
