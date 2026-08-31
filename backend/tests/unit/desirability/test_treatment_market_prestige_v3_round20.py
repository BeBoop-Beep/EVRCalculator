from backend.scripts.build_treatment_market_prestige_v3_round20 import GATES, build


def test_round20_freezes_cross_era_inputs_and_exclusions():
    study=build()
    assert study["targetedStructuralCards"]==2044
    assert study["distinctTreatmentAnchors"]>0 and study["structuralTreatmentBuckets"]>0
    assert sum(study["analogueAvailability"].values())==2044
    assert study["reproducibilityHashVerification"]["anchorHash"]


def test_round20_preregistered_contract_requires_magnitude_and_ordering():
    study=build()
    assert study["preregisteredGates"]==GATES
    assert GATES["maximumMAE"]<study["round17Baseline"]["mae"]
    assert GATES["minimumSpearman"]>=.65
    assert GATES["minimumOrderingAccuracy"]>=.70
    for method in study["validation"].values():
        for mode in method.values():
            if isinstance(mode,dict) and "passesGates" in mode and mode["passesGates"]:
                metrics=mode["CROSS_ERA"]["metrics"]
                assert metrics["mae"]<=GATES["maximumMAE"] and metrics["spearman"]>=GATES["minimumSpearman"]


def test_round20_failed_framework_publishes_no_scores():
    study=build()
    assert study["decisions"]["structuralTransfer"]=="CROSS_ERA_STRUCTURAL_INFERENCE_NOT_SUPPORTED"
    assert study["selectedAlgorithm"] is None
    assert not study["_inferred"]
    assert study["highConfidenceInferredCards"]==study["moderateConfidenceInferredCards"]==0
    assert study["unresolvedTargetedCards"]==2044


def test_round20_preserves_coverage_and_production_safety():
    study=build()
    assert study["collectorRelevantUsable"]["cards"]==2807
    assert study["premiumUsable"]["cards"]==2395
    assert study["decisions"]["fallback"]=="NUMERIC_TMP_FALLBACK_EXHAUSTED"
    assert study["cardDetailStatus"]=="DIRECT_ONLY_CARD_DETAIL_INTEGRATION_STUDY_REMAINS_VALID"
    assert study["productionPaused"] and study["rowsPersisted"]==0
