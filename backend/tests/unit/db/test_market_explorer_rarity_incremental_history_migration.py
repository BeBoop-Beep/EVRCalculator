from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20261002223000_market_explorer_rarity_incremental_history_v1.sql"


def _read(base: str) -> str:
    return (ROOT / base / "migrations" / NAME).read_text()


def test_incremental_rarity_migration_is_mirrored():
    assert (ROOT / "supabase" / "migrations" / NAME).read_bytes() == (
        ROOT / "backend" / "db" / "migrations" / NAME
    ).read_bytes()


def test_existing_rarity_history_anchors_to_validated_serving_generation():
    sql = _read("supabase")
    assert "pokemon_market_explorer_surface_serving_v2" in sql
    assert "g.state='VALIDATED'" in sql
    assert "h.market_date=v_prior_date" in sql
    assert "anchor_date" in sql
    assert "anchor_index" in sql
    assert "anchor_segment" in sql
    assert "h.market_date<=k.anchor_date" in sql


def test_rarity_stage_scans_only_anchor_forward_for_existing_markets():
    sql = _read("supabase")
    assert "k.anchor_date IS NULL OR d.market_date>=k.anchor_date" in sql
    assert "k.anchor_date IS NULL OR d.market_date>k.anchor_date" in sql
    assert "fullHistoryMarkets" in sql
    assert "memberRowsScanned" in sql


def test_incremental_chain_preserves_anchor_index_and_segment():
    sql = _read("supabase")
    assert "coalesce(s.anchor_segment,0)+s.segment_offset" in sql
    assert "coalesce(s.anchor_index,100)" in sql
    assert "PARTITION BY s.rarity_key,s.segment_offset" in sql


def test_rarity_stage_privileges_remain_service_role_only():
    sql = _read("supabase")
    assert (
        "ALTER FUNCTION public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)"
        in sql
    )
    assert "OWNER TO postgres" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO service_role" in sql
