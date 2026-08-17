from backend.Scraper.helpers.card_helper import process_card
from backend.Scraper.parsers.tcgplayer_parser import TCGPlayerParser

def _raw(product_id, name):
    return {'productID': product_id, 'productName': name, 'number': '031',
            'condition': 'Near Mint', 'marketPrice': 8.42, 'rarity': 'Promo',
            'printing': 'Holofoil', 'set': 'ME: Mega Evolution Promo', 'setAbbrv': 'MEP'}

def test_product_id_survives_parser_and_pc_printing_stays_distinct():
    parsed = TCGPlayerParser({}).parse_cards({'result': [
        _raw(680480, "N's Zekrom - 031"),
        _raw(680481, "N's Zekrom - 031 (Pokemon Center Exclusive)"),
    ]})
    assert {row['tcgplayer_product_id'] for row in parsed} == {'680480', '680481'}
    assert {row['name'] for row in parsed} == {"N's Zekrom"}
    assert {row['variant'] for row in parsed} == {'', 'pokemon-center-exclusive'}
    assert all(row['external_catalog_key'] == 'MEP' for row in parsed)

def test_process_card_preserves_external_provenance():
    _, row = process_card(_raw(685563, 'Tyrunt - 070 (Pokemon Center Exclusive)'), {})
    assert row['tcgplayerProductID'] == '685563'
    assert row['externalSourcePayload']['setAbbrv'] == 'MEP'
