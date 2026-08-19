from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from backend.domain.pokemon import sealed_product_comparison_scope as scope
from backend.scripts import research_realistic_upside_candidate_matrix as research


def test_candidate_matrix_is_exact_preregistered_factorial():
    matrix=research.candidates()
    assert len(matrix)==8
    assert set(c["definition"] for c in matrix.values())==set(research.DEFINITIONS)
    assert set(c["realisticWeight"] for c in matrix.values())==set(research.REALISTIC_WEIGHTS)


@pytest.mark.parametrize("weight",research.REALISTIC_WEIGHTS)
def test_weight_redistribution_is_exact_and_jackpot_fixed(weight):
    result=research.candidate_weights(weight);removed=.25-weight
    assert result["jackpot_upside"]==.10
    assert result["true_win_frequency"]==pytest.approx(.25+removed*25/65)
    assert result["typical_retention"]==pytest.approx(.20+removed*20/65)
    assert result["loss_resilience"]==pytest.approx(.15+removed*15/65)
    assert result["base_economic_efficiency"]==pytest.approx(.05+removed*5/65)
    assert sum(result.values())==pytest.approx(1)


def test_current_and_p95_only_reconstruction():
    assert research.realistic_score("CURRENT_REALISTIC",2,55)==55
    assert research.realistic_score("P95_THRESHOLD_ONLY",2,55)==70
    components={key:50 for key in research.FINANCIAL_RIP_V3_COMPONENT_ORDER}
    assert research.score_candidate(components,2,research.candidates()["CURRENT_REALISTIC@25"])==pytest.approx(50)


def test_deterministic_subsampling():
    values=np.arange(1000.)
    a=research.deterministic_subsample(values,100,2,"sku");b=research.deterministic_subsample(values,100,2,"sku")
    assert np.array_equal(a,b) and len(np.unique(a))==100
    assert not np.array_equal(a,research.deterministic_subsample(values,100,3,"sku"))


def test_p95_tie_and_boundary_diagnostics():
    values=np.repeat(np.arange(10.),100)
    result=research.p95_boundary_diagnostic(values,5)
    assert result["p95"]==9 and result["exactTieCount"]==100
    assert result["exactTieShare"]==pytest.approx(.1)
    assert result["normalizedAdjacentScoreSpan"]>=0


def _metrics(score=50,p95=2):
    return {"p95ThresholdRatio":p95,"realisticTailMeanRatio":3,"p99ThresholdRatio":5,"jackpotTailMeanRatio":8,
        "components":{key:score for key in research.FINANCIAL_RIP_V3_COMPONENT_ORDER}}


def test_cohort_layered_dominance_and_factorial_output():
    matrix=research.candidates();base={"sealedProductId":"a","setKey":"s1","budget":100,"quantity":1,"actualCommittedCapital":100,"financialRipV3":50,"rtp":.4,"medianRetention":.3,"chanceToRecoverCapital":.1,"lossResilience":20,"components":_metrics()["components"]}
    other={**base,"sealedProductId":"b","setKey":"s2","actualCommittedCapital":102,"financialRipV3":49,"rtp":.5,"medianRetention":.4,"chanceToRecoverCapital":.2,"lossResilience":30}
    a=research.enrich_row(base,_metrics(50,2),matrix);b=research.enrich_row(other,_metrics(40,1),matrix)
    result=research.cohort_matrix({"100":[a,b]},matrix,.05)
    assert result["comparisons"]==1
    assert result["candidates"]["CURRENT_REALISTIC@25"]["layer1Inversions"]==1
    assert result["candidates"]["CURRENT_REALISTIC@25"]["layer4Inversions"]==0


def test_cost_sensitivity_component_is_monotonic_for_fixed_raw_value():
    scores=[research.realistic_score("P95_THRESHOLD_ONLY",10/cost,0) for cost in (9.5,9.8,10,10.2,10.5)]
    assert all(a>=b for a,b in zip(scores,scores[1:]))


def test_set_folds_are_deterministic():
    matrix=research.candidates();observation={"setA":"a","setB":"a","candidates":{key:{"layers":[False,False,False,False]} for key in matrix}}
    first=research.fold_robustness({"observations":[observation]},matrix);second=research.fold_robustness({"observations":[observation]},matrix)
    assert first==second and sum(f["comparisons"] for f in first["folds"].values())==1


def test_authority_no_mutation_writes_contract_or_production_import():
    source=Path(research.__file__).read_text(encoding="utf-8");tree=ast.parse(source)
    assert all(name in source for name in ("STEP2A_PATH","STEP2C_PATH","STEP3A_PATH","resolve_authoritative_snapshot"))
    assert "financial_rip_v4" not in source.lower() and "explore_rip_statistics_latest" not in source
    forbidden={"insert","update","delete","upsert","rpc"};calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]
    def mentions_client(node):return any(isinstance(x,ast.Name) and x.id=="client" for x in ast.walk(node))
    assert not any(mentions_client(n.func.value) for n in calls)
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    repo=Path(research.__file__).resolve().parents[2];production=[p for p in (repo/"backend").rglob("*.py") if "tests" not in p.parts and p!=Path(research.__file__) and not p.name.startswith("research_")]
    assert all("research_realistic_upside_candidate_matrix" not in p.read_text(encoding="utf-8",errors="ignore") for p in production)
