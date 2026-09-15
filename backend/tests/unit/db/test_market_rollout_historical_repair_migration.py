from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260915224219_repair_certified_post_cutover_standard_top10_history_canonical_asof.sql"
BACKEND = ROOT / "backend" / "db" / "migrations" / NAME
SUPABASE = ROOT / "supabase" / "migrations" / NAME


def _sql() -> str:
    return SUPABASE.read_text(encoding="utf-8").lower()


def test_migration_mirrors_are_byte_identical() -> None:
    assert BACKEND.read_bytes() == SUPABASE.read_bytes()


def test_repair_is_bounded_to_exact_certified_cohort() -> None:
    sql = _sql()
    assert "r.certified_on_date" in sql
    assert "greatest(a.activated_market_date,date '2026-09-10')" in sql
    assert "a.deactivated_market_date is null" in sql
    assert "v_pairs<>113" in sql
    assert "a4d1cd357c3a73999e08e2b5f5b6bc22" in sql
    assert "c404f7946b8239254ee087964b3143d0" in sql
    assert "v_old_standard_sum<>150493.27" in sql
    assert "v_new_standard_sum<>185501.53" in sql
    assert "v_old_top10_sum<>112890.55" in sql
    assert "v_new_top10_sum<>133801.88" in sql


def test_repair_uses_canonical_asof_price_authority_and_root_membership() -> None:
    sql = _sql()
    assert "get_pokemon_set_value_canonical_prices_as_of_v2_shadow" in sql
    assert "parent_opening_set_id=p.set_id" in sql
    assert "counts_toward_parent_set_value=true" in sql
    assert "set_value_eligible=true" in sql
    assert "partition by root_set_id,snapshot_date,canonical_card_id" in sql
    assert "order by market_price desc nulls last,canonical_card_id" in sql


def test_standard_and_top10_are_repaired_atomically() -> None:
    sql = _sql()
    assert "source='canonical_root_standard_backfill_v1'" in sql
    assert "source='canonical_root_top10_backfill_v1'" in sql
    assert "v_standard_updated<>113 or v_top10_updated<>113" in sql
    assert "coverage_pct=100.00" in sql
    assert sql.startswith("begin;")
    assert sql.rstrip().endswith("commit;")


def test_replay_is_noop_without_production_cohort() -> None:
    sql = _sql()
    assert "if v_pairs=0 then" in sql
    assert "no certified post-cutover generic root-history cohort to repair" in sql
    assert "return;" in sql


def test_repair_records_audit_receipt() -> None:
    sql = _sql()
    assert "price_storage_v2_migration_audit" in sql
    assert "certified_post_cutover_standard_top10_canonical_asof_repair_20260915" in sql
    assert "'certifiedshadowgate',true" in sql.replace(" ", "")
