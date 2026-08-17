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


def test_parser_keeps_one_nm_row_per_unambiguous_commercial_product():
    rows = [
        {**_raw(680480, "N's Zekrom - 031"), 'condition': 'Lightly Played Holofoil', 'marketPrice': 7.0},
        _raw(680480, "N's Zekrom - 031"),
    ]
    parser = TCGPlayerParser({})
    parsed = parser.parse_cards({'result': rows})
    assert len(parsed) == 1
    assert parsed[0]['condition'] == 'Near Mint'
    assert parser.last_card_parse_report['commercial_products'] == 1


def test_parser_rejects_product_id_that_names_multiple_printings():
    rows = [
        _raw(654597, 'Alakazam - 003'),
        {**_raw(654597, 'Alakazam - 003'), 'printing': 'Normal', 'condition': 'Near Mint'},
    ]
    parser = TCGPlayerParser({})
    assert parser.parse_cards({'result': rows}) == []
    assert parser.last_card_parse_report['ambiguous_product_ids'] == ['654597']
