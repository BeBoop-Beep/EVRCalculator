from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from backend.domain.pokemon import sealed_product_comparison_scope as scope
from backend.scripts import research_product_rip_dominance_utility as research


COMP={"true_win_frequency":10,"typical_retention":20,"loss_resilience":30,"realistic_upside":40,"jackpot_upside":50,"base_economic_efficiency":60}


def _strategy(core=(.5,.4,.3,40),components=None):
    return {"rtp":core[0],"medianRetention":core[1],"chanceToRecoverCapital":core[2],"lossResilience":core[3],"components":components or dict(COMP)}


def test_layered_dominance_and_full_pareto():
    a=_strategy();b=_strategy((.6,.5,.4,50),{k:v+1 for k,v in COMP.items()})
    layers=research.dominance_layers(a,b)
    assert all(layers.values())
    b["components"]["jackpot_upside"]=1
    layers=research.dominance_layers(a,b)
    assert layers["layer3AllNonJackpot"] and not layers["layer4FullComponentPareto"]


def test_weighted_contribution_driver_classification():
    base={k:0 for k in COMP};base["realistic_upside"]=2
    assert research.classify_driver(base)=="REALISTIC_UPSIDE_DRIVEN"
    base["jackpot_upside"]=1
    assert research.classify_driver(base)=="BOTH_UPSIDE_COMPONENTS"
    base["realistic_upside"]=-1
    assert research.classify_driver(base)=="JACKPOT_UPSIDE_DRIVEN"


def test_tail_removal_attribution_does_not_renormalize():
    a={k:1 for k in COMP};b={k:1 for k in COMP};a["jackpot_upside"]=5
    result=research.tail_removal({"a":10,"b":8},a,b)
    assert result["removeJackpot"]["scoreA"]==5 and result["removeJackpot"]["scoreB"]==7
    assert result["removeJackpot"]["flipsToB"] is True


@pytest.mark.parametrize("value,label",[(.005,"<1pp"),(.02,"1-3pp"),(.04,"3-5pp"),(.08,"5-10pp"),(.15,">10pp")])
def test_sacrifice_bins(value,label):assert research.sacrifice_bin(value)==label


def test_utility_sensitivity_is_monotonic_and_defined_at_zero():
    safe=np.array([5.,5.,5.]);risky=np.array([0.,0.,15.])
    assert research.expected_utility(safe,5,0)==pytest.approx(research.expected_utility(risky,5,0))
    assert research.expected_utility(safe,5,2)>research.expected_utility(risky,5,2)
    assert np.isfinite(research.expected_utility(risky,5,1))


def test_reachability_classification():
    c={k:0 for k in COMP};c["realistic_upside"]=1
    assert research.reachability_classification({"p95_threshold_ratio":.2},c)=="P95_OR_ONE_TO_FIVE_PERCENT_REACHABLE"
    c["realistic_upside"]=-1;c["jackpot_upside"]=2
    assert research.reachability_classification({},c)=="BELOW_ONE_PERCENT_JACKPOT"


def test_matched_capital_tolerances_are_locked():
    assert research.PRIMARY_TOLERANCE==.05 and research.SENSITIVITY_TOLERANCE==.02


def test_ascended_control_is_explicit_and_authority_is_reused():
    source=Path(research.__file__).read_text(encoding="utf-8")
    assert "ascendedHeroesControl" in source and "resolve_authoritative_snapshot" in source
    assert "explore_rip_statistics_latest" not in source


def test_no_formula_mutation_database_writes_or_production_import():
    source=Path(research.__file__).read_text(encoding="utf-8");tree=ast.parse(source)
    assert "FINANCIAL_RIP_V3_WEIGHTS" not in source and "financial_rip_v4" not in source.lower()
    forbidden={"insert","update","delete","upsert","rpc"}
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]
    def mentions_client(node):return any(isinstance(x,ast.Name) and x.id=="client" for x in ast.walk(node))
    assert not any(mentions_client(n.func.value) for n in calls)
    assert "publish_pokemon_public_rip_leaderboard" not in source
    assert scope.SEALED_PRODUCT_CROSS_FORMAT_COMPARABLE is False
    repo=Path(research.__file__).resolve().parents[2]
    production=[p for p in (repo/"backend").rglob("*.py") if "tests" not in p.parts and p!=Path(research.__file__) and not p.name.startswith("research_")]
    assert all("research_product_rip_dominance_utility" not in p.read_text(encoding="utf-8",errors="ignore") for p in production)
