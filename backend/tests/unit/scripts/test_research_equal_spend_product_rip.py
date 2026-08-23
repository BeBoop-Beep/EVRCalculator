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


FORBIDDEN_WRITE_METHODS = {"insert", "update", "delete", "upsert", "rpc"}
FORBIDDEN_PUBLISH_SYMBOLS = (
    "publish_pokemon_public_rip_leaderboard",
    "publish_budget_product_ranking_snapshot",
)


def database_write_calls(source: str) -> list:
    """Write calls made against a database client, by AST — not by substring.

    Matches `<expr involving `client`>.insert(...)` and friends, so
    `sys.path.insert(...)` (a Python list) is correctly NOT a database write.
    That distinction is the whole point: the previous version of this contract
    used "does this file mention the research module" as a proxy for write
    safety, which flagged seven harmless harnesses whose only `insert` was
    `sys.path.insert` while proving nothing about actual writes.
    """
    tree = ast.parse(source)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in FORBIDDEN_WRITE_METHODS
    ]

    def mentions_client(node):
        return any(
            isinstance(x, ast.Name) and x.id in {"client", "supabase", "db"}
            for x in ast.walk(node)
        )

    return [node for node in calls if mentions_client(node.func.value)]


def research_harnesses() -> list:
    """Every SELECT-only research harness this contract governs."""
    scripts = Path(research.__file__).parent
    found = sorted(scripts.glob("research_*.py")) + [scripts / "_run_v4_research_driver.py"]
    return [p for p in found if p.exists()]


def test_research_harnesses_never_write_to_the_database():
    """THE actual safety invariant: research reads, it does not write.

    Enforced across every research harness, not just this one — the previous
    import-structure assertion failed on a pristine tree because seven
    legitimate harnesses referenced this module, so it proved nothing while
    appearing to guard something.
    """
    offenders = {}
    for path in research_harnesses():
        writes = database_write_calls(path.read_text(encoding="utf-8", errors="ignore"))
        if writes:
            offenders[path.name] = [node.func.attr for node in writes]
    assert not offenders, "research harnesses performing database writes: %s" % offenders


def test_research_harnesses_never_reference_a_publication_rpc():
    for path in research_harnesses():
        source = path.read_text(encoding="utf-8", errors="ignore")
        for symbol in FORBIDDEN_PUBLISH_SYMBOLS:
            assert symbol not in source, "%s references publication RPC %s" % (path.name, symbol)


def test_write_detector_actually_catches_writes_and_ignores_sys_path_insert():
    """Proof the guard above is not vacuous.

    A contract that can only ever pass is worse than no contract, so the
    detector is exercised on code that MUST trip it and code that must not.
    """
    assert database_write_calls("client.table('t').insert({'a': 1}).execute()")
    assert database_write_calls("client.table('t').delete().eq('id', 1).execute()")
    assert database_write_calls("client.rpc('publish_something', {}).execute()")
    assert database_write_calls("supabase.table('t').upsert(rows).execute()")
    # ...and the false positive that broke the old contract:
    assert not database_write_calls("import sys\nsys.path.insert(0, 'x')")
    assert not database_write_calls("client.table('t').select('*').execute()")
    assert not database_write_calls("results.update({'k': 'v'})")


def test_production_modules_never_import_a_research_harness():
    """Narrow, real version of the old import isolation rule: PRODUCTION code
    (services, calculations, domain) must not depend on research harnesses.
    Research-to-research reuse is fine and is how the matched-capital control
    is shared instead of reimplemented.
    """
    backend = Path(research.__file__).resolve().parents[1]
    production_roots = ("calculations", "db", "domain", "desirability", "simulations")
    offenders = []
    for root in production_roots:
        for path in (backend / root).rglob("*.py"):
            if "tests" in path.parts:
                continue
            source = path.read_text(encoding="utf-8", errors="ignore")
            if "backend.scripts.research_" in source or "from backend.scripts import research" in source:
                offenders.append(str(path.relative_to(backend)))
    assert not offenders, "production modules importing research harnesses: %s" % offenders


def test_cross_format_comparison_scope_contract_is_unchanged():
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
