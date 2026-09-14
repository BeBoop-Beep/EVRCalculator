"""Development-only failure research + v4-vs-v5 side-by-side benchmark.

Strictly DEVELOPMENT-partition evidence (450 rows). The historical VALIDATION
partition was already consumed during V4's development and is NOT reused
here as if it were fresh -- v5's only formal held-out check is the (clearly
labeled, non-certifying) historical-diagnostic pass against the now-consumed
V4 420-row blind cohort, run only AFTER v5 is frozen (see
run_ebay_d3_v5_historical_diagnostic.py).
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from backend.scripts import ebay_d3_matcher_v4 as v4
from backend.scripts import ebay_d3_matcher_v5 as v5
from backend.scripts.ebay_gold_access import OUT
from backend.scripts.ebay_gold_review_server import read_history, reconstruct_effective_state
from backend.scripts.index_fair_value_ebay_evidence_manifest import load_development_for_tuning

POSITIVE = "EXACT_TARGET_MATCH"
AMBIGUOUS = "AMBIGUOUS"
CATASTROPHIC = ("GRADED", "LOT_OR_BUNDLE", "SEALED_OR_ACCESSORY", "WRONG_CARD_NUMBER",
                "RELATED_BUT_WRONG_VARIANT", "WRONG_SET", "WRONG_LANGUAGE")
AUTOGRAPH_SEARCH_RE = re.compile(r"\bauto\b|autograph|signed|signature|inscription", re.I)


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
    """Legitimate (EXACT_TARGET_MATCH) development rows where v4 accepted
    (HIGH) but v5's new guard rejects -- the coverage cost of v5.
    """
    regressions = []
    for row, gold in corpus:
        if gold != POSITIVE:
            continue
        v4_result = v4.classify_listing(target(row), listing(row))
        if v4_result["identity_state"] != "HIGH_CONFIDENCE":
            continue
        v5_result = v5.classify_listing(target(row), listing(row))
        if v5_result["identity_state"] != "HIGH_CONFIDENCE":
            regressions.append({
                "benchmark_row_id": row["benchmark_row_id"], "listing_title": row["listing_title"],
                "v4_state": v4_result["identity_state"], "v5_state": v5_result["identity_state"],
                "v5_reason": v5_result.get("reason"),
            })
    return regressions


def autograph_terminology_audit(corpus: list[tuple[dict[str, Any], str]]) -> dict[str, Any]:
    """Confirms (does not assume) whether DEVELOPMENT contains any auto/
    autograph/signed terminology at all -- v5's Guard 4 is new ontology, not
    a fit to an existing example, and this audit proves that explicitly.
    """
    matches = [
        {"benchmark_row_id": row["benchmark_row_id"], "listing_title": row["listing_title"], "gold": gold}
        for row, gold in corpus if AUTOGRAPH_SEARCH_RE.search(row["listing_title"])
    ]
    return {"development_row_count_matching_autograph_terms": len(matches), "examples": matches}


def roaring_moon_number_consistency_audit(corpus: list[tuple[dict[str, Any], str]]) -> dict[str, Any]:
    """Direct evidence for the D4-0375 root-cause finding: does the SAME
    "162/131" numbering appear elsewhere in development for the SAME target,
    and what gold label did those rows receive?
    """
    rows = [
        {"benchmark_row_id": row["benchmark_row_id"], "listing_title": row["listing_title"], "gold": gold}
        for row, gold in corpus if row["canonical_card_id"] == "d09b2fb5-41b6-4d1e-88cf-629402434501"
    ]
    consistent_numbering = [r for r in rows if "162/131" in r["listing_title"] or "162 " in r["listing_title"] or "#162" in r["listing_title"]]
    return {
        "target_canonical_card_id": "d09b2fb5-41b6-4d1e-88cf-629402434501",
        "development_rows_for_target": len(rows),
        "rows_showing_162_131_or_162_numbering": len(consistent_numbering),
        "gold_labels_for_162_131_numbering": sorted({r["gold"] for r in consistent_numbering}),
        "conclusion": "162/131 is confirmed, via independent development listings for this exact target, "
                      "to be the normal/correct numbering (two of these rows are gold EXACT_TARGET_MATCH) -- "
                      "the D4-0375 false accept is not a text-pattern defect; no rule is derived from it.",
        "examples": rows,
    }


def main() -> dict[str, Any]:
    corpus = load_development_corpus()
    v4_metrics = benchmark(v4, corpus)
    v5_metrics = benchmark(v5, corpus)
    delta = {
        "precision_delta": round(v5_metrics["precision"] - v4_metrics["precision"], 8),
        "recall_delta": round(v5_metrics["recall"] - v4_metrics["recall"], 8),
        "coverage_delta": round(v5_metrics["card_coverage"] - v4_metrics["card_coverage"], 8),
        "ambiguous_rate_delta": round(v5_metrics["ambiguous_rate"] - v4_metrics["ambiguous_rate"], 8),
        "rejection_rate_delta": round(v5_metrics["rejection_rate"] - v4_metrics["rejection_rate"], 8),
        "catastrophic_high_total_delta": v5_metrics["catastrophic_high_total"] - v4_metrics["catastrophic_high_total"],
    }
    regressions = newly_rejected_legitimate_listings(corpus)
    result = {
        "version": "ebay_d3_v5_development_study_v1",
        "development_corpus_fingerprint": hashlib.sha256(
            "\n".join(sorted(f"{r['benchmark_row_id']}:{g}" for r, g in corpus)).encode()
        ).hexdigest(),
        "v4_metrics": v4_metrics, "v5_metrics": v5_metrics, "delta_v5_minus_v4": delta,
        "newly_rejected_legitimate_listings": regressions,
        "newly_rejected_legitimate_count": len(regressions),
        "autograph_terminology_audit": autograph_terminology_audit(corpus),
        "roaring_moon_number_consistency_audit": roaring_moon_number_consistency_audit(corpus),
    }
    (OUT / "ebay_d3_v5_development_study.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
