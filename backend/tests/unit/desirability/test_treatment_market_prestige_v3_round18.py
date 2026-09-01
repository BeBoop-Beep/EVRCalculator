from backend.scripts.build_treatment_market_prestige_v3_round18 import DENOMINATOR, EXPECTED, build


def test_round18_freezes_all_provenance_without_new_scoring():
    study=build()
    assert study["denominator"]==DENOMINATOR
    assert study["provenance"]==EXPECTED
    assert sum(study["provenance"].values())==DENOMINATOR
    assert study["rowsPersisted"]==0 and study["productionPaused"]


def test_round18_reuses_price_independent_hit_policy_and_separate_premium_scope():
    study=build(); hit=study["collectorRelevant"]; premium=study["premiumTreatment"]
    assert hit["policy"]=="pokemon_card_desirability_hit_policy_v2_coverage_cleanup"
    assert "no price threshold" in hit["implementation"]
    assert hit["summary"]["denominator"]>0 and premium["summary"]["denominator"]>0
    assert study["chaseCoverageDiagnostic"]["label"].startswith("MARKET-VALUE-WEIGHTED COVERAGE DIAGNOSTIC")


def test_round18_readiness_tables_and_missingness_are_complete():
    study=build()
    assert len(study["setLevelReadinessTable"])==165
    assert sum(study["residualBreakdown"]["era"].values())==EXPECTED["UNRESOLVED"]
    assert sum(study["residualBreakdown"]["terminalBlocker"].values())==EXPECTED["UNRESOLVED"]
    assert study["missingnessBiasFindings"]["conclusion"]=="MISSINGNESS_NOT_RANDOM"


def test_round18_decisions_do_not_treat_a_passing_set_gate_as_product_approval():
    study=build(); decisions=study["decisions"]
    assert study["gateEvaluations"]["A"]["passes"] is False
    assert study["gateEvaluations"]["B"]["passes"] is False
    assert study["gateEvaluations"]["C"]["passes"] is False
    assert decisions["collectorAppeal"]=="TMP_COLLECTOR_APPEAL_COVERAGE_STILL_INSUFFICIENT"
    assert decisions["cardDetail"]=="DIRECT_TMP_CARD_DETAIL_READY_FOR_INTEGRATION_STUDY"
