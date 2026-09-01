from backend.scripts.build_treatment_market_prestige_v3_round19 import build


def test_round19_relevant_ledger_is_disjoint_and_specific():
    study=build(); ledger=study["_ledger"]
    assert len(ledger)==2645==len({x["cardId"] for x in ledger})
    assert all(x["collectorRelevant"] or x["premiumTreatment"] for x in ledger)
    assert sum(study["blockerCounts"].values())==len(ledger)
    assert "UNSUPPORTED" not in study["blockerCounts"]


def test_round19_executes_tracks_without_manufacturing_recovery():
    study=build()
    assert study["historyRecoveryProjectsAttempted"] and study["taxonomyProjectsAttempted"]
    assert study["instabilityProjectsInvestigated"] and study["finiteSpecialTreatmentStudiesAttempted"]
    assert study["historyCardsRecovered"]==study["taxonomyCardsRecovered"]==0
    assert study["cardsRecoveredNewTreatmentModeling"]==study["instabilityCardsRecovered"]==0


def test_round19_preserves_locked_aligned_coverage_and_targets():
    study=build()
    assert study["finalCollectorEmpiricalCount"]==2807
    assert study["finalPremiumEmpiricalCount"]==2395
    assert study["remainingCollectorGapTo70"]==817
    assert study["remainingPremiumGapTo70"]==765
    assert study["setsAt70Before"]==study["setsAt70After"]==76


def test_round19_safety_and_decisions():
    study=build(); decisions=study["decisions"]
    assert decisions["evidenceCeiling"]=="CURRENT_INTERNAL_EVIDENCE_EXHAUSTED_FOR_PREMIUM_TMP"
    assert decisions["collectorAppeal"]=="TMP_COLLECTOR_APPEAL_COVERAGE_STILL_INSUFFICIENT"
    assert study["cardDetailIntegrationStudyStatus"]=="DIRECT_TMP_CARD_DETAIL_READY_FOR_INTEGRATION_STUDY"
    assert study["productionPaused"] and study["rowsPersisted"]==0
