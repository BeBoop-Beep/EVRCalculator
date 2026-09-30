from backend.pricing_pipeline.sold_condition_classifier import classify_sold_title
from backend.pricing_pipeline.sold_condition_classifier_v2 import (
    CLASSIFIER_VERSION,
    classification_record_v2,
    classify_sold_title_v2,
)


def test_v1_remains_frozen_and_still_exposes_hp_stat_failure():
    assert classify_sold_title("Pokemon card 350 HP NM")["condition_label"] == "AMBIGUOUS"


def test_v2_suppresses_numeric_hp_stats():
    assert classify_sold_title_v2("Pokemon card 350 HP")["condition_label"] == "UNLABELED"
    assert classify_sold_title_v2("Pokemon card HP 350")["condition_label"] == "UNLABELED"
    assert classify_sold_title_v2("Pokemon card 130HP")["condition_label"] == "UNLABELED"


def test_v2_preserves_real_heavily_played_evidence():
    assert classify_sold_title_v2("Pokemon card HP condition")["condition_label"] == "HP"
    assert classify_sold_title_v2("Pokemon card Heavily Played")["condition_label"] == "HP"
    assert classify_sold_title_v2("Pokemon card HP/DMG")["condition_label"] == "AMBIGUOUS"


def test_v2_keeps_other_condition_signal_when_hp_is_a_stat():
    assert classify_sold_title_v2("Pokemon card 350 HP NM")["condition_label"] == "NM"
    assert classify_sold_title_v2("near mint 370 HP")["condition_label"] == "NM"
    assert classify_sold_title_v2("HP 350 full art NM")["condition_label"] == "NM"
    assert classify_sold_title_v2("350 HP LP")["condition_label"] == "LP"


def test_v2_record_is_separately_versioned():
    row = classification_record_v2(
        "evidence-id",
        "Pokemon card 350 HP NM",
        classified_at="2026-09-30T18:00:00Z",
    )
    assert row["condition_label"] == "NM"
    assert row["classifier_version"] == CLASSIFIER_VERSION
    assert CLASSIFIER_VERSION == "pkmnprices_sold_title_condition_v2"
