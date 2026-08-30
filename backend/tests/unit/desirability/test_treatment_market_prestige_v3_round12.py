from backend.scripts.build_treatment_market_prestige_v3_round12 import SELECTED,build
def test_round12_freezes_selection_and_history_before_models():
 s=build();assert SELECTED==["Diamond and Pearl","Platinum","HeartGold and SoulSilver","Base/WOTC"]
 assert all(next(x for x in s["unsupportedPokemonEras"] if x["era"]==e)["historyReadiness"]=="HISTORY_READY_INTERNAL" for e in SELECTED)
def test_round12_downstream_recovery_and_waterfall_are_exact():
 s=build();gains=[x["gain"] for x in s["olderEraWaterfall"]];assert s["coverage"]["researchSupportedLikely"]==7579+sum(gains)
 assert all(x["cumulativeCards"]<=s["denominator"] for x in s["olderEraWaterfall"])
def test_round12_trainer_identity_is_conservative_and_production_paused():
 s=build();i=s["Trainer"]["identity"];assert i["usableIdentityCards"]+i["ambiguousCards"]+i["noParentIdentityCards"]==2718
 assert s["Trainer"]["pilot"]["run"] is False and s["Trainer"]["likelyRecoverable"]==0
 assert s["seventyPercentDecision"]=="70_PERCENT_PATH_REMAINS_UNPROVEN" and s["productionPaused"] and s["rowsPersisted"]==0
