from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260915222940_align_market_rollout_materialization_with_root_authority.sql"
BACKEND = ROOT / "backend" / "db" / "migrations" / NAME
SUPABASE = ROOT / "supabase" / "migrations" / NAME


def _sql() -> str:
    return SUPABASE.read_text(encoding="utf-8").lower()


def test_migration_mirrors_are_byte_identical() -> None:
    assert BACKEND.read_bytes() == SUPABASE.read_bytes()


def test_hotfix_is_definition_guarded_before_replacing_membership_source() -> None:
    sql = _sql()
    assert "7a091192a64ae902a8490e42753ad4ec" in sql
    assert "5b6191e3b4ef0127059136bcd04a6488" in sql
    assert "concurrent change detected: prepare rollout materializer changed" in sql
    assert "concurrent change detected: public rollout materializer changed" in sql
    assert "expected legacy prepare membership fragment not found" in sql
    assert "expected legacy refresh membership fragment not found" in sql
    assert "execute v_prepare" in sql
    assert "execute v_refresh" in sql


def test_replacement_uses_exact_root_authority_not_era_membership() -> None:
    sql = _sql()
    assert sql.count("from public.pokemon_market_root_authority authority") == 2
    assert sql.count("join public.sets s on s.id = authority.set_id") == 2
    assert sql.count("authority.enabled") >= 2
    assert sql.count("authority.activated_market_date <=") == 2
    assert sql.count("authority.deactivated_market_date is null") == 2
    assert sql.count("authority.deactivated_market_date >") == 2
    assert "prepare membership replacement failed closed" in sql
    assert "refresh membership replacement failed closed" in sql
    assert "position('pokemon_market_public_era_rollout_v1' in v_prepare) <> 0" in sql
    assert "position('pokemon_market_public_era_rollout_v1' in v_refresh) <> 0" in sql


def test_both_mutating_rpcs_are_service_role_only_after_hotfix() -> None:
    sql = _sql()
    for signature in (
        "public.prepare_pokemon_market_candidate_rollout_set_values_v1(date)",
        "public.refresh_pokemon_market_public_rollout_daily_snapshots_v1(date)",
    ):
        assert f"revoke all on function {signature}\n  from public, anon, authenticated" in sql
        assert f"grant execute on function {signature}\n  to service_role" in sql


def test_hotfix_preserves_function_bodies_except_membership_fragment() -> None:
    sql = _sql()
    assert "pg_get_functiondef" in sql
    assert "replace(v_prepare, v_old_prepare, v_new_prepare)" in sql
    assert "replace(v_refresh, v_old_refresh, v_new_refresh)" in sql
    assert "get_pokemon_market_root_set_card_prices_latest_v1(s.id)" in sql
    assert "prices.market_scope = 'standard'" in sql
