from backend.scripts.build_treatment_market_prestige_v3_round17 import DENOMINATOR, DIRECT, FROZEN_COUNT, NEUTRAL, build


def test_round17_frozen_population_integrity_and_protected_provenance():
    study = build()
    check = study["residualIntegrityCheck"]
    assert study["frozenResidualCount"] == FROZEN_COUNT
    assert check["actual"] == check["unique"] == check["expected"] == FROZEN_COUNT
    assert check["allInLedger"] and check["allUnresolved"] and check["excludedProtectedStates"]


def test_round17_preregistered_holdout_decision_controls_publication():
    study = build()
    assert study["preregisteredHoldoutGates"]["minimumSpearman"] == .50
    if study["decisions"]["framework"] == "BEST_FIT_FRAMEWORK_NOT_SUPPORTED":
        assert not study["_inferred"]
        assert len(study["_unresolved"]) == FROZEN_COUNT
    assert all(x["confidence"] == "BEST_FIT_LOW_CONFIDENCE" for x in study["_low"])


def test_round17_preserves_empirical_semantics_and_production_pause():
    study = build(); coverage = study["coverage"]
    assert coverage["empirical"]["cards"] == DIRECT
    assert coverage["neutral"]["cards"] == NEUTRAL
    assert coverage["empirical"]["coverage"] == DIRECT / DENOMINATOR
    assert coverage["conservativeUsable"]["cards"] == DIRECT + NEUTRAL + coverage["inferredHigh"]["cards"]
    assert coverage["broadDefensibleUsable"]["cards"] == coverage["conservativeUsable"]["cards"] + coverage["inferredModerate"]["cards"]
    assert study["productionPaused"] and study["rowsPersisted"] == 0


def test_round17_card_level_inference_is_auditable_and_non_circular():
    study = build()
    assert study["reproducibilityChecks"]["priceFeatureUsed"] is False
    for row in study["_inferred"] + study["_low"]:
        assert row["provenance"] == "BEST_FIT_INFERRED"
        assert 0.0 <= row["inferredScore"] <= 10.0
        assert row["anchorTreatments"] and len(row["anchorTreatments"]) == len(row["anchorScores"])
        assert row["method"] and row["explanationCode"]
