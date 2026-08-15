from pathlib import Path


SQL = (Path(__file__).resolve().parents[3] / "db" / "migrations" / "063_create_pokemon_explore_set_value_snapshot.sql").read_text(encoding="utf-8").lower()


def test_global_set_value_snapshot_is_persisted_read_only_for_public_roles():
    assert "create table if not exists public.pokemon_explore_set_value_snapshot_latest" in SQL
    assert "primary key (tcg, scope)" in SQL
    assert "grant select" in SQL
    assert "grant insert, update, delete" in SQL and "service_role" in SQL
    assert "payload_size_bytes" in SQL
