from .baseConfig import BaseSetConfig

class SetTeamMagmaVsTeamAquaConfig(BaseSetConfig):
    SET_NAME = 'Team Magma vs Team Aqua'
    SET_ABBREVIATION = 'MA'

    SET_ID = 'ex4'
    RELEASE_DATE = '2004/03/01'
    PRINTED_TOTAL = 95
    TOTAL = 97
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ex4/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ex4/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1377/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1377/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
