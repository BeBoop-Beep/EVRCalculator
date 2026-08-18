from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from backend.calculations.evr.financial_rip_v3_config import FINANCIAL_RIP_V3_COMPONENT_INPUTS, FINANCIAL_RIP_V3_TRANSFORMS
from backend.domain.pokemon import sealed_product_comparison_scope as scope
from backend.scripts import research_realistic_upside_semantics as research


def test_exact_production_upside_traces_are_reused():
    assert FINANCIAL_RIP_V3_COMPONENT_INPUTS["realistic_upside"] == {"p95_threshold_ratio": .4, "realistic_tail_mean_ratio": .6}
    assert FINANCIAL_RIP_V3_COMPONENT_INPUTS["jackpot_upside"] == {"p99_threshold_ratio": .35, "jackpot_tail_mean_ratio": .65}
    assert FINANCIAL_RIP_V3_TRANSFORMS["p95_threshold_ratio"]["family"] == "piecewise_linear"
    assert FINANCIAL_RIP_V3_TRANSFORMS["p99_threshold_ratio"]["family"] == "saturating_exp"


def test_tail_regions_are_mutually_exclusive_and_exclude_top1_from_realistic():
    values=np.arange(100.0);result=research.region_decomposition(values,10)
    assert [result[k]["count"] for k in ("belowP95","p95ToBelowP99","p99AndAbove")] == [95,4,1]
    assert sum(result[k]["probabilityMass"] for k in ("belowP95","p95ToBelowP99","p99AndAbove")) == pytest.approx(1)
    assert result["p95ToBelowP99"]["meanOutcome"] == pytest.approx(np.mean([95,96,97,98]))
    assert result["p99AndAbove"]["meanOutcome"] == 99
    assert result["currentRealisticTop1Contribution"] == 0


def test_counterfactual_definitions_are_transparent_and_current_equals_band_construct():
    raw={"p95_threshold_ratio":2,"realistic_tail_mean_ratio":3,"p99_threshold_ratio":8}
    result=research.counterfactual_realistic(raw)
    assert result["CURRENT"] == result["P95_TO_P99_BAND"]
    assert result["TOP5_WINSORIZED_AT_P99"]["raw"] == pytest.approx(4)
    assert result["P95_THRESHOLD_ONLY"]["componentScore"] == 70
    assert result["TOP5_EXCLUDING_TOP1"]["componentScore"] == 70


def test_risk_seeking_utility_math_and_threshold_detection():
    safe=np.array([5.,5.]);risky=np.array([0.,10.])
    assert research.power_utility(safe,5,.5) > research.power_utility(risky,5,.5)
    assert research.power_utility(risky,5,-1) > research.power_utility(safe,5,-1)
    threshold=research.weakest_risk_seeking(risky,5,safe,5)
    assert threshold is not None and threshold < 0
    assert np.isfinite(research.power_utility(np.array([0.,1.]),1,1))


def test_attribution_classifier_has_no_implicit_jackpot_class():
    assert research.attribution_class(3,1)=="P95_THRESHOLD"
    assert research.attribution_class(1,3)=="P95_TO_P99_BAND"
    assert research.attribution_class(1,1)=="MIXED"


def _row(score,shift=0):
    components={key:10+shift for key in research.FINANCIAL_RIP_V3_COMPONENT_ORDER}
    contributions={key:components[key]*research.FINANCIAL_RIP_V3_WEIGHTS[key] for key in components}
    return {"score":score,"components":components,"contributions":contributions}


def test_leave_one_component_attribution():
    result=research.effective_influence([_row(10),_row(20,1),_row(30,2)])
    assert set(result)==set(research.FINANCIAL_RIP_V3_COMPONENT_ORDER)
    assert result["realistic_upside"]["meanAbsoluteScoreChange"] > result["base_economic_efficiency"]["meanAbsoluteScoreChange"]


def test_full_cohort_comparison_counts_valid_pairs():
    base={"sealedProductId":"a","budget":100,"actualCommittedCapital":100,"rtp":.5,"medianRetention":.4,"chanceToRecoverCapital":.2,"lossResilience":30,"financialRipV3":40,
          "components":{"realistic_upside":50},"p95ThresholdRatio":2,"realisticTailMeanRatio":3,"p99ThresholdRatio":5,"jackpotTailMeanRatio":8}
    other={**base,"sealedProductId":"b","actualCommittedCapital":102,"rtp":.6,"medianRetention":.5,"chanceToRecoverCapital":.3,"lossResilience":40,"financialRipV3":39,
           "components":{"realistic_upside":40},"p95ThresholdRatio":1.5,"realisticTailMeanRatio":2.5}
    result=research.cohort_effect({"100":[base,other]},.05)
    assert result["validComparisons"]==1
    assert result["diagnostics"]["CURRENT"]["layer1Inversions"]==1


def test_authority_preservation_no_writes_and_import_isolation():
    source=Path(research.__file__).read_text(encoding="utf-8");tree=ast.parse(source)
    assert all(name in source for name in ("STEP1B_PATH","STEP2A_PATH","STEP2B_PATH","STEP2C_PATH","resolve_authoritative_snapshot","positiveControls"))
    assert "explore_rip_statistics_latest" not in source and "financial_rip_v4" not in source.lower()
    forbidden={"insert","update","delete","upsert","rpc"}
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]
    def mentions_client(node): return any(isinstance(x,ast.Name) and x.id=="client" for x in ast.walk(node))
    assert not any(mentions_client(n.func.value) for n in calls)
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    repo=Path(research.__file__).resolve().parents[2]
    production=[p for p in (repo/"backend").rglob("*.py") if "tests" not in p.parts and p!=Path(research.__file__) and not p.name.startswith("research_")]
    assert all("research_realistic_upside_semantics" not in p.read_text(encoding="utf-8",errors="ignore") for p in production)
