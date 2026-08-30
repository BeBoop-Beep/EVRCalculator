from backend.scripts.build_supporter_treatment_market_prestige_v3s_round2 import build


def test_round2_freezes_and_conserves_supporter_cohort():
    study=build()
    assert study["frozenCohort"]["cards"]==1132
    assert study["identityAudit"]["safeFunctionalIdentities"]==451
    assert study["identityAudit"]["crossTreatmentIdentities"]==315


def test_round2_separates_main_effect_absorption_from_treatment_identification():
    study=build()
    assert "does not imply treatment-effect non-identification" in study["correctedV1Interpretation"]
    assert any(x.get("identification")=="TREATMENT_IDENTIFIABLE" for x in study["eraModels"].values())


def test_round2_fails_closed_and_never_persists_production_rows():
    study=build()
    expected=9485+study["recovery"]["finalDownstreamValidCards"]
    assert study["coverage"]["updated"]==expected
    assert study["coverage"]["remainingTo70"]==13893-expected
    assert study["rowsPersisted"]==0
