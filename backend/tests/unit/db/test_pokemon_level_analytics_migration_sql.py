from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "db" / "migrations"


def test_market_history_is_private_and_uniquely_versioned():
    sql = (ROOT / "20260818032645_create_pokemon_market_index_history.sql").read_text().lower()
    assert "unique (tcg, index_key, market_date, methodology_version)" in sql
    assert "enable row level security" in sql
    assert "revoke all on public.pokemon_market_index_daily_history from public, anon, authenticated" in sql


def test_rip_publication_is_atomic_invoker_only_and_latest_is_public_safe():
    sql = (ROOT / "20260818032648_create_pokemon_rip_stats_snapshots.sql").read_text().lower()
    assert "security invoker" in sql
    assert "revoke all on function public.publish_pokemon_rip_stats_snapshot(jsonb,jsonb) from public, anon, authenticated" in sql
    assert "grant execute on function public.publish_pokemon_rip_stats_snapshot(jsonb,jsonb) to service_role" in sql
    latest = sql.split("create table public.pokemon_rip_stats_snapshot_latest", 1)[1].split(");", 1)[0]
    assert "payload bytea" not in latest and "artifact" not in latest
