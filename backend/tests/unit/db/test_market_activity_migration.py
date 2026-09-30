from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "backend/db/migrations/20260930210000_market_activity_projection_v1.sql"
SUPABASE = ROOT / "supabase/migrations/20260930210000_market_activity_projection_v1.sql"


def test_migration_mirrors_are_byte_equal():
    assert BACKEND.read_bytes() == SUPABASE.read_bytes()


def test_security_and_immutable_projection_contract_present():
    sql = BACKEND.read_text().lower()
    tables = ["market_activity_generations_v1", "market_activity_rosters_v1",
              "market_activity_instrument_windows_v1", "market_activity_daily_v1",
              "market_activity_supply_daily_v1", "market_activity_peer_ranks_v1"]
    for table in tables:
        assert table in sql
    assert "enable row level security" in sql
    assert "revoke all on table" in sql
    assert "from public,anon,authenticated,service_role" in sql
    assert "guard_market_activity_immutable_v1" in sql
    assert "promote_market_activity_generation_v1" in sql
    assert "e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007" in sql


def test_readers_are_service_only_and_bounded():
    sql = BACKEND.read_text().lower()
    assert "least(greatest(p_limit,1),100)" in sql
    for fn in ("get_market_activity_group_v1", "get_market_activity_instrument_v1",
               "get_market_activity_constituent_page_v1"):
        assert f"revoke all on function public.{fn}" in sql
        assert f"grant execute on function public.{fn}" in sql
