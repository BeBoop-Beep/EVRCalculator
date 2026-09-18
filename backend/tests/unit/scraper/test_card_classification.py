"""classify_raw_card_row is the single shared gate both process_card and the
catalog recheck evidence path must agree on -- these tests lock in its three
outcomes and prove process_card's accept/reject boundary is unchanged."""

from backend.Scraper.helpers.card_helper import classify_raw_card_row, process_card


def _row(**overrides):
    base = {
        "productName": "Pikachu - 025/128", "condition": "Near Mint",
        "marketPrice": 4.99, "rarity": "Common", "number": "025/128", "printing": "Normal",
    }
    base.update(overrides)
    return base


def test_normal_card_row_is_processable():
    assert classify_raw_card_row(_row()) == "processable"


def test_code_card_row_is_classified_as_code_card():
    row = _row(productName="Code Card - First Partner Illustration Collection (Series 1)")
    assert classify_raw_card_row(row) == "code_card"


def test_row_missing_market_price_is_missing_required_field():
    row = _row(marketPrice=None)
    assert classify_raw_card_row(row) == "missing_required_field"


def test_row_missing_product_name_is_missing_required_field():
    row = _row(productName=None)
    assert classify_raw_card_row(row) == "missing_required_field"


def test_row_missing_condition_is_missing_required_field():
    row = _row(condition=None)
    assert classify_raw_card_row(row) == "missing_required_field"


def test_process_card_rejects_exactly_the_rows_classify_marks_non_processable():
    """process_card must stay in lockstep with classify_raw_card_row: it IS the same
    gate, not a parallel copy of the rule."""
    pull_rate_mapping = {"Common": 1}

    processable_row = _row()
    code_card_row = _row(productName="Code Card - Some Set")
    missing_field_row = _row(marketPrice=None)

    assert classify_raw_card_row(processable_row) == "processable"
    name, card_dict = process_card(processable_row, pull_rate_mapping)
    assert name is not None
    assert card_dict is not None

    for rejected_row in (code_card_row, missing_field_row):
        assert classify_raw_card_row(rejected_row) != "processable"
        name, card_dict = process_card(rejected_row, pull_rate_mapping)
        assert name is None
        assert card_dict is None


def test_first_partner_collection_2026_three_code_card_rows_are_all_rejected():
    """Reproduces the live First Partner Collection 2026 catalog: TCGplayer's Cards
    surface returns exactly 3 rows, all Code Card rarity/name -- confirmed correct
    rejection, not a parser defect."""
    rows = [
        _row(productName="Code Card - First Partner Illustration Collection (Series 1)",
             rarity="Code Card", number="", marketPrice=0.08),
        _row(productName="Code Card - First Partner Illustration Collection (Series 2)",
             rarity="Code Card", number="", marketPrice=0.16),
        _row(productName="Code Card - First Partner Illustration Collection (Series 3)",
             rarity="Code Card", number="", marketPrice=0.07),
    ]
    classifications = [classify_raw_card_row(row) for row in rows]
    assert classifications == ["code_card", "code_card", "code_card"]
