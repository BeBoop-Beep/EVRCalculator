import pytest

from backend.Scraper.helpers.card_helper import process_card
from backend.Scraper.parsers.tcgplayer_parser import TCGPlayerParser

def _raw(product_id, name):
    return {'productID': product_id, 'productName': name, 'number': '031',
            'condition': 'Near Mint', 'marketPrice': 8.42, 'rarity': 'Promo',
            'printing': 'Holofoil', 'setID': 999, 'set': 'ME: Mega Evolution Promo', 'setAbbrv': 'MEP'}

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
    assert row['externalSourcePayload']['setID'] == 999
    assert row['externalSourcePayload']['productID'] == 685563


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


def test_parser_preserves_multiple_printings_for_one_product():
    rows = [
        _raw(654597, 'Alakazam - 003'),
        {**_raw(654597, 'Alakazam - 003'), 'printing': 'Normal', 'condition': 'Near Mint'},
    ]
    parser = TCGPlayerParser({})
    parsed = parser.parse_cards({'result': rows})
    assert {(row['edition'], row['printing_type']) for row in parsed} == {
        ('', 'holo'), ('', 'non-holo')}

def test_first_edition_and_unlimited_survive_same_product():
    rows = [
        {**_raw(1, 'Aerodactyl'), 'printing': '1st Edition Holofoil',
         'condition': 'Near Mint 1st Edition Holofoil'},
        {**_raw(1, 'Aerodactyl'), 'printing': 'Unlimited Holofoil',
         'condition': 'Near Mint Unlimited Holofoil'},
    ]
    parsed = TCGPlayerParser({}).parse_cards({'result': rows})
    assert {row['edition'] for row in parsed} == {'1st-edition', 'unlimited'}

def test_normal_and_reverse_holo_survive_same_product():
    rows = [_raw(2, 'Abra'), {**_raw(2, 'Abra'), 'printing': 'Reverse Holofoil',
            'condition': 'Near Mint Reverse Holofoil'}]
    parsed = TCGPlayerParser({}).parse_cards({'result': rows})
    assert {row['printing_type'] for row in parsed} == {'holo', 'reverse-holo'}

def test_identical_nm_duplicate_is_deduped():
    row = _raw(3, 'Abra')
    parser = TCGPlayerParser({})
    assert len(parser.parse_cards({'result': [row, dict(row)]})) == 1
    assert parser.last_card_parse_report['duplicate_nm_rows_deduped'] == 1

def test_conflicting_nm_rows_reject_only_that_variant():
    rows = [_raw(4, 'Abra'), {**_raw(4, 'Abra'), 'marketPrice': 9.99}]
    parser = TCGPlayerParser({})
    assert parser.parse_cards({'result': rows}) == []
    assert parser.last_card_parse_report['rejected_ambiguous_variant_groups'] == 1


def test_base_generic_holo_is_retained_for_market_only_collection():
    parser = TCGPlayerParser({}, set_name="Base")
    parsed = parser.parse_cards({'result': [_raw(42382, 'Charizard - 004/102')]})
    assert len(parsed) == 1
    assert parsed[0]['edition'] == '' and parsed[0]['printing_type'] == 'holo'
    assert parsed[0]['variant_collection_authority'] == 'MARKET_ONLY_AMBIGUOUS_VARIANT'
    assert parsed[0]['external_variant_key'] == 'edition=|printing_type=holo|special_type='
    assert parser.last_card_parse_report['accepted_market_only_ambiguous_variant_groups'] == 1
    assert parser.last_card_parse_report['rejected_external_variant_identity_unavailable'] == 0


def test_base_generic_non_holo_is_retained_for_market_only_collection():
    parser = TCGPlayerParser({}, set_name="Base")
    parsed = parser.parse_cards({'result': [{**_raw(42383, 'Beedrill - 017/102'), 'printing': 'Normal'}]})
    assert len(parsed) == 1
    assert parsed[0]['edition'] == '' and parsed[0]['printing_type'] == 'non-holo'
    assert parsed[0]['variant_collection_authority'] == 'MARKET_ONLY_AMBIGUOUS_VARIANT'
    assert parser.last_card_parse_report['market_only_ambiguous_variant_groups'] == [
        '42383|edition=|printing_type=non-holo|special_type='
    ]


@pytest.mark.parametrize('set_name', ['Jungle', 'Fossil', 'Team Rocket'])
def test_strict_vintage_sets_reject_generic_provider_printing(set_name):
    parser = TCGPlayerParser({}, set_name=set_name)
    assert parser.parse_cards({'result': [_raw(42382, 'Card - 004/102')]}) == []
    assert parser.last_card_parse_report['rejected_external_variant_identity_unavailable'] == 1
    assert parser.last_card_parse_report['external_variant_identity_unavailable'] == [
        '42382|edition=|printing_type=holo|special_type='
    ]


def test_jungle_explicit_first_edition_is_accepted_as_exact_variant():
    parser = TCGPlayerParser({}, set_name='Jungle')
    parsed = parser.parse_cards({'result': [{**_raw(4444, 'Snorlax - 011/64'), 'printing': '1st Edition Holofoil'}]})
    assert len(parsed) == 1
    assert parsed[0]['edition'] == '1st-edition'
    assert parsed[0]['variant_collection_authority'] == 'EXACT_PROVIDER_VARIANT'
    assert parser.last_card_parse_report['accepted_exact_variant_groups'] == 1


def test_vintage_edition_distinct_set_routes_explicit_provider_states_separately():
    rows = [
        {**_raw(42382, 'Charizard - 004/102'), 'printing': '1st Edition Holofoil'},
        {**_raw(42382, 'Charizard - 004/102'), 'printing': 'Unlimited Holofoil'},
        {**_raw(42382, 'Charizard - 004/102'), 'printing': 'Shadowless Holofoil'},
    ]
    parsed = TCGPlayerParser({}, set_name="Base").parse_cards({'result': rows})
    assert {row['edition'] for row in parsed} == {'1st-edition', 'unlimited', 'shadowless'}
    assert len({row['external_variant_key'] for row in parsed}) == 3
    assert {row['variant_collection_authority'] for row in parsed} == {'EXACT_PROVIDER_VARIANT'}
