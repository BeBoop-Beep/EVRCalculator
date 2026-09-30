from pathlib import Path

from backend.scripts.run_market_microstructure_bucket_b5 import (
    DAILY_B5_CREDIT_CAP,
    EXPECTED_CORE_PANEL_READY,
    HORIZON_DAYS,
    MAX_ROWS_PER_TARGET_ROUND,
    MODE,
    PAGE_SIZE,
    SELECTOR_VERSION,
)


def test_b5_contract_is_gap_first_and_bounded():
    assert MODE == "bucket_b5_targeted_sold_history_v1"
    assert SELECTOR_VERSION == "bucket_b5_gap_then_governed_7d_movers_v1"
    assert EXPECTED_CORE_PANEL_READY == 207
    assert HORIZON_DAYS == 180
    assert PAGE_SIZE == 20
    assert MAX_ROWS_PER_TARGET_ROUND == 80
    assert DAILY_B5_CREDIT_CAP == 8000


def test_b5_source_uses_governed_movers_and_exact_tcgplayer_identity():
    source = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b5.py"
    ).read_text(encoding="utf-8")
    assert "published Explore snapshot is already ordered" in source
    assert "pokemon_explore_card_movers_snapshot_latest" in source
    assert "card_variant_external_identities" in source
    assert '"provider", "tcgplayer"' not in source  # no accidental tuple misuse
    assert '.eq("provider", "tcgplayer")' in source
    assert "cards_by_tcgplayer_id" in source
    assert "B5_PROVIDER_IDENTITY_COUNT_" in source


def test_b5_never_mutates_canonical_price_authority():
    source = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b5.py"
    ).read_text(encoding="utf-8")
    assert '"canonical_price_mutation": False' in source
    assert "pokemon_canonical_card_market_prices_latest" not in source
    assert "update(" not in source or "store.update_run(" in source


def test_b5_requires_completed_core_panel_and_operational_pause_checks():
    source = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b5.py"
    ).read_text(encoding="utf-8")
    assert "CORE_PANEL_NOT_COMPLETE" in source
    assert "operational_pause_reason(db)" in source
    assert "priority_tier" in source
    assert "unresolved_t1" in source
    assert "GOVERNED_7D_MOVER" in source
    assert "MISSING_PRICE_EXACT_VARIANT" in source
