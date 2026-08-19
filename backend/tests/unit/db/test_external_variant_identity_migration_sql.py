from pathlib import Path

SQL = Path("backend/db/migrations/20260818213000_make_tcgplayer_external_identity_variant_aware.sql").read_text()

def test_external_identity_migration_backfills_before_not_null():
    assert SQL.index("UPDATE public.card_variant_external_identities") < SQL.index("SET NOT NULL")
    assert "coalesce(variant.edition" in SQL
    assert "coalesce(variant.printing_type" in SQL
    assert "coalesce(variant.special_type" in SQL

def test_external_identity_migration_replaces_exact_old_constraint():
    assert "DROP CONSTRAINT card_variant_external_identities_provider_external_product_id_key" in SQL
    assert "UNIQUE (provider, external_product_id, external_variant_key)" in SQL
