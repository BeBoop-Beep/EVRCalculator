from backend.scripts.build_treatment_market_prestige_v3_round10 import build

def test_round10_reconciles_round9_and_cascades_every_uncovered_card():
    s=build(); c=s["_cascades"]
    assert s["frozenDenominator"]==19847 and s["currentCoveredCards"]==5059
    assert len(c)==14788 and len({x["canonicalCardId"] for x in c})==14788
    assert all(x["primary_blocker"]==x["round9PrimaryBlocker"] for x in c)

def test_mapping_repair_follows_downstream_contract():
    s=build()
    assert sum(s["mappingRootCauses"].values())==3561
    assert s["deterministicMappingRecoveryCount"]==0
    assert s["mappingCardsUltimatelyScoreable"]==102
    assert s["mappingCardsUltimatelyScoreable"]<3561

def test_round10_never_counts_upper_bounds_as_expected_coverage():
    s=build()
    assert all(x["likely"]<=x["upper"] for x in s["recoveryProjects"])
    assert s["internalDataOnlyMaximum"]["validatedCards"]==5161
    assert s["coverageRecoveryDecision"]=="70_PERCENT_COVERAGE_PATH_REQUIRES_ADDITIONAL_RESEARCH"
    assert s["productionPaused"] and s["rowsPersisted"]==0
