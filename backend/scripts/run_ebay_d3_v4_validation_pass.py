"""ONE-TIME v3-vs-v4 validation-partition pass. Do not run this more than once
per matcher freeze -- index_fair_value_ebay_evidence_manifest.py enforces that
by refusing a second call. If this pass reveals a problem, the fix is to
diagnose on DEVELOPMENT and require a fresh held-out partition -- NOT to
re-run this script against the same VALIDATION rows again.
"""
from __future__ import annotations

import json
from typing import Any

from backend.scripts import ebay_d3_matcher_v3 as v3
from backend.scripts import ebay_d3_matcher_v4 as v4
from backend.scripts.build_ebay_d3_v4_development_study import benchmark, listing, target
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.ebay_gold_review_server import read_history, reconstruct_effective_state
from backend.scripts.index_fair_value_ebay_evidence_manifest import load_validation_for_one_time_pass

CATASTROPHIC_CLASSES = ("GRADED", "LOT_OR_BUNDLE", "SEALED_OR_ACCESSORY", "WRONG_CARD_NUMBER",
                         "RELATED_BUT_WRONG_VARIANT", "WRONG_SET", "WRONG_LANGUAGE")


def load_validation_corpus(consumer: str, allow_repeat_for_tests: bool = False) -> list[tuple[dict[str, Any], str]]:
    rows = load_validation_for_one_time_pass(consumer, allow_repeat_for_tests=allow_repeat_for_tests)
    events = read_history()
    state = reconstruct_effective_state(events, "VALIDATION", "Donny", [r["benchmark_row_id"] for r in rows])
    if state["skipped"] or state["unlabeled"]:
        raise RuntimeError("VALIDATION_CORPUS_INCOMPLETE")
    labels = {row_id: event["label"] for row_id, event in state["labels"].items()}
    return [(dict(row), labels[row["benchmark_row_id"]]) for row in rows]


PRECISION_MATERIAL_DROP_THRESHOLD = 0.02  # v4 precision must not fall more than 2pp below v3


def decide(v3_metrics: dict[str, Any], v4_metrics: dict[str, Any]) -> dict[str, Any]:
    v3_catastrophic = set(v3_metrics["catastrophic_high_counts"])
    v4_catastrophic = set(v4_metrics["catastrophic_high_counts"])
    eliminated_classes = v3_catastrophic - v4_catastrophic
    new_classes = v4_catastrophic - v3_catastrophic
    precision_ok = v4_metrics["precision"] >= v3_metrics["precision"] - PRECISION_MATERIAL_DROP_THRESHOLD
    no_new_catastrophic = v4_metrics["catastrophic_high_total"] <= v3_metrics["catastrophic_high_total"] and not new_classes
    coverage_ok = v4_metrics["card_coverage"] >= v3_metrics["card_coverage"] * 0.9  # tolerate small, expected loss from added guards
    passed = precision_ok and no_new_catastrophic and coverage_ok
    return {
        "eliminated_catastrophic_classes": sorted(eliminated_classes),
        "new_catastrophic_classes": sorted(new_classes),
        "precision_ok": precision_ok, "no_new_catastrophic": no_new_catastrophic, "coverage_ok": coverage_ok,
        "validation_pass_result": "PASS" if passed else "REQUIRES_ADDITIONAL_HELD_OUT_STAGE",
    }


def main(allow_repeat_for_tests: bool = False) -> dict[str, Any]:
    corpus = load_validation_corpus("run_ebay_d3_v4_validation_pass", allow_repeat_for_tests=allow_repeat_for_tests)
    v3_metrics = benchmark(v3, corpus)
    v4_metrics = benchmark(v4, corpus)
    decision = decide(v3_metrics, v4_metrics)
    result = {
        "version": "ebay_d3_v4_validation_pass_v1", "validation_row_count": len(corpus),
        "v3_metrics": v3_metrics, "v4_metrics": v4_metrics, "decision": decision,
    }
    (OUT / "ebay_d3_v4_validation_pass.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
