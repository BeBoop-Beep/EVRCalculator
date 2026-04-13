from .baseConfig import BaseSetConfig

class SetHsUndauntedConfig(BaseSetConfig):
    SET_NAME = 'HS—Undaunted'
    SET_ABBREVIATION = 'UD'

    SET_ID = 'hgss3'
    RELEASE_DATE = '2010/08/18'
    PRINTED_TOTAL = 90
    TOTAL = 91
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/hgss3/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/hgss3/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1403/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1403/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
