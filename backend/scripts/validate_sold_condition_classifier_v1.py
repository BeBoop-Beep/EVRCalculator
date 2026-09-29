"""Replay the reviewed title-condition validation artifact deterministically."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from backend.pricing_pipeline.sold_condition_classifier import CLASSIFIER_VERSION, classify_sold_title

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "docs/research/grading_population/condition_validation_sample_v1.json"
REPORT = ROOT / "docs/research/grading_population/condition_precision_report_v1.json"


def build_report() -> dict:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    predictions = []
    for row in sample["rows"]:
        result = classify_sold_title(row["title"])
        predictions.append({"id": row["id"], "expected": row["expected"],
                            "predicted": result["condition_label"], "correct": row["expected"] == result["condition_label"]})
    by_prediction = defaultdict(lambda: [0, 0])
    for row in predictions:
        by_prediction[row["predicted"]][1] += 1
        by_prediction[row["predicted"]][0] += int(row["correct"])
    precision = {label: {"correct": values[0], "predicted": values[1],
                         "precision": round(values[0] / values[1], 6)}
                 for label, values in sorted(by_prediction.items())}
    return {
        "version": "condition_precision_report_v1", "classifier_version": CLASSIFIER_VERSION,
        "sample_version": sample["version"], "reviewed": sample["reviewed"],
        "row_count": len(predictions), "correct_count": sum(row["correct"] for row in predictions),
        "accuracy": round(sum(row["correct"] for row in predictions) / len(predictions), 6),
        "precision_by_class": precision,
        "coverage": {field: dict(sorted(Counter(row[field] for row in sample["rows"]).items()))
                     for field in ("era", "value_band", "title_length", "language_kind", "risk")},
        "errors": [row for row in predictions if not row["correct"]],
        "pricing_use_authorized": False,
        "interpretation": "Precision on a small reviewed contract fixture, not population-level recall or price-adjustment validation."
    }


def main() -> int:
    report = build_report()
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
