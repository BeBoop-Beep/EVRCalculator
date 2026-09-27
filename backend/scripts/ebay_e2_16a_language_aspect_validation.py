"""EBAY E2.16A -- frozen human-truth Language-aspect validation.

DEVELOPMENT ONLY. Reads the frozen E2.16 development corpus (queue CSV with
materialized human_truth_label + raw_internal.jsonl with hidden getItem
Language aspect evidence), joins them by row_id, audits normalization,
computes the confusion matrix for a candidate LANGUAGE-v1 veto, and (if
freeze criteria are met) produces the LANGUAGE-v1 / COMBINED-IDENTITY-v3
contract fingerprints consumed by the report.

This module performs NO production writes and does not touch D3-v5,
IMAGE-v2, CAPTURE-ALLOCATION-v2, or the E2.14 frozen certification files.
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

QUEUE_PATH = OUT / "ebay_e2_16_language_development_queue.csv"
RAW_PATH = OUT / "ebay_e2_16_language_development_raw_internal.jsonl"
MANIFEST_PATH = OUT / "ebay_e2_16_language_development_manifest.json"
HISTORY_PATH = OUT / "ebay_e2_16_language_development_review_history.jsonl"

EXPECTED_CORPUS_FP = "8a22b6a76bb2eade33b0e0dddbba49a3ac8203067dcfcb3d291d4ffe07f0319f"
EXPECTED_LABEL_FP = "1934c5f038f62584432c32d5538983b851a2a63a1cb8a3a972f09a5e7d7fd46c"
EXPECTED_COUNTS = {"ENGLISH": 134, "NON_ENGLISH": 63, "UNCERTAIN": 3}

HUMAN_TRUTH_CHOICES = ("ENGLISH", "NON_ENGLISH", "UNCERTAIN")


# --------------------------------------------------------------------------
# Phase A -- precondition check
# --------------------------------------------------------------------------

def load_queue_rows() -> list[dict[str, Any]]:
    with QUEUE_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_raw_rows() -> list[dict[str, Any]]:
    rows = []
    with RAW_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_history() -> list[dict[str, Any]]:
    events = []
    with HISTORY_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def cohort_fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "|".join(sorted(f"{r['row_id']}:{r['listing_item_id']}" for r in rows)).encode()
    ).hexdigest()


def label_fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        "\n".join(sorted(f"{r['row_id']}:{r['human_truth_label']}" for r in rows)).encode()
    ).hexdigest()


class PreconditionFailure(RuntimeError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def check_preconditions() -> dict[str, Any]:
    results: dict[str, Any] = {}

    if not (QUEUE_PATH.exists() and RAW_PATH.exists() and MANIFEST_PATH.exists() and HISTORY_PATH.exists()):
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_ARTIFACTS_MISSING",
                                   "one or more of queue/raw/manifest/history files missing")

    rows = load_queue_rows()
    raw_rows = load_raw_rows()
    manifest = load_manifest()
    history = load_history()

    # 1. row count = 200
    results["row_count"] = len(rows)
    if len(rows) != 200:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_ROW_COUNT_MISMATCH", f"got {len(rows)}")

    # 2. corpus fingerprint matches
    recomputed_corpus_fp = cohort_fingerprint(rows)
    manifest_corpus_fp = manifest.get("corpus_fingerprint")
    results["corpus_fingerprint_recomputed"] = recomputed_corpus_fp
    results["corpus_fingerprint_manifest"] = manifest_corpus_fp
    results["corpus_fingerprint_expected"] = EXPECTED_CORPUS_FP
    if recomputed_corpus_fp != manifest_corpus_fp:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_CORPUS_FINGERPRINT_MISMATCH",
                                   f"recomputed={recomputed_corpus_fp} manifest={manifest_corpus_fp}")
    if recomputed_corpus_fp != EXPECTED_CORPUS_FP:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_CORPUS_FINGERPRINT_UNEXPECTED",
                                   f"recomputed={recomputed_corpus_fp} expected(spec)={EXPECTED_CORPUS_FP}")

    # 4. labels complete (human_truth_label present + valid for all 200 rows)
    if "human_truth_label" not in rows[0]:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_LABELS_NOT_MATERIALIZED",
                                   "queue CSV has no human_truth_label column -- freeze was never run")
    incomplete = [r["row_id"] for r in rows if r.get("human_truth_label", "").strip() not in HUMAN_TRUTH_CHOICES]
    results["incomplete_rows"] = incomplete
    if incomplete:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_INCOMPLETE_LABELS",
                                   f"{len(incomplete)} rows incomplete/invalid, e.g. {incomplete[:5]}")

    # 3. human label fingerprint matches
    recomputed_label_fp = label_fingerprint(rows)
    manifest_label_fp = manifest.get("label_fingerprint")
    results["label_fingerprint_recomputed"] = recomputed_label_fp
    results["label_fingerprint_manifest"] = manifest_label_fp
    results["label_fingerprint_expected"] = EXPECTED_LABEL_FP
    if recomputed_label_fp != manifest_label_fp:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_LABEL_FINGERPRINT_MISMATCH",
                                   f"recomputed={recomputed_label_fp} manifest={manifest_label_fp}")
    if recomputed_label_fp != EXPECTED_LABEL_FP:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_LABEL_FINGERPRINT_UNEXPECTED",
                                   f"recomputed={recomputed_label_fp} expected(spec)={EXPECTED_LABEL_FP}")

    # 5. counts remain ENGLISH 134 / NON_ENGLISH 63 / UNCERTAIN 3
    from collections import Counter
    counts = dict(Counter(r["human_truth_label"] for r in rows))
    results["label_counts"] = counts
    if counts != EXPECTED_COUNTS:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_LABEL_COUNTS_MISMATCH",
                                   f"got {counts} expected {EXPECTED_COUNTS}")

    # 6/7. development_only=true, production_authority=false
    results["development_only"] = manifest.get("development_only")
    results["production_authority"] = manifest.get("production_authority")
    if manifest.get("development_only") is not True or manifest.get("production_authority") is not False:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_AUTHORITY_FLAGS_WRONG",
                                   f"development_only={manifest.get('development_only')} production_authority={manifest.get('production_authority')}")

    # 8. raw internal evidence row IDs match reviewer rows exactly
    raw_ids = set(r["row_id"] for r in raw_rows)
    queue_ids = set(r["row_id"] for r in rows)
    results["raw_row_count"] = len(raw_rows)
    results["raw_ids_match_queue_ids"] = raw_ids == queue_ids
    if raw_ids != queue_ids:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_RAW_ROW_ID_MISMATCH",
                                   f"raw-only={sorted(raw_ids - queue_ids)[:5]} queue-only={sorted(queue_ids - raw_ids)[:5]}")

    # 9. no post-freeze human-label mutation
    manifest_check = manifest.get("labels_frozen")
    freeze_ts = manifest.get("freeze_timestamp")
    results["labels_frozen"] = manifest_check
    if not manifest_check or not freeze_ts:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_NOT_FROZEN",
                                   f"labels_frozen={manifest_check} freeze_timestamp={freeze_ts}")
    after_freeze = [e for e in history if e.get("timestamp", "") > freeze_ts]
    results["post_freeze_history_events"] = len(after_freeze)
    if after_freeze:
        raise PreconditionFailure("EBAY_E2_16A_BLOCKED_POST_FREEZE_MUTATION",
                                   f"{len(after_freeze)} history events recorded after freeze_timestamp={freeze_ts}")

    results["all_preconditions_passed"] = True
    return results


# --------------------------------------------------------------------------
# Phase B -- unblind / join
# --------------------------------------------------------------------------

def join_rows() -> list[dict[str, Any]]:
    queue_rows = {r["row_id"]: r for r in load_queue_rows()}
    raw_rows = {r["row_id"]: r for r in load_raw_rows()}
    joined = []
    for row_id, q in queue_rows.items():
        r = raw_rows[row_id]
        assert q["listing_item_id"] == r["listing_item_id"], f"item id mismatch for {row_id}"
        joined.append({
            "row_id": row_id,
            "item_id": r["listing_item_id"],
            "item_url": r.get("item_url", ""),
            "listing_title": r.get("listing_title", ""),
            "human_truth": q["human_truth_label"],
            "human_language_if_known": q.get("human_language_if_known", ""),
            "raw_language_aspect": r.get("language_aspect_raw"),
            "prior_normalized": r.get("language_aspect_normalized"),
            "aspect_present": bool(r.get("language_aspect_present")),
            "development_stratum": r.get("development_stratum", ""),
            "seller_country_context_only": r.get("seller_country_context_only", ""),
            "marketplace": r.get("marketplace", ""),
        })
    return joined


# --------------------------------------------------------------------------
# Phase C -- normalization audit (independent, does not trust E2.15 blindly)
# --------------------------------------------------------------------------

# Conservative normalization map: only raw strings we would actually expect
# eBay's Pokemon-card Language aspect taxonomy to emit. Anything else -> UNKNOWN.
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


def normalization_audit(joined: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from collections import defaultdict
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"row_count": 0, "ENGLISH": 0, "NON_ENGLISH": 0, "UNCERTAIN": 0, "normalized": None})
    for row in joined:
        raw = row["raw_language_aspect"] if row["aspect_present"] else None
        raw_key = raw if raw is not None else "<absent>"
        norm = normalize_raw_value(raw) if row["aspect_present"] else "UNKNOWN"
        b = buckets[raw_key]
        b["raw_value"] = raw_key
        b["normalized"] = norm
        b["row_count"] += 1
        b[row["human_truth"]] += 1
    return sorted(buckets.values(), key=lambda b: (-b["row_count"], b["raw_value"]))


# --------------------------------------------------------------------------
# Phase D -- LANGUAGE-v1 candidate classification
# --------------------------------------------------------------------------

# Values actually observed with >=1 row in this development corpus, restricted
# to those we are willing to treat as authoritative for MISMATCH per Phase H
# freeze criteria (populated after inspecting the normalization audit /
# confusion matrix -- see build_language_v1_contract()).
SUPPORTED_NON_ENGLISH_VALUES_DEFAULT = {"JAPANESE", "KOREAN", "CHINESE", "FRENCH"}


def classify_language_v1(normalized_value: str, supported_non_english: set[str]) -> str:
    if normalized_value == "ENGLISH":
        return "LANGUAGE_MATCH"
    if normalized_value in supported_non_english:
        return "LANGUAGE_MISMATCH"
    return "LANGUAGE_UNVERIFIED"  # includes UNKNOWN, missing, and any non-English value not yet validated


def annotate_language_v1(joined: list[dict[str, Any]], supported_non_english: set[str]) -> list[dict[str, Any]]:
    out = []
    for row in joined:
        raw = row["raw_language_aspect"] if row["aspect_present"] else None
        norm = normalize_raw_value(raw) if row["aspect_present"] else "UNKNOWN"
        state = classify_language_v1(norm, supported_non_english)
        out.append({**row, "normalized_language": norm, "language_v1_state": state})
    return out


# --------------------------------------------------------------------------
# Phase E -- confusion matrix + Wilson CI
# --------------------------------------------------------------------------

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


def confusion_matrix(annotated: list[dict[str, Any]]) -> dict[str, Any]:
    definitive = [r for r in annotated if r["human_truth"] != "UNCERTAIN"]
    tp = sum(1 for r in definitive if r["human_truth"] == "NON_ENGLISH" and r["language_v1_state"] == "LANGUAGE_MISMATCH")
    fp = sum(1 for r in definitive if r["human_truth"] == "ENGLISH" and r["language_v1_state"] == "LANGUAGE_MISMATCH")
    fn = sum(1 for r in definitive if r["human_truth"] == "NON_ENGLISH" and r["language_v1_state"] != "LANGUAGE_MISMATCH")
    tn = sum(1 for r in definitive if r["human_truth"] == "ENGLISH" and r["language_v1_state"] != "LANGUAGE_MISMATCH")
    n_english = sum(1 for r in definitive if r["human_truth"] == "ENGLISH")
    n_non_english = sum(1 for r in definitive if r["human_truth"] == "NON_ENGLISH")
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    false_mismatch_rate = fp / n_english if n_english else None
    recognized_explicit = sum(1 for r in definitive if r["normalized_language"] not in ("UNKNOWN",))
    coverage = recognized_explicit / len(definitive) if definitive else None
    return {
        "definitive_rows": len(definitive),
        "n_human_english": n_english,
        "n_human_non_english": n_non_english,
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "mismatch_precision": precision,
        "mismatch_precision_wilson_ci": wilson_ci(tp, tp + fp) if (tp + fp) else None,
        "mismatch_recall": recall,
        "mismatch_recall_wilson_ci": wilson_ci(tp, tp + fn) if (tp + fn) else None,
        "false_mismatch_rate_on_human_english": false_mismatch_rate,
        "false_mismatch_rate_wilson_ci": wilson_ci(fp, n_english) if n_english else None,
        "structured_aspect_coverage": coverage,
    }


# --------------------------------------------------------------------------
# Phase F -- per-language breakdown
# --------------------------------------------------------------------------

def per_language_breakdown(annotated: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Breakdown keyed by the human-identified non-English language, inferred
    conservatively from human_language_if_known free text when present, else
    from the normalized aspect value as a fallback grouping key for reporting
    only (never used to compute confusion-matrix truth)."""
    non_english_rows = [r for r in annotated if r["human_truth"] == "NON_ENGLISH"]
    from collections import defaultdict
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in non_english_rows:
        key = (r.get("human_language_if_known") or "").strip()
        if not key:
            # fall back to normalized aspect value's language name, else UNSPECIFIED
            key = r["normalized_language"] if r["normalized_language"] not in ("UNKNOWN",) else "UNSPECIFIED"
        groups[key.upper()].append(r)
    out = {}
    for lang, rows in groups.items():
        present = [r for r in rows if r["aspect_present"]]
        # "correct" = aspect explicitly names a real non-English language,
        # regardless of whether that value is on the current authoritative
        # allowlist (Phase F reports raw aspect fidelity; Phase H decides
        # which values are trusted enough to veto).
        correct = [r for r in present if r["normalized_language"] not in ("ENGLISH", "UNKNOWN")]
        wrong_english = [r for r in present if r["normalized_language"] == "ENGLISH"]
        missing = [r for r in rows if not r["aspect_present"]]
        unknown_aspect = [r for r in present if r["normalized_language"] == "UNKNOWN"]
        out[lang] = {
            "human_count": len(rows),
            "aspect_present": len(present),
            "correct_non_english_aspect": len(correct),
            "missing_aspect": len(missing),
            "wrong_aspect_says_english": len(wrong_english),
            "unknown_aspect_value": len(unknown_aspect),
        }
    return out


# --------------------------------------------------------------------------
# Phase G -- conflict forensics
# --------------------------------------------------------------------------

def conflicts(annotated: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    c1 = [r for r in annotated if r["human_truth"] == "ENGLISH" and r["normalized_language"] not in ("ENGLISH", "UNKNOWN")]
    c2 = [r for r in annotated if r["human_truth"] == "NON_ENGLISH" and r["normalized_language"] == "ENGLISH"]
    c3 = []  # human NON_ENGLISH with a *conflicting* foreign aspect value vs human_language_if_known -- see note in report; none expected structurally since aspect isn't compared to free text here beyond c1/c2
    c4 = [r for r in annotated if r["human_truth"] == "UNCERTAIN" and r["aspect_present"]]
    return {
        "human_english_aspect_non_english": c1,
        "human_non_english_aspect_english": c2,
        "human_non_english_conflicting_foreign_aspect": c3,
        "human_uncertain_with_explicit_aspect": c4,
    }


if __name__ == "__main__":
    results = check_preconditions()
    print(json.dumps(results, indent=2, default=str))
