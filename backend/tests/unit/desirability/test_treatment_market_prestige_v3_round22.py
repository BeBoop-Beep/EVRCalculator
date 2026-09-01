from backend.scripts.build_treatment_market_prestige_v3_round22 import GATES, PILOTS, build


def test_round22_freezes_the_ten_preregistered_pilot_environments():
    study = build()
    assert study["exactPilotSets"] == PILOTS
    assert len(study["setResults"]) == 10
    assert study["perSetCardCounts"]["Base Set"] == 95
    assert all(count >= GATES["minimumCards"] for count in study["perSetCardCounts"].values())


def test_round22_preserves_verified_live_base_audit_separately_from_model_cohort():
    audit = build()["liveBaseSetAudit"]
    assert audit["canonicalCards"] == audit["currentVariants"] == 102
    assert audit["observations"] == 63600
    assert audit["distinctDates"] == 132
    assert audit["firstDate"] == "2026-04-11"
    assert audit["lastDate"] == "2026-08-28"
    assert audit["editionMapped"] == 1


def test_round22_requires_graph_and_temporal_identification_before_recovery():
    study = build()
    assert study["matchedIdentityCounts"]["Base Set"] == 0
    assert sum(result["passesNonTemporalGates"] for result in study["setResults"].values()) == 2
    assert not any(result["temporal"]["passes"] for result in study["setResults"].values())
    assert not any(result["validated"] for result in study["setResults"].values())
    assert study["potentialCollectorRelevantRecovery"] == 0
    assert study["potentialPremiumRecovery"] == 0
    assert study["_potential"] == []


def test_round22_rejects_redesign_and_preserves_production_safety():
    study = build()
    assert study["decisions"]["framework"] == "SET_RELATIVE_TMP_NOT_SUPPORTED"
    assert study["decisions"]["fullCatalog"] == "SET_RELATIVE_TMP_DOES_NOT_JUSTIFY_REDESIGN"
    assert study["decisions"]["base"] == "BASE_SET_RELATIVE_TMP_NOT_SUPPORTED"
    assert study["productionPaused"]
    assert study["rowsPersisted"] == 0
