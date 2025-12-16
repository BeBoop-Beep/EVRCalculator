# Map DTO sections to their handlers
INGEST_HANDLERS = {
    'set': {
        'controller': 'sets_controller',
        'method': 'get_or_create_set',
        'returns_set_id': True,
    },
    'cards': {
        'controller': 'cards_controller',
        'method': 'ingest_cards',
        'requires_set_id': True,
    },
    'prices': {
        'controller': 'prices_controller',
        'method': 'ingest_prices',
        'requires_set_id': True,
    },
    'sealed_products': {
        'controller': 'sealed_products_controller',
        'method': 'ingest_sealed_products',
        'requires_set_id': True,
    },
}
