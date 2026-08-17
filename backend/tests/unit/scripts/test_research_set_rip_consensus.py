import ast
from pathlib import Path

import pytest

from backend.scripts import research_set_rip_consensus as research


TARGETS = [
    {"set_id": "a", "canonical_key": "alpha", "calculation_run_id": "run-a", "name": "Alpha", "pack_rank": 2},
    {"set_id": "b", "canonical_key": "beta", "calculation_run_id": "run-b", "name": "Beta", "pack_rank": 1},
]


def projection(extra=None):
    products = [
        {"setId": "a", "sealedProductId": "a1", "productName": "A Box", "familyRank": 1,
         "overallRipScore": -999999, "financialRipScore": 999999},
        {"setId": "b", "sealedProductId": "b1", "productName": "B Box", "familyRank": 2,
         "overallRipScore": 999999, "financialRipScore": -999999},
    ]
    products.extend(extra or [])
    return {"comparisonScope": "within_product_family_only", "crossFormatComparable": False,
            "families": {"booster_box": {"count": len(products), "products": products}}}


def test_raw_rip_magnitudes_never_enter_matrix_or_consensus():
    matrix = research.build_matrix(projection(), TARGETS)
    assert all("overallRipScore" not in cell and "financialRipScore" not in cell for cell in matrix)
    ranked = research.rank_candidate(matrix, representative_policy="best", method="mean")
    assert [row["setId"] for row in ranked if row.get("rank")] == ["a", "b"]


def test_rank_relative_standing_does_feed_consensus():
    matrix = research.build_matrix(projection(), TARGETS)
    ranked = research.rank_candidate(matrix, representative_policy="best", method="mean")
    assert ranked[0]["consensusValue"] == 1.0
    assert ranked[1]["consensusValue"] == 0.0
    assert research.rank_standing(1, 1) == 0.5


def test_missing_family_is_absent_not_zero_and_gate_is_unavailable():
    matrix = research.build_matrix(projection(), TARGETS)
    alpha_bundle = next(c for c in matrix if c["setId"] == "a" and c["family"] == "booster_bundle")
    assert alpha_bundle["bestFamilyPercentile"] is None
    assert alpha_bundle["availabilityStatus"] == "no_catalogued_product"
    gated = research.rank_candidate(matrix, representative_policy="best", method="mean", minimum_coverage=2)
    assert all(row["status"] == "insufficient_coverage" and row["consensusValue"] is None for row in gated)


@pytest.mark.parametrize("policy,expected", [("best", 1.0), ("median", 0.75), ("mean", 0.75)])
def test_representative_policy_is_explicit(policy, expected):
    assert research.representative([1.0, 0.5], policy) == expected


def test_candidate_grid_is_predeclared_and_deterministic():
    assert research.candidate_grid() == research.candidate_grid()
    assert {row["representativePolicy"] for row in research.candidate_grid()} == {"best", "median", "mean"}
    assert {row["priorStrength"] for row in research.candidate_grid() if row["method"] == "mean"} == {0, 1, 2, 3}


def test_future_product_rows_automatically_expand_matrix_coverage():
    before = research.build_matrix(projection(), TARGETS)
    new = {"setId": "a", "sealedProductId": "a2", "productName": "A second", "familyRank": 2}
    after = research.build_matrix(projection([new]), TARGETS)
    before_cell = next(c for c in before if c["setId"] == "a" and c["family"] == "booster_box")
    after_cell = next(c for c in after if c["setId"] == "a" and c["family"] == "booster_box")
    assert before_cell["rankableSkuCount"] == 1
    assert after_cell["rankableSkuCount"] == 2


def test_catalog_can_distinguish_existing_unscored_product():
    catalog = {"a": {"elite_trainer_box": [{"id": "etb"}]}}
    matrix = research.build_matrix(projection(), TARGETS, catalog)
    cell = next(c for c in matrix if c["setId"] == "a" and c["family"] == "elite_trainer_box")
    assert cell["availabilityStatus"] == "catalogued_product_exists_unscored"


def test_no_cross_family_comparator_or_database_write_path():
    source = Path(research.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not ({"update", "upsert", "delete"} & attributes)
    assert source.count(".insert(") == 1  # sys.path bootstrap only
    assert "may_compare_products" not in source


def test_production_modules_do_not_import_research_harness():
    root = Path(__file__).resolve().parents[4]
    offenders = []
    for path in list((root / "backend").rglob("*.py")) + list((root / "frontend").rglob("*.ts")) + list((root / "frontend").rglob("*.tsx")):
        if path == Path(research.__file__) or "tests" in path.parts:
            continue
        if "research_set_rip_consensus" in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_research_main_passes_exact_target_run_authority(monkeypatch, tmp_path):
    observed = {}
    monkeypatch.setattr(research, "get_rip_statistics_targets_payload", lambda: {"targets": TARGETS})
    monkeypatch.setattr(research, "_catalog_by_set", lambda *_a, **_k: {})
    monkeypatch.setattr(research, "build_report", lambda *_a, **_k: {"promotionStatus": research.PROMOTION_STATUS})
    monkeypatch.setattr(research, "render_markdown", lambda _report: "research only")
    def project(*, set_targets):
        observed["authority"] = {row["set_id"]: row["calculation_run_id"] for row in set_targets}
        return {"families": {}}
    monkeypatch.setattr(research, "build_product_family_rankings", project)
    monkeypatch.setattr("sys.argv", ["research_set_rip_consensus", "--output-dir", str(tmp_path)])
    assert research.main() == 0
    assert observed["authority"] == {"a": "run-a", "b": "run-b"}
