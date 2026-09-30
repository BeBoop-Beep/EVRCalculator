from backend.pricing_pipeline.sold_condition_classifier_v2 import classify_sold_title_v2
from backend.pricing_pipeline.sold_condition_classifier_v3 import (
    CLASSIFIER_VERSION,
    classification_record_v3,
    classify_sold_title_v3,
    resolve_hp_stat_tokens,
)


def test_v2_remains_frozen_and_over_suppresses_hp_card_number_cases():
    assert (
        classify_sold_title_v2(
            "Mewtwo Gold Star (HP 103/110) EX Holon Phantoms - Pokemon"
        )["condition_label"]
        == "UNLABELED"
    )
    assert (
        classify_sold_title_v2(
            "1999 Pokemon Base Set Unlimited Gyarados Rare Holo #6/102 HP"
        )["condition_label"]
        == "UNLABELED"
    )


def test_v3_suppresses_only_exact_canonical_hp_stats():
    assert (
        classify_sold_title_v3(
            "Mega Dragonite ex SIR Ascended Heroes 290/217 HP 370 English Pokemon TCG NM",
            canonical_hp="370",
        )["condition_label"]
        == "NM"
    )
    assert (
        classify_sold_title_v3("Pokemon card 350 HP", canonical_hp="350")[
            "condition_label"
        ]
        == "UNLABELED"
    )
    assert (
        classify_sold_title_v3("Pokemon card HP 350", canonical_hp=350)[
            "condition_label"
        ]
        == "UNLABELED"
    )


def test_v3_preserves_hp_when_adjacent_number_is_card_number_not_printed_hp():
    assert (
        classify_sold_title_v3(
            "Mewtwo Gold Star (HP 103/110) EX Holon Phantoms - Pokemon",
            canonical_hp="80",
        )["condition_label"]
        == "HP"
    )
    assert (
        classify_sold_title_v3(
            "1999 Pokemon Base Set Unlimited Gyarados Rare Holo #6/102 HP",
            canonical_hp="100",
        )["condition_label"]
        == "HP"
    )


def test_v3_preserves_hp_when_numeric_value_does_not_match_canonical_hp():
    assert (
        classify_sold_title_v3("Pokemon card HP 350 NM", canonical_hp="340")[
            "condition_label"
        ]
        == "AMBIGUOUS"
    )
    assert (
        classify_sold_title_v3("Pokemon card 350 HP LP", canonical_hp="340")[
            "condition_label"
        ]
        == "AMBIGUOUS"
    )


def test_v3_preserves_full_heavily_played_phrase_even_when_stat_is_present():
    result = classify_sold_title_v3(
        "Heavily Played Pokemon card 350 HP",
        canonical_hp="350",
    )
    assert result["condition_label"] == "HP"
    assert result["confidence"] == "HIGH"


def test_v3_does_not_suppress_hp_without_canonical_metadata():
    assert (
        classify_sold_title_v3("Pokemon card 350 HP", canonical_hp=None)[
            "condition_label"
        ]
        == "HP"
    )


def test_hp_resolution_receipt_is_exact_and_does_not_treat_fractions_as_stats():
    match = resolve_hp_stat_tokens("Pokemon card HP 100", 100)
    assert match["suppressed_hp_stat_count"] == 1
    assert match["canonical_hp"] == "100"
    assert match["suppressed_spans"][0]["direction"] == "HP_VALUE"

    fraction = resolve_hp_stat_tokens("Pokemon #6/102 HP", 100)
    assert fraction["suppressed_hp_stat_count"] == 0

    fraction_right = resolve_hp_stat_tokens("Pokemon HP 103/110", 80)
    assert fraction_right["suppressed_hp_stat_count"] == 0


def test_v3_record_is_separately_versioned():
    row = classification_record_v3(
        "evidence-id",
        "Pokemon card 350 HP NM",
        canonical_hp="350",
        classified_at="2026-09-30T20:00:00Z",
    )
    assert row["condition_label"] == "NM"
    assert row["classifier_version"] == CLASSIFIER_VERSION
    assert CLASSIFIER_VERSION == "pkmnprices_sold_title_condition_v3"
