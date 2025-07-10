from types import MappingProxyType

class BaseSetConfig:
    RARITY_MAPPING = MappingProxyType({
        'common': 'common',
        'uncommon': 'uncommon',
        'rare': 'rare',
        'double rare': 'hits', 
        'ace spec rare': 'hits',
        'poke ball pattern': 'hits',
        'master ball pattern': 'hits',
        'ultra rare': 'hits',
        'hyper rare': 'hits',
        'illustration rare': 'hits',             
        'special illustration rare': 'hits'       
    }) 

    DEFAULT_PRICE_ENDPOINTS = {
        "Pack Price": None,
        "Mini Tin Price": None,
        "Booster Bundle Price": None,
        "ETB Price": None,
        "ETB Promo Price": None,
        "Booster Box Price": None,
        "Special Collection Price": None
    }

    GOD_PACK_CONFIG = {
        "enabled": False,
        "pull_rate": 0,
        "strategy": {}
    }

    DEMI_GOD_PACK_CONFIG = {
        "enabled": False,
        "pull_rate": 0,
        "strategy": {}
    }

    @classmethod
    def get_rarity_pack_multiplier(cls):
        base_multipliers = {}
        if 'common' in cls.PULL_RATE_MAPPING:
            base_multipliers['common'] = 4
        if 'uncommon' in cls.PULL_RATE_MAPPING:
            base_multipliers['uncommon'] = 3

        return {
            **base_multipliers,
            **{
                rarity: 1 / cls.PULL_RATE_MAPPING[rarity]
                for rarity in cls.PULL_RATE_MAPPING
                if rarity not in ['common', 'uncommon']
            }
        }

    @classmethod
    def validate(cls):
        required_attrs = ['SET_NAME', 'PULL_RATE_MAPPING', 'PRICE_ENDPOINTS']
        for attr in required_attrs:
            if not hasattr(cls, attr):
                raise ValueError(f"{cls.__name__} missing required attribute: {attr}")