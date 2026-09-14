import csv
from pathlib import Path

from backend.scripts.prepare_index_fair_value_ebay_d2_gold import LABELS, populated


def test_gold_taxonomy_is_frozen_and_complete():
    assert LABELS == (
        "EXACT_TARGET_MATCH", "RELATED_BUT_WRONG_VARIANT", "WRONG_SET",
        "WRONG_CARD_NUMBER", "WRONG_LANGUAGE", "GRADED", "LOT_OR_BUNDLE",
        "SEALED_OR_ACCESSORY", "CONDITION_INELIGIBLE", "AMBIGUOUS", "OTHER",
    )


def test_population_treats_empty_containers_as_missing():
    assert not populated(None)
    assert not populated([])
    assert not populated({})
    assert populated("Ungraded")


def test_committed_queue_is_blinded_and_pending():
    path = Path(__file__).resolve().parents[3] / "artifacts" / "index_fair_value" / "ebay_manual_gold_labels.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert 750 <= len(rows) <= 1500
    assert all(not row["gold_label"] for row in rows)
    assert all(row["review_status"] == "PENDING_INDEPENDENT_HUMAN_REVIEW" for row in rows)
