import pytest

from backend.db.repositories import sealed_product_results_repository as repo


def test_v5_columns_are_not_in_default_select_or_enrichment():
    assert "financial_rip_v5" not in repo._SELECT_FIELDS
    assert not set(repo.FINANCIAL_RIP_V5_FIELDS) & set(repo.ENRICHMENT_FIELDS)


def test_v5_writer_refuses_v4_and_unknown_columns():
    for bad in ({"financial_rip_v4_score": 1}, {"typo": 1}):
        with pytest.raises(ValueError):
            repo.update_sealed_product_financial_v5("id", bad)
    assert repo.update_sealed_product_financial_v5("id", {}) == []


def test_migration_is_additive_and_mirrored():
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    a = (root / "backend/db/migrations/20260920000000_add_sealed_product_financial_rip_v5.sql").read_text()
    b = (root / "supabase/migrations/20260920000000_add_sealed_product_financial_rip_v5.sql").read_text()
    assert a == b
    body = a.upper()
    assert "DROP " not in body.replace("DROP COLUMN THE", "") and "RENAME" not in body.split("--")[0]
    assert all(f"ADD COLUMN IF NOT EXISTS {c}" in a for c in repo.FINANCIAL_RIP_V5_FIELDS)
