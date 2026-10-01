from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAME = "20261001200500_market_explorer_rarity_stage_narrow_history_v1.sql"
SUPABASE = ROOT.parent / "supabase" / "migrations" / NAME
BACKEND = ROOT / "db" / "migrations" / NAME


def _sql() -> str:
    return SUPABASE.read_text(encoding="utf-8")


def test_migration_mirrors_match():
    assert SUPABASE.read_bytes() == BACKEND.read_bytes()


def test_historical_temp_table_is_identity_price_only():
    sql = _sql()
    create = sql.split("create temp table _mx_rarity_members on commit drop as", 1)[1]
    create = create.split("create index on _mx_rarity_members", 1)[0]
    for required in (
        "r.rarity_key",
        "market_key",
        "d.market_date",
        "d.card_variant_id",
        "d.set_id",
        "d.market_price",
    ):
        assert required in create
    for forbidden in (
        "m.canonical_card_id",
        "m.card_name",
        "m.card_number",
        "m.rarity,",
        "m.edition",
        "m.printing_type",
        "m.special_type",
        "m.image_url",
    ):
        assert forbidden not in create


def test_display_metadata_is_rejoined_only_for_current_constituent_output():
    sql = _sql()
    assert "join public.pokemon_market_explorer_card_current_metadata m" in sql
    assert "m.card_variant_id=x.card_variant_id and m.set_id=x.set_id" in sql
    assert "m.filter_rarity_key=x.rarity_key" in sql
    assert "where x.market_date=p_market_date" in sql
    assert "'canonicalCardId',m.canonical_card_id" in sql
    assert "'cardName',m.card_name" in sql


def test_chain_link_math_and_self_join_remain_unchanged():
    sql = _sql()
    assert "left join _mx_rarity_members p" in sql
    assert "p.card_variant_id=m.card_variant_id" in sql
    assert "p.market_date=dt.prev_date" in sql
    assert "count(p.card_variant_id)::integer common_count" in sql
    assert "l.common_current/l.common_previous" in sql
    assert "sum(ln(s.link_ratio))" in sql
    assert "member_windows as" not in sql
    assert "lag(m.market_date)" not in sql
    assert "lag(m.market_price)" not in sql
    assert "set statement_timeout='180s'" in sql
    assert "set work_mem='64MB'" in sql
