from .baseConfig import BaseSetConfig

class SetShiningFatesShinyVaultConfig(BaseSetConfig):
    SET_NAME = 'Shining Fates Shiny Vault'
    SET_ABBREVIATION = 'SHF'

    SET_ID = 'swsh45sv'
    RELEASE_DATE = '2021/02/19'
    PRINTED_TOTAL = 122
    TOTAL = 122
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh45sv/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh45sv/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
