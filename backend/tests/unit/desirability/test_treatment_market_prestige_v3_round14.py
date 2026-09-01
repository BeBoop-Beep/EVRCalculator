from backend.scripts.build_treatment_market_prestige_v3_round14 import build
def test_round14_reconciles_likely_and_remaining_card_universe():
 s=build();assert s["startingLikelyCoverage"]["cards"]==9485 and len(s["_residual"])==s["uncoveredCards"]==10362
 assert sum(s["terminalBlockerTable"].values())==10362 and len({x["cardId"] for x in s["_residual"]})==10362
def test_round14_supporter_and_vintage_fail_closed_on_missing_evidence():
 s=build();assert s["Supporter"]["safelyMapped"]==0 and s["Supporter"]["pilot"]=="NOT_RUN_IDENTIFICATION_GATE_FAILED"
 assert s["ECard"]["preservedAudit"]["round13Preserved"]["missingCardDates"]==454
 assert s["ECard"]["preservedAudit"]["round13Preserved"]["allFourCoverage"]==0.6265060240963856
 assert s["BaseWOTC"]["oneEightyDay"]["historyReady"] is False and s["BaseWOTC"]["threeSixtyFiveDay"]["historyReady"] is False
 assert s["vintageTemporalDecision"]=="VINTAGE_TEMPORAL_CONTRACT_UNRESOLVED"
def test_round14_applies_stop_rule_and_zero_write_posture():
 s=build();assert s["coverage"]["likely"]["cards"]==9485 and s["minimumNamedProjectSetFor70"] is None
 assert s["finalDecision"]=="70_PERCENT_PATH_REMAINS_UNPROVEN" and "Stop incremental modeling" in s["researchStopRecommendation"]
 assert s["productionPaused"] and s["rowsPersisted"]==0
