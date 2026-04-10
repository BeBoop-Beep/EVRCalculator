from .baseConfig import BaseSetConfig

class SetPokMonGOConfig(BaseSetConfig):
    SET_NAME = 'Pokémon GO'
    SET_ABBREVIATION = 'PGO'

    SET_ID = 'pgo'
    RELEASE_DATE = '2022/07/01'
    PRINTED_TOTAL = 78
    TOTAL = 88
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/pgo/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/pgo/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
