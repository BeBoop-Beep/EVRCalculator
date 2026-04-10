from .baseConfig import BaseSetConfig

class SetDragonVaultConfig(BaseSetConfig):
    SET_NAME = 'Dragon Vault'
    SET_ABBREVIATION = 'DRV'

    SET_ID = 'dv1'
    RELEASE_DATE = '2012/10/05'
    PRINTED_TOTAL = 20
    TOTAL = 21
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/dv1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/dv1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
