from pathlib import Path

MIGRATION = Path("supabase/migrations/20260929192500_market_standard_history_setbased_reconcile_v2.sql")


def test_standard_history_setbased_reconcile_is_bounded_and_excludes_vintage_generic_roots():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "reconcile_pokemon_market_standard_history_setbased_v2" in sql
    assert "p_limit integer default 25" in sql
    assert "p_limit>50" in sql
    assert "pokemon_market_root_set_value_daily_history_v2_shadow" in sql
    assert "pokemon_set_value_daily_history" in sql
    assert "pokemon_edition_split_root_sets_v2" in sql
    assert "value_scope in ('hits','top10')" in sql
    assert "canonical_root_standard_history_v2_reconciled_setbased_v2" in sql
    assert "rootsremaining" in sql.replace("_", "")
