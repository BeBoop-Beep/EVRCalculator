from backend.scripts.build_treatment_market_prestige_v3_round15 import build
def test_round15_branch_and_failure_guard():
 s=build();assert s["branchVerification"]["passed"];assert s["validButSimilarCandidateCount"]==0;assert all(x["failureReasons"] for x in s["treatmentLevelMatrix"] if x["currentAvailabilityStatus"]!="AVAILABLE")
def test_round15_scarcity_never_creates_eligibility():
 s=build();assert s["treatmentsNewlyEligible"]==[];assert s["cardsNewlyRecoverable"]==0;assert s["chosenMaximumAdjustment"] is None;assert s["scarcityDifferentiatorStatus"]=="SCARCITY_DIFFERENTIATOR_REDUNDANT"
def test_round15_preserves_coverage_and_production_pause():
 s=build();assert s["newCoverage"]["cards"]==10175;assert s["newCoverage"]["remainingTo70"]==3718;assert s["productionPaused"] and s["rowsPersisted"]==0
