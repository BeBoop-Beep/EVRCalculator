from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from backend.domain.pokemon import sealed_product_comparison_scope as scope
from backend.scripts import research_opponent_adjusted_product_rip as research


def _e(a,b,winner,budget=100,spend_a=100,spend_b=100,**extra):
    return {"skuA":a,"skuB":b,"winner":winner,"budget":budget,"spendA":spend_a,"spendB":spend_b,
            "dominator":extra.pop("dominator",None),"dominated":extra.pop("dominated",None),**extra}


def test_actual_spend_tolerance_not_nominal_coeligibility():
    base={"productName":"x","productFamily":"f","setKey":"s","unitPrice":10,"quantity":1,"financialRipV3":50,
          "rtp":.7,"medianRetention":.5,"chanceToRecoverCapital":.3,"lossResilience":50,"components":{},"ev":7,"leftoverBudget":0}
    budgets={"100":[{"sealedProductId":"a","actualCommittedCapital":100,**base},
                    {"sealedProductId":"b","actualCommittedCapital":80,**base}]}
    assert research.enrich_evidence(budgets,.05)==[]


def test_pair_balancing_gives_each_distinct_pair_one_unit():
    evidence=[_e("a","b","a") for _ in range(5)]+[_e("a","c","c")]
    model=research.fit_bradley_terry(evidence,["a","b","c"],regularization=1,pair_balanced=True,max_iter=1)
    # Pair balancing is contractually recorded and sees two distinct pairs.
    assert model["pairBalanced"] is True and model["distinctPairCount"]==2


def test_distinct_opponents_and_minimum_evidence_sparse_unranked():
    evidence=[_e("a",f"b{i}","a") for i in range(5)]
    stats=research.evidence_stats(evidence)
    assert stats["a"]["distinctOpponents"]==5 and stats["a"]["observations"]==5
    assert "a" in research.eligible_ids(evidence,3,5)
    assert "b0" not in research.eligible_ids(evidence,3,5)


def test_bradley_terry_recovers_controlled_order():
    evidence=[]
    for _ in range(4):evidence += [_e("strong","mid","strong"),_e("strong","weak","strong"),_e("mid","weak","mid")]
    model=research.fit_bradley_terry(evidence,["strong","mid","weak"],regularization=.1)
    values=dict(zip(model["ids"],model["strength"]))
    assert values["strong"]>values["mid"]>values["weak"]


def test_regularization_keeps_undefeated_strength_finite():
    evidence=[_e("a","b","a") for _ in range(20)]
    model=research.fit_bradley_terry(evidence,["a","b"],regularization=1)
    assert np.isfinite(model["strength"]).all() and np.isfinite(model["standardError"]).all()


def test_ties_are_deterministic_half_outcomes():
    evidence=[_e("a","b",None)]*3
    model=research.fit_bradley_terry(evidence,["a","b"],regularization=1)
    assert model["strength"][0]==pytest.approx(model["strength"][1])


def test_repeated_direct_and_dominance_inversion_diagnostics():
    ranking=[{"sealedProductId":"loser","rank":1},{"sealedProductId":"winner","rank":2}]
    evidence=[_e("winner","loser","winner",dominator="winner",dominated="loser") for _ in range(3)]
    assert research.repeated_direct_inversions(ranking,evidence,2)["inversionCount"]==1
    dominance=[{**r,"winner":r["dominator"]} for r in evidence]
    assert research.repeated_direct_inversions(ranking,dominance,3)["inversionCount"]==1


def test_capital_strata_can_be_fit_independently():
    low=[_e("a","b","a",spend_a=50,spend_b=50)]*3
    high=[_e("a","b","b",spend_a=500,spend_b=500)]*3
    ml=research.fit_bradley_terry(low,["a","b"],regularization=1)
    mh=research.fit_bradley_terry(high,["a","b"],regularization=1)
    assert ml["strength"][0]>ml["strength"][1] and mh["strength"][0]<mh["strength"][1]


def test_grouped_cv_keeps_pairs_in_one_fold():
    evidence=[]
    for i in range(8):evidence += [_e("a",f"b{i}","a")]*2
    results=research.grouped_cross_validation(evidence,["a"]+[f"b{i}" for i in range(8)],lambdas=(1,),folds=3)
    assert results[0]["folds"]>=2 and 0<=results[0]["brier"]<=1


def test_cycle_diagnostic_reuses_exact_graph_helper():
    from backend.scripts.research_product_rip_publication_architecture import detect_cycles
    majority=[{"skuA":"a","skuB":"b","majorityWinner":"a"},{"skuA":"b","skuB":"c","majorityWinner":"b"},{"skuA":"a","skuB":"c","majorityWinner":"c"}]
    assert detect_cycles(majority)["cycleCount"]==1


def test_price_bias_uses_spearman_diagnostics():
    assert research.spearman([10,20,30],[3,2,1])==pytest.approx(-1)


def test_exact_authority_no_family_hardcoding_and_v3_delegation():
    source=Path(research.__file__).read_text(encoding="utf-8")
    assert "run_step2a(client)" in source and "explore_rip_statistics_latest" not in source
    assert "ALLOWED_FAMIL" not in source and "build_financial_rip_v3" not in source


def test_no_database_snapshot_writes_contract_and_import_isolation():
    source=Path(research.__file__).read_text(encoding="utf-8");tree=ast.parse(source);forbidden={"insert","update","delete","upsert","rpc"}
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]
    def mentions_client(node):return any(isinstance(x,ast.Name) and x.id=="client" for x in ast.walk(node))
    assert not any(mentions_client(n.func.value) for n in calls)
    assert "publish_pokemon_public_rip_leaderboard" not in source
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    repo=Path(research.__file__).resolve().parents[2]
    production=[p for p in (repo/"backend").rglob("*.py") if "tests" not in p.parts and p!=Path(research.__file__) and not p.name.startswith("research_")]
    assert all("research_opponent_adjusted_product_rip" not in p.read_text(encoding="utf-8",errors="ignore") for p in production)
