from .baseConfig import BaseSetConfig

class SetShiningLegendsConfig(BaseSetConfig):
    SET_NAME = 'Shining Legends'
    SET_ABBREVIATION = 'SLG'

    SET_ID = 'sm35'
    RELEASE_DATE = '2017/10/06'
    PRINTED_TOTAL = 73
    TOTAL = 81
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm35/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm35/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2054/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2054/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
