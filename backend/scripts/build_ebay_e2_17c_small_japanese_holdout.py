"""EBAY E2.17C -- Phase D: small independent Japanese-vs-not-Japanese
DEVELOPMENT HOLDOUT capture.

DEVELOPMENT-ONLY. Not certification, not production authority. Runs ONLY
after OCR-v2 is frozen (see ebay_e2_17c_ocr_v2_korean_reader_fix.py and
EBAY_E2_17C_OCR_V2_AND_SMALL_JAPANESE_HOLDOUT_PREP.md). Captures a SMALL new
live-eBay corpus for a later E2.17D human-labeling pass. Performs NO OCR,
NO human labeling, and NO evaluation itself.

Sampling design (task spec):
  JAPANESE-CANDIDATE STRATUM     ~24-26 rows -- Japanese-targeted query OR
                                                  provider Language=Japanese
  NOT-JAPANESE HARD NEGATIVE     ~12-14 rows -- Korean-targeted, Chinese-
                                                  targeted, or English-control
                                                  queries / provider values
Target total: 35-40 rows (do not exceed ~45 without strong reason).
Sampling metadata (query term, provider language) is NOT human truth and is
NEVER exposed to the reviewer -- see FORBIDDEN_REVIEWER_COLUMNS in
ebay_e2_17c_holdout_review_server.py.

INDEPENDENCE: historical exclusion set is the union of the E2.16 builder's
own HISTORICAL_FILES list (covers D2, D3 v3/v4/v5, V4, V5, E2.9B, E2.13,
E2.14 predictions, E2.15 study) PLUS the E2.16 queue itself (covers E2.16 +
E2.16A) PLUS the E2.16B queue (covers E2.16B) PLUS the E2.17 combined-corpus
split + E2.17A specific-language queue (covers E2.17/E2.17A/E2.17B, which
never captured new listings of its own -- it only relabeled the E2.16/E2.16B
rows already excluded above; included here anyway for defense in depth).
Canonical-card-id novelty is tracked and reported, not silently assumed.

CRITICAL: this script never runs OCR-v2 (or OCR-v1) against captured rows,
and never reads any OCR output to choose which rows to keep. Selection is
strictly query-stratum + provider-Language based, per the task's "sampling
metadata is NOT human truth" rule.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.scripts.index_fair_value_ebay_evidence_collector import (
    ROOT,
    TokenProvider,
    load_ebay_env,
)
from backend.services.ebay_language_evidence_v1 import normalize_language_value  # research parser only
from backend.scripts.build_ebay_e2_16_language_development_cohort import (
    HISTORICAL_FILES as E216_HISTORICAL_FILES,
    E214_PREDICTIONS_PATH,
    E215_STUDY_PATH,
)

ARTIFACTS_DIR = ROOT / "backend/artifacts/index_fair_value"
QUEUE_PATH = ARTIFACTS_DIR / "ebay_e2_17c_small_japanese_holdout_queue.csv"
MANIFEST_PATH = ARTIFACTS_DIR / "ebay_e2_17c_small_japanese_holdout_manifest.json"
RAW_INTERNAL_PATH = ARTIFACTS_DIR / "ebay_e2_17c_small_japanese_holdout_raw_internal.jsonl"

E216_QUEUE_PATH = ARTIFACTS_DIR / "ebay_e2_16_language_development_queue.csv"
E216B_QUEUE_PATH = ARTIFACTS_DIR / "ebay_e2_16b_japanese_language_development_queue.csv"
E217_SPLIT_PATH = ARTIFACTS_DIR / "ebay_e2_17_combined_corpus_split.json"
E217A_QUEUE_PATH = ARTIFACTS_DIR / "ebay_e2_17_japanese_specific_language_review_queue.csv"

SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/{item_id}"
CATEGORY_ID = "183454"

CORPUS_VERSION = "ebay_e2_17c_small_japanese_holdout_v1"

MAX_SEARCH_REQUESTS = 120
MAX_GETITEM_REQUESTS = 200
TARGET_JAPANESE_CANDIDATE = 25
TARGET_NOT_JAPANESE = 13
TARGET_TOTAL_MAX = 45

STRATUM_JAPANESE_CANDIDATE = "JAPANESE_CANDIDATE"
STRATUM_NOT_JAPANESE_KOREAN_QUERY = "NOT_JAPANESE_KOREAN_QUERY"
STRATUM_NOT_JAPANESE_CHINESE_QUERY = "NOT_JAPANESE_CHINESE_QUERY"
STRATUM_NOT_JAPANESE_ENGLISH_CONTROL = "NOT_JAPANESE_ENGLISH_CONTROL"

# Reviewer never sees: provider Language, sampling stratum, query term,
# OCR-anything, seller/listing title (title can leak language). Reviewer
# sees only row id + image(s) + minimal navigation context.
REVIEWER_VISIBLE_COLUMNS = ["row_id", "canonical_card_id", "image_url",
                            "human_truth_label", "human_note", "reviewer_id",
                            "label_timestamp"]

FORBIDDEN_REVIEWER_COLUMNS = frozenset({
    "language_aspect_raw", "language_aspect_normalized", "language_aspect_present",
    "development_stratum", "search_language_term", "listing_title",
    "ocr_v2_decision", "japanese_kana_count", "korean_hangul_count",
    "cjk_shared_count", "confidence", "seller_query_language",
})


def _load_env_and_token():
    cfg = load_ebay_env()
    tp = TokenProvider(cfg)
    return tp.get()


def normalize_language_aspect(raw_value: str | None) -> str:
    if raw_value is None:
        return "UNKNOWN"
    normalized = normalize_language_value(raw_value)
    if normalized is None:
        return "OTHER"
    known = {"English", "Japanese", "Korean", "Chinese", "German", "French",
              "Spanish", "Italian", "Portuguese"}
    return normalized.upper() if normalized in known else "OTHER"


def _collect_historical_exclusions() -> dict[str, Any]:
    exact_ids: set[str] = set()
    canonical_card_ids: set[str] = set()
    counts: dict[str, int] = {}

    for name in E216_HISTORICAL_FILES:
        path = ARTIFACTS_DIR / name
        if not path.exists():
            counts[name] = -1
            continue
        n = 0
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if "listing_item_id" not in (reader.fieldnames or []):
                counts[name] = -2
                continue
            for row in reader:
                v = str(row.get("listing_item_id") or "").strip()
                if v:
                    exact_ids.add(v)
                    n += 1
        counts[name] = n

    n214 = 0
    if E214_PREDICTIONS_PATH.exists():
        data = json.loads(E214_PREDICTIONS_PATH.read_text(encoding="utf-8"))
        for row in data.get("predictions", {}).values():
            v = str(row.get("listing_item_id") or "").strip()
            if v:
                exact_ids.add(v)
                n214 += 1
    counts["ebay_e2_14_fresh_blind_predictions.json"] = n214

    n215 = 0
    if E215_STUDY_PATH.exists():
        data = json.loads(E215_STUDY_PATH.read_text(encoding="utf-8"))
        for row in data.get("results", []):
            v = str(row.get("item_id") or "").strip()
            if v:
                exact_ids.add(v)
                n215 += 1
    counts["ebay_e2_15_item_detail_language_study.json"] = n215

    # E2.16 (covers E2.16 + E2.16A, which never added new listings)
    n216 = 0
    if E216_QUEUE_PATH.exists():
        with E216_QUEUE_PATH.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                v = str(row.get("listing_item_id") or "").strip()
                if v:
                    exact_ids.add(v)
                    n216 += 1
                cc = str(row.get("canonical_card_id") or "").strip()
                if cc:
                    canonical_card_ids.add(cc)
    counts["ebay_e2_16_language_development_queue.csv"] = n216

    # E2.16B (covers E2.16B + all of E2.17/E2.17A/E2.17B, which only
    # relabeled rows sourced from E2.16/E2.16B and never captured new
    # listings of their own).
    n216b = 0
    if E216B_QUEUE_PATH.exists():
        with E216B_QUEUE_PATH.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                v = str(row.get("listing_item_id") or "").strip()
                if v:
                    exact_ids.add(v)
                    n216b += 1
    counts["ebay_e2_16b_japanese_language_development_queue.csv"] = n216b

    # Defense in depth: E2.17 split + E2.17A queue canonical_card_ids
    # (these never carry a distinct listing_item_id not already covered
    # above, but their canonical_card_id set is recorded for novelty
    # reporting).
    n217a = 0
    if E217A_QUEUE_PATH.exists():
        with E217A_QUEUE_PATH.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                cc = str(row.get("canonical_card_id") or "").strip()
                if cc:
                    canonical_card_ids.add(cc)
                    n217a += 1
    counts["ebay_e2_17_japanese_specific_language_review_queue.csv (canonical_card_id only)"] = n217a

    return {
        "exact_ids": exact_ids,
        "prior_canonical_card_ids": canonical_card_ids,
        "counts_per_file": counts,
        "total_excluded_listing_ids": len(exact_ids),
        "total_prior_canonical_card_ids": len(canonical_card_ids),
    }


def _search(token: str, query: str, budget: dict[str, int]) -> list[dict[str, Any]]:
    if budget["search"] >= MAX_SEARCH_REQUESTS:
        return []
    params = urllib.parse.urlencode({
        "q": query, "category_ids": CATEGORY_ID, "limit": 30,
        "filter": "buyingOptions:{FIXED_PRICE|AUCTION}",
    })
    url = f"{SEARCH_URL}?{params}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Accept": "application/json",
    })
    budget["search"] += 1
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("itemSummaries") or []
    except urllib.error.HTTPError:
        budget["search_errors"] = budget.get("search_errors", 0) + 1
        return []
    except Exception:
        budget["search_errors"] = budget.get("search_errors", 0) + 1
        return []


def _get_item(token: str, item_id: str, budget: dict[str, int]) -> dict[str, Any] | None:
    if budget["getitem"] >= MAX_GETITEM_REQUESTS:
        return None
    url = ITEM_URL.format(item_id=urllib.parse.quote(item_id, safe=""))
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Accept": "application/json",
    })
    budget["getitem"] += 1
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        budget["getitem_errors"] = budget.get("getitem_errors", 0) + 1
        return None


def _extract_language_aspect(item: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    localized = item.get("localizedAspects") or []
    for a in localized:
        if isinstance(a, dict) and str(a.get("name") or "").strip().lower() == "language":
            return a.get("value"), {"localized_aspect_count": len(localized)}
    return None, {"localized_aspect_count": len(localized)}


def _all_image_urls(item: dict[str, Any], listing: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    primary = item.get("image") or {}
    if isinstance(primary, dict) and primary.get("imageUrl"):
        urls.append(primary["imageUrl"])
    for extra in item.get("additionalImages") or []:
        if isinstance(extra, dict) and extra.get("imageUrl"):
            urls.append(extra["imageUrl"])
    if not urls:
        limg = listing.get("image") if isinstance(listing.get("image"), dict) else {}
        if limg.get("imageUrl"):
            urls.append(limg["imageUrl"])
    seen: set[str] = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def cohort_fingerprint(rows: list[dict[str, Any]]) -> str:
    ids = sorted(f"{r['row_id']}:{r['listing_item_id']}" for r in rows)
    return hashlib.sha256("|".join(ids).encode()).hexdigest()


def build(pilot_limit: int = 70, seed: int = 217003, ocr_v2_freeze_fingerprint: str = "") -> dict[str, Any]:
    exclusions = _collect_historical_exclusions()
    exact_excluded = exclusions["exact_ids"]

    pilot = json.loads((ARTIFACTS_DIR / "ebay_pilot_cohort.json").read_text(encoding="utf-8"))
    cards = pilot["cards"][:pilot_limit]

    token = _load_env_and_token()
    budget = {"search": 0, "getitem": 0}

    rng = random.Random(seed)
    order = list(range(len(cards)))
    rng.shuffle(order)

    # One-listing-per-canonical-card-id preference for independence.
    seen_item_ids: set[str] = set()
    used_canonical_ids: set[str] = set()
    candidates: list[dict[str, Any]] = []

    # Query plan cycles: Japanese-targeted (drives JAPANESE_CANDIDATE),
    # Korean-targeted + Chinese-targeted + plain English-control (drive
    # NOT_JAPANESE hard negatives).
    query_plan = [
        ("Japanese", STRATUM_JAPANESE_CANDIDATE),
        ("Korean", STRATUM_NOT_JAPANESE_KOREAN_QUERY),
        ("Chinese", STRATUM_NOT_JAPANESE_CHINESE_QUERY),
        (None, STRATUM_NOT_JAPANESE_ENGLISH_CONTROL),
    ]

    idx = 0
    max_iters = len(order) * len(query_plan)
    while budget["search"] < MAX_SEARCH_REQUESTS and idx < max_iters:
        ci = order[idx % len(order)]
        term, query_stratum = query_plan[idx % len(query_plan)]
        idx += 1
        card = cards[ci]
        name = str(card["card_name"]).strip()
        number = str(card.get("card_number") or "").strip()
        set_name = str(card["set_name"]).strip()
        base = f"{name} {number} {set_name} Pokemon card"
        query_text = base if term is None else f"{base} {term}"
        results = _search(token, query_text, budget)
        for item in results:
            item_id = str(item.get("itemId") or "")
            if not item_id or item_id in seen_item_ids or item_id in exact_excluded:
                continue
            seen_item_ids.add(item_id)
            candidates.append({"card": card, "search_language_term": term,
                                 "query_stratum": query_stratum, "listing": item})

    internal_rows: list[dict[str, Any]] = []
    rng.shuffle(candidates)
    strata_seen: dict[str, int] = {}
    novel_canonical_count = 0
    reused_canonical_count = 0

    for cand in candidates:
        if budget["getitem"] >= MAX_GETITEM_REQUESTS or len(internal_rows) >= TARGET_TOTAL_MAX:
            break
        query_stratum = cand["query_stratum"]
        cap = TARGET_JAPANESE_CANDIDATE if query_stratum == STRATUM_JAPANESE_CANDIDATE else (TARGET_NOT_JAPANESE // 3 + 2)
        if strata_seen.get(query_stratum, 0) >= cap:
            continue
        card = cand["card"]
        canonical_id = card.get("canonical_card_id", "")
        # Prefer one listing per canonical_card_id within THIS holdout.
        if canonical_id in used_canonical_ids:
            continue

        listing = cand["listing"]
        item_id = str(listing.get("itemId") or "")
        item = _get_item(token, item_id, budget)
        if item is None:
            continue
        raw_lang, extra = _extract_language_aspect(item)
        normalized = normalize_language_aspect(raw_lang)
        title = str(item.get("title") or listing.get("title") or "")
        image_urls = _all_image_urls(item, listing)
        if not image_urls:
            continue

        used_canonical_ids.add(canonical_id)
        if canonical_id and canonical_id not in exclusions["prior_canonical_card_ids"]:
            novel_canonical_count += 1
        elif canonical_id:
            reused_canonical_count += 1

        strata_seen[query_stratum] = strata_seen.get(query_stratum, 0) + 1
        internal_rows.append({
            "row_id": f"e2_17c_holdout_{len(internal_rows):04d}",
            "listing_item_id": item_id,
            "item_url": item.get("itemWebUrl") or listing.get("itemWebUrl") or "",
            "listing_title": title,
            "image_url": image_urls[0],
            "image_urls_json": json.dumps(image_urls),
            "canonical_card_id": canonical_id,
            "target_card_name": card.get("card_name", ""),
            "target_set_name": card.get("set_name", ""),
            "target_card_number": card.get("card_number", ""),
            "search_language_term": cand["search_language_term"] or "",
            "development_stratum": query_stratum,
            "language_aspect_raw": raw_lang,
            "language_aspect_normalized": normalized,
            "capture_timestamp": datetime.now(timezone.utc).isoformat(),
        })

    RAW_INTERNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RAW_INTERNAL_PATH.open("w", encoding="utf-8") as fh:
        for row in internal_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    reviewer_rows = []
    for row in internal_rows:
        r = {
            "row_id": row["row_id"],
            "canonical_card_id": row["canonical_card_id"],
            "image_url": row["image_url"],
            "human_truth_label": "",
            "human_note": "",
            "reviewer_id": "",
            "label_timestamp": "",
        }
        reviewer_rows.append(r)

    with QUEUE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEWER_VISIBLE_COLUMNS)
        writer.writeheader()
        writer.writerows(reviewer_rows)

    strata_counts = {s: strata_seen.get(s, 0) for s in
                      [STRATUM_JAPANESE_CANDIDATE, STRATUM_NOT_JAPANESE_KOREAN_QUERY,
                       STRATUM_NOT_JAPANESE_CHINESE_QUERY, STRATUM_NOT_JAPANESE_ENGLISH_CONTROL]}
    not_japanese_total = (strata_counts[STRATUM_NOT_JAPANESE_KOREAN_QUERY]
                           + strata_counts[STRATUM_NOT_JAPANESE_CHINESE_QUERY]
                           + strata_counts[STRATUM_NOT_JAPANESE_ENGLISH_CONTROL])

    fingerprint = cohort_fingerprint(internal_rows)
    manifest = {
        "version": CORPUS_VERSION,
        "development_holdout": True,
        "production_authority": False,
        "ocr_v2_freeze_fingerprint": ocr_v2_freeze_fingerprint,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_fingerprint": fingerprint,
        "row_count": len(internal_rows),
        "japanese_candidate_count": strata_counts[STRATUM_JAPANESE_CANDIDATE],
        "not_japanese_hard_negative_count": not_japanese_total,
        "strata_counts": strata_counts,
        "unique_canonical_card_ids": len(used_canonical_ids),
        "novel_canonical_card_ids_vs_prior_ocr_development": novel_canonical_count,
        "reused_canonical_card_ids_vs_prior_ocr_development": reused_canonical_count,
        "search_request_count": budget["search"],
        "getitem_request_count": budget["getitem"],
        "search_errors": budget.get("search_errors", 0),
        "getitem_errors": budget.get("getitem_errors", 0),
        "historical_exclusion": {
            "counts_per_file": exclusions["counts_per_file"],
            "total_excluded_listing_ids": exclusions["total_excluded_listing_ids"],
            "total_prior_canonical_card_ids_tracked": exclusions["total_prior_canonical_card_ids"],
            "sources_covered": [
                "D2 (ebay_manual_gold_labels/ebay_gold_*)",
                "D3 v3/v4/v5 (ebay_d3_*_blind_queue/coverage/precision/forensics)",
                "V4 (ebay_gold_development/validation/final_blind)",
                "V5 (ebay_d3_v5_fresh_blind_queue)",
                "E2.9B (ebay_e2_9b_fresh_blind_queue)",
                "E2.13/E2.14 (ebay_e2_13_fresh_blind_queue + ebay_e2_14_fresh_blind_predictions.json)",
                "E2.15 (ebay_e2_15_item_detail_language_study.json)",
                "E2.16/E2.16A (ebay_e2_16_language_development_queue.csv)",
                "E2.16B (ebay_e2_16b_japanese_language_development_queue.csv)",
                "E2.17/E2.17A/E2.17B (canonical_card_id defense-in-depth; these cohorts captured no new listings of their own -- all rows sourced from E2.16/E2.16B, already excluded above)",
            ],
        },
        "review_session_id": None,
        "reviewed_count": 0,
        "queue_path": str(QUEUE_PATH.relative_to(ROOT)),
        "internal_raw_path": str(RAW_INTERNAL_PATH.relative_to(ROOT)),
        "ocr_v2_predictions_precomputed": False,  # set true by seal script if run
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import sys
    fp = sys.argv[1] if len(sys.argv) > 1 else ""
    result = build(ocr_v2_freeze_fingerprint=fp)
    print(json.dumps(result, indent=2))
