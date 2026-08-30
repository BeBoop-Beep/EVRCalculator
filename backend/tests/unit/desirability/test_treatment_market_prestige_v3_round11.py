from backend.scripts.build_treatment_market_prestige_v3_round11 import build
def test_round11_uses_authoritative_four_checkpoint_history():
 s=build();assert s["historyAudit"]["readOnly"] and len(s["historyAudit"]["checkpointDates"])==4
 assert s["EX"]["internalHistory"]["allFourCoverage"]>=.95 and s["BlackAndWhite"]["internalHistory"]["allFourCoverage"]>=.95
def test_round11_price_blind_architecture_and_domain_counts():
 s=build();assert s["EX"]["architecture"]["decision"]=="ERA_RELATIVE";assert s["BlackAndWhite"]["architecture"]["decision"]=="TREATMENT_REGIME_RELATIVE"
 assert s["Trainer"]["audit"]["cards"]==2718 and s["Energy"]["audit"]["cards"]==371
def test_round11_does_not_overclaim_new_estimands_or_coverage():
 s=build();assert s["Trainer"]["pilot"]["run"] is False and s["Energy"]["pilot"]["run"] is False
 assert s["seventyPercentPathStatus"]=="70_PERCENT_PATH_REMAINS_UNPROVEN" and s["productionPaused"] and s["rowsPersisted"]==0
