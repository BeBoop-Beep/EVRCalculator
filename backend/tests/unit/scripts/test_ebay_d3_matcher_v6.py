import json

import pytest

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts import ebay_d3_matcher_v6 as v6
from backend.scripts.ebay_gold_access import OUT


def target(treatment="uncommon", **overrides):
    t = {"card_name": "Lt. Surge's Bargain", "set_name": "Mega Evolution", "card_number": "120",
         "treatment": treatment, "canonical_card_id": "x"}
    t.update(overrides)
    return t


def listing(title, **overrides):
    l = {"title": title, "condition": "Ungraded", "conditionId": "4000", "category": "",
         "aspects": "[]", "buying_options": "[]", "itemId": "1"}
    l.update(overrides)
    return l


# 1. BASE_PARALLEL_NOT_EXPLICIT safe case (no evidence at all) stays capped,
#    NOT promoted -- v6 never promotes, only ever downgrades.
def test_base_parallel_blank_title_not_promoted():
    result = v6.classify_listing(target(), listing("Lt. Surge's Bargain 120/132 Uncommon Mega Evolution Pokemon Near Mint"))
    assert result["identity_state"] == "MEDIUM_CONFIDENCE"
    assert result["reason"] == "BASE_PARALLEL_NOT_EXPLICIT"


# 2. explicit "Reverse Holo" contradiction (already caught correctly by v5
#    itself -- v6 must not disturb that)
def test_explicit_reverse_holo_still_rejected_by_v5_path():
    result = v6.classify_listing(target(), listing("Lt. Surge's Bargain 120/132 Uncommon Mega Evolution Reverse Holo NM"))
    assert result["identity_state"] == "REJECTED"


# 3. explicit "Reverse Holofoil" contradiction -- the actual bug fixed here
def _arbok_target(**overrides):
    return target(treatment="common", card_name="Arbok", set_name="Temporal Forces", card_number="101", **overrides)


def test_explicit_reverse_holofoil_now_rejected():
    arbok_listing = listing("Arbok 101/162 Temporal Forces Pokemon TCG Common Reverse Holofoil NM")
    v5_result = v5.classify_listing(_arbok_target(), arbok_listing)
    assert v5_result["identity_state"] == "MEDIUM_CONFIDENCE"  # confirms the v5 gap exists
    v6_result = v6.classify_listing(_arbok_target(), arbok_listing)
    assert v6_result["identity_state"] == "REJECTED"
    assert v6_result["reason"] == v6.D3_V6_REJECTION_REASON


# 4. RH abbreviation -- NOT recognized (unambiguous-only scope); confirms
#    v6 deliberately does not attempt to expand to ambiguous abbreviations
def test_rh_abbreviation_not_treated_as_explicit():
    result = v6.classify_listing(_arbok_target(), listing("Arbok 101/162 Temporal Forces RH NM"))
    assert result["identity_state"] == "MEDIUM_CONFIDENCE"
    assert result["reason"] == "BASE_PARALLEL_NOT_EXPLICIT"


# 5. generic "Holo" legitimate case remains non-rejected (not promoted, but
#    critically not newly rejected either)
def test_generic_holo_legitimate_case_not_rejected():
    dhelmise_target = target(treatment="common", card_name="Dhelmise", set_name="Mega Evolution", card_number="18")
    result = v6.classify_listing(dhelmise_target, listing("Dhelmise  - Mega Evolutions - 18/132 - Holo"))
    assert result["identity_state"] != "REJECTED"
    assert result["identity_state"] == "MEDIUM_CONFIDENCE"


# 6. set-conditioned holo semantics: "Holo Rare" on a legacy-rarity target
#    also remains non-rejected
def test_holo_rare_legacy_rarity_language_not_rejected():
    result = v6.classify_listing(target(treatment="rare", card_name="Victini", set_name="Black Bolt", card_number="171"),
                                  listing("Red Victini 171/086 BWR Holo Rare Pokemon Black Bolt. 171 NM"))
    assert result["identity_state"] != "REJECTED"


# 7. target-treatment-conditioned semantics: the same "Reverse Holofoil"
#    phrase only triggers the v6 guard when v5 already capped via
#    BASE_PARALLEL_NOT_EXPLICIT (i.e. only for base-treatment targets)
def test_supplemental_guard_is_conditioned_on_v5_reason_not_bare_keyword():
    non_base_target = target(treatment="special_illustration_rare")
    result = v6.classify_listing(non_base_target, listing("Some SIR Card 1/100 Reverse Holofoil"))
    # whatever v5 says stands unchanged -- v6 only intervenes on the exact
    # MEDIUM_CONFIDENCE + BASE_PARALLEL_NOT_EXPLICIT combination
    v5_result = v5.classify_listing(non_base_target, listing("Some SIR Card 1/100 Reverse Holofoil"))
    assert result["identity_state"] == v5_result["identity_state"]


# 8. ambiguous treatment remains capped (neither promoted nor rejected)
def test_ambiguous_treatment_language_remains_capped():
    result = v6.classify_listing(target(treatment="common"), listing("Coalossal 095/162 Common Temporal Forces Foil-Like Finish NM"))
    assert result["identity_state"] != "HIGH_CONFIDENCE"


# 9. a different V5 reason code (not BASE_PARALLEL_NOT_EXPLICIT) is untouched
def test_other_v5_reason_code_untouched():
    result_v5 = v5.classify_listing(target(card_number="999"), listing("Lt. Surge's Bargain 1/132 Uncommon Mega Evolution"))
    result_v6 = v6.classify_listing(target(card_number="999"), listing("Lt. Surge's Bargain 1/132 Uncommon Mega Evolution"))
    assert result_v6["identity_state"] == result_v5["identity_state"]
    assert result_v6.get("reason") == result_v5.get("reason")


# 10-15. critical invariant: unrelated contradiction classes are unaffected
@pytest.mark.parametrize("bad_listing_kwargs,expected_v5_state", [
    ({"title": "Lt. Surge's Bargain 999/132 Uncommon Mega Evolution"}, None),  # wrong number
])
def test_wrong_number_unaffected(bad_listing_kwargs, expected_v5_state):
    v5_result = v5.classify_listing(target(), listing(**bad_listing_kwargs))
    v6_result = v6.classify_listing(target(), listing(**bad_listing_kwargs))
    assert v6_result["identity_state"] == v5_result["identity_state"]


def test_wrong_set_unaffected():
    l = listing("Lt. Surge's Bargain 120/132 Uncommon Obsidian Flames")
    assert v6.classify_listing(target(), l)["identity_state"] == v5.classify_listing(target(), l)["identity_state"]


def test_graded_unaffected():
    l = listing("Lt. Surge's Bargain 120/132 Uncommon Mega Evolution PSA 10")
    assert v6.classify_listing(target(), l)["identity_state"] == v5.classify_listing(target(), l)["identity_state"]


def test_lot_unaffected():
    l = listing("Lot of 10 Mega Evolution cards including Lt. Surge's Bargain 120/132")
    assert v6.classify_listing(target(), l)["identity_state"] == v5.classify_listing(target(), l)["identity_state"]


def test_sealed_unaffected():
    l = listing("Mega Evolution Booster Box Sealed")
    assert v6.classify_listing(target(), l)["identity_state"] == v5.classify_listing(target(), l)["identity_state"]


def test_autograph_altered_unaffected():
    l = listing("Lt. Surge's Bargain 120/132 Uncommon Mega Evolution Signed Autograph")
    assert v6.classify_listing(target(), l)["identity_state"] == v5.classify_listing(target(), l)["identity_state"]


# 16. E9B-0165 regression -- the actual real-world consumed-fresh-blind
#     hard negative -- MUST NOT become HIGH_CONFIDENCE-eligible.
def test_e9b_0165_regression():
    result = v6.classify_listing(
        target(treatment="uncommon"),
        listing("Lt. Surge's Bargain 120/132 Mega Evolution Reverse Holofoil Pokemon (MP-NM)"),
    )
    assert result["identity_state"] != "HIGH_CONFIDENCE"
    assert result["identity_state"] == "REJECTED"


# 17. V4/V5 hard negatives (real rows, from the development corpus)
@pytest.mark.parametrize("card_name,set_name,number,treatment,title", [
    ("Arbok", "Temporal Forces", "101", "common", "Arbok 101/162 Temporal Forces Pokemon TCG Common Reverse Holofoil NM"),
    ("Lt. Surge's Bargain", "Mega Evolution", "120", "uncommon", "Lt. Surge's Bargain [MEG - 120/132] Uncommon Reverse Holofoil NM Mega Evolution"),
    ("Arbok", "Temporal Forces", "101", "common", "Pokemon Arbok 101/162 Temporal Forces Reverse Holofoil"),
])
def test_v4_v5_hard_negatives_rejected(card_name, set_name, number, treatment, title):
    t = target(treatment=treatment, card_name=card_name, set_name=set_name, card_number=number)
    result = v6.classify_listing(t, listing(title))
    assert result["identity_state"] == "REJECTED"


# 18. no image dependency inside the text matcher
def test_no_image_dependency():
    import inspect
    source = inspect.getsource(v6)
    for forbidden in ("image_retrieval_verifier", "resolve_image_state", "IMAGE-v2", "verify_by_retrieval"):
        assert forbidden not in source


# 19. D3-v5 remains immutable
def test_d3_v5_immutable():
    import subprocess
    from pathlib import Path
    diff = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "backend/scripts/ebay_d3_matcher_v5.py"],
        cwd=Path(v5.__file__).resolve().parents[2],
    )
    assert diff.returncode == 0


# 20. deterministic fingerprint
def test_deterministic_fingerprint():
    assert v6.rule_fingerprint() == v6.rule_fingerprint()
    material_changes_with_v5 = v6.rule_fingerprint()
    assert isinstance(material_changes_with_v5, str) and len(material_changes_with_v5) == 64


# 21. post-freeze no mutation -- v6 was NOT frozen this task (Phase J gate
#     failed); no freeze manifest should exist.
def test_v6_not_frozen_this_task():
    assert not (OUT / "ebay_d3_v6_freeze_manifest.json").exists()


# 22. consumed cohort marked post-hoc only in the prospective diagnostic
def test_prospective_diagnostic_labeled_non_certifying():
    doc = json.loads((OUT / "ebay_combined_identity_v3_prospective_diagnostic.json").read_text(encoding="utf-8"))
    assert "NON_CERTIFYING" in doc["label"]
    assert "NOT a certification" in doc["note"]


# 23. no production writes
def test_no_production_writes_in_v6_module():
    import pathlib
    source = pathlib.Path(v6.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("fair_value_publish", "publish_price", "market_explorer", "set_value_write"):
        assert forbidden not in source


# 24. development metrics: real, measured, zero new false accepts, zero new
#     high-confidence rows (recall gain), confirming the safe-but-insufficient
#     conclusion with real data, not an estimate.
def test_real_development_metrics_zero_new_false_accepts_and_zero_recall_gain():
    doc = json.loads((OUT / "ebay_d3_v6_development_metrics.json").read_text(encoding="utf-8"))
    assert doc["summary"]["new_high_confidence_false_positives"] == 0
    assert doc["summary"]["new_high_confidence_true_positives"] == 0
    assert doc["summary"]["new_rejected_incorrect_yes_rows"] == 0
    assert doc["summary"]["new_rejected_correct_no_rows"] == 4


def test_prospective_diagnostic_e2_9b_matches_original_certification_exactly():
    diag = json.loads((OUT / "ebay_combined_identity_v3_prospective_diagnostic.json").read_text(encoding="utf-8"))
    cert = json.loads((OUT / "ebay_combined_identity_v2_fresh_blind_certification.json").read_text(encoding="utf-8"))
    e29b = diag["results"]["E2.9B"]
    assert e29b["accepted_count"] == cert["metrics"]["accepted_rows"] == 185
    assert e29b["distinct_cards_covered"] == cert["card_coverage_detail"]["covered_count"] == 54
    assert e29b["accepted_precision_wilson_95"][0] == pytest.approx(cert["metrics"]["accepted_precision_wilson_95"][0])
