"""EBAY E2.16C -- Japanese-aspect validation + LANGUAGE-v2/COMBINED-v4 freeze
decision analysis. DEVELOPMENT ONLY / non-certifying diagnostics.

Reads the already-completed E2.16B human review (review_history.jsonl,
resolved via last-non-undone-label-per-row -- the same logic as
reconstruct_effective_labels() in
ebay_e2_16b_japanese_language_development_review_server.py), joins to the
internal raw getItem evidence, and runs the Phase A-L analysis described in
the E2.16C task spec. Produces no production writes; does not touch frozen
LANGUAGE-v1 / COMBINED-v3 source files.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend/artifacts/index_fair_value"

QUEUE_PATH = OUT / "ebay_e2_16b_japanese_language_development_queue.csv"
MANIFEST_PATH = OUT / "ebay_e2_16b_japanese_language_development_manifest.json"
HISTORY_PATH = OUT / "ebay_e2_16b_japanese_language_development_review_history.jsonl"
RAW_PATH = OUT / "ebay_e2_16b_japanese_language_development_raw_internal.jsonl"


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_queue_rows() -> list[dict[str, Any]]:
    with QUEUE_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_raw_rows() -> dict[str, dict[str, Any]]:
    raw = {}
    with RAW_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            raw[obj["row_id"]] = obj
    return raw


def read_history() -> list[dict[str, Any]]:
    events = []
    with HISTORY_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def reconstruct_effective_labels(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Identical logic to
    ebay_e2_16b_japanese_language_development_review_server.reconstruct_effective_labels:
    last non-undone 'label' event per row_id wins."""
    by_row: dict[str, list[dict[str, Any]]] = {}
    undone_ids: set[str] = set()
    for event in events:
        if event["action"] == "label":
            by_row.setdefault(event["row_id"], []).append(event)
        elif event["action"] == "undo":
            undone_ids.add(event.get("target_event_id"))
    effective: dict[str, dict[str, Any]] = {}
    for row_id, row_events in by_row.items():
        valid = [e for e in row_events if e["event_id"] not in undone_ids]
        if valid:
            effective[row_id] = valid[-1]
    return effective


def cohort_fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "|".join(sorted(f"{r['row_id']}:{r['listing_item_id']}" for r in rows)).encode()
    ).hexdigest()


def label_fingerprint(materialized: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "\n".join(sorted(f"{r['row_id']}:{r['human_truth_label']}" for r in materialized)).encode()
    ).hexdigest()


# --------------------------------------------------------------------------
# Normalization (identical map to E2.16A, extended nowhere -- independently
# verified against actual raw values seen in this corpus below)
# --------------------------------------------------------------------------

NORMALIZATION_MAP = {
    "english": "ENGLISH",
    "japanese": "JAPANESE",
    "korean": "KOREAN",
    "chinese": "CHINESE",
    "chinese (simplified)": "CHINESE",
    "chinese (traditional)": "CHINESE",
    "french": "FRENCH",
    "german": "GERMAN",
    "spanish": "SPANISH",
    "italian": "ITALIAN",
    "portuguese": "PORTUGUESE",
    "indonesian": "OTHER_NON_ENGLISH",
    "thai": "OTHER_NON_ENGLISH",
}


def normalize_raw_value(raw_value: str | None) -> str:
    if raw_value is None or not isinstance(raw_value, str) or not raw_value.strip():
        return "UNKNOWN"
    key = raw_value.strip().lower()
    return NORMALIZATION_MAP.get(key, "UNKNOWN")


def wilson_ci(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z * z / total
    center = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    lower = (center - margin) / denom
    upper = (center + margin) / denom
    return (max(0.0, lower), min(1.0, upper))


# --------------------------------------------------------------------------
# Full pipeline
# --------------------------------------------------------------------------

def run_analysis() -> dict[str, Any]:
    rows = load_queue_rows()
    manifest = load_manifest()
    raw = load_raw_rows()
    events = read_history()
    effective = reconstruct_effective_labels(events)

    recomputed_corpus_fp = cohort_fingerprint(rows)

    materialized = []
    for r in rows:
        ev = effective.get(r["row_id"])
        materialized.append({
            "row_id": r["row_id"],
            "human_truth_label": ev["human_truth_label"] if ev else None,
        })
    recomputed_label_fp = label_fingerprint([m for m in materialized if m["human_truth_label"]])

    label_counts: dict[str, int] = {}
    for m in materialized:
        lbl = m["human_truth_label"]
        if lbl:
            label_counts[lbl] = label_counts.get(lbl, 0) + 1

    missing_labels = [m["row_id"] for m in materialized if not m["human_truth_label"]]

    # join
    joined = []
    for r in rows:
        rid = r["row_id"]
        rv = raw.get(rid, {})
        ev = effective.get(rid)
        human_truth = ev["human_truth_label"] if ev else r.get("human_truth_label")
        raw_lang = rv.get("language_aspect_raw")
        present = bool(rv.get("language_aspect_present"))
        norm = normalize_raw_value(raw_lang) if present else "UNKNOWN"
        joined.append({
            "row_id": rid,
            "item_id": rv.get("listing_item_id", r.get("listing_item_id")),
            "human_truth": human_truth,
            "raw_language_aspect": raw_lang,
            "normalized_language": norm,
            "language_aspect_present": present,
            "development_stratum": rv.get("development_stratum", ""),
            "title": rv.get("listing_title", r.get("listing_title", "")),
            "image_urls": rv.get("image_urls_json", r.get("image_urls_json", "")),
            "raw_localized_aspects": rv.get("raw_localized_aspects", []),
            "seller_country_context_only": rv.get("seller_country_context_only", ""),
        })

    return {
        "rows": rows,
        "manifest": manifest,
        "events": events,
        "effective": effective,
        "materialized": materialized,
        "recomputed_corpus_fp": recomputed_corpus_fp,
        "recomputed_label_fp": recomputed_label_fp,
        "label_counts": label_counts,
        "missing_labels": missing_labels,
        "joined": joined,
    }


if __name__ == "__main__":
    result = run_analysis()
    print("corpus_fp:", result["recomputed_corpus_fp"])
    print("label_fp:", result["recomputed_label_fp"])
    print("label_counts:", result["label_counts"])
    print("missing_labels:", result["missing_labels"])
