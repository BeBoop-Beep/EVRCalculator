from backend.scripts.build_treatment_market_prestige_v3_round24 import GATES, QUERY, build


def test_round24_freezes_round23_baseline_and_exactly_decomposes_blockers():
    study = build()
    assert study["round23MetadataBlockedBaseline"] == {
        "POTENTIAL_MATCH_BLOCKED_BY_METADATA": 1680,
        "NO_MATCHED_LADDER": 965,
    }
    assert sum(study["metadataBlockerDecomposition"].values()) == 1680
    assert study["editionMissingCount"] == 152
    assert study["specialTreatmentMissingCount"] == 680
    assert study["treatmentCollapsedCount"] == 438
    assert study["conditionAlignmentBlockerCount"] == 410


def test_round24_preserves_vintage_uncertainty_instead_of_inventing_editions():
    study = build()
    base = study["base"]
    assert base["canonicalCards"] == base["variants"] == 102
    assert base["safelyEditionMappedVariants"] == 1
    assert base["unresolvedEditionVariants"] == 101
    assert base["exactSameIdentityEditionLadders"] == 0
    assert study["vintageTotalRepairs"] == 0


def test_round24_grouped_query_requires_same_condition_and_exact_date():
    normalized = " ".join(QUERY.lower().split())
    assert "condition_id,captured_date" in normalized
    assert "join b using(identity_key,variant_a,variant_b,condition_id,captured_date)" in normalized
    assert "forward fill" not in normalized
    assert GATES["noInterpolation"] and GATES["noForwardFill"]


def test_round24_panel_gates_do_not_promote_metadata_opportunity_to_scores():
    study = build()
    counts = study["panelReadinessCounts"]
    disposition = study["original1680Disposition"]
    assert counts["PANEL_READY_STRONG"] == 1
    assert counts["PANEL_READY_MODERATE"] == 4
    assert sum(disposition.values()) == 1680
    assert disposition["strong"] == 0
    assert disposition["moderate"] == 8
    assert study["original965NewlyMatched"] == 0
    assert study["decisions"]["nextEstimator"] == "MATCHED_ESTIMATION_RECONSIDERATION_NOT_WARRANTED"
    assert study["productionPaused"] and study["rowsPersisted"] == 0
