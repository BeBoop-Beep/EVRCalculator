"""Stage-III tests: labeling apparatus, blindness, and the benchmark framework.

The two properties that matter most here are adversarial:

* ``test_packet_is_blind_*`` - the packet must not leak the model under test.
  If it does, the human labels stop being independent evidence and the whole
  stage becomes a tautology.
* ``test_benchmark_refuses_to_score_without_human_labels`` - the benchmark must
  never invent ground truth. A benchmark scored against an algorithm's own
  output measures nothing at all.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from backend.research.set_chase_efficiency.benchmark import (
    NO_LABELS_STATUS,
    benchmark,
    confusion,
    disagreement_profile,
    evaluate_method,
    leave_one_set_out,
    scores,
)
from backend.research.set_chase_efficiency.labeling import (
    LABELING_COHORT,
    LABEL_COLUMNS,
    PACKET_COLUMNS,
    TARGET_CORE,
    TARGET_MEANINGFUL,
    LabelRow,
    agreement_report,
    assert_packet_is_blind,
    assert_packet_rows_are_unique,
    build_candidate_pool,
    cohens_kappa,
    consensus_labels,
    fleiss_kappa,
    packet_row,
    read_labels,
    target_positive,
    write_label_template_csv,
    write_packet_csv,
)


def card(variant: str, price, *, name: str = None, number: str = "001/100"):
    return {
        "card_id": f"card-{variant}", "card_variant_id": variant,
        "card_name": name or f"Card {variant}", "card_number": number,
        "rarity": "illustration rare", "treatment": "", "printing_type": "holo",
        "market_price": price, "image_url": "",
    }


def rows_for(cards, *, set_id="set-1", set_name="Test Set", pack_price=10.0):
    return [packet_row(c, set_id=set_id, set_name=set_name, pack_price=pack_price)
            for c in cards]


# --- Cohort -----------------------------------------------------------------

def test_cohort_is_ten_structurally_distinct_sets_each_with_a_rationale():
    assert 8 <= len(LABELING_COHORT) <= 10
    assert len({entry.canonical_key for entry in LABELING_COHORT}) == len(LABELING_COHORT)
    assert len({entry.structure for entry in LABELING_COHORT}) >= 8
    for entry in LABELING_COHORT:
        assert len(entry.rationale) > 80, f"{entry.set_name} has no real rationale"


def test_cohort_spans_hero_and_deep_and_cheap_and_expensive_structures():
    structures = " ".join(entry.structure for entry in LABELING_COHORT)
    for required in ("hero", "deep", "cheap", "expensive", "unstable", "stable"):
        assert required in structures


def test_cohort_rationale_never_cites_financial_rip():
    """Selection had to be structural, not driven by the production ranking."""
    for entry in LABELING_COHORT:
        lowered = entry.rationale.lower()
        assert "financial rip" not in lowered
        assert "overall rip" not in lowered


# --- Blindness --------------------------------------------------------------

def test_packet_is_blind_to_model_output():
    rows = rows_for([card("v1", 100.0)])
    assert_packet_is_blind(rows)  # baseline passes
    for leak in ("beat_the_buy", "chase_ev_contribution", "effective_chase_count",
                 "financial_rip_v3_score", "p95_value_to_cost_ratio",
                 "jackpot_upside", "hhi_value", "hit_probability",
                 "algorithm_selected", "predicted_label", "elbow_k"):
        polluted = [{**rows[0], leak: "anything"}]
        with pytest.raises(ValueError):
            assert_packet_is_blind(polluted)


def test_packet_columns_are_a_closed_allow_list():
    rows = rows_for([card("v1", 100.0)])
    assert set(rows[0]) == set(PACKET_COLUMNS)
    with pytest.raises(ValueError):
        assert_packet_is_blind([{**rows[0], "harmless_looking_extra": "x"}])


def test_written_packet_contains_only_allow_listed_columns(tmp_path: Path):
    path = write_packet_csv(rows_for([card("v1", 100.0), card("v2", 50.0)]),
                            tmp_path / "packet.csv")
    with path.open(encoding="utf-8") as handle:
        assert next(csv.reader(handle)) == list(PACKET_COLUMNS)


# --- The duplicate defect ---------------------------------------------------

def test_duplicate_printing_is_rejected():
    """THE STAGE-III DEFECT. A human must never label the same printing twice."""
    rows = rows_for([card("v1", 100.0)]) * 2
    with pytest.raises(ValueError, match="duplicate"):
        assert_packet_rows_are_unique(rows)


def test_same_variant_in_two_different_sets_is_allowed():
    """Uniqueness is per ``(set_id, card_variant_id)``, not per variant alone."""
    rows = (rows_for([card("v1", 100.0)], set_id="set-1")
            + rows_for([card("v1", 100.0)], set_id="set-2"))
    assert_packet_rows_are_unique(rows)


def test_row_without_a_variant_id_is_rejected():
    with pytest.raises(ValueError, match="no card_variant_id"):
        assert_packet_rows_are_unique(rows_for([card("", 100.0)]))


def test_both_writers_enforce_uniqueness(tmp_path: Path):
    duplicated = rows_for([card("v1", 100.0)]) * 2
    with pytest.raises(ValueError, match="duplicate"):
        write_packet_csv(duplicated, tmp_path / "a.csv")
    with pytest.raises(ValueError, match="duplicate"):
        write_label_template_csv(duplicated, tmp_path / "b.csv")


# --- Candidate pool ---------------------------------------------------------

def test_pool_prefers_recall_and_proves_what_it_excluded():
    cards = [card(f"v{i}", price) for i, price in
             enumerate([500.0, 120.0, 45.0, 12.0, 9.0, 3.0, 0.25])]
    result = build_candidate_pool(cards, pack_price=10.0, top_n=3)
    proof = result["proof"]
    assert proof["dearestCardExcluded"] < proof["cheapestCardInPool"]
    assert proof["exclusionHeadroomRatio"] < 1.0


def test_pool_always_contains_every_algorithm_selection():
    """Otherwise a method's recall would be capped for a reason unrelated to it."""
    cards = [card("expensive", 500.0), card("obscure", 1.25)]
    result = build_candidate_pool(cards, pack_price=10.0,
                                  algorithm_selected_ids=["obscure"])
    assert {row["card_variant_id"] for row in result["pool"]} == {"expensive", "obscure"}
    assert result["proof"]["algorithmSelectedCoveredByPool"] is True


def test_pool_records_why_each_card_entered():
    result = build_candidate_pool([card("v1", 500.0)], pack_price=10.0)
    assert result["pool"][0]["_pool_reasons"]


def test_unpriced_cards_are_reported_not_silently_dropped():
    result = build_candidate_pool([card("v1", 500.0), card("v2", None)], pack_price=10.0)
    assert result["proof"]["unpricedCount"] == 1


# --- Label template ---------------------------------------------------------

def test_template_has_label_columns_and_no_prefilled_labels(tmp_path: Path):
    path = write_label_template_csv(rows_for([card("v1", 100.0), card("v2", 20.0)]),
                                    tmp_path / "labels.csv")
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert set(LABEL_COLUMNS) <= set(rows[0])
    assert all(row["human_label"] == "" for row in rows), "labels must never be fabricated"


# --- Ingestion --------------------------------------------------------------

def _write_labels(tmp_path: Path, records) -> Path:
    path = tmp_path / "filled.csv"
    fieldnames = list(PACKET_COLUMNS) + list(LABEL_COLUMNS)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            base = {name: "" for name in fieldnames}
            writer.writerow({**base, **record})
    return path


def test_read_labels_accepts_valid_rows_and_rejects_bad_ones_with_reasons(tmp_path: Path):
    path = _write_labels(tmp_path, [
        {"set_name": "S", "card_variant_id": "v1", "human_label": "CORE_CHASE",
         "labeler_id": "alice", "label_confidence": "3", "market_price": "500"},
        {"set_name": "S", "card_variant_id": "v2", "human_label": "CORE",
         "labeler_id": "alice"},
        {"set_name": "S", "card_variant_id": "v3", "human_label": "NOT_CHASE",
         "labeler_id": ""},
        {"set_name": "S", "card_variant_id": "v4", "human_label": "NOT_CHASE",
         "labeler_id": "alice", "label_confidence": "9"},
        {"set_name": "S", "card_variant_id": "v5", "human_label": "",
         "labeler_id": "alice"},
    ])
    rows, rejected = read_labels(path)
    assert [row.card_variant_id for row in rows] == ["v1"]
    assert len(rejected) == 3
    assert all(entry["reason"] for entry in rejected)
    assert rows[0].label_confidence == 3 and rows[0].market_price == 500.0


def test_lowercase_labels_are_accepted():
    """A labeler typing lowercase is not making a semantic error."""
    assert target_positive("CORE_CHASE", TARGET_CORE) is True


# --- Targets ----------------------------------------------------------------

def test_target_definitions_differ_on_extended_chase():
    assert target_positive("CORE_CHASE", TARGET_CORE) is True
    assert target_positive("EXTENDED_CHASE", TARGET_CORE) is False
    assert target_positive("EXTENDED_CHASE", TARGET_MEANINGFUL) is True
    assert target_positive("NOT_CHASE", TARGET_MEANINGFUL) is False


def test_unsure_is_excluded_from_both_targets_rather_than_guessed():
    assert target_positive("UNSURE", TARGET_CORE) is None
    assert target_positive("UNSURE", TARGET_MEANINGFUL) is None


def test_consensus_majority_drops_ties_rather_than_breaking_them():
    rows = [
        LabelRow("S", "v1", "A", 10.0, "CORE_CHASE", "alice", 3, ""),
        LabelRow("S", "v1", "A", 10.0, "NOT_CHASE", "bob", 3, ""),
        LabelRow("S", "v2", "B", 10.0, "CORE_CHASE", "alice", 3, ""),
        LabelRow("S", "v2", "B", 10.0, "CORE_CHASE", "bob", 3, ""),
    ]
    truth = consensus_labels(rows, target=TARGET_CORE)
    assert ("S", "v1") not in truth, "a tied card is not agreed ground truth"
    assert truth[("S", "v2")] is True


def test_unanimous_rule_is_stricter_than_majority():
    rows = [
        LabelRow("S", "v1", "A", 10.0, "CORE_CHASE", "alice", 3, ""),
        LabelRow("S", "v1", "A", 10.0, "CORE_CHASE", "bob", 3, ""),
        LabelRow("S", "v1", "A", 10.0, "NOT_CHASE", "carol", 3, ""),
    ]
    assert consensus_labels(rows, target=TARGET_CORE)[("S", "v1")] is True
    assert ("S", "v1") not in consensus_labels(rows, target=TARGET_CORE, rule="unanimous")


# --- Agreement --------------------------------------------------------------

def test_cohens_kappa_is_one_for_perfect_and_near_zero_for_chance():
    perfect = cohens_kappa({1: "A", 2: "B", 3: "A", 4: "B"},
                           {1: "A", 2: "B", 3: "A", 4: "B"})
    assert perfect["cohensKappa"] == pytest.approx(1.0)
    opposed = cohens_kappa({1: "A", 2: "A", 3: "B", 4: "B"},
                           {1: "B", 2: "B", 3: "A", 4: "A"})
    assert opposed["cohensKappa"] < 0


def test_kappa_is_undefined_not_perfect_when_everyone_used_one_category():
    result = cohens_kappa({1: "A", 2: "A", 3: "A"}, {1: "A", 2: "A", 3: "A"})
    assert result["rawAgreement"] == 1.0
    assert result["cohensKappa"] is None
    assert result["kappaUndefinedReason"]


def test_kappa_needs_enough_shared_items():
    assert cohens_kappa({1: "A"}, {1: "A"}) is None


def test_fleiss_kappa_requires_three_labelers():
    two = [LabelRow("S", f"v{i}", "C", 10.0, "CORE_CHASE", who, 3, "")
           for i in range(4) for who in ("alice", "bob")]
    assert fleiss_kappa(two) is None
    three = [LabelRow("S", f"v{i}", "C", 10.0, "CORE_CHASE", who, 3, "")
             for i in range(4) for who in ("alice", "bob", "carol")]
    assert fleiss_kappa(three)["labelers"] == 3


def test_agreement_report_isolates_core_versus_extended_disputes():
    """Disagreeing about the Core line is different from disagreeing about chase."""
    rows = [
        LabelRow("S", "v1", "Hero", 500.0, "CORE_CHASE", "alice", 3, ""),
        LabelRow("S", "v1", "Hero", 500.0, "EXTENDED_CHASE", "bob", 2, ""),
        LabelRow("S", "v2", "Bulk", 2.0, "NOT_CHASE", "alice", 3, ""),
        LabelRow("S", "v2", "Bulk", 2.0, "NOT_CHASE", "bob", 3, ""),
    ]
    report = agreement_report(rows)
    assert report["disputedCount"] == 1
    assert report["disputedCoreVsExtendedOnly"] == 1
    # Under Target B both labelers call v1 a chase, so there is no dispute there.
    assert report["labelDistribution"]["CORE_CHASE"] == 1


def test_agreement_report_survives_a_single_labeler():
    """Schema must support one labeler now and more later."""
    rows = [LabelRow("S", "v1", "A", 10.0, "CORE_CHASE", "alice", 3, "")]
    report = agreement_report(rows)
    assert report["labelers"] == ["alice"]
    assert report["pairwiseRawScheme"] == {}
    assert report["fleiss"] is None


# --- Benchmark --------------------------------------------------------------

def test_benchmark_refuses_to_score_without_human_labels():
    """THE ANTI-TAUTOLOGY GUARD."""
    result = benchmark(labels=[], selections_by_method={"top_5": {"S": ["v1"]}})
    assert result["status"] == NO_LABELS_STATUS
    assert result["targets"] == {}
    assert leave_one_set_out(labels=[], fit=lambda names: None,
                             predict=lambda p, s: [], target=TARGET_CORE)["status"] == NO_LABELS_STATUS
    assert disagreement_profile([])["status"] == NO_LABELS_STATUS


def test_confusion_ignores_predictions_outside_the_labelled_pool():
    counts = confusion(["v1", "v9"], {"v1": True, "v2": True, "v3": False})
    assert counts["truePositives"] == 1
    assert counts["falseNegatives"] == 1
    assert counts["falsePositives"] == 0
    assert counts["predictedOutsideTruth"] == 1


def test_scores_are_none_not_one_when_a_rule_selects_nothing():
    counts = confusion([], {"v1": True, "v2": False})
    assert scores(counts)["precision"] is None
    assert scores(counts)["recall"] == 0.0


def test_scores_are_correct_on_a_worked_example():
    counts = confusion(["a", "b", "c"], {"a": True, "b": True, "c": False,
                                         "d": True, "e": False})
    assert (counts["truePositives"], counts["falsePositives"],
            counts["falseNegatives"], counts["trueNegatives"]) == (2, 1, 1, 1)
    result = scores(counts)
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(2 / 3)
    assert result["f1"] == pytest.approx(2 / 3)
    assert result["jaccard"] == pytest.approx(0.5)


def test_macro_average_does_not_let_the_largest_set_decide():
    """A rule perfect on a tiny set and useless on a huge one must not score ~1."""
    truth = {
        "small": {"v1": True},
        "large": {f"c{i}": (i < 20) for i in range(200)},
    }
    selections = {"small": ["v1"], "large": []}
    result = evaluate_method(method_key="m", selections_by_set=selections,
                             truth_by_set=truth)
    assert result["perSet"]["small"]["f1"] == pytest.approx(1.0)
    assert result["macro"]["f1"] == pytest.approx(0.5)
    assert result["worstSetF1"] == pytest.approx(0.0)


def test_exact_k_and_k_error_are_reported():
    truth = {"S": {"v1": True, "v2": True, "v3": False}}
    result = evaluate_method(method_key="m", selections_by_set={"S": ["v1"]},
                             truth_by_set=truth)
    assert result["exactKAgreement"] == 0.0
    assert result["meanAbsoluteKError"] == 1.0


def test_leave_one_set_out_needs_at_least_three_labelled_sets():
    rows = [LabelRow(f"S{i}", "v1", "A", 10.0, "CORE_CHASE", "alice", 3, "")
            for i in range(2)]
    result = leave_one_set_out(labels=rows, fit=lambda names: 1,
                               predict=lambda p, s: ["v1"], target=TARGET_CORE)
    assert result["status"] == "INSUFFICIENT_SETS"


def test_leave_one_set_out_never_fits_on_the_held_out_set():
    rows = []
    for index in range(4):
        rows.append(LabelRow(f"S{index}", "v1", "A", 10.0, "CORE_CHASE", "alice", 3, ""))
        rows.append(LabelRow(f"S{index}", "v2", "B", 5.0, "NOT_CHASE", "alice", 3, ""))
    seen = []

    def fit(training):
        seen.append(tuple(sorted(training)))
        return len(training)

    result = leave_one_set_out(labels=rows, fit=fit,
                               predict=lambda parameter, held: ["v1"],
                               target=TARGET_CORE)
    assert result["status"] == "SCORED"
    assert len(result["folds"]) == 4
    for fold, training in zip(result["folds"], seen):
        assert fold["heldOutSet"] not in training
    assert result["heldOutMacro"]["f1"] == pytest.approx(1.0)


def test_disagreement_profile_buckets_disputes_by_price():
    rows = [
        LabelRow("S", "v1", "Hero", 500.0, "CORE_CHASE", "alice", 3, ""),
        LabelRow("S", "v1", "Hero", 500.0, "CORE_CHASE", "bob", 3, ""),
        LabelRow("S", "v2", "Mid", 30.0, "EXTENDED_CHASE", "alice", 2, ""),
        LabelRow("S", "v2", "Mid", 30.0, "NOT_CHASE", "bob", 2, ""),
    ]
    profile = disagreement_profile(rows)["priceBands"]
    assert profile["25-50"]["disputed"] == 1
    assert profile["250-inf"]["disputed"] == 0
