from backend.scripts.build_trainer_treatment_market_prestige_v3t_round3 import build
def test_round3_reconciles_trainer_and_catalog_ledgers():
 s=build();assert s["totalTrainerCards"]==2718;assert s["previouslySupportedTrainerCards"]["total"]==973;assert s["finalTrainerDownstreamValidCards"]==973;assert s["catalogCoverage"]["totalLikely"]==10175
def test_round3_expansion_fails_closed_without_double_counting():
 s=build();assert s["incrementalTrainerCatalogRecovery"]==0;assert sum(s["terminalBlockerTable"].values())==19847-10175;assert len({x["cardId"] for x in s["_residual"]})==19847-10175
def test_round3_preserves_production_pause_and_gate():
 s=build();assert s["rowsPersisted"]==0;assert s["catalogCoverage"]["remainingTo70"]==3718;assert s["seventyPercentStatus"]=="70_PERCENT_PATH_REMAINS_UNPROVEN"
