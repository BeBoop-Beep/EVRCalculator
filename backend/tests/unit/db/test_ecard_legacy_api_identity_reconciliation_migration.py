from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260917202730_reconcile_ecard_holo_legacy_api_identity.sql"
BACKEND = ROOT / "backend" / "db" / "migrations" / NAME
SUPABASE = ROOT / "supabase" / "migrations" / NAME


def test_migration_mirrors_are_byte_identical():
    assert BACKEND.read_bytes() == SUPABASE.read_bytes()


def test_repair_is_bounded_by_existing_reviewed_identity_evidence():
    sql = BACKEND.read_text(encoding="utf-8")
    assert "pokemon_canonical_card_legacy_identity_links" in sql
    assert "canonical.catalog_role = 'main'" in sql
    assert "canonical.canonical_review_status = 'approved'" in sql
    assert "set_row.canonical_key IN ('aquapolis', 'skyridge')" in sql
    assert "canonical.pokemon_tcg_api_card_id ~ '^ecard[23]-H[0-9]+$'" in sql
    assert "legacy.pokemon_tcg_api_id IS NULL" in sql


def test_repair_fails_closed_on_candidate_or_identity_conflict_drift():
    sql = BACKEND.read_text(encoding="utf-8")
    assert "v_candidate_count <> 18" in sql
    assert "v_conflict_count <> 0" in sql
    assert "other.pokemon_tcg_api_id = candidates.canonical_api_id" in sql
    assert "v_updated_count <> 18" in sql


def test_repair_only_backfills_legacy_api_identity():
    sql = BACKEND.read_text(encoding="utf-8")
    update_block = sql.split("UPDATE public.cards legacy", 1)[1]
    assert "SET pokemon_tcg_api_id = canonical.pokemon_tcg_api_card_id" in update_block
    assert "DELETE FROM" not in sql.upper()
    assert "UPDATE public.pokemon_canonical_cards" not in sql
    assert "UPDATE public.card_variants" not in sql
