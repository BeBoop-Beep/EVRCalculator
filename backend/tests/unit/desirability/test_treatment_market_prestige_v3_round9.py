from backend.scripts.build_treatment_market_prestige_v3_round9 import build


def test_round9_card_decomposition_is_exhaustive_and_exclusive():
    study = build()
    cards = study["_card_results"]
    assert len(cards) == study["currentAuthoritativeDenominator"] == 19847
    assert sum(x["covered"] for x in cards) == study["currentlyCoveredCards"] == 5059
    assert sum(study["primaryFailureCategories"].values()) == study["uncoveredCards"] == 14788
    assert all((x["primaryBlocker"] is None) == x["covered"] for x in cards)


def test_round9_does_not_convert_near_ties_into_false_eligibility():
    study = build()
    audit = study["similarityAudit"]
    assert audit["existingRule"]["unique_ordering_required"] is False
    assert audit["ruleAudit"] == "SIMILARITY_AWARE_UNIVERSE_RULE_ALREADY_CORRECT"
    assert audit["cardsRecoverable"] == 0


def test_round9_is_research_only_and_product_gate_fails_closed():
    study = build()
    assert study["currentCoverage"] < study["catalogProductCoverageTarget"]
    assert study["productionImplementationPaused"] is True
    assert study["rowsPersisted"] == 0
    assert study["productStatus"] == "CATALOG_COVERAGE_BELOW_PRODUCT_THRESHOLD"
