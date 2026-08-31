from backend.scripts.build_treatment_market_prestige_v3_round23 import build


def test_round23_builds_explicit_identity_tiers_without_name_only_pokemon_matches():
    study = build()
    assert study["tier1PairCount"] == 12671
    assert study["tier1TripleCount"] == 982
    assert study["tier1FourPlusCount"] == 211
    assert study["tier2PairCount"] == 1430
    assert study["trainerMatchedLadderCount"] == 440
    assert "Names alone never establish Pokémon identity" in study["canonicalIdentityMethodology"]


def test_round23_accounts_for_locked_unresolved_and_structural_populations():
    study = build()
    unresolved = study["unresolvedRelevantClassification"]
    structural = study["round21StructuralClassification"]
    assert sum(unresolved.values()) == 2645
    assert sum(structural.values()) == 2043
    assert unresolved["MATCHED_LADDER_DIRECT"] == 0
    assert unresolved["MATCHED_LADDER_INDIRECT"] == 0
    assert unresolved["POTENTIAL_MATCH_BLOCKED_BY_METADATA"] > 0


def test_round23_freezes_only_condition_aligned_panels_without_imputation():
    study = build()
    panels = study["_panels"]
    assert study["naturalExperimentCounts"]["strong"] >= 1
    assert study["overlapDateBands"][">=90"] >= 1
    assert panels
    assert all(row["conditionAuthority"] and row["marketPrice"] > 0 for row in panels)
    assert len({(row["canonicalIdentity"], row["variantId"], row["date"]) for row in panels}) == len(panels)


def test_round23_does_not_publish_scores_or_change_production():
    study = build()
    assert study["decisions"]["futureStudy"] == "MATCHED_TREATMENT_ESTIMATION_STUDY_NOT_WARRANTED"
    assert study["decisions"]["matchedStructure"] == "MATCHED_TREATMENT_STRUCTURE_LIMITED"
    assert study["decisions"]["taxonomy"] == "TAXONOMY_REPAIR_LIMITED_FOR_TMP"
    assert study["projectedMaximumCardsAddressableByMatchedFramework"] == 0
    assert study["productionPaused"]
    assert study["rowsPersisted"] == 0
