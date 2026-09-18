from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260915224557_prevent_canonical_set_value_history_provenance_downgrade.sql"
BACKEND = ROOT / "backend" / "db" / "migrations" / NAME
SUPABASE = ROOT / "supabase" / "migrations" / NAME


def _sql() -> str:
    return SUPABASE.read_text(encoding="utf-8").lower()


def test_migration_mirrors_are_byte_identical() -> None:
    assert BACKEND.read_bytes() == SUPABASE.read_bytes()


def test_guard_redefinition_is_pinned_to_observed_live_definition() -> None:
    sql = _sql()
    assert "829f38642188902b1a4f0a124ae1ae85" in sql
    assert "concurrent change detected: canonical set value history guard changed" in sql
    assert "pg_get_functiondef" in sql


def test_canonical_to_generic_update_is_blocked() -> None:
    sql = _sql()
    assert "v_old_is_canonical := tg_op = 'update'" in sql
    assert "if v_old_is_canonical and not v_new_is_canonical then" in sql
    assert "return null;" in sql


def test_canonical_sources_remain_allowed() -> None:
    sql = _sql()
    for source in (
        "canonical_root_set_public_rollout_v1",
        "canonical_root_top10_public_rollout_v1",
        "canonical_root_set_public_rollout_candidate_v1",
        "canonical_root_top10_public_rollout_candidate_v1",
        "canonical_root_standard_backfill_v1",
        "canonical_root_top10_backfill_v1",
        "price_storage_v2_transition_anchor_v1",
        "price_storage_v2_serving_compatibility_v1",
    ):
        assert source in sql
    assert "if v_new_is_canonical then" in sql
    assert "return new;" in sql


def test_prior_composite_guard_is_retained() -> None:
    sql = _sql()
    assert "pokemon_market_public_rollout_root_sets_v1" in sql
    assert "parent_opening_set_id = new.set_id" in sql
    assert "counts_toward_parent_set_value = true" in sql
