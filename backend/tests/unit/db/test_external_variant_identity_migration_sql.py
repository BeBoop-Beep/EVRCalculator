from pathlib import Path

SQL = Path("backend/db/migrations/20260818213000_make_tcgplayer_external_identity_variant_aware.sql").read_text()

def test_external_identity_migration_backfills_before_not_null():
    assert SQL.index("UPDATE public.card_variant_external_identities") < SQL.index("SET NOT NULL")
    assert "coalesce(variant.edition" in SQL
    assert "coalesce(variant.printing_type" in SQL
    assert "coalesce(variant.special_type" in SQL

def test_external_identity_migration_resolves_old_constraint_semantically():
    assert "constraint_def.contype = 'u'" in SQL
    assert "constraint_def.conkey = ARRAY[" in SQL
    assert "attname = 'provider'" in SQL
    assert "attname = 'external_product_id'" in SQL
    assert "expected exactly one UNIQUE(provider, external_product_id) constraint" in SQL
    assert "DROP CONSTRAINT %I" in SQL
    assert "UNIQUE (provider, external_product_id, external_variant_key)" in SQL

def test_external_identity_migration_is_explicitly_atomic():
    assert SQL.lstrip().startswith("-- A TCGplayer")
    assert "BEGIN;" in SQL
    assert SQL.rstrip().endswith("COMMIT;")
