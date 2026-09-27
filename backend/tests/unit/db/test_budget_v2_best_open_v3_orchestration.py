"""Explicit Ranking V2 / Best-Open V3 DB-backed orchestration (non-default)."""
import inspect
from types import SimpleNamespace

import numpy as np
import pytest

from backend.calculations.evr import best_open_price_v3 as bo3
from backend.calculations.evr.budget_normalized_product_ranking import (
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION, BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2,
)
from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.db.services import budget_best_open_v3_orchestration as o3
from backend.db.services import budget_ranking_v2_orchestration as o2
from backend.desirability import scoring_config as sc

V2, V1 = BUDGET_NORMALIZED_RANKING_METHOD_VERSION_V2, BUDGET_NORMALIZED_RANKING_METHOD_VERSION


def _product(i, price, **kw):
    return dict(sealed_product_id=f"00000000-0000-0000-0000-{i:012d}", set_id="set-a", calculation_run_id="run-a",
                product_family="booster_box", product_name=f"P{i}", product_market_cost=price, pack_count=1,
                random_pack_count=1, guaranteed_component_market_value=None, collector_appeal_score=60.0,
                price_as_of="2026-09-14", financial_rip_v5_version=FINANCIAL_RIP_V5_VERSION,
                financial_rip_v5_status="ready", financial_rip_v5_score=50.0, financial_rip_v5_rankable=True, **kw)


PRODUCTS = [_product(1, 4.0), _product(2, 6.5), _product(3, 9.0)]
RESOLUTION = {"bySet": {"set-a": {"ready": True, "aRaw": 0.01}}, "batchReadCount": 1}
OUTCOMES = np.random.default_rng(3).choice([0.05, 0.3, 1.0, 5.0, 40.0], size=20001, p=[.35, .3, .2, .1, .05])


def _build(products=PRODUCTS, method=V2, **kw):
    loads = []

    def loader(client, run_id):
        loads.append(run_id)
        return SimpleNamespace(outcomes=OUTCOMES)
    result = o2.build_ranking_v2_for_cohort(
        None, products, method_version=method, accessibility_resolver_fn=lambda c, m: RESOLUTION,
        artifact_loader_fn=loader, base_builder_fn=lambda artifact, count, run_id: artifact.outcomes, **kw)
    return result, loads


# ------------------------------------------------------------------ Ranking V2

@pytest.mark.parametrize("method", [V1, None, "", "budget_product_ranking_v3"])
def test_only_an_explicit_v2_request_is_accepted_and_v1_is_never_relabelled(method):
    with pytest.raises(o2.RankingV2NotReady, match="explicitly"):
        _build(method=method)


def test_v5_source_rows_are_required_no_v4_fallback():
    for mutate in (dict(financial_rip_v5_score=None), dict(financial_rip_v5_status="unavailable"),
                   dict(financial_rip_v5_version="financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5"),
                   dict(financial_rip_v5_rankable=False)):
        bad = [dict(PRODUCTS[0], **mutate)] + PRODUCTS[1:]
        with pytest.raises(o2.RankingV2NotReady, match="financial_v5_source_rows_not_ready"):
            _build(products=bad)
    only_v4 = [{k: v for k, v in p.items() if not k.startswith("financial_rip_v5")} for p in PRODUCTS]
    with pytest.raises(o2.RankingV2NotReady):
        _build(products=only_v4)


def test_unlanded_v5_schema_is_reported_truthfully_not_as_a_crash():
    def reader(runs, **kw):
        raise RuntimeError("{'code': '42703', 'message': 'column financial_rip_v5_score does not exist'}")
    with pytest.raises(o2.RankingV2NotReady, match="financial_v5_schema_not_landed"):
        o2.read_v5_source_rows(PRODUCTS, reader_fn=reader)


def test_v5_columns_are_merged_from_the_persisted_rows_only():
    base = [{k: v for k, v in p.items() if not k.startswith("financial_rip_v5")} for p in PRODUCTS]
    persisted = [dict(calculation_run_id="run-a", sealed_product_id=p["sealed_product_id"],
                      financial_rip_v5_score=51.0, financial_rip_v5_status="ready", financial_rip_v5_rankable=True,
                      financial_rip_v5_version=FINANCIAL_RIP_V5_VERSION, financial_rip_v4_score=1.0) for p in PRODUCTS]
    merged = o2.read_v5_source_rows(base, reader_fn=lambda runs, **kw: persisted)
    assert all(m["financial_rip_v5_score"] == 51.0 and "financial_rip_v4_score" not in m for m in merged)
    o2.require_v5_source_rows(merged)


def test_explicit_v2_build_scores_v5_v14_loads_each_artifact_once_and_ranks_contiguously():
    result, loads = _build()
    assert loads == ["run-a"] and result["artifactLoads"] == 1 and result["batchAccessibilityReadCount"] == 1
    assert result["rankingMethodVersion"] == V2
    fm = next(b for b in result["budgets"].values() if b["budgetType"] == "full_market")
    assert fm["rankedCount"] == 3 and sorted(r["budgetRankV14"] for r in fm["rows"]) == [1, 2, 3]
    assert sorted(r["financialOnlyRankV5"] for r in fm["rows"]) == [1, 2, 3]
    assert all(r["overallRipV14Version"] == sc.OVERALL_RIP_V14_VERSION and r["financialRipV5Version"] == FINANCIAL_RIP_V5_VERSION
               for r in fm["rows"])
    assert not [k for r in fm["rows"] for k in r if "V4" in k or "V12" in k or "V10" in k]


def test_publication_payload_uses_the_validated_builders_and_the_versioned_rpc_only():
    result, _ = _build()
    pub = o2.assemble_ranking_v2_publication(result, PRODUCTS, market_date="2026-09-14", pinned_price_as_of="2026-09-14",
                                             cohort_fingerprint="fp")
    snap = pub["snapshot"]
    assert snap["ranking_method_version"] == V2 and snap["ranked_under_v14_authority"] is True
    assert snap["financial_rip_version"] == FINANCIAL_RIP_V5_VERSION and "overall_rip_v12_version" not in snap
    assert pub["rows"] and all("financial_rip_v4_score" not in r and "budget_rank" not in r for r in pub["rows"])
    calls = []
    client = SimpleNamespace(rpc=lambda name, args: calls.append((name, args)) or SimpleNamespace(execute=lambda: "ok"))
    assert o2.publish_ranking_v2(client, pub) == "ok"
    assert calls == [("publish_budget_product_ranking_snapshot", {"p_snapshot": snap, "p_rows": pub["rows"]})]
    with pytest.raises(o2.RankingV2NotReady):
        o2.publish_ranking_v2(client, {"snapshot": dict(snap, ranking_method_version=V1), "rows": []})


def test_default_v1_v12_path_and_default_resolver_are_unchanged():
    from backend.scripts import build_budget_normalized_product_rankings as v1builder
    assert V1 == "budget_product_ranking_v1" and V2 != V1
    assert "budget_ranking_v2_orchestration" not in inspect.getsource(v1builder)
    assert "budget_ranking_v2_orchestration" not in inspect.getsource(o3)


# ------------------------------------------------------------------ Best-Open V3

RANKING_V2 = {"id": "rk2", "ranking_method_version": V2, "ranked_under_v14_authority": True, "published_at": "t",
              "cohort_fingerprint": "f", "overall_rip_v14_version": sc.OVERALL_RIP_V14_VERSION,
              "financial_rip_v5_version": FINANCIAL_RIP_V5_VERSION}


def test_v3_source_must_be_a_v14_ranking_v2_snapshot():
    o3.require_ranking_v2_snapshot(RANKING_V2)
    for bad in (None, dict(RANKING_V2, ranking_method_version=V1), dict(RANKING_V2, ranked_under_v14_authority=None),
                dict(RANKING_V2, overall_rip_v14_version=sc.OVERALL_RIP_V12_VERSION),
                dict(RANKING_V2, financial_rip_v5_version=sc.FINANCIAL_RIP_V4_VERSION)):
        with pytest.raises(o3.BestOpenV3NotReady):
            o3.require_ranking_v2_snapshot(bad)


def _v3(**kw):
    base = {"best_open_price_method_version": bo3.BEST_OPEN_PRICE_V3_METHOD_VERSION, "source_budget_snapshot_id": "rk2",
            "source_budget_published_at": "t", "source_cohort_fingerprint": "f",
            "financial_rip_version": FINANCIAL_RIP_V5_VERSION, "overall_rip_v14_version": sc.OVERALL_RIP_V14_VERSION}
    return dict(base, **kw)


def test_currentness_is_method_aware_and_v1_v2_cannot_mask_or_satisfy_v3():
    assert o3.is_v3_snapshot_current(_v3(), RANKING_V2) == {"current": True, "reasons": []}
    for kw in (dict(source_budget_snapshot_id="old"), dict(source_budget_published_at="older"),
               dict(source_cohort_fingerprint="other"), dict(financial_rip_version=sc.FINANCIAL_RIP_V4_VERSION),
               dict(overall_rip_v14_version=None),
               dict(best_open_price_method_version="budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12"),
               dict(best_open_price_method_version="budget_product_best_open_price_full_market_v1")):
        r = o3.is_v3_snapshot_current(_v3(**kw), RANKING_V2)
        assert r["current"] is False and r["reasons"]
    assert o3.is_v3_snapshot_current(None, RANKING_V2)["current"] is False


def _ranking_row(i, o_rank, f_rank, price, q, o=55.0, f=50.0):
    return dict(sealed_product_id=f"00000000-0000-0000-0000-{i:012d}", set_id="s", product_family="booster_box",
                source_calculation_run_id="r", product_market_price=price, quantity=q, budget_rank_v14=o_rank,
                financial_only_rank_v5=f_rank, overall_rip_v14_score=o, financial_rip_v5_score=f,
                chance_to_recover_capital=0.05, actual_committed_capital=q * price, target_budget=1300.0,
                collector_appeal_score=60.0, chase_accessibility_raw=0.01, budget_cohort_size_v14=3,
                set_id_=None)


def test_each_axis_benchmark_comes_from_its_own_authority_never_v4_v12():
    rows = [_ranking_row(1, 1, 2, 200.0, 6), _ranking_row(2, 2, 1, 260.0, 5), _ranking_row(3, 3, 3, 310.0, 4)]
    by_o = {r["budget_rank_v14"]: r for r in rows}
    by_f = {r["financial_only_rank_v5"]: r for r in rows}
    o_b, f_b = o3.pick_benchmarks(rows[0], by_o, by_f)      # overall leader -> rank 2 ; financial rank 2 -> rank 1
    assert o_b["sealed_product_id"] == rows[1]["sealed_product_id"] and f_b["sealed_product_id"] == rows[1]["sealed_product_id"]
    o_b, f_b = o3.pick_benchmarks(rows[1], by_o, by_f)      # overall rank 2 -> 1 ; financial leader -> 2
    assert o_b["sealed_product_id"] == rows[0]["sealed_product_id"] and f_b["sealed_product_id"] == rows[0]["sealed_product_id"]
    eng = o3._engine_row(rows[0])
    assert not [k for k in eng if "V4" in k or "V12" in k]


def test_search_and_assembly_use_the_v3_engine_and_versioned_rpc_only():
    class Fake:
        def __init__(self, product_id, q):
            self.product_id, self.quantity, self._last_comparator_seconds = product_id, q, 0.0

        def score_candidate(self, cents):
            return {"sealedProductId": self.product_id, "priceCents": cents, "quantity": self.quantity,
                    "targetBudget": 1300.0, "actualCommittedCapital": self.quantity * cents / 100,
                    "financialRipV5Score": float(cents), "overallRipV14Score": float(cents), "chanceToRecoverCapital": .05,
                    "scoringSeconds": 0.0}

        def compare(self, record, benchmark, *, authority):
            return record["priceCents"] <= 24000

    rows = [_ranking_row(1, 1, 1, 200.0, 6), _ranking_row(2, 2, 2, 260.0, 5)]  # product 2 leads neither axis
    cur = rows[1]
    bench = rows[0]
    factories = {"prepare_quantity": lambda q: Fake(cur["sealed_product_id"], q)}
    result = o3.search_product_v3(current=cur, overall_benchmark=bench, financial_benchmark=bench, budget_cents=130000,
                                  factories=factories, source_authority_fingerprint="fp", ranking_method_version=V2)
    assert result["overallResult"]["methodVersion"] == bo3.BEST_OPEN_PRICE_V3_METHOD_VERSION
    assert result["overallResult"]["threshold"]["priceCents"] == 24000
    with pytest.raises(bo3.BestOpenPriceSearchError):  # a V1 source can never seed the search
        o3.search_product_v3(current=cur, overall_benchmark=bench, financial_benchmark=bench, budget_cents=130000,
                             factories=factories, source_authority_fingerprint="fp", ranking_method_version=V1)
    entry = dict(current=dict(cur, overall_rip_v14_score=55.0), overall_result=result["overallResult"],
                 financial_result=result["financialResult"], overall_benchmark=bench, financial_benchmark=bench)
    pub = o3.assemble_best_open_v3_publication(
        source_ranking_snapshot=dict(id="rk2", published_at="t", market_date="2026-09-14", cohort_fingerprint="f",
                                     full_market_budget=1300.0, eligible_cohort_count=1),
        entries=[entry], built_at="2026-09-16T00:00:00+00:00", runtime_seconds=1.0, source_full_market_row_fingerprint="x")
    assert pub["snapshot"]["best_open_price_method_version"] == bo3.BEST_OPEN_PRICE_V3_METHOD_VERSION
    assert pub["snapshot"]["ranking_method_version"] == V2 and pub["rows"][0]["threshold_exact_verified"] is True
    calls = []
    client = SimpleNamespace(rpc=lambda n, a: calls.append(n) or SimpleNamespace(execute=lambda: "ok"))
    o3.publish_best_open_v3(client, pub)
    assert calls == ["publish_budget_product_best_open_price_snapshot"]
    with pytest.raises(o3.BestOpenV3NotReady):
        o3.publish_best_open_v3(client, {"snapshot": dict(pub["snapshot"], ranking_method_version=V1), "rows": []})
    non_exact = dict(result["overallResult"], status="unresolved_extreme_quantity")
    with pytest.raises(ValueError):
        o3.assemble_best_open_v3_publication(
            source_ranking_snapshot=dict(id="rk2", published_at="t", market_date="d", cohort_fingerprint="f",
                                         full_market_budget=1300.0, eligible_cohort_count=1),
            entries=[dict(entry, overall_result=non_exact)], built_at="t", runtime_seconds=1, source_full_market_row_fingerprint="x")
