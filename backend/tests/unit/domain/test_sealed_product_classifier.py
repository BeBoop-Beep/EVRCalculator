from backend.domain.pokemon.sealed_product_classifier import classify_sealed_product


def family(name):
    return classify_sealed_product(name)["productFamily"]


def test_classifier_precedence_and_variants():
    standard = classify_sealed_product("Scarlet & Violet Elite Trainer Box [Koraidon]")
    center = classify_sealed_product("Scarlet & Violet Pokemon Center Elite Trainer Box [Miraidon]")
    assert standard["productFamily"] == "elite_trainer_box"
    assert standard["variantLabel"] == "Koraidon"
    assert center["productFamily"] == "pokemon_center_elite_trainer_box"
    assert center["variantLabel"] == "Miraidon"
    assert family("Booster Box Case") == "case"
    assert family("Build & Battle Box Display") == "display"
    assert family("Enhanced Booster Box") == "enhanced_booster_box"
    assert family("Surging Sparks Half Booster Box") == "half_booster_box"
    assert family("Surging Sparks Booster Box") == "booster_box"
    assert family("Sleeved Booster Pack") == "sleeved_booster_pack"
    assert family("Booster Pack") == "loose_booster_pack"


def test_bundle_and_exclusion_rules():
    assert family("Journey Together Booster Bundle") == "booster_bundle"
    assert classify_sealed_product("Journey Together Booster Bundle")["isOverviewEligible"]
    for name in ("Booster Bundle Case", "Set of 2 Elite Trainer Boxes", "Booster Pack Art Bundle"):
        assert not classify_sealed_product(name)["isOverviewEligible"]


def test_loose_pack_excludes_multi_pack_and_container_products():
    assert family("Booster Pack") == "loose_booster_pack"
    assert family("Sleeved Booster Pack") == "sleeved_booster_pack"
    for name in ("Booster Pack Art Bundle", "Set of 4 Booster Packs", "Booster Pack Case", "Booster Pack Display"):
        assert family(name) != "loose_booster_pack"


def test_set_page_consumer_policy_includes_retail_products_and_other_family():
    names = (
        "Booster Bundle", "Elite Trainer Box", "Pokemon Center Elite Trainer Box",
        "Ascended Heroes Mega ex Box", "Premium Collection", "Mini Tins 5-Pack",
        "Tin Set of 3", "Costco Retail Bundle", "Booster Pack", "Sleeved Booster Pack",
    )
    for name in names:
        identity = classify_sealed_product(name)
        assert identity["isSetPageConsumerMarketEligible"], name
        assert not identity["isBulkContainer"], name
    assert family("Ascended Heroes Mega ex Box") == "other"


def test_set_page_consumer_policy_excludes_bulk_containers_without_changing_legacy_family():
    names = (
        "Booster Bundle Case", "Booster Bundle Display", "Elite Trainer Box Case",
        "Mini Tin Display", "Mini Tin Display Case", "Stellar Crown Sleeved Booster Master Carton",
    )
    for name in names:
        identity = classify_sealed_product(name)
        assert identity["isBulkContainer"], name
        assert not identity["isSetPageConsumerMarketEligible"], name
    carton = classify_sealed_product("Stellar Crown Sleeved Booster Master Carton")
    assert carton["productFamily"] == "other"
    assert carton["isOverviewEligible"] is False
