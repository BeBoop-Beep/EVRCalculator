"""EBAY E2.16B -- Japanese-focused LANGUAGE-v1 DEVELOPMENT corpus extension.

DEVELOPMENT-ONLY. Not certification, not production authority. Does NOT
modify the frozen LANGUAGE-v1 ({KOREAN, CHINESE}) or COMBINED-IDENTITY-v3
contracts. Builds a NEW, dedicated Japanese-targeted human-review corpus to
estimate the precision of eBay Browse getItem's explicit
localizedAspects Language="Japanese" signal against a human-confirmed
ENGLISH/NON_ENGLISH population, so a LATER task (E2.16C) can decide whether
Japanese may be added to the authoritative mismatch vocabulary.

Sampling design (per task spec):
  A. JAPANESE-ASPECT PRIMARY   ~100-120 rows -- getItem Language == Japanese
  B. ENGLISH-ASPECT CONTROLS   ~20-30 rows  -- getItem Language == English
  C. JAPANESE-QUERY HARD CASES ~20-30 rows  -- Japanese-targeted search hit,
                                               but Language aspect missing/unknown

Historical exclusion (exact listing_item_id / item_id match) drawn from
every prior blind/certification/development cohort in this series: D2, D3
(v3/v4/v5), V4, V5, E2.9B, E2.13/E2.14, E2.15, E2.16, E2.16A. This reuses
the exact HISTORICAL_FILES list from build_ebay_e2_16_language_development_cohort.py
(which already covers D2/D3/V4/V5/E2.9B/E2.13) and additionally excludes:
  * the E2.16 development queue + raw internal (covers E2.16 and E2.16A,
    which analyzed the same corpus without adding new listings),
  * the E2.14 fresh-blind predictions (covers the single known catastrophic
    WRONG_LANGUAGE row E13-0127 / v1|407215142815|0),
  * the E2.15 item-detail language study.

Never touches ebay_e2_16_language_development_*.{csv,json,jsonl} (read-only
here). Never freezes LANGUAGE-v1. Never writes public prices, Fair Value,
or Market Explorer state.
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
QUEUE_PATH = ARTIFACTS_DIR / "ebay_e2_16b_japanese_language_development_queue.csv"
MANIFEST_PATH = ARTIFACTS_DIR / "ebay_e2_16b_japanese_language_development_manifest.json"
RAW_INTERNAL_PATH = ARTIFACTS_DIR / "ebay_e2_16b_japanese_language_development_raw_internal.jsonl"

# E2.16 / E2.16A artifacts (read-only historical exclusion sources; this
# task never writes to these files).
E216_QUEUE_PATH = ARTIFACTS_DIR / "ebay_e2_16_language_development_queue.csv"
E216_RAW_PATH = ARTIFACTS_DIR / "ebay_e2_16_language_development_raw_internal.jsonl"

SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/{item_id}"
CATEGORY_ID = "183454"

CORPUS_VERSION = "ebay_e2_16b_japanese_language_development_cohort_v1"

MAX_SEARCH_REQUESTS = 160
MAX_GETITEM_REQUESTS = 320
TARGET_ROWS = 150

STRATUM_JAPANESE_ASPECT_PRIMARY = "JAPANESE_ASPECT_PRIMARY"
STRATUM_ENGLISH_ASPECT_CONTROL = "ENGLISH_ASPECT_CONTROL"
STRATUM_JAPANESE_QUERY_HARD_CASE = "JAPANESE_QUERY_HARD_CASE"
STRATUM_OTHER = "OTHER_UNCLASSIFIED"

QUOTA = {
    STRATUM_JAPANESE_ASPECT_PRIMARY: 120,
    STRATUM_ENGLISH_ASPECT_CONTROL: 30,
    STRATUM_JAPANESE_QUERY_HARD_CASE: 30,
}

REVIEWER_VISIBLE_COLUMNS = [
    "row_id", "listing_item_id", "item_url", "listing_title", "condition",
    "buying_options_json", "seller_id", "image_url", "image_urls_json",
    "target_card_name", "target_set_name", "target_card_number", "target_treatment",
    "human_truth_label", "human_language_if_known", "reviewer_id", "label_timestamp", "review_note",
]

FORBIDDEN_REVIEWER_COLUMNS = frozenset({
    "language_aspect_raw", "language_aspect_normalized", "language_aspect_present",
    "languagev1_state", "combined_policy_output", "localized_aspects_json",
    "development_stratum", "search_language_term",
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
    known = {
        "English", "Japanese", "Korean", "Chinese", "German", "French",
        "Spanish", "Italian", "Portuguese",
    }
    return normalized.upper() if normalized in known else "OTHER"


def _collect_historical_exclusions() -> dict[str, Any]:
    """Union of: every ID already excluded by the E2.16 builder (which
    covers D2, D3 v3/v4/v5, V4, V5, E2.9B, E2.13/E2.14, E2.15) PLUS the
    E2.16 and E2.16A corpus's own listing IDs (so E2.16B never re-samples a
    listing E2.16A already adjudicated, Japanese or not).
    """
    exact_ids: set[str] = set()
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

    # E2.16 development queue (covers E2.16 itself + is analyzed, unmodified,
    # by E2.16A -- so excluding this one file transitively excludes E2.16A).
    n216 = 0
    if E216_QUEUE_PATH.exists():
        with E216_QUEUE_PATH.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                v = str(row.get("listing_item_id") or "").strip()
                if v:
                    exact_ids.add(v)
                    n216 += 1
    counts["ebay_e2_16_language_development_queue.csv"] = n216

    return {"exact_ids": exact_ids, "counts_per_file": counts, "total_excluded_ids": len(exact_ids)}


def _search(token: str, query: str, budget: dict[str, int]) -> list[dict[str, Any]]:
    if budget["search"] >= MAX_SEARCH_REQUESTS:
        return []
    params = urllib.parse.urlencode({
        "q": query, "category_ids": CATEGORY_ID, "limit": 50,
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
            return a.get("value"), {"localized_aspect_count": len(localized), "raw_localized_aspects": localized}
    return None, {"localized_aspect_count": len(localized), "raw_localized_aspects": localized}


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
    # de-dup, preserve order
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


def build(pilot_limit: int = 70, seed: int = 2016002) -> dict[str, Any]:
    exclusions = _collect_historical_exclusions()
    exact_excluded = exclusions["exact_ids"]

    pilot = json.loads((ARTIFACTS_DIR / "ebay_pilot_cohort.json").read_text(encoding="utf-8"))
    cards = pilot["cards"][:pilot_limit]

    token = _load_env_and_token()
    budget = {"search": 0, "getitem": 0}

    rng = random.Random(seed)
    order = list(range(len(cards)))
    rng.shuffle(order)

    seen_item_ids: set[str] = set()
    candidates: list[dict[str, Any]] = []

    # Query plan: for each card, issue ONE Japanese-targeted query (drives
    # strata A/C) and ONE English-control query (drives stratum B), cycling
    # through the pilot catalog until the search budget is exhausted.
    query_plan = ["Japanese", None]

    idx = 0
    while budget["search"] < MAX_SEARCH_REQUESTS and idx < len(order) * len(query_plan):
        ci = order[idx % len(order)]
        term = query_plan[idx % len(query_plan)]
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
            candidates.append({"card": card, "search_language_term": term, "listing": item})

    internal_rows: list[dict[str, Any]] = []
    rng.shuffle(candidates)
    for cand in candidates:
        if budget["getitem"] >= MAX_GETITEM_REQUESTS or len(internal_rows) >= TARGET_ROWS * 3:
            break
        listing = cand["listing"]
        item_id = str(listing.get("itemId") or "")
        item = _get_item(token, item_id, budget)
        if item is None:
            continue
        raw_lang, extra = _extract_language_aspect(item)
        normalized = normalize_language_aspect(raw_lang)
        title = str(item.get("title") or listing.get("title") or "")
        search_term = cand["search_language_term"]

        if normalized == "JAPANESE":
            stratum = STRATUM_JAPANESE_ASPECT_PRIMARY
        elif normalized == "ENGLISH":
            stratum = STRATUM_ENGLISH_ASPECT_CONTROL
        elif search_term == "Japanese" and normalized in ("UNKNOWN", "OTHER") and raw_lang is None:
            stratum = STRATUM_JAPANESE_QUERY_HARD_CASE
        else:
            stratum = STRATUM_OTHER

        image_urls = _all_image_urls(item, listing)
        card = cand["card"]
        internal_rows.append({
            "row_id": f"e2_16b_dev_{len(internal_rows):04d}",
            "listing_item_id": item_id,
            "item_url": item.get("itemWebUrl") or listing.get("itemWebUrl") or "",
            "listing_title": title,
            "condition": item.get("condition") or listing.get("condition") or "",
            "buying_options_json": json.dumps(item.get("buyingOptions") or listing.get("buyingOptions") or []),
            "seller_id": (item.get("seller") or {}).get("username") or "",
            "image_url": image_urls[0] if image_urls else "",
            "image_urls_json": json.dumps(image_urls),
            "canonical_card_id": card.get("canonical_card_id", ""),
            "card_variant_id": card.get("card_variant_id", ""),
            "target_card_name": card.get("card_name", ""),
            "target_set_name": card.get("set_name", ""),
            "target_card_number": card.get("card_number", ""),
            "target_treatment": card.get("treatment_key", ""),
            "search_language_term": search_term or "",
            "development_stratum": stratum,
            "marketplace": item.get("marketplaceId") or "",
            "seller_country_context_only": (item.get("itemLocation") or {}).get("country", ""),
            # internal-only, hidden from reviewer:
            "language_aspect_raw": raw_lang,
            "language_aspect_normalized": normalized,
            "language_aspect_present": raw_lang is not None,
            "localized_aspect_count": extra.get("localized_aspect_count", 0),
            "raw_localized_aspects": extra.get("raw_localized_aspects", []),
            "capture_timestamp": datetime.now(timezone.utc).isoformat(),
        })

    by_stratum: dict[str, list[dict[str, Any]]] = {}
    for row in internal_rows:
        by_stratum.setdefault(row["development_stratum"], []).append(row)

    selected: list[dict[str, Any]] = []
    for stratum, cap in QUOTA.items():
        pool = by_stratum.get(stratum, [])
        selected.extend(pool[:cap])
    if len(selected) < TARGET_ROWS:
        leftover = [r for r in by_stratum.get(STRATUM_OTHER, [])]
        selected.extend(leftover[: TARGET_ROWS - len(selected)])

    for i, row in enumerate(selected):
        row["row_id"] = f"e2_16b_dev_{i:04d}"

    RAW_INTERNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RAW_INTERNAL_PATH.open("w", encoding="utf-8") as fh:
        for row in selected:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    reviewer_rows = []
    for row in selected:
        r = {k: row.get(k, "") for k in REVIEWER_VISIBLE_COLUMNS}
        r["human_truth_label"] = ""
        r["human_language_if_known"] = ""
        r["reviewer_id"] = ""
        r["label_timestamp"] = ""
        r["review_note"] = ""
        reviewer_rows.append(r)

    with QUEUE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEWER_VISIBLE_COLUMNS)
        writer.writeheader()
        writer.writerows(reviewer_rows)

    selected_strata_counts: dict[str, int] = {}
    for row in selected:
        selected_strata_counts[row["development_stratum"]] = selected_strata_counts.get(row["development_stratum"], 0) + 1
    candidate_pool_strata_counts = {s: len(by_stratum.get(s, [])) for s in by_stratum}

    fingerprint = cohort_fingerprint(selected)
    manifest = {
        "version": CORPUS_VERSION,
        "development_only": True,
        "production_authority": False,
        "modifies_frozen_language_v1": False,
        "modifies_frozen_combined_v3": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_fingerprint": fingerprint,
        "row_count": len(selected),
        "candidate_pool_size_before_selection": len(internal_rows),
        "strata_counts_selected": selected_strata_counts,
        "strata_counts_candidate_pool": candidate_pool_strata_counts,
        "target_row_range": [120, 180],
        "target_row_preferred": 150,
        "getitem_request_count": budget["getitem"],
        "search_request_count": budget["search"],
        "search_errors": budget.get("search_errors", 0),
        "getitem_errors": budget.get("getitem_errors", 0),
        "language_aspect_present_count": sum(1 for r in selected if r["language_aspect_present"]),
        "historical_exclusion": {
            "counts_per_file": exclusions["counts_per_file"],
            "total_excluded_ids": exclusions["total_excluded_ids"],
            "sources_covered": [
                "D2 (ebay_manual_gold_labels/ebay_gold_*)",
                "D3 v3/v4/v5 (ebay_d3_*_blind_queue/coverage/precision/forensics)",
                "V4 (ebay_gold_development/validation/final_blind)",
                "V5 (ebay_d3_v5_fresh_blind_queue)",
                "E2.9B (ebay_e2_9b_fresh_blind_queue)",
                "E2.13/E2.14 (ebay_e2_13_fresh_blind_queue + ebay_e2_14_fresh_blind_predictions.json, includes catastrophic row E13-0127 / v1|407215142815|0)",
                "E2.15 (ebay_e2_15_item_detail_language_study.json)",
                "E2.16/E2.16A (ebay_e2_16_language_development_queue.csv, includes false-positive row e2_16_dev_0153 / v1|317094720076|0)",
            ],
        },
        "review_session_id": None,
        "reviewed_count": 0,
        "queue_path": str(QUEUE_PATH.relative_to(ROOT)),
        "internal_raw_path": str(RAW_INTERNAL_PATH.relative_to(ROOT)),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = build()
    print(json.dumps(result, indent=2))
