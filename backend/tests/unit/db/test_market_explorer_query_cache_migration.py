from pathlib import Path


PATH = Path("supabase/migrations/20260831034744_add_market_explorer_query_cache.sql")
SQL = " ".join(PATH.read_text(encoding="utf-8").lower().split())


def test_cache_is_jsonb_one_row_versioned_and_has_no_daily_or_current_fact_table():
    assert "create table if not exists public.pokemon_market_explorer_query_cache" in SQL
    for field in ("query_fingerprint text not null unique", "normalized_spec jsonb not null",
                  "series_payload jsonb", "computed_through date",
                  "instrument_methodology_version text not null"):
        assert field in SQL
    assert "pokemon_market_variant_current" not in SQL
    assert "daily_fact" not in SQL


def test_exact_table_acl_is_service_only_and_excludes_broad_privileges():
    assert ("revoke all on table public.pokemon_market_explorer_query_cache "
            "from public, anon, authenticated, service_role") in SQL
    assert ("grant select, insert, update, delete on table "
            "public.pokemon_market_explorer_query_cache to service_role") in SQL
    acl = SQL.split("grant select, insert, update, delete on table", 1)[1].split(";", 1)[0]
    for forbidden in ("truncate", "references", "trigger", "anon", "authenticated"):
        assert forbidden not in acl
    assert "enable row level security" in SQL


def test_helpers_are_invoker_safe_service_only_and_have_atomic_token_ownership():
    for name in ("claim_pokemon_market_explorer_query_cache_build",
                 "publish_pokemon_market_explorer_query_cache_build",
                 "fail_pokemon_market_explorer_query_cache_build",
                 "invalidate_pokemon_market_explorer_query_cache"):
        body = SQL.split(f"create or replace function public.{name}", 1)[1]
        assert "security invoker" in body.split("$$;", 1)[0]
        assert f"grant execute on function public.{name}" in SQL
    assert "on conflict (query_fingerprint) do update" in SQL
    assert "build_expires_at <= clock_timestamp()" in SQL
    assert "and build_token = p_build_token" in SQL
    assert "and build_expires_at > clock_timestamp()" in SQL


def test_historical_repair_invalidation_is_explicit_and_forward_publication_stays_lazy():
    assert "computed_through >= p_changed_market_date" in SQL
    assert "normal forward publication remains lazy" in SQL
    assert "status = 'stale'" in SQL

