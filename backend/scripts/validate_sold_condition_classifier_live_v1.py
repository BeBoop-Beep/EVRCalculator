"""Score frozen sold-title condition V1 against the locked live blind holdout."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from backend.pricing_pipeline.sold_condition_classifier import (
    CLASSIFIER_VERSION,
    classify_sold_title,
)

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "docs/research/grading_population/condition_validation_live_blind_sample_v1.json"
LABELS = ROOT / "docs/research/grading_population/condition_validation_live_blind_labels_v1.json"
REPORT = ROOT / "docs/research/grading_population/condition_validation_live_precision_report_v1.json"
REPORT_MD = ROOT / "docs/research/grading_population/CONDITION_VALIDATION_LIVE_REPORT_20260930.md"


def _safe_div(a: int, b: int) -> float | None:
    return None if b == 0 else round(a / b, 6)


def build_report() -> dict:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    labels = json.loads(LABELS.read_text(encoding="utf-8"))

    if sample["sample_fingerprint_md5"] != labels["sample_fingerprint_md5"]:
        raise RuntimeError("D3_SAMPLE_LABEL_FINGERPRINT_MISMATCH")
    if labels["classifier_frozen"]["version"] != CLASSIFIER_VERSION:
        raise RuntimeError("D3_CLASSIFIER_VERSION_DRIFT")

    label_by_id = {row["evidence_id"]: row for row in labels["rows"]}
    rows = []
    for sample_row in sample["rows"]:
        label_row = label_by_id[sample_row["evidence_id"]]
        result = classify_sold_title(sample_row["title"])
        rows.append({
            "review_index": label_row["review_index"],
            "evidence_id": sample_row["evidence_id"],
            "title": sample_row["title"],
            "expected": label_row["expected"],
            "predicted": result["condition_label"],
            "confidence": result["confidence"],
            "correct": label_row["expected"] == result["condition_label"],
            "review_reason": label_row["review_reason"],
            "value_band": sample_row["value_band"],
            "title_length": sample_row["title_length"],
            "attribution": sample_row["attribution"],
            "set_name": sample_row["set_name"],
        })

    classes = ["NM", "LP", "MP", "HP", "DAMAGED", "AMBIGUOUS", "UNLABELED"]
    confusion = {e: {p: 0 for p in classes} for e in classes}
    for row in rows:
        confusion[row["expected"]][row["predicted"]] += 1

    metrics = {}
    for label in classes:
        tp = sum(r["expected"] == label and r["predicted"] == label for r in rows)
        fp = sum(r["expected"] != label and r["predicted"] == label for r in rows)
        fn = sum(r["expected"] == label and r["predicted"] != label for r in rows)
        predicted = tp + fp
        support = tp + fn
        precision = _safe_div(tp, predicted)
        recall = _safe_div(tp, support)
        f1 = None
        if precision is not None and recall is not None and precision + recall > 0:
            f1 = round(2 * precision * recall / (precision + recall), 6)
        metrics[label] = {
            "support": support,
            "predicted": predicted,
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    confidence = {}
    for conf in ["HIGH", "MEDIUM", "LOW", "NONE"]:
        subset = [r for r in rows if r["confidence"] == conf]
        correct = sum(r["correct"] for r in subset)
        confidence[conf] = {
            "count": len(subset),
            "correct": correct,
            "accuracy": _safe_div(correct, len(subset)),
        }

    error_reason = Counter(r["review_reason"] for r in rows if not r["correct"])
    errors = [
        {
            "review_index": r["review_index"],
            "evidence_id": r["evidence_id"],
            "title": r["title"],
            "expected": r["expected"],
            "predicted": r["predicted"],
            "confidence": r["confidence"],
            "review_reason": r["review_reason"],
            "value_band": r["value_band"],
            "attribution": r["attribution"],
        }
        for r in rows if not r["correct"]
    ]

    expected_counts = Counter(r["expected"] for r in rows)
    predicted_counts = Counter(r["predicted"] for r in rows)
    correct_count = sum(r["correct"] for r in rows)

    hp_stat_rows = [r for r in rows if r["review_reason"] == "HP_STAT_NOT_CONDITION"]
    hp_stat_errors = [r for r in hp_stat_rows if not r["correct"]]
    marketing_rows = [
        r for r in rows
        if r["review_reason"] == "MARKETING_OR_NON_TAXONOMY_MINT_LANGUAGE"
    ]
    marketing_errors = [r for r in marketing_rows if not r["correct"]]

    return {
        "version": "condition_validation_live_precision_report_v1",
        "classifier_version": CLASSIFIER_VERSION,
        "classifier_blob_sha": labels["classifier_frozen"]["blob_sha"],
        "sample_version": sample["version"],
        "sample_fingerprint_md5": sample["sample_fingerprint_md5"],
        "row_count": len(rows),
        "correct_count": correct_count,
        "accuracy": _safe_div(correct_count, len(rows)),
        "metrics_by_class": metrics,
        "confusion_matrix_expected_by_predicted": confusion,
        "expected_class_counts": dict(sorted(expected_counts.items())),
        "predicted_class_counts": dict(sorted(predicted_counts.items())),
        "confidence_calibration": confidence,
        "coverage": sample["coverage"],
        "expected_condition_bearing_share": _safe_div(
            len(rows) - expected_counts["UNLABELED"], len(rows)
        ),
        "expected_unlabeled_share": _safe_div(expected_counts["UNLABELED"], len(rows)),
        "expected_ambiguity_share": _safe_div(expected_counts["AMBIGUOUS"], len(rows)),
        "predicted_unlabeled_share": _safe_div(predicted_counts["UNLABELED"], len(rows)),
        "predicted_ambiguity_share": _safe_div(predicted_counts["AMBIGUOUS"], len(rows)),
        "error_reason_counts": dict(sorted(error_reason.items())),
        "hp_stat_false_positive_audit": {
            "reviewed_rows": len(hp_stat_rows),
            "errors": len(hp_stat_errors),
            "error_rate": _safe_div(len(hp_stat_errors), len(hp_stat_rows)),
        },
        "marketing_mint_false_positive_audit": {
            "reviewed_rows": len(marketing_rows),
            "errors": len(marketing_errors),
            "error_rate": _safe_div(len(marketing_errors), len(marketing_rows)),
        },
        "errors": errors,
        "reviewer": labels["reviewer"],
        "human_review_requirement_satisfied": labels["human_review_requirement_satisfied"],
        "modern_only": True,
        "vintage_generalization_authorized": False,
        "pricing_use_authorized": False,
        "decision": "D3_NEEDS_V2",
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def build_markdown(report: dict) -> str:
    lines = [
        "# D3 live blind condition-classifier validation",
        "",
        "Date: 2026-09-30",
        "",
        f"Decision: **{report['decision']}**",
        "",
        "## Scope",
        "",
        f"- Frozen classifier: {report['classifier_version']} / blob {report['classifier_blob_sha']}.",
        f"- Locked sample: {report['row_count']} distinct raw/ungraded real sold-listing titles.",
        f"- Sample fingerprint: {report['sample_fingerprint_md5']}.",
        "- Core Panel coverage: modern only (2023–2026); vintage generalization remains unproven.",
        f"- Reviewer: {report['reviewer']}.",
        f"- Human-review gate satisfied: **{str(report['human_review_requirement_satisfied']).lower()}**.",
        "- No condition-to-NM price conversion or canonical pricing mutation is authorized.",
        "",
        "## Headline performance",
        "",
        f"- Accuracy: **{_pct(report['accuracy'])}** ({report['correct_count']} / {report['row_count']}).",
        f"- Expected unlabeled share: {_pct(report['expected_unlabeled_share'])}.",
        f"- Expected ambiguity share: {_pct(report['expected_ambiguity_share'])}.",
        f"- Predicted unlabeled share: {_pct(report['predicted_unlabeled_share'])}.",
        f"- Predicted ambiguity share: {_pct(report['predicted_ambiguity_share'])}.",
        "",
        "## Per-class metrics",
        "",
        "| Class | Support | Predicted | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, metric in report["metrics_by_class"].items():
        lines.append(
            f"| {label} | {metric['support']} | {metric['predicted']} | "
            f"{_pct(metric['precision'])} | {_pct(metric['recall'])} | {_pct(metric['f1'])} |"
        )
    lines += [
        "",
        "## False-positive audits",
        "",
        f"- Pokémon HP-stat rows reviewed: {report['hp_stat_false_positive_audit']['reviewed_rows']}; "
        f"errors: {report['hp_stat_false_positive_audit']['errors']} "
        f"({_pct(report['hp_stat_false_positive_audit']['error_rate'])}).",
        f"- Marketing/non-taxonomy mint-language rows reviewed: "
        f"{report['marketing_mint_false_positive_audit']['reviewed_rows']}; "
        f"errors: {report['marketing_mint_false_positive_audit']['errors']} "
        f"({_pct(report['marketing_mint_false_positive_audit']['error_rate'])}).",
        "",
        "## Interpretation",
        "",
        "This holdout is materially broader than the authored 35-row contract fixture and is prediction-blind, "
        "but it is not a human-annotated holdout and it contains no vintage Core Panel cards. "
        "Accordingly it is diagnostic evidence only. Any classifier revision must be versioned as V2 and "
        "evaluated on a fresh holdout; this sample must not be reused as V2 promotion evidence.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    report = build_report()
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_MD.write_text(build_markdown(report), encoding="utf-8")
    print(json.dumps({
        "decision": report["decision"],
        "row_count": report["row_count"],
        "accuracy": report["accuracy"],
        "error_count": len(report["errors"]),
        "metrics_by_class": report["metrics_by_class"],
        "error_reason_counts": report["error_reason_counts"],
        "hp_stat_false_positive_audit": report["hp_stat_false_positive_audit"],
        "marketing_mint_false_positive_audit": report["marketing_mint_false_positive_audit"],
        "confidence_calibration": report["confidence_calibration"],
        "expected_class_counts": report["expected_class_counts"],
        "predicted_class_counts": report["predicted_class_counts"],
        "confusion_matrix": report["confusion_matrix_expected_by_predicted"],
        "errors": report["errors"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
