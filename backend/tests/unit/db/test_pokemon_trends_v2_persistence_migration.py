from pathlib import Path


SQL = Path("backend/db/migrations/20260910190000_persist_pokemon_trends_v2_source_run.sql").read_text(encoding="utf-8").lower()


def test_atomic_rpc_and_duplicate_protection_are_present():
    assert "persist_pokemon_trends_v2_source_run" in SQL
    assert "pg_advisory_xact_lock" in SQL
    assert "pokemon_trends_v2_fingerprint_uidx" in SQL
    assert "jsonb_array_length(p_observations) <> 1025" in SQL


def test_rpc_is_service_only_and_reuses_existing_tables():
    assert "revoke all on function" in SQL and "grant execute" in SQL
    assert "pokemon_collector_source_runs" in SQL
    assert "pokemon_collector_entity_observations" in SQL
    assert "create table" not in SQL


def test_idempotent_resolution_and_terminal_guards_are_explicit():
    assert "'created', false" in SQL
    sealed = Path("backend/db/migrations/20260904050026_harden_collector_card_appeal_validation_and_current_reads.sql").read_text(encoding="utf-8").lower()
    boundary = Path("backend/db/migrations/20260904060447_seal_collector_appeal_run_boundaries.sql").read_text(encoding="utf-8").lower()
    assert "terminal collector source run % is immutable" in sealed
    assert "require_running_pokemon_collector_source_run" in boundary
