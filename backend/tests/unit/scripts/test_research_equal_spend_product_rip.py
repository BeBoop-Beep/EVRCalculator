from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from backend.domain.pokemon import sealed_product_comparison_scope as scope
from backend.scripts import research_equal_spend_product_rip as research


def test_nearest_spend_uses_positive_whole_units_and_enforces_tolerance():
    match = research.nearest_spend_pair(10.0, 59.0, tolerance=.05)
    assert match == pytest.approx({"quantityA": 6, "quantityB": 1, "spendA": 60,
                                   "spendB": 59, "mismatch": 1/60, "tolerance": .05})
    assert isinstance(match["quantityA"], int) and isinstance(match["quantityB"], int)
    assert research.nearest_spend_pair(10, 59, tolerance=.001, max_spend=100) is None


def test_fixed_budget_leftover_is_not_treated_as_spent():
    result = research.fixed_budget_quantity(100, 33)
    assert result == {"quantity": 3, "actualCommittedCapital": 99.0, "leftoverCapital": 1.0}


def test_anchored_quantity_rejects_large_mismatch():
    assert research.anchored_quantity(50, 80, tolerance=.05) is None
    assert research.anchored_quantity(60, 29, tolerance=.05)["quantity"] == 2


def test_strategy_requires_whole_retail_units():
    engine = object.__new__(research.StrategyEngine)
    engine.cache = {}; engine.base = {"p": np.ones(10_000)}
    product = {"sealed_product_id":"p", "product_market_cost":10, "product_family":"pack",
               "pack_count":1, "calculation_run_id":"run"}
    with pytest.raises(ValueError, match="whole retail unit"):
        engine.strategy(product, 1.5)


def test_strategy_aggregates_empirical_distribution_not_percentiles(monkeypatch):
    calls=[]
    engine=object.__new__(research.StrategyEngine);engine.cache={};engine.base={"p":np.arange(10_000,dtype=float)}
    product={"sealed_product_id":"p","product_market_cost":10,"product_family":"pack","pack_count":1,"calculation_run_id":"run"}
    def build(values, **kwargs):
        calls.append(kwargs["pack_counts"]);return {"distributions":{3:values[:]*3}}
    monkeypatch.setattr(research,"build_stage1_product_distributions",build)
    monkeypatch.setattr(research,"score_values",lambda values,cost:{"financialRipV3":1})
    result=engine.strategy(product,3)
    assert calls==[[3]] and result["actualCommittedCapital"]==30


def test_stage2_uses_only_canonical_guaranteed_offset(monkeypatch):
    calls=[]
    monkeypatch.setattr(research,"EXPECTED_OUTCOMES",4)
    monkeypatch.setattr(research,"load_pack_outcome_artifact",lambda *_:type("A",(),{
        "outcomes":np.ones(4),"metadata":{"outcome_count":4,"raw_sha256":"a"*64}})())
    monkeypatch.setattr(research,"build_stage1_product_distributions",lambda *_,**__:{"distributions":{9:np.ones(4)}})
    monkeypatch.setattr(research,"add_guaranteed_components",lambda values,offset:(calls.append(offset) or values+offset))
    engine=research.StrategyEngine(None,[{"simulation_calculation_run_id":"r","set_canonical_key":"s"}],[])
    monkeypatch.setattr(engine,"strategy",lambda p,q:{"metrics":{"financialRipV3":p["financial_rip_v3_score"]}})
    p={"sealed_product_id":"p","random_pack_count":9,"pack_count":9,"guaranteed_component_market_value":7.5,
       "calculation_run_id":"r","financial_rip_v3_score":1,"product_name":"ETB"}
    engine.build_set("r",[p])
    assert calls==[7.5] and np.all(engine.base["p"]==8.5)


def test_score_values_reuses_canonical_v3_and_rtp_is_correct(monkeypatch):
    payload={"status":"ready","rankable":True,"score":42,"components":{c:{"score":1} for c in research.FINANCIAL_RIP_V3_COMPONENT_ORDER},
             "audit":{"normalizedInputs":{}},"distributionDisclosures":{},"estimationDiagnostics":{}}
    seen=[]
    monkeypatch.setattr(research,"build_financial_rip_v3",lambda values,cost:(seen.append(cost) or payload))
    result=research.score_values(np.array([5.,15.]),20.)
    assert seen==[20.] and result["rtp"]==pytest.approx(.5)


def test_dominance_classifier():
    a={"rtp":.8,"medianRetention":.5,"chanceToRecoverCapital":.4,"lossResilience":60}
    b={"rtp":.7,"medianRetention":.4,"chanceToRecoverCapital":.3,"lossResilience":50}
    assert research.multi_metric_dominator(a,b)=="A"
    assert research.strict_return_dominator(a,b)=="A"
    b["chanceToRecoverCapital"]=.9
    assert research.multi_metric_dominator(a,b) is None
    assert research.strict_return_dominator(a,b) is None


def test_authority_loader_only_queries_published_run_ids():
    source=Path(research.__file__).read_text(encoding="utf-8")
    fn=source[source.index("def load_authoritative_products"):source.index("def nearest_spend_pair")]
    assert "calculation_run_id" in fn and "explore_rip_statistics_latest" not in fn


def test_no_database_or_snapshot_writes_contract_and_import_isolation():
    source=Path(research.__file__).read_text(encoding="utf-8");tree=ast.parse(source)
    forbidden={"insert","update","delete","upsert","rpc"}
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]
    def mentions_client(node):return any(isinstance(x,ast.Name) and x.id=="client" for x in ast.walk(node))
    assert not any(mentions_client(n.func.value) for n in calls)
    assert "publish_pokemon_public_rip_leaderboard" not in source
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    repo=Path(research.__file__).resolve().parents[2]
    production=[p for p in (repo/"backend").rglob("*.py") if "tests" not in p.parts and p != Path(research.__file__)
                and "research_cross_format_product_rip.py" not in str(p)]
    assert all("research_equal_spend_product_rip" not in p.read_text(encoding="utf-8",errors="ignore") for p in production)
