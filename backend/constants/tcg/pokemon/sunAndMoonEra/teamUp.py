from .baseConfig import BaseSetConfig

class SetTeamUpConfig(BaseSetConfig):
    SET_NAME = 'Team Up'
    SET_ABBREVIATION = 'TEU'

    SET_ID = 'sm9'
    RELEASE_DATE = '2019/02/01'
    PRINTED_TOTAL = 181
    TOTAL = 198
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sm9/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sm9/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2377/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/2377/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
