from .baseConfig import BaseSetConfig

class SetPokMonRumbleConfig(BaseSetConfig):
    SET_NAME = 'Pokémon Rumble'
    SET_ABBREVIATION = None

    SET_ID = 'ru1'
    RELEASE_DATE = '2009/12/02'
    PRINTED_TOTAL = 16
    TOTAL = 16
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/ru1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/ru1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1433/cards/?rows=5000&productTypeID=1'
    SEALED_DETAILS_URL = 'https://infinite-api.tcgplayer.com/priceguide/set/1433/cards/?rows=5000&productTypeID=25'
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
