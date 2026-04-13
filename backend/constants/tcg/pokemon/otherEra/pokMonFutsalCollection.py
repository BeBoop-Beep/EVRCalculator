from .baseConfig import BaseSetConfig

class SetPokMonFutsalCollectionConfig(BaseSetConfig):
    SET_NAME = 'Pokémon Futsal Collection'
    SET_ABBREVIATION = 'FUT20'

    SET_ID = 'fut20'
    RELEASE_DATE = '2020/09/11'
    PRINTED_TOTAL = 5
    TOTAL = 5
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/fut20/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/fut20/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
