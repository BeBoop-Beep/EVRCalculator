from .baseConfig import BaseSetConfig

class SetMegaEvolutionPromosConfig(BaseSetConfig):
    SET_NAME = 'ME: Mega Evolution Promo'
    SET_ABBREVIATION = 'MEP'
    SET_ID = RELEASE_DATE = PRINTED_TOTAL = TOTAL = SYMBOL_IMAGE_URL = LOGO_IMAGE_URL = None
    TCGPLAYER_SET_ID = '24451'
    TCGPLAYER_SET_NAME = SET_NAME
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24451/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/24451/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}
    CATALOG_ONLY = True
    SUPPORTS_OPENING_SIMULATION = False
    USE_MONTE_CARLO_V2 = False
    PULL_MODEL_STATUS = 'unsupported'
    PULL_RATE_MAPPING = {}
