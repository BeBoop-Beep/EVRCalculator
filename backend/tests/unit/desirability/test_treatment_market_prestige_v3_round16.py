from backend.scripts.build_treatment_market_prestige_v3_round16 import build
def test_round16_disjoint_ledger_and_no_best_fit_assignment():
 s=build();ledger=s["_ledger"];assert len(ledger)==19847==len({x["cardId"] for x in ledger});assert sum(x["coverageProvenance"]=="UNRESOLVED" for x in ledger)==len(s["_bestfit"]);assert all(x["coverageProvenance"]!="BEST_FIT_INFERRED" for x in ledger)
def test_round16_trainer_fallback_energy_and_assignment_rules():
 s=build();assert s["Trainer"]["normalTreatmentFallbackRecovered"]>0;assert s["Energy"]["neutralCount"]==371;assert s["canonicalMappingAssignment"]["cardsRecovered"]>0
def test_round16_coverage_and_production_safety():
 s=build();c=s["coverage"];assert c["direct"]["cards"]+c["unresolved"]==19847-371;assert c["strongEvidence"]["cards"]==c["direct"]["cards"];assert c["usableScore"]["cards"]==c["direct"]["cards"]+371;assert s["rowsPersisted"]==0 and s["productionPaused"]
