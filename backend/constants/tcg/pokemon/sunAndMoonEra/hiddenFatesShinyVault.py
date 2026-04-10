from .baseConfig import BaseSetConfig

class SetHiddenFatesShinyVaultConfig(BaseSetConfig):
    SET_NAME = 'Hidden Fates Shiny Vault'
    SET_ABBREVIATION = 'HIF'

    SET_ID = 'sma'
    RELEASE_DATE = '2019/08/23'
    PRINTED_TOTAL = 94
    TOTAL = 94
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/sma/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/sma/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
