from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAME = "20261001220000_market_explorer_rarity_current_subset_v1.sql"
SUPABASE = ROOT.parent / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME

def test_migration_mirrors_match():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()

def test_current_subset_is_materialized_from_same_history_authority():
    sql = SUPABASE.read_text(encoding="utf-8").lower()
    assert "create temp table _mx_rarity_current on commit drop as" in sql
    assert "select * from _mx_rarity_members where market_date=p_market_date" in sql
    assert "create index on _mx_rarity_current(market_key,market_price desc,card_variant_id)" in sql

def test_only_current_output_sources_are_retargeted():
    sql = SUPABASE.read_text(encoding="utf-8").lower()
    assert "replace(v_def,'from _mx_rarity_members x','from _mx_rarity_current x')" in sql
    assert "replace(v_def,'from _mx_rarity_members d','from _mx_rarity_current d')" in sql
    assert "linked as (" not in sql
    assert "sum(ln(s.link_ratio))" not in sql

def test_patch_fails_closed_if_expected_function_shape_changes():
    sql = SUPABASE.read_text(encoding="utf-8").lower()
    assert "rarity_current_subset_anchor_not_found" in sql
    assert "rarity_current_subset_x_source_not_found" in sql
    assert "rarity_current_subset_d_source_not_found" in sql
