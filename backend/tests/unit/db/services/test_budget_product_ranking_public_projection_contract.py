from pathlib import Path

SOURCE = Path("backend/db/services/budget_product_ranking_service.py").read_text(encoding="utf-8")


def test_public_projection_is_explicitly_allowlisted():
    assert "PUBLIC_ROW_FIELDS" in SOURCE
    assert '.select(PUBLIC_ROW_FIELDS)' in SOURCE
    assert "financial_only_rank" not in SOURCE.split("PUBLIC_ROW_FIELDS", 1)[1].split(")", 1)[0]


def test_projection_carries_budget_strategy_and_family_context():
    for field in (
        '"budgetRank"', '"budgetTier"', '"quantity"', '"actualCommittedCapital"',
        '"unusedCapital"', '"expectedValue"', '"chanceToRecoverCapital"',
        '"familyRank"', '"familySize"', '"familyTier"',
    ):
        assert field in SOURCE


def test_full_market_is_dynamic_and_canonical_bands_are_backend_owned():
    assert "CANONICAL_BUDGET_BANDS" in SOURCE
    assert 'snapshot["full_market_budget"]' in SOURCE
    assert "1350" not in SOURCE
