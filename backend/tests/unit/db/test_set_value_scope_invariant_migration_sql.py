from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[3] / "db" / "migrations" / "044_enforce_pokemon_set_value_scope_invariants.sql"


def test_scope_invariant_trigger_is_deferred_and_structured():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE CONSTRAINT TRIGGER" in sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert "POKEMON_SET_VALUE_SCOPE_INVARIANT" in sql
    assert "NEW.set_value > v_checklist_value + 0.01" in sql
    assert "v_subset.set_value > NEW.set_value + 0.01" in sql
    assert "value_not_finite" in sql
    assert "value_negative" in sql


def test_scope_invariant_does_not_require_top10_to_be_below_hits():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "value_scope IN ('hits', 'top10')" in sql
    assert "top10" in sql
    assert "hits_value" not in sql
