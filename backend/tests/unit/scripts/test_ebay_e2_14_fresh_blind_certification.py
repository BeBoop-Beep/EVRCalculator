import json
import math

import pytest

from backend.scripts.ebay_gold_access import OUT
from backend.scripts.run_ebay_e2_14_fresh_blind_certification import (
    wilson, ratio, run_precondition_checks, DESIGN_GATE, TOTAL_TARGET_CARDS,
    E2_13_MANIFEST_PATH, COMBINED_V2_FREEZE_PATH, ALLOCATION_V2_FREEZE_PATH,
)


# 1. cohort fingerprint mismatch blocks
def test_cohort_fingerprint_mismatch_blocks(monkeypatch):
    import backend.scripts.run_ebay_e2_14_fresh_blind_certification as mod
    real = json.loads(mod.E2_13_MANIFEST_PATH.read_text(encoding="utf-8"))
    tampered = dict(real)
    tampered["cohort_fingerprint"] = "0" * 64
    tmp = OUT / "_test_e214_tampered_manifest1.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "E2_13_MANIFEST_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["cohort_fingerprint_matches"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 2. final-label fingerprint mismatch blocks
def test_final_label_fingerprint_mismatch_blocks(monkeypatch):
    import backend.scripts.run_ebay_e2_14_fresh_blind_certification as mod
    real = json.loads(mod.E2_13_MANIFEST_PATH.read_text(encoding="utf-8"))
    tampered = dict(real)
    tampered["final_label_fingerprint"] = "0" * 64
    tmp = OUT / "_test_e214_tampered_manifest2.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "E2_13_MANIFEST_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["final_label_fingerprint_recomputes"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 3. correction-history mismatch blocks
def test_correction_history_mismatch_blocks(monkeypatch):
    import backend.scripts.run_ebay_e2_14_fresh_blind_certification as mod
    real = json.loads(mod.E2_13_MANIFEST_PATH.read_text(encoding="utf-8"))
    tampered = json.loads(json.dumps(real))
    tampered["correction_audit"]["correction_history_fingerprint"] = "0" * 64
    tmp = OUT / "_test_e214_tampered_manifest3.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "E2_13_MANIFEST_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["correction_history_fingerprint_matches"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 4. D3-v5 mismatch blocks
def test_d3_v5_mismatch_blocks(monkeypatch):
    import backend.scripts.run_ebay_e2_14_fresh_blind_certification as mod
    real = json.loads(mod.COMBINED_V2_FREEZE_PATH.read_text(encoding="utf-8"))
    tampered = dict(real)
    tampered["text_matcher_fingerprint"] = "0" * 64
    tmp = OUT / "_test_e214_tampered_freeze1.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "COMBINED_V2_FREEZE_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["d3_v5_fingerprint_matches_frozen"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 5. IMAGE-v2 mismatch blocks
def test_image_v2_mismatch_blocks(monkeypatch):
    import backend.scripts.run_ebay_e2_14_fresh_blind_certification as mod
    real = json.loads(mod.COMBINED_V2_FREEZE_PATH.read_text(encoding="utf-8"))
    tampered = dict(real)
    tampered["image_verifier_fingerprint"] = "0" * 64
    tmp = OUT / "_test_e214_tampered_freeze2.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "COMBINED_V2_FREEZE_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["image_v2_fingerprint_matches_frozen"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 6. COMBINED-v2 mismatch blocks
def test_combined_v2_mismatch_blocks(monkeypatch):
    import backend.scripts.run_ebay_e2_14_fresh_blind_certification as mod
    real = json.loads(mod.COMBINED_V2_FREEZE_PATH.read_text(encoding="utf-8"))
    tampered = dict(real)
    tampered["policy_source_sha256"] = "0" * 64
    tmp = OUT / "_test_e214_tampered_freeze3.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "COMBINED_V2_FREEZE_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["combined_v2_fingerprint_matches_frozen"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 7. allocation-v2 mismatch blocks
def test_allocation_v2_mismatch_blocks(monkeypatch):
    import backend.scripts.run_ebay_e2_14_fresh_blind_certification as mod
    real = json.loads(mod.ALLOCATION_V2_FREEZE_PATH.read_text(encoding="utf-8"))
    tampered = dict(real)
    tampered["allocation_fingerprint"] = "0" * 64
    tmp = OUT / "_test_e214_tampered_alloc.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "ALLOCATION_V2_FREEZE_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["allocation_v2_fingerprint_matches_frozen"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 8. canonical-resolution mismatch blocks
def test_canonical_resolution_mismatch_blocks(monkeypatch):
    import backend.scripts.run_ebay_e2_14_fresh_blind_certification as mod
    real = json.loads(mod.E2_13_MANIFEST_PATH.read_text(encoding="utf-8"))
    tampered = dict(real)
    tampered["canonical_resolution_manifest_fingerprint"] = "0" * 64
    tmp = OUT / "_test_e214_tampered_manifest4.json"
    tmp.write_text(json.dumps(tampered), encoding="utf-8")
    monkeypatch.setattr(mod, "E2_13_MANIFEST_PATH", tmp)
    try:
        checks = mod.run_precondition_checks()
        assert checks["canonical_resolution_fingerprint_matches"] is False
    finally:
        tmp.unlink(missing_ok=True)


# 9. Phase 1 cannot consume human truth
def test_phase1_scoring_never_reads_human_label():
    import inspect
    from backend.scripts import run_ebay_e2_14_fresh_blind_scoring as scoring_mod
    source = inspect.getsource(scoring_mod.main)
    assert 'pop("exact_match_yes_no_uncertain"' in source


# 10. prediction artifact fingerprinted before evaluation
def test_predictions_fingerprint_verified_before_evaluation():
    doc = json.loads((OUT / "ebay_e2_14_fresh_blind_predictions.json").read_text(encoding="utf-8"))
    import hashlib
    recomputed = hashlib.sha256(json.dumps(doc["predictions"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert recomputed == doc["predictions_fingerprint"]


# 11. UNCERTAIN excluded from definitive precision
def test_uncertain_excluded_from_definitive_metrics():
    cert = json.loads((OUT / "ebay_e2_14_fresh_blind_certification.json").read_text(encoding="utf-8"))
    assert cert["uncertain"]["uncertain_count"] == 2
    assert cert["metrics"]["definitive_row_count"] == 551  # 553 - 2 UNCERTAIN
    assert cert["uncertain"]["uncertain_accepted"] + cert["uncertain"]["uncertain_rejected"] == 2


# 12. Tier A accounting
def test_tier_a_accounting_real():
    cert = json.loads((OUT / "ebay_e2_14_fresh_blind_certification.json").read_text(encoding="utf-8"))
    ta = cert["tier_a"]
    assert ta["accepted_count"] == ta["true_accepts"] + ta["false_accepts"]
    assert ta["false_accepts"] == 0
    assert ta["precision"] == 1.0


# 13. Tier B accounting
def test_tier_b_accounting_real():
    cert = json.loads((OUT / "ebay_e2_14_fresh_blind_certification.json").read_text(encoding="utf-8"))
    tb = cert["tier_b"]
    assert tb["accepted_count"] == tb["true_accepts"] + tb["false_accepts"]
    assert tb["false_accepts"] == 1  # the real WRONG_LANGUAGE catastrophic case


# 14. false accept accounting
def test_false_accept_row_recorded_with_full_forensics():
    cert = json.loads((OUT / "ebay_e2_14_fresh_blind_certification.json").read_text(encoding="utf-8"))
    rows = cert["false_accept_rows"]
    assert len(rows) == 1
    row = rows[0]
    assert row["row_id"] == "E13-0127"
    assert row["human_no_derived_reason"] == "WRONG_LANGUAGE"
    assert row["combined_v2_tier"] == "TIER_B"
    assert row["image_v2_state"] == "UNVERIFIED"


# 15. card de-duplication
def test_card_dedup_never_exceeds_accepted_rows():
    cert = json.loads((OUT / "ebay_e2_14_fresh_blind_certification.json").read_text(encoding="utf-8"))
    assert cert["tier_a"]["distinct_cards_covered"] <= cert["tier_a"]["true_accepts"]
    assert cert["tier_b"]["distinct_cards_covered"] <= cert["tier_b"]["true_accepts"]


# 16. coverage denominator = 70
def test_coverage_denominator_is_70():
    assert TOTAL_TARGET_CARDS == 70
    cert = json.loads((OUT / "ebay_e2_14_fresh_blind_certification.json").read_text(encoding="utf-8"))
    assert cert["card_coverage_detail"]["denominator"] == 70
    assert cert["metrics"]["distinct_card_coverage"] == cert["card_coverage_detail"]["covered_count"] / 70


# 17. 56/70 passes
def test_56_of_70_passes_coverage_gate():
    assert (56 / 70) >= DESIGN_GATE["card_coverage_minimum"]


# 18. 55/70 fails
def test_55_of_70_fails_coverage_gate():
    assert not ((55 / 70) >= DESIGN_GATE["card_coverage_minimum"])


# 19. Wilson calculation
def test_wilson_calculation_known_values():
    lower, upper = wilson(258, 259)
    assert lower == pytest.approx(0.97846, abs=1e-4)
    lo0, hi0 = wilson(0, 0)
    assert lo0 == 0.0 and hi0 == 0.0


# 20. catastrophic gate
def test_catastrophic_gate_real_result_fails():
    cert = json.loads((OUT / "ebay_e2_14_fresh_blind_certification.json").read_text(encoding="utf-8"))
    assert cert["gates"]["catastrophic_false_accepts_eq_0"] is False
    assert len(cert["false_accept_rows"]) == 1


# 21. frozen predictions cannot be mutated during evaluation
def test_certification_script_never_writes_predictions_file():
    import inspect
    from backend.scripts import run_ebay_e2_14_fresh_blind_certification as cert_mod
    source = inspect.getsource(cert_mod)
    assert "PREDICTIONS_PATH.write_text" not in source


# 22. no production pricing writes
def test_no_pricing_writes_in_certification_module():
    import pathlib
    from backend.scripts import run_ebay_e2_14_fresh_blind_certification as cert_mod
    source = pathlib.Path(cert_mod.__file__).read_text(encoding="utf-8").lower()
    for forbidden in ("fair_value_publish", "publish_price", "set_value_write"):
        assert forbidden not in source


# 23. no Fair Value activation
def test_certification_output_declares_production_authority_false():
    cert = json.loads((OUT / "ebay_e2_14_fresh_blind_certification.json").read_text(encoding="utf-8"))
    assert cert["production_authority"] is False


# 24. no Explorer writes
def test_no_explorer_imports_in_certification_scripts():
    import pathlib
    for mod_name in ("run_ebay_e2_14_fresh_blind_scoring", "run_ebay_e2_14_fresh_blind_certification"):
        mod = __import__(f"backend.scripts.{mod_name}", fromlist=["x"])
        source = pathlib.Path(mod.__file__).read_text(encoding="utf-8").lower()
        assert "market_explorer" not in source and "explorer" not in source


# 25. frozen authorities unchanged
def test_frozen_authorities_unchanged_for_real():
    from backend.scripts import ebay_d3_matcher_v5 as v5
    from backend.scripts import ebay_image_retrieval_verifier as image_v2
    from backend.scripts import ebay_combined_identity_policy_v2 as policy_v2
    frozen = json.loads(COMBINED_V2_FREEZE_PATH.read_text(encoding="utf-8"))
    assert v5.rule_fingerprint() == frozen["text_matcher_fingerprint"]
    assert image_v2.source_sha256() == frozen["image_verifier_fingerprint"]
    assert policy_v2.policy_source_hash() == frozen["policy_source_sha256"]


def test_all_real_preconditions_passed():
    checks = run_precondition_checks()
    failed = [k for k, v in checks.items() if not v]
    assert failed == [], f"unexpected failed preconditions: {failed}"
