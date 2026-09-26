import json
import math

import pytest

from backend.scripts.ebay_gold_access import OUT
from backend.scripts.run_ebay_e2_10_coverage_failure_forensics import (
    build_per_card_forensics, TOTAL_TARGET_CARDS,
)
from backend.scripts import ebay_d3_matcher_v5 as v5


FORENSICS_PATH = OUT / "ebay_e2_10_coverage_failure_forensics.json"


@pytest.fixture(scope="module")
def forensics():
    return json.loads(FORENSICS_PATH.read_text(encoding="utf-8"))


# 1. diagnostic is non-certifying and read-only over frozen artifacts
def test_forensics_labeled_non_certifying(forensics):
    assert "NON_CERTIFYING" in forensics["label"]


def test_forensics_script_never_writes_predictions_or_labels():
    import inspect
    from backend.scripts import run_ebay_e2_10_coverage_failure_forensics as mod
    source = inspect.getsource(mod)
    assert "PREDICTIONS_OUTPUT_PATH" not in source
    assert "write_text" not in inspect.getsource(mod.build_per_card_forensics).replace(
        "OUTPUT_PATH.write_text", ""
    )


# 2. exactly 70 cards enumerated, fixed denominator
def test_all_70_cards_enumerated(forensics):
    assert TOTAL_TARGET_CARDS == 70
    assert len(forensics["per_card"]) == 70


# 3. covered/uncovered counts match certification's real result
def test_covered_count_matches_certification():
    cert = json.loads((OUT / "ebay_combined_identity_v2_fresh_blind_certification.json").read_text(encoding="utf-8"))
    forensics_doc = json.loads(FORENSICS_PATH.read_text(encoding="utf-8"))
    assert forensics_doc["covered_count"] == cert["card_coverage_detail"]["covered_count"] == 54
    assert forensics_doc["uncovered_count"] == 16


# 4. the one capture-unrepresented card is present and unrepresented
def test_capture_unrepresented_card_flagged(forensics):
    unrepresented = [c for c in forensics["per_card"] if not c["represented"]]
    assert len(unrepresented) == 1
    assert unrepresented[0]["canonical_card_id"] == "640cd931-d97f-4173-ad9d-3ab86f91d92c"
    assert unrepresented[0]["covered"] is False


# 5. represented-but-uncovered cards are distinct from the unrepresented one
def test_represented_but_uncovered_distinct_from_unrepresented(forensics):
    uncovered = [c for c in forensics["per_card"] if not c["covered"]]
    represented_uncovered = [c for c in uncovered if c["represented"]]
    assert len(represented_uncovered) == 15
    assert len(uncovered) == 16


# 6. covered implies at least one Tier A or Tier B true accept
def test_covered_requires_true_accept(forensics):
    for c in forensics["per_card"]:
        if c["covered"]:
            assert c["tier_a_true"] + c["tier_b_true"] > 0
        else:
            assert c["tier_a_true"] + c["tier_b_true"] == 0


# 7. zero-YES cards (category B) are correctly identified and uncovered
def test_zero_yes_cards_are_category_b_and_uncovered(forensics):
    zero_yes_represented = [c for c in forensics["per_card"] if c["represented"] and c["yes"] == 0]
    assert len(zero_yes_represented) == 5
    for c in zero_yes_represented:
        assert c["covered"] is False


# 8. BASE_PARALLEL_NOT_EXPLICIT is reproducible: real, deterministic reason code
def test_base_parallel_not_explicit_reason_is_real_and_deterministic():
    target = {"card_name": "Coalossal", "set_name": "Temporal Forces", "card_number": "95",
              "treatment": "uncommon", "canonical_card_id": "x"}
    listing = {"title": "Coalossal 095/162 Uncommon Temporal Forces Pokemon Near Mint",
               "condition": "Ungraded", "conditionId": "4000", "category": "", "aspects": "[]",
               "buying_options": "[]", "itemId": "1"}
    result = v5.classify_listing(target, listing)
    assert result["identity_state"] == "MEDIUM_CONFIDENCE"
    assert result["reason"] == "BASE_PARALLEL_NOT_EXPLICIT"
    # deterministic: same inputs, same output
    result2 = v5.classify_listing(target, listing)
    assert result2 == result


# 9. explicit conflicting foil term on an otherwise BASE_PARALLEL target is a
#    real, present safety hazard for any naive "promote on UNRESOLVED" fix --
#    this listing's variant is UNRESOLVED under current D3-v5, not CONFLICT,
#    even though "Reverse Holofoil" is an explicit, real treatment claim.
def test_foil_keyword_row_is_not_currently_flagged_as_conflict():
    target = {"card_name": "Lt. Surge's Bargain", "set_name": "Mega Evolution", "card_number": "120",
              "treatment": "uncommon", "canonical_card_id": "x"}
    listing = {"title": "Lt. Surge's Bargain 120/132 Mega Evolution Reverse Holofoil Pokemon (MP-NM)",
               "condition": "Ungraded", "conditionId": "4000", "category": "", "aspects": "[]",
               "buying_options": "[]", "itemId": "1"}
    result = v5.classify_listing(target, listing)
    assert result["evidence"]["variant"]["state"] == "UNRESOLVED"
    assert result["reason"] == "BASE_PARALLEL_NOT_EXPLICIT"


# 10. minimum recovery sizing: Wilson lower >= 0.98 at zero false accepts
def test_minimum_accepted_count_for_wilson_gate():
    def wilson_lower(n):
        z = 1.959963984540054
        p = 1.0
        d = 1 + z * z / n
        c = (p + z * z / (2 * n)) / d
        m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
        return c - m

    assert wilson_lower(185) < 0.98
    assert wilson_lower(188) < 0.98
    assert wilson_lower(189) >= 0.98


# 11. coverage sizing: +2 cards needed, never relaxed
def test_coverage_sizing_requires_at_least_56():
    current_covered = 54
    required = 56
    assert required - current_covered == 2
    assert (55 / 70) < 0.80
    assert (56 / 70) >= 0.80


# 12. diagnostic script performs no certification, no policy mutation
def test_forensics_script_imports_no_policy_mutation_surface():
    import pathlib
    import backend.scripts.run_ebay_e2_10_coverage_failure_forensics as mod
    source = pathlib.Path(mod.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("combine(", "freeze_"):
        assert forbidden not in source


# 13. frozen authorities remain untouched by this task
def test_frozen_authorities_still_match_after_forensics():
    from backend.scripts import ebay_image_retrieval_verifier as image_v2
    from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
    frozen = json.loads((OUT / "ebay_combined_identity_v2_freeze_manifest.json").read_text(encoding="utf-8"))
    assert v5.rule_fingerprint() == frozen["text_matcher_fingerprint"]
    assert image_v2.source_sha256() == frozen["image_verifier_fingerprint"]
    assert policy_v2.policy_source_hash() == frozen["policy_source_sha256"]


# 14. no production pricing / Fair Value / Explorer surface touched
def test_no_pricing_fair_value_explorer_surface():
    import pathlib
    import backend.scripts.run_ebay_e2_10_coverage_failure_forensics as mod
    source = pathlib.Path(mod.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("fair_value_publish", "publish_price", "market_explorer", "set_value_write"):
        assert forbidden not in source
