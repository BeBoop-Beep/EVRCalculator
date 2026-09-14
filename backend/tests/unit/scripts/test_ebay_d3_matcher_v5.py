import pytest

from backend.scripts import ebay_d3_matcher_v4 as v4
from backend.scripts import ebay_d3_matcher_v5 as v5

TARGET = {"card_name": "Kyurem ex", "set_name": "Black Bolt", "card_number": "165", "treatment": "special_illustration_rare"}


def listing(title, condition="Ungraded", condition_id="4000"):
    return {"title": title, "condition": condition, "conditionId": condition_id, "category": "",
            "aspects": "[]", "buying_options": '["FIXED_PRICE"]', "itemId": "v1|1|0"}


# 1. explicit collector-number contradiction (still handled by v4's inherited logic)
def test_explicit_collector_number_contradiction_rejected():
    result = v5.classify_listing(TARGET, listing("Kyurem ex 190/086 Black Bolt Special Illustration Rare"))
    assert result["identity_state"] == "REJECTED"


# 2. valid collector-number agreement
def test_valid_collector_number_agreement_accepted():
    title = "Kyurem ex 165/086 Black Bolt Special Illustration Rare Near Mint"
    result = v5.classify_listing(TARGET, listing(title))
    assert result["identity_state"] == "HIGH_CONFIDENCE"


# 3. price numerics do not become collector numbers (inherited v4 guard)
def test_price_numerics_do_not_become_collector_numbers():
    title = "Kyurem ex Black Bolt Special Illustration Rare Near Mint $165 OBO"
    result = v5.classify_listing(TARGET, listing(title))
    assert result["identity_state"] != "HIGH_CONFIDENCE"


# 4. year numerics -- a 4-digit year adjacent to the target number is not itself evidence
def test_year_numerics_do_not_falsely_confirm():
    title = "2024 Kyurem ex Black Bolt Special Illustration Rare"  # no collector number at all
    result = v5.classify_listing(TARGET, listing(title))
    assert result["identity_state"] != "HIGH_CONFIDENCE"


# 5. quantity numerics do not become collector numbers (inherited v4 guard)
def test_quantity_numerics_do_not_become_collector_numbers():
    title = "Kyurem ex Black Bolt Special Illustration Rare lot of 165 cards"
    result = v5.classify_listing(TARGET, listing(title))
    assert result["identity_state"] != "HIGH_CONFIDENCE"


# 6. grade numerics (PSA) never accepted raw
def test_grade_numerics_rejected():
    result = v5.classify_listing(TARGET, listing("PSA 10 Kyurem ex 165/086 Black Bolt Special Illustration Rare", condition="Graded"))
    assert result["identity_state"] == "REJECTED"


# 7. unusual collector-number formats -- hash format still trusted
def test_hash_format_collector_number_trusted():
    title = "Kyurem ex #165 Black Bolt Special Illustration Rare"
    result = v5.classify_listing(TARGET, listing(title))
    assert result["identity_state"] == "HIGH_CONFIDENCE"


# 8. promo formats -- multi-fraction still caught (inherited v4 guard)
def test_promo_or_multi_card_fraction_rejected():
    title = "Kyurem ex 165/086 and 164/086 Combo Black Bolt Special Illustration Rare"
    result = v5.classify_listing(TARGET, listing(title))
    assert result["identity_state"] == "REJECTED"
    assert result["reason"] == "MULTI_CARD_OFFER_V4_MULTI_FRACTION"


# 9. second failure-class detection: autograph/altered guard (Guard 4, new in v5)
@pytest.mark.parametrize("title", [
    "Kyurem ex 165/086 Black Bolt Special Illustration Rare Auto",
    "Kyurem ex 165/086 Black Bolt Special Illustration Rare Autograph",
    "Kyurem ex 165/086 Black Bolt Special Illustration Rare Signed by Artist",
    "Kyurem ex 165/086 Black Bolt Special Illustration Rare Signature Edition",
])
def test_autograph_or_altered_terms_rejected_by_v5(title):
    v5_result = v5.classify_listing(TARGET, listing(title))
    v4_result = v4.classify_listing(TARGET, listing(title))
    assert v5_result["identity_state"] == "REJECTED"
    assert v5_result["reason"] == "ALTERED_OR_AUTOGRAPHED_V5"
    # this is exactly the class of false accept v4 would have missed
    if v4_result["identity_state"] == "HIGH_CONFIDENCE":
        assert v5_result["identity_state"] != v4_result["identity_state"]


# 10. legitimate controls for second failure class -- no false positives on ordinary titles
@pytest.mark.parametrize("title", [
    "Kyurem ex 165/086 Black Bolt Special Illustration Rare Near Mint",
    "Kyurem ex 165/086 Black Bolt Special Illustration Rare Automatic Ball Machine Pull",  # "auto" not standalone word here would still match \bauto\b though
])
def test_ordinary_titles_not_flagged_as_altered(title):
    check = v5.altered_or_autograph_guard(listing(title))
    if "auto" not in title.lower().split():
        assert check["altered_or_autograph_detected"] is False


def test_word_boundary_prevents_partial_word_false_positive():
    # "automatic" contains "auto" as a substring but is not the standalone word
    check = v5.altered_or_autograph_guard(listing("Kyurem ex 165/086 Black Bolt automatic pack opening promo"))
    assert check["altered_or_autograph_detected"] is False


def test_false_positive_escape_hatch_for_auto_draft_phrasing():
    check = v5.altered_or_autograph_guard(listing("Kyurem ex 165/086 Black Bolt auto draft checklist card"))
    assert check["altered_or_autograph_detected"] is False


# 11. downgrade-only behavior -- v5 never upgrades a v4 rejection
def test_v5_never_upgrades_a_v4_rejection():
    title = "PSA 10 Kyurem ex 165/086 Black Bolt Special Illustration Rare"
    v4_result = v4.classify_listing(TARGET, listing(title, condition="Graded"))
    v5_result = v5.classify_listing(TARGET, listing(title, condition="Graded"))
    assert v4_result["identity_state"] == "REJECTED"
    assert v5_result["identity_state"] == "REJECTED"


def test_v5_downgrades_only_never_upgrades_high_confidence_cases():
    title = "Kyurem ex 165/086 Black Bolt Special Illustration Rare Near Mint"
    v4_result = v4.classify_listing(TARGET, listing(title))
    v5_result = v5.classify_listing(TARGET, listing(title))
    order = {"REJECTED": 0, "AMBIGUOUS": 1, "MEDIUM_CONFIDENCE": 2, "HIGH_CONFIDENCE": 3}
    assert order[v5_result["identity_state"]] <= order[v4_result["identity_state"]]


# 12. no listing-ID special cases -- the guard is pattern-based, not row-specific
def test_no_listing_id_or_title_literal_special_case_in_guard_source():
    """The module DOCSTRING documents the two triggering blind rows for
    provenance (explicitly permitted -- explaining root cause is not the
    same as coding a special case). The actual executable logic below the
    docstring must contain no such literal.
    """
    import inspect

    source = inspect.getsource(v5)
    code_only = source.split('"""', 2)[-1]  # strip the module docstring
    for literal in ("D4-0375", "D4-0415", "162/131", "Roaring Moon", "Nidoking"):
        assert literal not in code_only


# 13. v4 unaffected controls -- v5 wraps v4 without copying/altering its decision tree
def test_v4_decision_tree_unaffected_by_v5_wrapper():
    title = "Kyurem ex 165/086 Black Bolt Special Illustration Rare Near Mint"
    before = v4.classify_listing(TARGET, listing(title))
    v5.classify_listing(TARGET, listing(title))  # exercise v5
    after = v4.classify_listing(TARGET, listing(title))
    assert before["identity_state"] == after["identity_state"] == "HIGH_CONFIDENCE"


# 14. matcher fingerprint is deterministic (freeze-readiness)
def test_v5_fingerprint_deterministic():
    assert v5.rule_fingerprint() == v5.rule_fingerprint()
    assert len(v5.rule_fingerprint()) == 64


# 15. post-freeze mutation detection
def test_v5_fingerprint_changes_if_pattern_changes(monkeypatch):
    import re

    original = v5.rule_fingerprint()
    monkeypatch.setattr(v5, "_ALTERED_OR_AUTOGRAPH_RE", re.compile(r"DIFFERENT_PATTERN"))
    mutated = v5.rule_fingerprint()
    assert original != mutated
