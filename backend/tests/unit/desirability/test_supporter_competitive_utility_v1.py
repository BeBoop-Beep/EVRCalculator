from backend.scripts.build_supporter_competitive_utility_v1 import CONTRACT, build


def test_contract_is_outcome_blind_and_capped():
    assert CONTRACT["primaryWindowDays"] == 30
    assert CONTRACT["minimumPlayers"] == 32
    assert CONTRACT["minimumDecklistCoverage"] == .80
    assert CONTRACT["maximumSelectedEvents"] == 15


def test_competitive_score_excludes_market_and_treatment_inputs():
    study = build()
    assert study["competitiveMethodology"]["marketPriceUsed"] is False
    assert study["competitiveMethodology"]["treatmentUsed"] is False
    assert all(0 <= x["fieldUsageDemand"] <= 100 for x in study["competitiveScores"])


def test_supporter_model_fails_closed_and_production_is_untouched():
    study = build()
    assert study["supporter"]["modelB"]["status"] == "NOT_IDENTIFIABLE_WITH_FUNCTIONAL_IDENTITY_FE"
    assert study["supporter"]["finalLikelyRecoverableCards"] == 0
    assert study["coverage"]["updatedLikelyCards"] == 9485
    assert study["rowsPersisted"] == 0
