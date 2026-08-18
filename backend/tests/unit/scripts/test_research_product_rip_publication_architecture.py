from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.domain.pokemon import sealed_product_comparison_scope as scope
from backend.scripts import research_product_rip_publication_architecture as research


def _item(pid, score, **extra):
    return {"sealedProductId":pid,"financialRipV3":score,"productName":pid,"productFamily":"dynamic_family",
            "setKey":"set","unitPrice":10,**extra}


def test_rank_to_standing_is_deterministic_and_uses_midrank_ties():
    rows=research.rank_to_standings([_item("b",5),_item("a",5),_item("c",1)],score_key="financialRipV3")
    assert [(x["sealedProductId"],x["rank"],x["relativeStanding"]) for x in rows]==[
        ("a",1.5,.75),("b",1.5,.75),("c",3.0,0.0)]


def test_missing_budgets_are_absent_not_zero_and_aggregations_are_correct():
    obs=[{**_item("a",1),"budget":25,"relativeStanding":1.0},
         {**_item("a",1),"budget":50,"relativeStanding":.5},
         {**_item("b",1),"budget":50,"relativeStanding":0.0}]
    rows=research.aggregate_standings(obs);a=next(x for x in rows if x["sealedProductId"]=="a")
    assert a["budgetsEligible"]==[25,50] and a["observationCount"]==2
    assert a["meanStanding"]==pytest.approx(.75) and "100" not in a["standingsByBudget"]


def test_pairwise_tolerance_and_result_aggregation():
    a=_item("a",60,actualCommittedCapital=100,rtp=.8,medianRetention=.6,chanceToRecoverCapital=.4,lossResilience=60)
    b=_item("b",50,actualCommittedCapital=104,rtp=.7,medianRetention=.5,chanceToRecoverCapital=.3,lossResilience=50)
    c=_item("c",40,actualCommittedCapital=110,rtp=.6,medianRetention=.4,chanceToRecoverCapital=.2,lossResilience=40)
    obs=research.pairwise_observations({100:[a,b,c]},.05)
    assert len(obs)==1 and obs[0]["winner"]=="a" and obs[0]["dominator"]=="a"
    products={x["sealedProductId"]:x for x in (a,b,c)}
    ranking,majority=research.aggregate_pairwise(obs*3,products)
    assert len(ranking)==0  # sparse safeguard: only one distinct opponent
    assert majority[0]["majorityWinner"]=="a"


def test_cycle_detection_counts_directed_three_cycles():
    majority=[{"skuA":"a","skuB":"b","majorityWinner":"a"},
              {"skuA":"b","skuB":"c","majorityWinner":"b"},
              {"skuA":"a","skuB":"c","majorityWinner":"c"}]
    result=research.detect_cycles(majority)
    assert result["cycleCount"]==1 and result["comparableTripletCount"]==1


def test_dominance_inversion_detection():
    ranking=[{"sealedProductId":"bad","rank":1},{"sealedProductId":"good","rank":2}]
    observations=[{"dominator":"good","dominated":"bad"},{"dominator":"good","dominated":"bad"}]
    result=research.dominance_inversions(ranking,observations)
    assert result["inversionCount"]==1


def test_global_dominance_requires_repetition_without_reverse():
    observations=[{"dominator":"a","dominated":"b"},{"dominator":"a","dominated":"b"},
                  {"dominator":"c","dominated":"d"},{"dominator":"d","dominated":"c"}]
    kept=research.consistent_dominance_observations(observations)
    assert len(kept)==2 and all(row["dominator"]=="a" for row in kept)


def test_budget_eligibility_comes_from_whole_unit_helper():
    from backend.scripts.research_equal_spend_product_rip import fixed_budget_quantity
    assert fixed_budget_quantity(25,30)["quantity"]==0
    assert fixed_budget_quantity(25,12)["quantity"]==2


def test_no_family_allowlist_in_methodology():
    source=Path(research.__file__).read_text(encoding="utf-8")
    assert "ALLOWED_FAMIL" not in source and "PRODUCT_FAMILIES =" not in source
    assert research.MIN_DISTINCT_OPPONENTS>=3


def test_exact_authority_and_no_newer_run_substitution_are_reused():
    source=Path(research.__file__).read_text(encoding="utf-8")
    assert "resolve_authoritative_snapshot" in source
    assert "load_authoritative_products" in source
    assert "explore_rip_statistics_latest" not in source


def test_no_database_snapshot_writes_and_contract_unchanged():
    source=Path(research.__file__).read_text(encoding="utf-8");tree=ast.parse(source)
    forbidden={"insert","update","delete","upsert","rpc"}
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]
    def mentions_client(node):return any(isinstance(x,ast.Name) and x.id=="client" for x in ast.walk(node))
    assert not any(mentions_client(n.func.value) for n in calls)
    assert "publish_pokemon_public_rip_leaderboard" not in source
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False


def test_financial_v3_is_not_reimplemented_and_no_production_imports_harness():
    source=Path(research.__file__).read_text(encoding="utf-8")
    assert "build_financial_rip_v3" not in source  # delegated to validated Step 1B StrategyEngine
    repo=Path(research.__file__).resolve().parents[2]
    production=[p for p in (repo/"backend").rglob("*.py") if "tests" not in p.parts and p!=Path(research.__file__)
                and not p.name.startswith("research_")]
    assert all("research_product_rip_publication_architecture" not in p.read_text(encoding="utf-8",errors="ignore") for p in production)
