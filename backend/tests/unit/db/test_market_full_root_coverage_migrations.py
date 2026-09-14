from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SUPABASE = ROOT / ".." / "supabase" / "migrations"
BACKEND = ROOT / "db" / "migrations"

AUTHORITY_NAME = "20260914190258_expand_market_root_authority_full_tracking.sql"
EXPLORER_NAME = "20260914190614_sync_explorer_directory_with_global_set_market.sql"
DIGEST_FIX_NAME = "20260914190721_fix_market_root_authority_sync_digest_resolution.sql"
FULL_ROOT_FP = "f61c619e1f346924b55eb288cffaff6c3802e1c2519cb42426e10b1d8e3b24eb"
LEGACY_FP = "470c8e49e083ca29c7df4d075175b62fb5dd69311b67ca48fec6baf76cd6e892"


def _read(folder: Path, name: str) -> str:
    return (folder / name).read_text(encoding="utf-8")


def test_market_full_root_migrations_are_mirrored_byte_for_byte():
    assert _read(SUPABASE, AUTHORITY_NAME) == _read(BACKEND, AUTHORITY_NAME)
    assert _read(SUPABASE, EXPLORER_NAME) == _read(BACKEND, EXPLORER_NAME)
    assert _read(SUPABASE, DIGEST_FIX_NAME) == _read(BACKEND, DIGEST_FIX_NAME)


def test_authority_expansion_preserves_history_and_uses_structural_membership():
    sql = _read(SUPABASE, AUTHORITY_NAME)
    assert "sync_pokemon_market_root_authority_v1" in sql
    assert "SECURITY DEFINER" in sql
    assert "ready_for_daily_scrape" in sql
    assert "catalog_only" in sql
    assert "parent_opening_set_id IS NULL" in sql
    assert "release_date IS NULL OR s.release_date <= p_market_date" in sql
    assert "Pokemon Market authority sync is current-date only" in sql
    assert "DATE '2026-09-13'" in sql
    assert "v_hist_count <> 106" in sql
    assert LEGACY_FP in sql
    assert "DATE '2026-09-14'" in sql
    assert "v_structural_count <> 155" in sql
    assert FULL_ROOT_FP in sql
    assert "structural_market_root_expansion_20260914" in sql
    # Runtime sync is insert-only: certification/freshness may never delete an
    # authority member.
    assert "DELETE FROM public.pokemon_market_root_authority" not in sql
    assert "UPDATE public.pokemon_market_root_authority" not in sql


def test_authority_sync_digest_fix_qualifies_pgcrypto_under_empty_search_path():
    sql = _read(SUPABASE, DIGEST_FIX_NAME)
    assert "sync_pokemon_market_root_authority_v1" in sql
    assert "SET search_path = ''" in sql
    assert "extensions.digest" in sql
    assert "GRANT EXECUTE ON FUNCTION public.sync_pokemon_market_root_authority_v1(date)" in sql
    assert "TO service_role" in sql


def test_explorer_directory_refresh_is_coupled_to_changed_global_set_snapshot():
    sql = _read(SUPABASE, EXPLORER_NAME)
    assert "refresh_market_explorer_directory_after_set_market_v1" in sql
    assert "refresh_pokemon_market_explorer_prepared_directory_v1" in sql
    assert "pokemon_global_set_market_refresh_explorer_directory" in sql
    assert "AFTER INSERT OR UPDATE OF market_date, set_count, source_generation_fingerprint, payload_json" in sql
    assert "NEW.tcg = 'pokemon' AND NEW.scope = 'market'" in sql
    assert "OLD.source_generation_fingerprint IS NOT DISTINCT FROM NEW.source_generation_fingerprint" in sql
