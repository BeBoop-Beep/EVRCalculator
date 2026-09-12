from backend.scripts.build_ebay_d2f_final_certification import coverage, high_metrics, wilson


def record(card, gold, state):
    return {"canonical_card_id":card, "target_card_name":card, "human_gold_label":gold, "matcher_confidence_state":state}


def test_binary_metrics_exclude_ambiguous_and_calculate_confusion_matrix():
    rows = [record("a","EXACT_TARGET_MATCH","HIGH_CONFIDENCE"), record("a","EXACT_TARGET_MATCH","REJECTED"),
            record("b","GRADED","HIGH_CONFIDENCE"), record("b","WRONG_CARD_NUMBER","REJECTED"),
            record("c","AMBIGUOUS","HIGH_CONFIDENCE")]
    found = high_metrics(rows)
    assert (found["true_positives"], found["false_positives"], found["true_negatives"], found["false_negatives"]) == (1,1,1,1)
    assert found["binary_denominator"] == 4 and found["ambiguous_excluded"] is True


def test_wilson_interval_known_perfect_sample():
    low, high = wilson(298, 298)
    assert low == 0.98727326 and high == 1.0


def test_card_coverage_categories_are_not_faked():
    rows = [record("high","EXACT_TARGET_MATCH","HIGH_CONFIDENCE"),
            record("medium","EXACT_TARGET_MATCH","MEDIUM_CONFIDENCE"),
            record("rejected","EXACT_TARGET_MATCH","REJECTED"),
            record("none","GRADED","REJECTED")]
    found = coverage(rows)
    assert found["covered_card_count"] == 1 and found["observed_benchmark_coverage"] == .25
    assert [x["canonical_card_id"] for x in found["cards_with_only_medium_exact"]] == ["medium"]
    assert [x["canonical_card_id"] for x in found["cards_with_exact_all_rejected_or_ambiguous"]] == ["rejected"]
    assert [x["canonical_card_id"] for x in found["cards_with_no_human_exact"]] == ["none"]
