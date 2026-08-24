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

    # TCGplayer group 1375 ("Expedition", EX, 2002-09-15, 165 cards). This set
    # previously pointed at group 604, which is Base Set: Expedition therefore
    # ingested Base Set prices for its entire history and claimed the /102
    # external identities that belong to `base`.
    TCGPLAYER_SET_ID = '1375'
    TCGPLAYER_SET_NAME = 'Expedition'
    TCGPLAYER_SET_ABBREVIATION = 'EX'
    TCGPLAYER_EXPECTED_CARD_DENOMINATORS = {'165'}
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1375/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1375/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
