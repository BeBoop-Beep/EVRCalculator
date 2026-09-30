from pathlib import Path

from backend.scripts.run_market_microstructure_bucket_b4_tail_completion import (
    CANONICAL_CARD_ID,
    CREDIT_CAP,
    PROVIDER_CARD_ID,
    TCGPLAYER_PRODUCT_ID,
)


def test_tail_target_is_frozen_to_the_single_remaining_core_panel_card():
    assert CANONICAL_CARD_ID == "ad79530b-263d-45bd-be6a-6c0dc17e682d"
    assert PROVIDER_CARD_ID == 76774
    assert TCGPLAYER_PRODUCT_ID == "693517"


def test_tail_completion_is_tightly_bounded():
    assert CREDIT_CAP == 3000
    source = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b4_tail_completion.py"
    ).read_text(encoding="utf-8")
    assert "ebay_sold_page(" in source
    assert "graded=None" in source
    assert "operational_pause_reason(db)" in source
    assert "core_panel_backfill_cursor" in source
    assert "phase2_lifetime_archival" in source
    assert "CREDIT_CAP = 3000" in source
    assert "cards_by_tcgplayer_id" not in source
