"""D3-v5 fresh-blind certification -- fail-closed, run-exactly-once.

The V5 equivalent of certify_ebay_d3_v4_fresh_blind.py. Reuses the exact
same preregistered gates from ebay_d3_new_blind_benchmark_design.json
(high_precision_minimum=0.99, wilson_95_lower_minimum=0.98,
card_coverage_minimum=0.80, catastrophic_high_false_positives_maximum=0),
the exact same catastrophic-mismatch taxonomy, and the exact same Wilson/
precision/coverage formulas -- no new methodology is invented here.

E2.3B introduced review SESSIONS to ebay_d3_v5_blind_review_server.py after
the original v5_session_1 review session was found to have a UI navigation/
image-rendering defect and was invalidated
(status=INVALIDATED_UI_NAVIGATION_RENDERING_DEFECT,
labels_eligible_for_certification=false). This certifier additionally
refuses to run unless the frozen labels are traceable to a SINGLE valid
(non-invalidated) review session -- it fails closed on v5_session_1, on any
other invalidated session, and on any freeze whose recorded
review_session_id cannot be matched to a valid session record.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts.ebay_gold_access import OUT

QUEUE_PATH = OUT / "ebay_d3_v5_fresh_blind_queue.csv"
BLIND_MANIFEST_PATH = OUT / "ebay_d3_v5_fresh_blind_manifest.json"
FREEZE_MANIFEST_PATH = OUT / "ebay_d3_v5_freeze_manifest.json"
DESIGN_PATH = OUT / "ebay_d3_new_blind_benchmark_design.json"
CERTIFICATION_OUTPUT_PATH = OUT / "ebay_d3_v5_fresh_blind_certification.json"

EXPECTED_ROW_COUNT = 417

FORBIDDEN_LABEL_COLUMNS = frozenset({
    "matcher_version", "matcher_state", "identity_state", "match_status", "confidence",
    "confidence_tier", "score", "accepted", "rejection_reason", "v3_state", "v4_state", "v5_state", "reason",
})
REQUIRED_LABEL_FIELDS = (
    "exact_match_yes_no_uncertain", "single_card_or_lot", "raw_or_graded", "card_or_sealed_nonshcard",
    "reviewer_id", "label_timestamp",
)
DETERMINABLE_WHEN_PRESENT_FIELDS = ("collector_number_consistency", "set_consistency", "language", "variant_treatment")
POSITIVE = "yes"
NEGATIVE = "no"
UNCERTAIN = "uncertain"

SESSION_INVALIDATED_STATUS = "INVALIDATED_UI_NAVIGATION_RENDERING_DEFECT"
CERTIFICATION_BLOCKED_INVALID_SESSION = "EBAY_D3_V5_CERTIFICATION_BLOCKED_INVALID_REVIEW_SESSION"


class CertificationBlocked(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _cohort_fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "\n".join(sorted(f"{r['benchmark_row_id']}:{r['listing_item_id']}" for r in rows)).encode()
    ).hexdigest()


LABEL_FINGERPRINT_FIELDS = REQUIRED_LABEL_FIELDS


def compute_label_fingerprint(rows: list[dict[str, Any]]) -> str:
    """THE single canonical human-label fingerprint for V5 -- mirrors
    certify_ebay_d3_v4_fresh_blind.compute_label_fingerprint() exactly (same
    formula, same field set). Every V5 tool that freezes or verifies labels
    (ebay_d3_v5_blind_review_server.py's freeze() and this certifier's
    check_preconditions()) must call this exact function.
    """
    material = "\n".join(
        sorted(f"{r['benchmark_row_id']}:{f}:{r.get(f, '')}" for r in rows for f in LABEL_FINGERPRINT_FIELDS)
    )
    return hashlib.sha256(material.encode()).hexdigest()


# Backwards-compatible alias -- do not add a second implementation here.
_label_fingerprint = compute_label_fingerprint


def load_queue_rows() -> list[dict[str, Any]]:
    if not QUEUE_PATH.exists():
        raise CertificationBlocked("EBAY_D3_V5_CERTIFICATION_BLOCKED_COHORT_MISSING", str(QUEUE_PATH))
    with QUEUE_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _validate_review_session(blind_manifest: dict[str, Any], checks: dict[str, Any]) -> str | None:
    """Session-safety gate (E2.3B/E2.4): the frozen labels must be traceable
    to exactly one review session, and that session must not be invalidated.
    Returns a blocking_reason string, or None if the session checks pass.
    """
    review_sessions = blind_manifest.get("review_sessions", {}) or {}
    initial_session_id = (blind_manifest.get("initial_human_freeze") or {}).get("review_session_id")
    final_session_id = (blind_manifest.get("final_human_freeze") or {}).get("review_session_id")

    checks["initial_human_freeze_review_session_id"] = initial_session_id
    checks["final_human_freeze_review_session_id"] = final_session_id
    checks["review_sessions"] = review_sessions

    if not final_session_id:
        checks["review_session_declared"] = False
        return "EBAY_D3_V5_CERTIFICATION_BLOCKED_REVIEW_SESSION_UNDECLARED"
    checks["review_session_declared"] = True

    # Mixed-session label provenance: the session the initial freeze
    # materialized from must be the SAME session the final freeze recorded.
    mixed_sessions = bool(initial_session_id) and initial_session_id != final_session_id
    checks["mixed_session_provenance"] = mixed_sessions
    if mixed_sessions:
        return "EBAY_D3_V5_CERTIFICATION_BLOCKED_MIXED_SESSION_PROVENANCE"

    session_record = review_sessions.get(final_session_id, {})
    checks["final_review_session_status"] = session_record.get("status")
    session_invalidated = session_record.get("status") == SESSION_INVALIDATED_STATUS
    checks["final_review_session_invalidated"] = session_invalidated
    if session_invalidated:
        return CERTIFICATION_BLOCKED_INVALID_SESSION

    labels_eligible = session_record.get("labels_eligible_for_certification", True)
    checks["final_review_session_labels_eligible_for_certification"] = labels_eligible
    if labels_eligible is False:
        return CERTIFICATION_BLOCKED_INVALID_SESSION

    matcher_consulted = session_record.get("matcher_predictions_consulted", False)
    checks["final_review_session_matcher_predictions_consulted"] = matcher_consulted
    if matcher_consulted:
        return "EBAY_D3_V5_CERTIFICATION_BLOCKED_MATCHER_PREDICTIONS_PREVIOUSLY_CONSULTED"

    return None


def check_preconditions() -> dict[str, Any]:
    """Returns a report dict; never raises for a normal "not ready" state --
    callers decide what to do with `overall_pass`/`blocking_reason`.
    """
    checks: dict[str, Any] = {}
    blocking_reason = None

    if not QUEUE_PATH.exists() or not BLIND_MANIFEST_PATH.exists():
        return {"overall_pass": False, "blocking_reason": "EBAY_D3_V5_CERTIFICATION_BLOCKED_COHORT_MISSING", "checks": checks}
    if not FREEZE_MANIFEST_PATH.exists():
        return {"overall_pass": False, "blocking_reason": "EBAY_D3_V5_CERTIFICATION_BLOCKED_FREEZE_MANIFEST_MISSING", "checks": checks}

    rows = load_queue_rows()
    blind_manifest = json.loads(BLIND_MANIFEST_PATH.read_text(encoding="utf-8"))
    freeze_manifest = json.loads(FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))

    checks["cohort_row_count"] = len(rows)
    row_count_ok = len(rows) == EXPECTED_ROW_COUNT
    checks["cohort_row_count_matches_expected"] = row_count_ok
    if not row_count_ok:
        blocking_reason = "EBAY_D3_V5_CERTIFICATION_BLOCKED_ROW_COUNT_MISMATCH"

    checks["cohort_fingerprint_recorded"] = blind_manifest.get("cohort_fingerprint")
    checks["cohort_fingerprint_recomputed"] = _cohort_fingerprint(rows)
    cohort_fingerprint_matches = checks["cohort_fingerprint_recorded"] == checks["cohort_fingerprint_recomputed"]
    checks["cohort_fingerprint_matches"] = cohort_fingerprint_matches
    if not cohort_fingerprint_matches and blocking_reason is None:
        blocking_reason = "EBAY_D3_V5_CERTIFICATION_BLOCKED_COHORT_FINGERPRINT_MISMATCH"

    forbidden_present = FORBIDDEN_LABEL_COLUMNS & set(rows[0].keys()) if rows else set()
    checks["forbidden_matcher_columns_present"] = sorted(forbidden_present)
    if forbidden_present and blocking_reason is None:
        blocking_reason = "EBAY_D3_V5_CERTIFICATION_BLOCKED_LABEL_FILE_CONTAINS_MATCHER_OUTPUT"

    labeled_rows = [r for r in rows if str(r.get("exact_match_yes_no_uncertain", "")).strip()]
    checks["labeled_row_count"] = len(labeled_rows)
    checks["total_row_count"] = len(rows)
    labels_complete = len(labeled_rows) == len(rows) and len(rows) > 0
    checks["labels_complete"] = labels_complete
    checks["blind_manifest_labels_exist_flag"] = blind_manifest.get("labels_exist")
    if (not labels_complete or not blind_manifest.get("labels_exist")) and blocking_reason is None:
        blocking_reason = "EBAY_D3_V5_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN"

    # Final (post-correction-audit) human freeze must exist and be closed.
    checks["finally_frozen"] = blind_manifest.get("finally_frozen")
    checks["final_human_freeze_present"] = "final_human_freeze" in blind_manifest
    if not checks["final_human_freeze_present"] or not checks["finally_frozen"]:
        if blocking_reason is None:
            blocking_reason = "EBAY_D3_V5_CERTIFICATION_BLOCKED_FINAL_HUMAN_FREEZE_MISSING"

    current_fingerprint = v5.rule_fingerprint()
    frozen_fingerprint = freeze_manifest.get("matcher_fingerprint")
    checks["frozen_matcher_fingerprint"] = frozen_fingerprint
    checks["current_matcher_fingerprint"] = current_fingerprint
    fingerprint_matches = current_fingerprint == frozen_fingerprint
    checks["matcher_fingerprint_matches"] = fingerprint_matches
    if not fingerprint_matches and blocking_reason is None:
        blocking_reason = "EBAY_D3_V5_CERTIFICATION_BLOCKED_MATCHER_HASH_MISMATCH"

    checks["reviewer_protocol"] = blind_manifest.get("protocol") or blind_manifest.get("reviewer_protocol")
    checks["reviewer_b_exists"] = blind_manifest.get("reviewer_b_exists")
    checks["reviewer_protocol_declared"] = checks["reviewer_protocol"] is not None
    if not checks["reviewer_protocol_declared"] and blocking_reason is None:
        blocking_reason = "EBAY_D3_V5_CERTIFICATION_BLOCKED_REVIEWER_PROTOCOL_UNDECLARED"
    if checks["reviewer_protocol"] not in (None, "SINGLE_REVIEWER_BLIND") and blocking_reason is None:
        blocking_reason = "EBAY_D3_V5_CERTIFICATION_BLOCKED_REVIEWER_PROTOCOL_UNRECOGNIZED"

    # E2.3B/E2.4 session-safety gate -- fails closed on the invalidated
    # v5_session_1, on any other invalidated session, and on mixed-session
    # label provenance.
    session_blocking_reason = _validate_review_session(blind_manifest, checks)
    if session_blocking_reason and blocking_reason is None:
        blocking_reason = session_blocking_reason

    if labels_complete:
        recomputed_label_fingerprint = compute_label_fingerprint(rows)
        checks["label_fingerprint_recomputed"] = recomputed_label_fingerprint
        recorded_label_fingerprint = blind_manifest.get("final_label_fingerprint")
        checks["label_fingerprint_recorded"] = recorded_label_fingerprint
        checks["legacy_label_fingerprint_recorded"] = blind_manifest.get("label_fingerprint")
        if recorded_label_fingerprint is None:
            checks["label_fingerprint_matches"] = False
            if blocking_reason is None:
                blocking_reason = "EBAY_D3_V5_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN"
        else:
            fingerprint_ok = recorded_label_fingerprint == recomputed_label_fingerprint
            checks["label_fingerprint_matches"] = fingerprint_ok
            if not fingerprint_ok and blocking_reason is None:
                blocking_reason = "EBAY_D3_V5_CERTIFICATION_BLOCKED_LABEL_FINGERPRINT_MISMATCH"

    return {"overall_pass": blocking_reason is None, "blocking_reason": blocking_reason, "checks": checks}


def classify_human_label(row: dict[str, Any]) -> str:
    """Never assumes a definitive answer for an uncertain human row."""
    value = str(row.get("exact_match_yes_no_uncertain", "")).strip().lower()
    if value == POSITIVE:
        return POSITIVE
    if value == NEGATIVE:
        return NEGATIVE
    return UNCERTAIN


def validate_label_contract(rows: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete = []
    for row in rows:
        missing = [f for f in REQUIRED_LABEL_FIELDS if not str(row.get(f, "")).strip()]
        if missing:
            incomplete.append({"benchmark_row_id": row.get("benchmark_row_id"), "missing_fields": missing})
    definitive = [r for r in rows if classify_human_label(r) in (POSITIVE, NEGATIVE)]
    uncertain = [r for r in rows if classify_human_label(r) == UNCERTAIN]
    return {
        "incomplete_rows": incomplete, "incomplete_count": len(incomplete),
        "definitive_count": len(definitive), "uncertain_count": len(uncertain),
        "uncertain_policy": "excluded from precision/recall denominators; reported separately; never coerced to yes/no",
    }


def wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    if not total:
        return [0.0, 0.0]
    p = successes / total
    d = 1 + z * z / total
    c = (p + z * z / (2 * total)) / d
    m = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return [round(c - m, 8), round(c + m, 8)]


def ratio(a: int, b: int) -> float:
    return round(a / b, 8) if b else 0.0


CATASTROPHIC_CLASSES = ("GRADED", "LOT_OR_BUNDLE", "SEALED_OR_ACCESSORY", "WRONG_CARD_NUMBER",
                         "RELATED_BUT_WRONG_VARIANT", "WRONG_SET", "WRONG_LANGUAGE")


GRADED_VALUES = {"graded"}
LOT_VALUES = {"lot", "lot_or_bundle"}
SEALED_VALUES = {"sealed", "accessory", "non-card", "noncard", "sealed_or_non_card"}
CONFLICT_VALUES = {"conflict", "inconsistent"}
NOT_APPLICABLE_VALUES = {"", "not_visible", "uncertain"}
ENGLISH_VALUES = {"english", "en"}


def _human_error_class(row: dict[str, Any]) -> str | None:
    """Maps the label schema's descriptive fields to the repository's
    existing catastrophic taxonomy, for a definitive (non-uncertain) negative
    row. Identical to certify_ebay_d3_v4_fresh_blind._human_error_class() --
    the taxonomy is not weakened or re-derived here.
    """
    if str(row.get("raw_or_graded", "")).strip().lower() in GRADED_VALUES:
        return "GRADED"
    if str(row.get("single_card_or_lot", "")).strip().lower() in LOT_VALUES:
        return "LOT_OR_BUNDLE"
    if str(row.get("card_or_sealed_nonshcard", "")).strip().lower() in SEALED_VALUES:
        return "SEALED_OR_ACCESSORY"
    if str(row.get("collector_number_consistency", "")).strip().lower() in CONFLICT_VALUES:
        return "WRONG_CARD_NUMBER"
    if str(row.get("set_consistency", "")).strip().lower() in CONFLICT_VALUES:
        return "WRONG_SET"
    language = str(row.get("language", "")).strip().lower()
    if language not in NOT_APPLICABLE_VALUES and language not in ENGLISH_VALUES:
        return "WRONG_LANGUAGE"
    if str(row.get("variant_treatment", "")).strip().lower() in CONFLICT_VALUES:
        return "RELATED_BUT_WRONG_VARIANT"
    return "OTHER_MISMATCH"


def compute_certification_metrics(matcher_module, rows: list[dict[str, Any]]) -> dict[str, Any]:
    def target(row: dict[str, Any]) -> dict[str, Any]:
        return {"card_name": row["target_card_name"], "set_name": row["target_set_name"],
                "card_number": row["target_card_number"], "treatment": row["target_treatment"],
                "canonical_card_id": row["canonical_card_id"]}

    def listing(row: dict[str, Any]) -> dict[str, Any]:
        return {"title": row["listing_title"], "condition": row["condition"], "conditionId": row["condition_id"],
                "category": row.get("category_id") or "", "aspects": "[]",
                "buying_options": row.get("buying_options_json") or "[]", "itemId": row["listing_item_id"]}

    definitive_rows = [r for r in rows if classify_human_label(r) in (POSITIVE, NEGATIVE)]
    uncertain_rows = [r for r in rows if classify_human_label(r) == UNCERTAIN]

    states = Counter()
    tp = fp = 0
    catastrophic: Counter = Counter()
    catastrophic_high_confidence = 0
    error_rows = []
    cards_with_true_accept: set[str] = set()
    cards_with_false_only_accept: set[str] = set()
    cards_with_any_accept: dict[str, list[bool]] = {}

    for row in definitive_rows:
        result = matcher_module.classify_listing(target(row), listing(row))
        state = result["identity_state"]
        states[state] += 1
        gold_positive = classify_human_label(row) == POSITIVE
        card_id = row["canonical_card_id"]
        if state == "HIGH_CONFIDENCE":
            cards_with_any_accept.setdefault(card_id, []).append(gold_positive)
            if gold_positive:
                tp += 1
                cards_with_true_accept.add(card_id)
            else:
                fp += 1
                error_class = _human_error_class(row)
                catastrophic[error_class] += 1
                catastrophic_high_confidence += 1
                error_rows.append({
                    "benchmark_row_id": row["benchmark_row_id"], "human_error_class": error_class,
                    "matcher_state": state, "listing_title": row["listing_title"],
                })

    for card_id, flags in cards_with_any_accept.items():
        if not any(flags):
            cards_with_false_only_accept.add(card_id)

    accepted = tp + fp
    positives_total = sum(1 for r in definitive_rows if classify_human_label(r) == POSITIVE)
    all_cards = {r["canonical_card_id"] for r in rows}

    return {
        "total_scored_rows": len(rows), "human_uncertain_rows": len(uncertain_rows),
        "definitive_rows": len(definitive_rows),
        "matcher_state_breakdown": dict(sorted(states.items())),
        "accepted_count": accepted, "true_accepts": tp, "false_accepts": fp,
        "accepted_precision": ratio(tp, accepted), "accepted_precision_wilson_95": wilson(tp, accepted),
        "accepted_recall": ratio(tp, positives_total),
        "acceptance_rate": ratio(accepted, len(definitive_rows)),
        "rejection_rate": ratio(states.get("REJECTED", 0), len(definitive_rows)),
        "ambiguity_rate": ratio(states.get("AMBIGUOUS", 0) + states.get("MEDIUM_CONFIDENCE", 0), len(definitive_rows)),
        "cards_with_true_accept": len(cards_with_true_accept), "cards_total": len(all_cards),
        "card_coverage": ratio(len(cards_with_true_accept), len(all_cards)),
        "cards_with_false_only_accept": sorted(cards_with_false_only_accept),
        "catastrophic_false_accepts": dict(sorted(catastrophic.items())),
        "catastrophic_false_accept_total": sum(catastrophic.values()),
        "catastrophic_false_accept_rate_among_accepted": ratio(sum(catastrophic.values()), accepted),
        "catastrophic_high_confidence_count": catastrophic_high_confidence,
        "error_rows": error_rows,
    }


def apply_gates(metrics: dict[str, Any], design: dict[str, Any]) -> dict[str, Any]:
    gate_spec = design["preregistered_gate"]
    n = metrics["accepted_count"]

    def gate(name: str, observed, threshold, comparison, evaluable: bool) -> dict[str, Any]:
        if not evaluable:
            return {"status": "NOT_EVALUABLE", "threshold": threshold, "observed": observed, "sample_size": n,
                    "reason": "accepted sample too small or undefined"}
        passed = comparison(observed, threshold)
        return {"status": "PASS" if passed else "FAIL", "threshold": threshold, "observed": observed, "sample_size": n}

    precision_evaluable = n > 0
    gates = {
        "accepted_precision": gate("accepted_precision", metrics["accepted_precision"], gate_spec["high_precision_minimum"],
                                    lambda o, t: o >= t, precision_evaluable),
        "wilson_lower": gate("wilson_lower", metrics["accepted_precision_wilson_95"][0], gate_spec["wilson_95_lower_minimum"],
                              lambda o, t: o >= t, precision_evaluable),
        "coverage": gate("coverage", metrics["card_coverage"], gate_spec["card_coverage_minimum"], lambda o, t: o >= t, True),
        "catastrophic": gate("catastrophic", metrics["catastrophic_false_accept_total"],
                              gate_spec["catastrophic_high_false_positives_maximum"], lambda o, t: o <= t, True),
    }
    all_evaluated_pass = all(g["status"] == "PASS" for g in gates.values())
    any_not_evaluable = any(g["status"] == "NOT_EVALUABLE" for g in gates.values())
    # A single strong headline precision figure can never substitute for, or
    # override, a failed Wilson-lower-bound gate or a nonzero catastrophic
    # false-accept count -- `overall` requires EVERY gate to independently
    # report PASS, with no special-casing of any one gate's result.
    overall = "PASS" if all_evaluated_pass and not any_not_evaluable else "FAIL"
    return {"gates": gates, "overall_result": overall}


def main() -> dict[str, Any]:
    precondition_report = check_preconditions()
    if not precondition_report["overall_pass"]:
        raise CertificationBlocked(precondition_report["blocking_reason"], json.dumps(precondition_report["checks"]))

    rows = load_queue_rows()
    contract = validate_label_contract(rows)
    design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
    v5_metrics = compute_certification_metrics(v5, rows)
    gate_result = apply_gates(v5_metrics, design)

    output = {
        "version": "ebay_d3_v5_fresh_blind_certification_v1",
        "precondition_report": precondition_report, "label_contract": contract,
        "v5_metrics": v5_metrics, "gate_result": gate_result,
        "final_result": "EBAY_D3_V5_SINGLE_REVIEWER_BLIND_CERTIFIED_E3_READY" if gate_result["overall_result"] == "PASS"
                        else "EBAY_D3_V5_NOT_CERTIFIED",
    }
    CERTIFICATION_OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
