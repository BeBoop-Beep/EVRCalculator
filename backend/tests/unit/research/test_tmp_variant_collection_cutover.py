from backend.scripts.build_tmp_variant_collection_cutover import CUTOVER_DATE, build


def test_cutover_reconciles_every_round24_static_blocker():
    result = build()
    assert result["staticBlockerBaseline"] == {
        "EDITION_MISSING": 152,
        "SPECIAL_TREATMENT_MISSING": 680,
        "TREATMENT_COLLAPSED": 438,
    }
    assert len(result["records"]) == 1270
    assert sum(result["collectionStatusCounts"].values()) == 1270


def test_base_priority_cases_fail_closed_without_provider_edition_identity():
    result = build()
    for key in ("baseCharizardVariantStates", "baseBlastoiseVariantStates", "baseVenusaurVariantStates", "baseMewtwoVariantStates", "baseAlakazamVariantStates"):
        case = result[key]
        assert case["collectionStatus"] == "PROVIDER_VARIANT_IDENTITY_MISSING"
        assert case["externalProviderEvidenceMissing"]
        assert not case["waitingCanNowHelp"]
    charizard = result["baseCharizardVariantStates"]
    assert charizard["externalIdentities"][0]["external_product_id"] == "42382"
    assert charizard["externalIdentities"][0]["external_variant_key"] == "edition=|printing_type=holo|special_type="


def test_ready_states_have_exact_external_authority_and_await_first_post_cutover_date():
    result = build()
    ready = [row for row in result["records"] if row["collectionStatus"] == "COLLECTION_READY"]
    assert ready
    assert all(row["firstTrustworthyDate"] is None and row["waitingCanNowHelp"] for row in ready)
    assert all(row["externalIdentities"] for row in ready)
    assert result["cutoverDate"] == CUTOVER_DATE
    assert result["firstAuthoritativeCollectionDate"] is None


def test_cutover_preserves_history_and_tmp_production_safety():
    result = build()
    assert all(row["legacyCollapsedHistoryRetained"] for row in result["records"])
    assert result["failClosedBehavior"]["genericPriceDuplicated"] is False
    assert result["productionTmpRowsPersisted"] == 0
    assert result["finalReadinessDecision"] == "TMP_VARIANT_COLLECTION_READY_FOR_DECEMBER"
