from .baseConfig import BaseSetConfig

class SetBattleStylesConfig(BaseSetConfig):
    SET_NAME = 'Battle Styles'
    SET_ABBREVIATION = 'BST'

    SET_ID = 'swsh5'
    RELEASE_DATE = '2021/03/19'
    PRINTED_TOTAL = 163
    TOTAL = 183
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/swsh5/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/swsh5/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
