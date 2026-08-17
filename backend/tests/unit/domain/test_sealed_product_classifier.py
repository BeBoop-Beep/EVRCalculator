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
    assert family("Booster Pack") == "booster_pack"


def test_bundle_and_exclusion_rules():
    assert family("Journey Together Booster Bundle") == "booster_bundle"
    assert classify_sealed_product("Journey Together Booster Bundle")["isOverviewEligible"]
    for name in ("Booster Bundle Case", "Set of 2 Elite Trainer Boxes", "Booster Pack Art Bundle"):
        assert not classify_sealed_product(name)["isOverviewEligible"]
