from backend.db.services.collector_appeal_current_service import build_public_collector_appeal_contract


def _row(status="scored"):
    scored=status=="scored"
    return {"model_run_id":"run","model_version":"model","as_of_date":"2026-09-08","set_id":"set","collector_appeal_score":100 if scored else None,"collector_appeal_rank":1 if scored else None,"score_status":status,"score_status_reason":None if scored else "collector_appeal_unavailable_no_generalized_frequency","collector_roster_desirability_score":99,"collector_roster_desirability_rank":2,"generalized_desirable_outcome_frequency":.25 if scored else None,"generalized_frequency_status":"available" if scored else "unavailable","generalized_frequency_status_reason":None if scored else "collector_appeal_unavailable_no_generalized_frequency","eligible_card_count":20,"scored_card_count":18,"score_coverage_ratio":1,"roster_diagnostics_json":{"distinctGroupCount":8,"pokemonGroupCount":5,"trainerGroupCount":2,"neutralFunctionalGroupCount":1},"subject_rollups_json":[{"identity":"Iono","type":"trainer","appeal":98,"cardCount":1}]}


def test_scored_public_contract_is_standalone_and_hides_formula_inputs():
    contract=build_public_collector_appeal_contract(_row())
    assert contract["contractVersion"]=="public_collector_appeal_contract_v1"
    assert contract["collectorAppeal"]["score"]==100
    assert contract["collectorAppeal"]["rankedSetCount"]==22
    assert contract["components"]["rosterDesirability"]["topCollectorGroups"][0]["type"]=="trainer"
    serialized=str(contract)
    for forbidden in ("frequencyIndex","frequencyModifierPoints","fingerprint","lambda","saturationK"):
        assert forbidden not in serialized


def test_unavailable_contract_never_falls_back_to_roster_score():
    contract=build_public_collector_appeal_contract(_row("unavailable"))
    assert contract["collectorAppeal"]["score"] is None
    assert contract["collectorAppeal"]["rank"] is None
    assert contract["components"]["rosterDesirability"]["score"]==99
    assert contract["components"]["desirableOutcomeFrequency"]["rawValue"] is None
