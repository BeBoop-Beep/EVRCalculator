from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAME = "20261001194500_market_explorer_rarity_stage_self_join_v1.sql"
SUPABASE = ROOT.parent / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME


def _sql() -> str:
    return SUPABASE.read_text(encoding="utf-8")


def test_migration_mirrors_match():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()


def test_rarity_stage_uses_previous_date_self_join_not_member_lag_window():
    sql = _sql()
    assert "create or replace function public.stage_pokemon_market_explorer_rarity_candidates_v2" in sql
    assert "left join _mx_rarity_members p" in sql
    assert "p.card_variant_id=m.card_variant_id" in sql
    assert "p.market_date=dt.prev_date" in sql
    assert "count(p.card_variant_id)::integer common_count" in sql
    assert "sum(p.market_price)" in sql
    assert "member_windows as" not in sql
    assert "lag(m.market_date)" not in sql
    assert "lag(m.market_price)" not in sql


def test_chain_link_methodology_and_runtime_guard_are_unchanged():
    sql = _sql()
    assert "set statement_timeout='180s'" in sql
    assert "set work_mem='64MB'" in sql
    assert "l.common_current/l.common_previous" in sql
    assert "sum(break_flag) over(partition by rarity_key order by market_date rows unbounded preceding)" in sql
    assert "sum(ln(s.link_ratio))" in sql
    assert "over(partition by s.rarity_key,s.segment_id order by s.market_date rows unbounded preceding)" in sql


def test_membership_and_output_contracts_are_preserved():
    sql = _sql()
    assert "r.eligibility_state='CUSTOM_BUILD_AVAILABLE'" in sql
    assert "r.prepared_market_key is null" in sql
    assert "d.market_date<=p_market_date and d.market_price>0" in sql
    assert "insert into public.pokemon_market_explorer_surface_history_v2" in sql
    assert "insert into public.pokemon_market_explorer_surface_constituent_totals_v2" in sql
    assert "insert into public.pokemon_market_explorer_surface_constituents_v2" in sql
    assert "return jsonb_build_object('markets',v_markets,'historyRows',v_history,'constituentRows',v_rows)" in sql
