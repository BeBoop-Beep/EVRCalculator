from .baseConfig import BaseSetConfig

class SetExpeditionBaseSetConfig(BaseSetConfig):
    SET_NAME = 'Expedition Base Set'
    SET_ABBREVIATION = 'EX'

    SET_ID = 'ecard1'
    RELEASE_DATE = '2002/09/15'
    PRINTED_TOTAL = 165
    TOTAL = 165
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ecard1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ecard1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/604/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/604/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
