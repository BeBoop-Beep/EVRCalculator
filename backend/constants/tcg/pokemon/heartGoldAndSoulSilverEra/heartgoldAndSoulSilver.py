from .baseConfig import BaseSetConfig

class SetHeartgoldAndSoulSilverConfig(BaseSetConfig):
    SET_NAME = 'HeartGold & SoulSilver'
    SET_ABBREVIATION = 'HS'

    SET_ID = 'hgss1'
    RELEASE_DATE = '2010/02/10'
    PRINTED_TOTAL = 123
    TOTAL = 124
    SYMBOL_IMAGE_URL = 'https://images.pokemontcg.io/hgss1/symbol.png'
    LOGO_IMAGE_URL = 'https://images.pokemontcg.io/hgss1/logo.png'

    # TODO: Populate scrape targets once TCGplayer set links are resolved.
    CARD_DETAILS_URL = None
    SEALED_DETAILS_URL = None
    PRICE_ENDPOINTS = {}

    # TODO: Add set-specific pull rate mappings when data is available.
    PULL_RATE_MAPPING = {}
