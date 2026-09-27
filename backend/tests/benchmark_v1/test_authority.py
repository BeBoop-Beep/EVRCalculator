from copy import deepcopy
from decimal import Decimal
from uuid import UUID

import pytest

from backend.benchmarking.authority_v1 import (
    ERA_AGGREGATION_VERSION, certify_product_family_policy,
    product_calibration_study, aggregate_era_rows,
)
from backend.domain.pokemon.rip_benchmark_v1 import (
    BenchmarkError, Calibration, Reference, metric_row,
)


def uid(n): return str(UUID(int=n))


def product_fixture():
    products, rows = [], []
    definitions = [("box", 1, 20, 40), ("box", 2, 10, 30),
                   ("etb", 3, 70, 60), ("etb", 4, 50, 50)]
    for family, n, financial, overall in definitions:
        rank = 1 if overall in (40, 60) else 2
        products.append({"sealedProductId": uid(n), "productFamily": family,
                         "familyRank": rank, "familySize": 2})
        for metric, raw, version in (("financial", financial, "financial-v4"),
                                     ("overall", overall, "overall-v12")):
            rows.append({"entity_type": "sealed_product", "entity_id": uid(n),
                "metric_key": metric, "raw_model_value": Decimal(raw),
                "source_model_version": version, "source_market_date": "2026-09-15",
                "source_fingerprint": str(n)*64})
    return products, rows


def test_product_policy_requires_complete_family_and_never_uses_leader_reference():
    products, rows = product_fixture()
    policy = certify_product_family_policy(products, rows)
    assert policy["status"] == "certified"
    assert policy["references"][("box", "financial")].raw_value == 15
    assert policy["references"][("box", "financial")].raw_value != 20
    assert policy["references"][("etb", "overall")].raw_value == 55
    assert policy["families"]["box"]["financial_rank_authority"].startswith("unavailable")

    with pytest.raises(BenchmarkError, match="complete native"):
        certify_product_family_policy(products, rows[:-1])
    duplicate = products + [deepcopy(products[0])]
    with pytest.raises(BenchmarkError, match="duplicate"):
        certify_product_family_policy(duplicate, rows)
    singleton_products = [products[0]]
    singleton_rows = [r for r in rows if r["entity_id"] == products[0]["sealedProductId"]]
    with pytest.raises(BenchmarkError, match="singleton"):
        certify_product_family_policy(singleton_products, singleton_rows)


def test_product_shadow_is_family_isolated_exactly_anchored_and_rank_independent():
    products, rows = product_fixture()
    policy = certify_product_family_policy(products, rows)
    study = product_calibration_study(products, rows, policy)
    assert study["production_calibration_selected"] is False
    for metric in ("financial", "overall"):
        for candidate in study["metrics"][metric]["candidates"]:
            assert candidate["monotonicity_violations"] == 0
            assert candidate["canonical_rank_inversions"] == 0
            assert all(family["score_at_family_mean"] == "5" for family in candidate["by_family"].values())
            assert set(candidate["by_family"]) == {"box", "etb"}


def set_rows_and_contract():
    metrics = ("financial", "chase", "collector", "overall")
    versions = {m: m+"-v" for m in metrics}
    values = {
        1: {"financial": 10, "chase": 20, "collector": 30, "overall": 80},
        2: {"financial": 20, "chase": 30, "collector": 40, "overall": 60},
        3: {"financial": 50, "chase": 60, "collector": 70, "overall": 20},
        4: {"financial": 60, "chase": 70, "collector": 80, "overall": 40}}
    rows = []
    for n, scores in values.items():
        for metric, raw in scores.items():
            source = {"entity_type": "set", "entity_id": uid(n), "market_date": "2026-09-15",
                "model_version": versions[metric], "raw_model_value": raw,
                "rank": None, "cohort_size": None, "reconstruction_status": "persisted_exact",
                "source_publication_id": uid(900), "lineage": {"fixture": True}}
            rows.append(metric_row(entity_type="set", entity_id=uid(n), metric_key=metric,
                                   market_date="2026-09-15", source=source))
    refs, cals = {}, {}
    for metric in metrics:
        raw = sum(Decimal(values[n][metric]) for n in values)/4
        refs[metric] = Reference("sets", metric, versions[metric], "2026-09-15", raw, "a"*64)
        cals[metric] = Calibration("fixture", metric, versions[metric], "sets", Decimal(10))
    entries = [{"setId": uid(n), "eraId": uid(100 if n < 3 else 200),
                "eraName": "Era A" if n < 3 else "Era B"} for n in values]
    return rows, entries, refs, cals


def test_era_equal_set_aggregation_overall_rule_reconciliation_and_rank():
    rows, entries, refs, cals = set_rows_and_contract()
    era_rows, proof = aggregate_era_rows(rows, entries, market_date="2026-09-15",
                                         references=refs, calibrations=cals)
    assert proof["status"] == "certified" and proof["aggregation_version"] == ERA_AGGREGATION_VERSION
    overall = {r["entity_id"]: r for r in era_rows if r["metric_key"] == "overall"}
    # Mean(Set Overall): Era A=(80+60)/2, Era B=(20+40)/2.
    assert overall[uid(100)]["raw_model_value"] == 70
    assert overall[uid(200)]["raw_model_value"] == 30
    assert overall[uid(100)]["rank"] == 1 and overall[uid(200)]["rank"] == 2
    for metric in ("financial", "chase", "collector", "overall"):
        assert proof["metrics"][metric]["weighted_reconciliation"]["exact"] is True
        assert proof["metrics"][metric]["weighted_reconciliation"]["value"] == str(refs[metric].raw_value)

    with pytest.raises(BenchmarkError, match="incomplete Era membership"):
        aggregate_era_rows(rows, entries[:-1], market_date="2026-09-15",
                           references=refs, calibrations=cals)
