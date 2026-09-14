"""Development-only failure research + v3-vs-v4 side-by-side benchmark.

Strictly DEVELOPMENT-partition evidence (450 rows) -- unlike v3's own study,
this does NOT fold VALIDATION or historical FINAL_BLIND_TEST rows into the
tuning corpus, so VALIDATION remains available for one bounded post-freeze
pass (see index_fair_value_ebay_evidence_manifest.py). Historical final-blind
catastrophic rows are never opened here.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from backend.scripts import ebay_d3_matcher_v3 as v3
from backend.scripts import ebay_d3_matcher_v4 as v4
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.ebay_gold_review_server import read_history, reconstruct_effective_state
from backend.scripts.index_fair_value_ebay_evidence_manifest import load_development_for_tuning

POSITIVE = "EXACT_TARGET_MATCH"
AMBIGUOUS = "AMBIGUOUS"
CATASTROPHIC = ("GRADED", "LOT_OR_BUNDLE", "SEALED_OR_ACCESSORY", "WRONG_CARD_NUMBER",
                "RELATED_BUT_WRONG_VARIANT", "WRONG_SET", "WRONG_LANGUAGE")


def target(row: dict[str, Any]) -> dict[str, Any]:
    return {"card_name": row["target_card_name"], "set_name": row["target_set_name"],
            "card_number": row["target_card_number"], "treatment": row["target_treatment"],
            "canonical_card_id": row["canonical_card_id"]}


def listing(row: dict[str, Any]) -> dict[str, Any]:
    return {"title": row["listing_title"], "condition": row["condition"], "conditionId": row["condition_id"],
            "category": row["category_id"], "aspects": row["localized_aspects_json"],
            "buying_options": row["buying_options_json"], "itemId": row["listing_item_id"]}


def load_development_corpus() -> list[tuple[dict[str, Any], str]]:
    rows = load_development_for_tuning()
    events = read_history()
    state = reconstruct_effective_state(events, "DEVELOPMENT", "Donny", [r["benchmark_row_id"] for r in rows])
    if state["skipped"] or state["unlabeled"]:
        raise RuntimeError("DEVELOPMENT_CORPUS_INCOMPLETE")
    labels = {row_id: event["label"] for row_id, event in state["labels"].items()}
    if len(rows) != 450 or len(labels) != 450:
        raise RuntimeError("DEVELOPMENT_CORPUS_SIZE_MISMATCH")
    return [(dict(row), labels[row["benchmark_row_id"]]) for row in rows]


def ratio(a: int, b: int) -> float:
    return round(a / b, 8) if b else 0.0


def benchmark(matcher_module, corpus: list[tuple[dict[str, Any], str]]) -> dict[str, Any]:
    states = Counter()
    matrix = Counter()
    high_cards: set[str] = set()
    catastrophic_high: Counter = Counter()
    high_errors = []
    for row, gold in corpus:
        result = matcher_module.classify_listing(target(row), listing(row))
        state = result["identity_state"]
        states[state] += 1
        if gold != AMBIGUOUS:
            positive = gold == POSITIVE
            accepted = state == "HIGH_CONFIDENCE"
            matrix["tp" if positive and accepted else "fn" if positive else "fp" if accepted else "tn"] += 1
        if state == "HIGH_CONFIDENCE" and gold == POSITIVE:
            high_cards.add(row["canonical_card_id"])
        if state == "HIGH_CONFIDENCE" and gold != POSITIVE:
            catastrophic_high[gold] += 1
            high_errors.append({
                "benchmark_row_id": row["benchmark_row_id"], "gold": gold,
                "listing_title": row["listing_title"], "reason": result.get("reason"),
            })
    tp, fp, tn, fn = (matrix[k] for k in ("tp", "fp", "tn", "fn"))
    exact_count = sum(1 for _, gold in corpus if gold == POSITIVE)
    return {
        "matcher_version": matcher_module.MATCHER_VERSION,
        "accepted": tp + fp, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": ratio(tp, tp + fp), "recall": ratio(tp, exact_count),
        "card_coverage_count": len(high_cards), "card_coverage": ratio(len(high_cards), 70),
        "matcher_state_breakdown": dict(sorted(states.items())),
        "ambiguous_rate": ratio(states.get("AMBIGUOUS", 0), len(corpus)),
        "rejection_rate": ratio(states.get("REJECTED", 0), len(corpus)),
        "catastrophic_high_counts": dict(sorted(catastrophic_high.items())),
        "catastrophic_high_total": sum(catastrophic_high.values()),
        "high_error_rows": high_errors,
    }


def newly_rejected_legitimate_listings(corpus: list[tuple[dict[str, Any], str]]) -> list[dict[str, Any]]:
    """Legitimate (EXACT_TARGET_MATCH) development rows where v3 accepted (HIGH)
    but v4's new guards reject/downgrade -- the coverage cost of the new guards.
    """
    regressions = []
    for row, gold in corpus:
        if gold != POSITIVE:
            continue
        v3_result = v3.classify_listing(target(row), listing(row))
        if v3_result["identity_state"] != "HIGH_CONFIDENCE":
            continue
        v4_result = v4.classify_listing(target(row), listing(row))
        if v4_result["identity_state"] != "HIGH_CONFIDENCE":
            regressions.append({
                "benchmark_row_id": row["benchmark_row_id"], "listing_title": row["listing_title"],
                "v3_state": v3_result["identity_state"], "v4_state": v4_result["identity_state"],
                "v4_reason": v4_result.get("reason"),
            })
    return regressions


def failure_class_research(corpus: list[tuple[dict[str, Any], str]], gold_label: str) -> dict[str, Any]:
    """Development-only audit of one catastrophic class: does v3 correctly
    reject it, and does v4 change that outcome?
    """
    rows = [(row, gold) for row, gold in corpus if gold == gold_label]
    v3_high = 0
    v4_high = 0
    examples = []
    for row, gold in rows:
        v3_result = v3.classify_listing(target(row), listing(row))
        v4_result = v4.classify_listing(target(row), listing(row))
        if v3_result["identity_state"] == "HIGH_CONFIDENCE":
            v3_high += 1
        if v4_result["identity_state"] == "HIGH_CONFIDENCE":
            v4_high += 1
        examples.append({
            "benchmark_row_id": row["benchmark_row_id"], "listing_title": row["listing_title"],
            "v3_state": v3_result["identity_state"], "v4_state": v4_result["identity_state"],
        })
    return {
        "gold_label": gold_label, "development_row_count": len(rows),
        "v3_incorrectly_accepted_high": v3_high, "v4_incorrectly_accepted_high": v4_high,
        "examples": examples[:20],
    }


def main() -> dict[str, Any]:
    corpus = load_development_corpus()
    v3_metrics = benchmark(v3, corpus)
    v4_metrics = benchmark(v4, corpus)
    delta = {
        "precision_delta": round(v4_metrics["precision"] - v3_metrics["precision"], 8),
        "recall_delta": round(v4_metrics["recall"] - v3_metrics["recall"], 8),
        "coverage_delta": round(v4_metrics["card_coverage"] - v3_metrics["card_coverage"], 8),
        "ambiguous_rate_delta": round(v4_metrics["ambiguous_rate"] - v3_metrics["ambiguous_rate"], 8),
        "rejection_rate_delta": round(v4_metrics["rejection_rate"] - v3_metrics["rejection_rate"], 8),
        "catastrophic_high_total_delta": v4_metrics["catastrophic_high_total"] - v3_metrics["catastrophic_high_total"],
    }
    regressions = newly_rejected_legitimate_listings(corpus)
    failure_research = {
        label: failure_class_research(corpus, label)
        for label in ("WRONG_CARD_NUMBER", "LOT_OR_BUNDLE", "SEALED_OR_ACCESSORY")
    }
    result = {
        "version": "ebay_d3_v4_development_study_v1",
        "development_corpus_fingerprint": hashlib.sha256(
            "\n".join(sorted(f"{r['benchmark_row_id']}:{g}" for r, g in corpus)).encode()
        ).hexdigest(),
        "v3_metrics": v3_metrics, "v4_metrics": v4_metrics, "delta_v4_minus_v3": delta,
        "newly_rejected_legitimate_listings": regressions,
        "newly_rejected_legitimate_count": len(regressions),
        "failure_class_research": failure_research,
    }
    (OUT / "ebay_d3_v4_development_study.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
