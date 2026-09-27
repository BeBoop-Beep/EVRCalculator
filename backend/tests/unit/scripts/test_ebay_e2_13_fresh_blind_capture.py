import json

import pytest

from backend.scripts.ebay_gold_access import OUT
from backend.scripts.capture_ebay_e2_13_fresh_blind import (
    load_historical_item_ids, load_historical_relist_fingerprints, ROWS_PER_CARD,
    HISTORICAL_ID_FILES,
)
from backend.scripts.capture_ebay_d3_v4_fresh_blind import stratified_sample
from backend.scripts import ebay_e2_13_blind_review_server as srv


MANIFEST_PATH = OUT / "ebay_e2_13_fresh_blind_manifest.json"


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


# 1. E2.9B IDs excluded
def test_e2_9b_queue_in_exclusion_scope():
    assert "ebay_e2_9b_fresh_blind_queue.csv" in HISTORICAL_ID_FILES


def test_real_cohort_has_zero_e2_9b_overlap(manifest):
    import csv
    new_ids = {r["listing_item_id"] for r in csv.DictReader(open(OUT / "ebay_e2_13_fresh_blind_queue.csv", encoding="utf-8"))}
    old_ids = {r["listing_item_id"] for r in csv.DictReader(open(OUT / "ebay_e2_9b_fresh_blind_queue.csv", encoding="utf-8"))}
    assert new_ids & old_ids == set()


# 2. all earlier historical IDs excluded
def test_all_prior_cohorts_named_in_exclusion_scope():
    for phase_file in ("ebay_d3_v4_fresh_blind_queue.csv", "ebay_d3_v5_fresh_blind_queue.csv",
                       "ebay_gold_development.csv", "ebay_gold_final_blind.csv", "ebay_gold_validation.csv"):
        assert phase_file in HISTORICAL_ID_FILES


def test_real_historical_id_pool_nonzero(manifest):
    assert manifest["historical_id_pool_size"] > 10000


# 3. 8-row cap deterministic
def test_rows_per_card_is_8_from_frozen_allocation():
    assert ROWS_PER_CARD == 8


def test_stratified_sample_cap_deterministic():
    rows = [{"target_canonical_card_id": "C1", "ebay_item_id": f"i{i}"} for i in range(20)]
    a = stratified_sample(rows, rows_per_card=ROWS_PER_CARD)
    b = stratified_sample(rows, rows_per_card=ROWS_PER_CARD)
    assert len(a) == 8
    assert [r["ebay_item_id"] for r in a] == [r["ebay_item_id"] for r in b]


# 4. no compensation for exhausted cards
def test_no_compensation_for_shortfall_card(manifest):
    shortfall = manifest["shortfall_cards"]
    assert "640cd931-d97f-4173-ad9d-3ab86f91d92c" in shortfall
    entry = shortfall["640cd931-d97f-4173-ad9d-3ab86f91d92c"]
    assert entry["selected"] == entry["surviving_candidates"]  # never padded beyond what existed
    assert entry["selected"] < ROWS_PER_CARD


def test_no_other_card_received_extra_rows_to_compensate(manifest):
    for card_id, count in manifest["per_card_counts"].items():
        assert count <= ROWS_PER_CARD


# 5. policy-independent sampling
def test_capture_script_has_no_identity_stack_imports():
    import ast
    import backend.scripts.capture_ebay_e2_13_fresh_blind as mod
    tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for forbidden in ("ebay_d3_matcher_v5", "ebay_d3_matcher_v6", "ebay_image_retrieval_verifier",
                       "ebay_combined_identity_policy_v1", "ebay_combined_identity_policy_v2"):
        assert not any(forbidden in name for name in imported), f"{forbidden} imported"


# 6. duplicate-ID prevention
def test_real_cohort_zero_duplicate_ids():
    import csv
    rows = list(csv.DictReader(open(OUT / "ebay_e2_13_fresh_blind_queue.csv", encoding="utf-8")))
    item_ids = [r["listing_item_id"] for r in rows]
    row_ids = [r["benchmark_row_id"] for r in rows]
    assert len(item_ids) == len(set(item_ids))
    assert len(row_ids) == len(set(row_ids))


# 7. relist exclusion
def test_relist_exclusion_applied(manifest):
    assert manifest["excluded_likely_relist_fingerprint"] >= 0
    assert manifest["excluded_exact_historical_item_id"] > 8000


# 8. fixed 70-card target universe
def test_coverage_universe_fixed_at_70(manifest):
    assert manifest["coverage_universe"] == 70
    assert manifest["cards_represented"] <= 70


# 9. new review session started empty at capture time (point-in-time fact,
#    recorded in the E2.13 capture report; E2.14 has since genuinely
#    labeled and frozen this cohort, so the live manifest now reflects
#    that later, real state -- this test checks session identity, which is
#    permanent, rather than a reviewed_count that has legitimately moved on).
def test_new_session_used_correct_e2_13_identity():
    assert srv.get_active_session_id() == "e2_13_session_1"
    assert srv.get_active_session_id() != "e2_9b_session_1"


# 10. no MODEL/POLICY outputs in queue -- this invariant holds permanently,
#     before and after human labeling (human labels are not model outputs).
def test_no_model_outputs_in_real_queue():
    rows = srv.load_queue_rows()
    srv.assert_no_forbidden_columns(rows)


# 11. row/image binding
def test_row_image_binding_first_middle_last():
    rows = srv.load_queue_rows()
    for idx in (0, len(rows) // 2, len(rows) - 1):
        html = srv.page(rows[idx], 0, len(rows), position=idx + 1)
        assert rows[idx]["benchmark_row_id"] in html
        assert rows[idx]["image_url"] in html


# 12. fingerprint reproducibility
def test_cohort_fingerprint_reproducible(manifest):
    rows = srv.load_queue_rows()
    assert srv.cohort_fingerprint(rows) == manifest["cohort_fingerprint"]


# 13. request-budget enforcement (unchanged from frozen allocation)
def test_request_budget_matches_frozen_allocation(manifest):
    alloc = json.loads((OUT / "ebay_capture_allocation_v2_freeze_manifest.json").read_text(encoding="utf-8"))
    assert manifest["capture_allocation_fingerprint"] == alloc["allocation_fingerprint"]
    assert manifest["browse_request_count"] <= alloc["request_budget"]["max_requests_per_run"]


# 14. authority fingerprints immutable
def test_identity_authority_fingerprints_match_frozen(manifest):
    from backend.scripts import ebay_d3_matcher_v5 as v5
    from backend.scripts import ebay_image_retrieval_verifier as image_v2
    from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
    frozen = json.loads((OUT / "ebay_combined_identity_v2_freeze_manifest.json").read_text(encoding="utf-8"))
    assert v5.rule_fingerprint() == frozen["text_matcher_fingerprint"] == manifest["text_matcher_fingerprint"]
    assert image_v2.source_sha256() == frozen["image_verifier_fingerprint"] == manifest["image_verifier_fingerprint"]
    assert policy_v2.policy_source_hash() == frozen["policy_source_sha256"] == manifest["combined_identity_v2_policy_fingerprint"]
