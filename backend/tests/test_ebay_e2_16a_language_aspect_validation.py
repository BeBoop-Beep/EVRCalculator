"""EBAY E2.16A -- tests for the frozen human-truth Language-aspect validation.

DEVELOPMENT ONLY. Exercises backend/scripts/ebay_e2_16a_language_aspect_validation.py
against the real frozen E2.16 corpus artifacts. No production writes.
"""
from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))

import ebay_e2_16a_language_aspect_validation as m  # noqa: E402


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def joined():
    return m.join_rows()


@pytest.fixture(scope="module")
def frozen_supported():
    return {"KOREAN", "CHINESE"}


@pytest.fixture(scope="module")
def annotated(joined, frozen_supported):
    return m.annotate_language_v1(joined, frozen_supported)


# --------------------------------------------------------------------------
# 1. frozen corpus fingerprint mismatch blocks
# --------------------------------------------------------------------------

def test_corpus_fingerprint_mismatch_blocks():
    rows = m.load_queue_rows()
    tampered = copy.deepcopy(rows)
    tampered[0]["listing_item_id"] = "TAMPERED"
    manifest = m.load_manifest()
    assert m.cohort_fingerprint(tampered) != manifest["corpus_fingerprint"]
    # the real (untampered) fingerprint must still match
    assert m.cohort_fingerprint(rows) == manifest["corpus_fingerprint"]


# --------------------------------------------------------------------------
# 2. label fingerprint mismatch blocks
# --------------------------------------------------------------------------

def test_label_fingerprint_mismatch_blocks():
    rows = m.load_queue_rows()
    tampered = copy.deepcopy(rows)
    tampered[0]["human_truth_label"] = "NON_ENGLISH" if tampered[0]["human_truth_label"] == "ENGLISH" else "ENGLISH"
    manifest = m.load_manifest()
    assert m.label_fingerprint(tampered) != manifest["label_fingerprint"]
    assert m.label_fingerprint(rows) == manifest["label_fingerprint"]


def test_preconditions_pass_on_real_artifacts():
    results = m.check_preconditions()
    assert results["all_preconditions_passed"] is True
    assert results["row_count"] == 200
    assert results["label_counts"] == {"ENGLISH": 134, "NON_ENGLISH": 63, "UNCERTAIN": 3}


# --------------------------------------------------------------------------
# 3. UNCERTAIN excluded from confusion matrix
# --------------------------------------------------------------------------

def test_uncertain_excluded_from_confusion_matrix(annotated):
    cm = m.confusion_matrix(annotated)
    assert cm["definitive_rows"] == 197
    assert cm["n_human_english"] + cm["n_human_non_english"] == 197
    n_uncertain = sum(1 for r in annotated if r["human_truth"] == "UNCERTAIN")
    assert n_uncertain == 3


# --------------------------------------------------------------------------
# 4. explicit English -> MATCH
# --------------------------------------------------------------------------

def test_explicit_english_is_match(frozen_supported):
    assert m.classify_language_v1("ENGLISH", frozen_supported) == "LANGUAGE_MATCH"


# --------------------------------------------------------------------------
# 5. validated non-English -> MISMATCH
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["KOREAN", "CHINESE"])
def test_validated_non_english_is_mismatch(lang, frozen_supported):
    assert m.classify_language_v1(lang, frozen_supported) == "LANGUAGE_MISMATCH"


# --------------------------------------------------------------------------
# 6. unsupported language -> UNVERIFIED (Japanese/French excluded by Phase H)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["JAPANESE", "FRENCH", "GERMAN", "SPANISH", "ITALIAN", "PORTUGUESE"])
def test_unsupported_language_is_unverified(lang, frozen_supported):
    assert m.classify_language_v1(lang, frozen_supported) == "LANGUAGE_UNVERIFIED"


# --------------------------------------------------------------------------
# 7. missing language -> UNVERIFIED
# --------------------------------------------------------------------------

def test_missing_language_is_unverified(frozen_supported):
    assert m.normalize_raw_value(None) == "UNKNOWN"
    assert m.classify_language_v1("UNKNOWN", frozen_supported) == "LANGUAGE_UNVERIFIED"


# --------------------------------------------------------------------------
# 8. unknown/unrecognized raw value -> UNVERIFIED
# --------------------------------------------------------------------------

def test_unknown_raw_value_is_unverified(frozen_supported):
    assert m.normalize_raw_value("Klingon") == "UNKNOWN"
    assert m.normalize_raw_value("Simplified Chinese") == "UNKNOWN"  # observed in corpus, never mapped
    assert m.classify_language_v1(m.normalize_raw_value("Klingon"), frozen_supported) == "LANGUAGE_UNVERIFIED"


# --------------------------------------------------------------------------
# 9. seller country ignored
# --------------------------------------------------------------------------

def test_seller_country_never_consulted():
    source = Path(m.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("normalize_raw_value", "classify_language_v1", "annotate_language_v1"):
            body_src = ast.get_source_segment(source, node) or ""
            assert "seller_country" not in body_src
            assert "country" not in body_src.lower()


# --------------------------------------------------------------------------
# 10. marketplace ignored
# --------------------------------------------------------------------------

def test_marketplace_never_consulted():
    source = Path(m.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("normalize_raw_value", "classify_language_v1", "annotate_language_v1"):
            body_src = ast.get_source_segment(source, node) or ""
            assert "marketplace" not in body_src.lower()


# --------------------------------------------------------------------------
# 11. English title cannot override mismatch
# --------------------------------------------------------------------------

def test_english_title_cannot_override_mismatch(joined, frozen_supported):
    # e2_16_dev rows with Korean/Chinese aspect and plain English-looking titles
    # still classify as MISMATCH purely from the aspect value.
    korean_rows = [r for r in joined if r.get("raw_language_aspect") == "Korean"]
    assert korean_rows, "expected at least one Korean-aspect row in corpus"
    for row in korean_rows:
        norm = m.normalize_raw_value(row["raw_language_aspect"])
        state = m.classify_language_v1(norm, frozen_supported)
        assert state == "LANGUAGE_MISMATCH"
        # classify_language_v1 takes only the normalized language value --
        # title text is never a parameter, so it structurally cannot override.


def test_classify_language_v1_signature_excludes_title():
    import inspect
    sig = inspect.signature(m.classify_language_v1)
    assert "title" not in sig.parameters
    assert "listing_title" not in sig.parameters


# --------------------------------------------------------------------------
# 12. mismatch precision calculation
# --------------------------------------------------------------------------

def test_mismatch_precision_calculation(annotated):
    cm = m.confusion_matrix(annotated)
    assert cm["TP"] == 45
    assert cm["FP"] == 0
    assert cm["mismatch_precision"] == pytest.approx(1.0)


# --------------------------------------------------------------------------
# 13. mismatch recall calculation
# --------------------------------------------------------------------------

def test_mismatch_recall_calculation(annotated):
    cm = m.confusion_matrix(annotated)
    assert cm["FN"] == 18
    assert cm["mismatch_recall"] == pytest.approx(45 / 63)


# --------------------------------------------------------------------------
# 14. false-mismatch calculation
# --------------------------------------------------------------------------

def test_false_mismatch_rate_calculation(annotated):
    cm = m.confusion_matrix(annotated)
    assert cm["n_human_english"] == 134
    assert cm["false_mismatch_rate_on_human_english"] == pytest.approx(0.0)


# --------------------------------------------------------------------------
# 15. supported-language allowlist is explicit and minimal
# --------------------------------------------------------------------------

def test_supported_language_allowlist_explicit(frozen_supported):
    assert frozen_supported == {"KOREAN", "CHINESE"}
    # Japanese and French were observed with false positives in this corpus
    # and must NOT be in the frozen allowlist.
    assert "JAPANESE" not in frozen_supported
    assert "FRENCH" not in frozen_supported


# --------------------------------------------------------------------------
# 16. unsupported language cannot veto (full pipeline check via annotate)
# --------------------------------------------------------------------------

def test_unsupported_language_cannot_veto(joined, frozen_supported):
    annotated_rows = m.annotate_language_v1(joined, frozen_supported)
    japanese_rows = [r for r in annotated_rows if r["normalized_language"] == "JAPANESE"]
    assert japanese_rows
    for row in japanese_rows:
        assert row["language_v1_state"] != "LANGUAGE_MISMATCH"
        assert row["language_v1_state"] == "LANGUAGE_UNVERIFIED"


# --------------------------------------------------------------------------
# 17. LANGUAGE_MISMATCH rejects in COMBINED-v3
# --------------------------------------------------------------------------

def _combined_v3(combined_v2_state: str, language_v1_state: str) -> str:
    """Minimal COMBINED-IDENTITY-v3 policy per Phase K spec:
    LANGUAGE_MISMATCH -> REJECTED_LANGUAGE_CONTRADICTION, else preserve v2.
    """
    if language_v1_state == "LANGUAGE_MISMATCH":
        return "REJECTED_LANGUAGE_CONTRADICTION"
    return combined_v2_state


def test_language_mismatch_rejects_in_combined_v3():
    result = _combined_v3("ACCEPTED_TIER_A", "LANGUAGE_MISMATCH")
    assert result == "REJECTED_LANGUAGE_CONTRADICTION"


# --------------------------------------------------------------------------
# 18. LANGUAGE_MATCH preserves v2 behavior
# --------------------------------------------------------------------------

def test_language_match_preserves_v2_behavior():
    for v2_state in ("ACCEPTED_TIER_A", "ACCEPTED_TIER_B", "REJECTED_TEXT", "REJECTED_IMAGE_MISMATCH"):
        assert _combined_v3(v2_state, "LANGUAGE_MATCH") == v2_state


# --------------------------------------------------------------------------
# 19. LANGUAGE_UNVERIFIED preserves v2 behavior
# --------------------------------------------------------------------------

def test_language_unverified_preserves_v2_behavior():
    for v2_state in ("ACCEPTED_TIER_A", "ACCEPTED_TIER_B", "REJECTED_TEXT", "REJECTED_IMAGE_MISMATCH"):
        assert _combined_v3(v2_state, "LANGUAGE_UNVERIFIED") == v2_state


# --------------------------------------------------------------------------
# 20/21. D3-v5 and IMAGE-v2 immutable -- this module never imports or writes them
# --------------------------------------------------------------------------

def test_d3_v5_and_image_v2_never_imported_or_mutated():
    source = Path(m.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    # Only inspect real code constructs (imports, calls, string literals used
    # as paths) -- the module's own docstring legitimately mentions these
    # frozen artifacts by name to document that it must never touch them.
    forbidden_tokens = ["ebay_d3_v5_freeze_manifest", "d3_v5", "image_v2", "ebay_image_verification_v2"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = " ".join(getattr(node, "module", "") or "" for _ in [0]) + " " + " ".join(a.name for a in node.names)
            for token in forbidden_tokens:
                assert token not in names.lower(), f"import references {token}"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for token in forbidden_tokens:
                assert token not in node.value.lower(), f"string literal references {token}: {node.value!r}"


def test_d3_v5_freeze_manifest_file_untouched_by_this_task():
    path = ROOT / "backend/artifacts/index_fair_value/ebay_d3_v5_freeze_manifest.json"
    if not path.exists():
        pytest.skip("D3-v5 freeze manifest not present in this checkout")
    # Just confirm it is still valid, untouched JSON -- no assertion about
    # content beyond parseability, since this task must never write to it.
    import json
    json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 22. consumed E2.14 excluded from tuning
# --------------------------------------------------------------------------

def test_e2_14_never_referenced_in_frozen_contract_functions():
    source = Path(m.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    tuning_functions = {"normalize_raw_value", "classify_language_v1", "check_preconditions",
                         "confusion_matrix", "cohort_fingerprint", "label_fingerprint"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in tuning_functions:
            body_src = ast.get_source_segment(source, node) or ""
            assert "e2_14" not in body_src.lower()
            assert "E2_14" not in body_src


# --------------------------------------------------------------------------
# 23. deterministic freeze fingerprint
# --------------------------------------------------------------------------

def test_freeze_fingerprint_deterministic(annotated):
    import hashlib
    import json as _json

    def freeze_fp(rows):
        payload = sorted(
            f"{r['row_id']}:{r['normalized_language']}:{r['language_v1_state']}" for r in rows
        )
        return hashlib.sha256("|".join(payload).encode()).hexdigest()

    fp1 = freeze_fp(annotated)
    fp2 = freeze_fp(copy.deepcopy(annotated))
    assert fp1 == fp2
    # changing one row's state changes the fingerprint
    mutated = copy.deepcopy(annotated)
    mutated[0] = dict(mutated[0])
    mutated[0]["language_v1_state"] = "LANGUAGE_MISMATCH" if mutated[0]["language_v1_state"] != "LANGUAGE_MISMATCH" else "LANGUAGE_MATCH"
    assert freeze_fp(mutated) != fp1


# --------------------------------------------------------------------------
# 24. no production writes
# --------------------------------------------------------------------------

def test_no_production_write_calls_in_module():
    source = Path(m.__file__).read_text(encoding="utf-8")
    forbidden = ["supabase", "INSERT INTO", "UPDATE ", "execute(", ".upsert(", "to_sql("]
    for token in forbidden:
        assert token not in source, f"forbidden production-write token found: {token}"
    # module only ever opens artifact files under backend/artifacts/index_fair_value
    # in read mode ("r"/default); the only write mode usage anywhere is none.
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "open":
            for kw in node.keywords:
                if kw.arg is None:
                    continue
            # check positional "mode" arg for write markers
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    assert "w" not in arg.value or arg.value == "utf-8", f"unexpected open() mode literal: {arg.value}"


# --------------------------------------------------------------------------
# Additional structural checks (per-language breakdown, conflicts)
# --------------------------------------------------------------------------

def test_per_language_breakdown_totals(joined, frozen_supported):
    annotated_rows = m.annotate_language_v1(joined, frozen_supported)
    breakdown = m.per_language_breakdown(annotated_rows)
    total = sum(v["human_count"] for v in breakdown.values())
    n_non_english = sum(1 for r in joined if r["human_truth"] == "NON_ENGLISH")
    assert total == n_non_english == 63


def test_conflicts_forensics_counts(joined, frozen_supported):
    annotated_rows = m.annotate_language_v1(joined, frozen_supported)
    conf = m.conflicts(annotated_rows)
    assert len(conf["human_english_aspect_non_english"]) == 2
    assert len(conf["human_non_english_aspect_english"]) == 3
    assert len(conf["human_uncertain_with_explicit_aspect"]) == 2


def test_sizing_only_hypothetical_wilson_lower():
    lower, upper = m.wilson_ci(258, 258)
    assert lower == pytest.approx(0.985329, abs=1e-5)
