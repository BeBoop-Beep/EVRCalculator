from datetime import date
from pathlib import Path

from backend.scripts.run_market_microstructure_bucket_b5 import (
    DAILY_B5_CREDIT_CAP,
    EXPECTED_CORE_PANEL_READY,
    HORIZON_DAYS,
    IDENTITY_RESOLUTION_VERSION,
    _exact_name_number_matches,
    _number_key,
    MAX_ROWS_PER_TARGET_ROUND,
    MODE,
    PAGE_SIZE,
    SELECTOR_VERSION,
    _state,
    _persist_scope_reconciliation,
    _evidence_summary,
    B5_SCOPE_VERSION,
)


def test_b5_contract_is_gap_first_and_bounded():
    assert MODE == "bucket_b5_targeted_sold_history_v1"
    assert SELECTOR_VERSION == "bucket_b5_gap_then_governed_7d_movers_v2"
    assert IDENTITY_RESOLUTION_VERSION == "b5_name_number_first_v2"
    assert EXPECTED_CORE_PANEL_READY == 207
    assert HORIZON_DAYS == 180
    assert PAGE_SIZE == 20
    assert MAX_ROWS_PER_TARGET_ROUND == 80
    assert DAILY_B5_CREDIT_CAP == 55000


def test_b5_source_uses_governed_movers_and_exact_tcgplayer_identity():
    source = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b5.py"
    ).read_text(encoding="utf-8")
    assert "published Explore snapshot is already ordered" in source
    assert "pokemon_explore_card_movers_snapshot_latest" in source
    assert "card_variant_external_identities" in source
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


def test_b5_provider_search_resolves_name_number_before_set_name():
    source = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b5.py"
    ).read_text(encoding="utf-8")
    assert "cards_by_name_number" in source
    assert "Only consult set search" in source
    assert "_exact_name_number_matches" in source
    assert "provider.startswith(target + \" - \")" in source


def test_b5_deterministic_identity_misses_are_not_retried_every_cron_tick():
    source = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b5.py"
    ).read_text(encoding="utf-8")
    assert "_deterministic_identity_blocks_today" in source
    assert "identity_resolution_version" in source
    assert 'error.startswith("B5_PROVIDER_IDENTITY_COUNT_")' in source
    assert 'error.startswith("B5_PROVIDER_SET_COUNT_")' in source


def test_b5_name_number_match_accepts_provider_display_suffix_and_zero_padding():
    rows = [
        {"id": 1, "name": "Mewtwo V - SWSH229", "number": "SWSH229"},
        {"id": 2, "name": "Mewtwo VMAX", "number": "SWSH229"},
    ]
    matches = _exact_name_number_matches(rows, name="Mewtwo V", number="SWSH229")
    assert [row["id"] for row in matches] == [1]
    assert _number_key("004") == _number_key("4") == "4"


def test_b5_name_number_match_rejects_wrong_number():
    rows = [{"id": 1, "name": "Charizard", "number": "5"}]
    assert _exact_name_number_matches(rows, name="Charizard", number="4") == []


def test_b5_scope_version_is_exact_variant_v2():
    assert B5_SCOPE_VERSION == "exact_target_variant_v2"


def test_evidence_summary_filters_provider_variant_and_exact_attribution():
    calls = []

    class Query:
        def select(self, columns):
            calls.append(("select", columns))
            return self
        def eq(self, field, value):
            calls.append(("eq", field, str(value)))
            return self
        def order(self, field):
            calls.append(("order", field))
            return self
        def range(self, start, end):
            calls.append(("range", start, end))
            return self
        def execute(self):
            return type("Result", (), {"data": [{"sold_at": "2026-03-30"}]})()

    class DB:
        def table(self, name):
            calls.append(("table", name))
            return Query()

    result = _evidence_summary(DB(), 10796, "f6610127-cea6-4c61-8f5d-bb14ba3d42a2")
    assert result["oldest_sold_at"] == "2026-03-30"
    assert ("eq", "provider_card_id", "10796") in calls
    assert ("eq", "card_variant_id", "f6610127-cea6-4c61-8f5d-bb14ba3d42a2") in calls
    assert ("eq", "attribution", "exact") in calls


def test_old_v1_ready_metadata_is_invalidated_and_recomputed(monkeypatch):
    target = {
        "canonical_card_id": "gap-card",
        "card_variant_id": "first-edition-variant",
        "priority_tier": 1,
        "priority_reason": "MISSING_PRICE_EXACT_VARIANT",
    }
    identity = {
        "provider_card_id": 10796,
        "canonical_card_id": "gap-card",
    }
    sync = {
        "provider_card_id": 10796,
        "canonical_card_id": "gap-card",
        "status": "PARTIAL",
        "rows_seen": 580,
        "rows_inserted": 580,
        "metadata": {
            "b5_ready": True,
            "b5_ready_reason": "HORIZON_180D",
            "b5_horizon_cutoff": "2026-04-03",
            # Deliberately no b5_scope_version: this is the unsafe v1 state.
            "targeted_backfill_in_progress": True,
            "targeted_backfill_cursor": "opaque",
        },
    }

    class Store:
        def get_identity_by_canonical(self, cid):
            return identity
        def get_sync_state(self, provider_id):
            return sync

    import backend.scripts.run_market_microstructure_bucket_b5 as b5

    monkeypatch.setattr(
        b5,
        "_evidence_summary",
        lambda db, provider_card_id, card_variant_id: {
            "oldest_sold_at": "2026-08-17",
            "exact_target_transaction_count_lower_bound": 15,
        },
    )
    state = _state(
        object(),
        Store(),
        target,
        reference=date(2026, 9, 30),
        cutoff=date(2026, 4, 3),
    )
    assert state["ready"] is False
    assert state["needs_scope_reconciliation"] is True
    assert state["oldest"] == "2026-08-17"

    monkeypatch.setattr(
        b5,
        "_evidence_summary",
        lambda db, provider_card_id, card_variant_id: {
            "oldest_sold_at": "2026-03-30",
            "exact_target_transaction_count_lower_bound": 110,
        },
    )
    state = _state(
        object(),
        Store(),
        target,
        reference=date(2026, 9, 30),
        cutoff=date(2026, 4, 3),
    )
    assert state["ready"] is True
    assert state["ready_reason"] == "HORIZON_180D"
    assert state["needs_scope_reconciliation"] is True


def test_scope_reconciliation_preserves_cursor_and_writes_v2_metadata():
    target = {
        "canonical_card_id": "gap-card",
        "priority_tier": 1,
        "priority_reason": "MISSING_PRICE_EXACT_VARIANT",
    }
    sync = {
        "provider_card_id": 10796,
        "canonical_card_id": "gap-card",
        "last_ingested_at": None,
        "last_sold_at": "2026-09-27",
        "last_attempt_at": "2026-09-30T00:00:00+00:00",
        "last_success_at": "2026-09-30T00:00:00+00:00",
        "status": "PARTIAL",
        "consecutive_failures": 0,
        "rows_seen": 580,
        "rows_inserted": 580,
        "last_error_code": None,
        "metadata": {
            "targeted_backfill_in_progress": True,
            "targeted_backfill_cursor": "opaque-cursor",
        },
    }
    state = {
        "identity": {"provider_card_id": 10796},
        "sync": sync,
        "ready": True,
        "ready_reason": "HORIZON_180D",
        "oldest": "2026-03-30",
    }

    class Store:
        payload = None
        def upsert_sync_state(self, payload):
            self.payload = payload

    store = Store()
    _persist_scope_reconciliation(
        store,
        target,
        state,
        reference=date(2026, 9, 30),
        cutoff=date(2026, 4, 3),
    )
    assert store.payload["metadata"]["b5_scope_version"] == B5_SCOPE_VERSION
    assert store.payload["metadata"]["b5_ready"] is True
    assert store.payload["metadata"]["b5_oldest_sold_at"] == "2026-03-30"
    assert store.payload["metadata"]["targeted_backfill_cursor"] == "opaque-cursor"


def test_page_oldest_is_exact_target_variant_only():
    source = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "run_market_microstructure_bucket_b5.py"
    ).read_text(encoding="utf-8")
    assert 'row.get("attribution") == "exact"' in source
    assert 'row.get("card_variant_id")' in source
    assert '"b5_scope_version": B5_SCOPE_VERSION' in source
