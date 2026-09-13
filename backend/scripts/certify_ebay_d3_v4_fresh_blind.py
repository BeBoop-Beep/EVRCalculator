"""D3-v4 fresh-blind certification -- fail-closed, run-exactly-once.

Reuses the exact preregistered gates from ebay_d3_new_blind_benchmark_design.json
(high_precision_minimum=0.99, wilson_95_lower_minimum=0.98,
card_coverage_minimum=0.80, catastrophic_high_false_positives_maximum=0) --
no easier gate is invented here.

This module refuses to run the matcher against the blind cohort at all unless
every precondition in `check_preconditions()` holds: labels frozen and
complete, no matcher-derived fields in the label file, frozen fingerprint
unchanged since freeze, cohort fingerprint unchanged since capture.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from backend.scripts import ebay_d3_matcher_v3 as v3
from backend.scripts import ebay_d3_matcher_v4 as v4
from backend.scripts.ebay_gold_access import OUT

QUEUE_PATH = OUT / "ebay_d3_v4_fresh_blind_queue.csv"
BLIND_MANIFEST_PATH = OUT / "ebay_d3_v4_fresh_blind_manifest.json"
FREEZE_MANIFEST_PATH = OUT / "ebay_d3_v4_freeze_manifest.json"
DESIGN_PATH = OUT / "ebay_d3_new_blind_benchmark_design.json"
CERTIFICATION_OUTPUT_PATH = OUT / "ebay_d3_v4_fresh_blind_certification.json"

FORBIDDEN_LABEL_COLUMNS = frozenset({
    "matcher_version", "matcher_state", "identity_state", "match_status", "confidence",
    "confidence_tier", "score", "accepted", "rejection_reason", "v3_state", "v4_state", "reason",
})
REQUIRED_LABEL_FIELDS = (
    "exact_match_yes_no_uncertain", "single_card_or_lot", "raw_or_graded", "card_or_sealed_nonshcard",
    "reviewer_id", "label_timestamp",
)
DETERMINABLE_WHEN_PRESENT_FIELDS = ("collector_number_consistency", "set_consistency", "language", "variant_treatment")
POSITIVE = "yes"
NEGATIVE = "no"
UNCERTAIN = "uncertain"


class CertificationBlocked(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _cohort_fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "\n".join(sorted(f"{r['benchmark_row_id']}:{r['listing_item_id']}" for r in rows)).encode()
    ).hexdigest()


def _label_fingerprint(rows: list[dict[str, Any]]) -> str:
    material = "\n".join(
        sorted(f"{r['benchmark_row_id']}:{r.get(f, '')}" for r in rows for f in REQUIRED_LABEL_FIELDS)
    )
    return hashlib.sha256(material.encode()).hexdigest()


def load_queue_rows() -> list[dict[str, Any]]:
    if not QUEUE_PATH.exists():
        raise CertificationBlocked("EBAY_D3_V4_CERTIFICATION_BLOCKED_COHORT_MISSING", str(QUEUE_PATH))
    with QUEUE_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def check_preconditions() -> dict[str, Any]:
    """Returns a report dict; never raises for a normal "not ready" state --
    callers decide what to do with `overall_pass`/`blocking_reason`.
    """
    checks: dict[str, Any] = {}
    blocking_reason = None

    if not QUEUE_PATH.exists() or not BLIND_MANIFEST_PATH.exists():
        return {"overall_pass": False, "blocking_reason": "EBAY_D3_V4_CERTIFICATION_BLOCKED_COHORT_MISSING", "checks": checks}
    if not FREEZE_MANIFEST_PATH.exists():
        return {"overall_pass": False, "blocking_reason": "EBAY_D3_V4_CERTIFICATION_BLOCKED_FREEZE_MANIFEST_MISSING", "checks": checks}

    rows = load_queue_rows()
    blind_manifest = json.loads(BLIND_MANIFEST_PATH.read_text(encoding="utf-8"))
    freeze_manifest = json.loads(FREEZE_MANIFEST_PATH.read_text(encoding="utf-8"))

    checks["cohort_row_count"] = len(rows)
    checks["cohort_fingerprint_recorded"] = blind_manifest.get("cohort_fingerprint")
    checks["cohort_fingerprint_recomputed"] = _cohort_fingerprint(rows)
    cohort_fingerprint_matches = checks["cohort_fingerprint_recorded"] == checks["cohort_fingerprint_recomputed"]
    checks["cohort_fingerprint_matches"] = cohort_fingerprint_matches
    if not cohort_fingerprint_matches:
        blocking_reason = "EBAY_D3_V4_CERTIFICATION_BLOCKED_COHORT_FINGERPRINT_MISMATCH"

    forbidden_present = FORBIDDEN_LABEL_COLUMNS & set(rows[0].keys()) if rows else set()
    checks["forbidden_matcher_columns_present"] = sorted(forbidden_present)
    if forbidden_present and blocking_reason is None:
        blocking_reason = "EBAY_D3_V4_CERTIFICATION_BLOCKED_LABEL_FILE_CONTAINS_MATCHER_OUTPUT"

    labeled_rows = [r for r in rows if str(r.get("exact_match_yes_no_uncertain", "")).strip()]
    checks["labeled_row_count"] = len(labeled_rows)
    checks["total_row_count"] = len(rows)
    labels_complete = len(labeled_rows) == len(rows) and len(rows) > 0
    checks["labels_complete"] = labels_complete
    checks["blind_manifest_labels_exist_flag"] = blind_manifest.get("labels_exist")
    if (not labels_complete or not blind_manifest.get("labels_exist")) and blocking_reason is None:
        blocking_reason = "EBAY_D3_V4_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN"

    current_fingerprint = v4.rule_fingerprint()
    frozen_fingerprint = freeze_manifest.get("matcher_fingerprint")
    checks["frozen_matcher_fingerprint"] = frozen_fingerprint
    checks["current_matcher_fingerprint"] = current_fingerprint
    fingerprint_matches = current_fingerprint == frozen_fingerprint
    checks["matcher_fingerprint_matches"] = fingerprint_matches
    if not fingerprint_matches and blocking_reason is None:
        blocking_reason = "EBAY_D3_V4_CERTIFICATION_BLOCKED_MATCHER_HASH_MISMATCH"

    checks["reviewer_protocol"] = blind_manifest.get("protocol")
    checks["reviewer_b_exists"] = blind_manifest.get("reviewer_b_exists")
    checks["reviewer_protocol_declared"] = blind_manifest.get("protocol") is not None
    if not checks["reviewer_protocol_declared"] and blocking_reason is None:
        blocking_reason = "EBAY_D3_V4_CERTIFICATION_BLOCKED_REVIEWER_PROTOCOL_UNDECLARED"

    if labels_complete:
        checks["label_fingerprint"] = _label_fingerprint(rows)

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


def _human_error_class(row: dict[str, Any]) -> str | None:
    """Maps the label schema's descriptive fields to the repository's
    existing catastrophic taxonomy, for a definitive (non-uncertain) negative row.
    """
    if str(row.get("raw_or_graded", "")).strip().lower() == "graded":
        return "GRADED"
    if str(row.get("single_card_or_lot", "")).strip().lower() == "lot":
        return "LOT_OR_BUNDLE"
    if str(row.get("card_or_sealed_nonshcard", "")).strip().lower() in {"sealed", "accessory", "non-card", "noncard"}:
        return "SEALED_OR_ACCESSORY"
    if str(row.get("collector_number_consistency", "")).strip().lower() == "conflict":
        return "WRONG_CARD_NUMBER"
    if str(row.get("set_consistency", "")).strip().lower() == "conflict":
        return "WRONG_SET"
    if str(row.get("language", "")).strip().lower() not in ("", "english", "en"):
        return "WRONG_LANGUAGE"
    if str(row.get("variant_treatment", "")).strip().lower() == "conflict":
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
    overall = "PASS" if all_evaluated_pass and not any_not_evaluable else "FAIL"
    return {"gates": gates, "overall_result": overall}


def main() -> dict[str, Any]:
    precondition_report = check_preconditions()
    if not precondition_report["overall_pass"]:
        raise CertificationBlocked(precondition_report["blocking_reason"], json.dumps(precondition_report["checks"]))

    rows = load_queue_rows()
    contract = validate_label_contract(rows)
    design = json.loads(DESIGN_PATH.read_text(encoding="utf-8"))
    v4_metrics = compute_certification_metrics(v4, rows)
    gate_result = apply_gates(v4_metrics, design)

    output = {
        "version": "ebay_d3_v4_fresh_blind_certification_v1",
        "precondition_report": precondition_report, "label_contract": contract,
        "v4_metrics": v4_metrics, "gate_result": gate_result,
        "final_result": "EBAY_D3_V4_SINGLE_REVIEWER_BLIND_CERTIFIED_E3_READY" if gate_result["overall_result"] == "PASS"
                        else "EBAY_D3_V4_NOT_CERTIFIED",
    }
    CERTIFICATION_OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
