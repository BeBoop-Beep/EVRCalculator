from backend.scripts.build_treatment_market_prestige_v3_round13 import PREREG,build
def test_round13_preregistration_and_functional_trainer_gates():
 s=build();assert PREREG["frozen_before_coefficients"] and PREREG["minimum_within_identity_set_pairs"]==20
 assert {x["era"] for x in s["functionalTrainer"]["pilots"]}=={"Sun and Moon","Sword and Shield"}
def test_round13_ecard_and_failed_eras_remain_fail_closed():
 s=build();assert s["ECard"]["recoverableCards"]==0 and s["ECard"]["repairedHistoryCoverage"]<.95
 assert s["BaseWOTC"]["recoverableCards"]==s["POP"]["recoverableCards"]==s["Other"]["recoverableCards"]==0
def test_round13_coverage_math_and_production_pause():
 s=build();gain=s["functionalTrainer"]["recoverableCards"];assert s["coverageEstimates"]["likely"]["cards"]==9202+gain
 assert s["remainingTo70"]==13893-(9202+gain) and s["minimumProjectSetFor70"]["likely"] is None
 assert s["productionPaused"] and s["rowsPersisted"]==0 and s["seventyPercentDecision"]=="70_PERCENT_PATH_REMAINS_UNPROVEN"
