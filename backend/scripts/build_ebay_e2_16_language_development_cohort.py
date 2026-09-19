"""EBAY E2.16 -- targeted foreign-language DEVELOPMENT cohort builder.

DEVELOPMENT-ONLY. Not certification, not production authority. Builds a
human-review corpus intentionally enriched for foreign-language listings,
English-language controls, and hard language cases, to later (E2.16A,
NOT this task) evaluate whether eBay Browse `getItem`'s explicit
localizedAspects "Language" value can act as a high-precision
wrong-language veto for English-target Pokemon cards.

This script:
  * builds a historical-ID exclusion set from every prior certification /
    blind cohort file plus the E2.15 development study item IDs,
  * issues live Browse `item_summary/search` calls using both ordinary
    (English-control) queries and language-targeting query forms
    (canonical card name + collector number + language term), for the
    existing 70-card pilot cohort,
  * calls `getItem` for surviving candidates (respecting a bounded request
    budget) to retrieve `localizedAspects`, extracts + normalizes the
    Language aspect via the E2.15 research normalizer (research parser
    only -- never frozen, never treated as ground truth),
  * assigns each surviving row to one of four DEVELOPMENT strata (English
    control / non-Latin foreign / Latin-script foreign / ambiguous),
  * writes a reviewer-facing queue CSV (NO Language aspect, NO normalized
    language, NO policy output -- human-observable listing evidence only)
    and an internal raw JSONL that retains everything for a future E2.16A
    analysis script,
  * writes a manifest recording corpus fingerprint, strata counts, request
    counts, and the development-only/no-production-authority contract.

Never imports or modifies D3-v5, IMAGE-v2, COMBINED-IDENTITY-v2,
CAPTURE-ALLOCATION-v2, or E2.14. Never freezes LANGUAGE-v1. Never writes
public prices or Fair Value / Explorer state.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
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


def normalize_language_aspect(raw_value: str | None) -> str:
    """E2.16-local wrapper mapping E2.15's `normalize_language_value` (which
    returns a Title-case canonical name, or None if unrecognized) onto the
    E2.16 DEVELOPMENT-COHORT enum: ENGLISH / JAPANESE / KOREAN / CHINESE /
    GERMAN / FRENCH / SPANISH / ITALIAN / PORTUGUESE / OTHER / UNKNOWN.
    Research parser only -- never frozen, never treated as ground truth.
    """
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

ARTIFACTS_DIR = ROOT / "backend/artifacts/index_fair_value"
QUEUE_PATH = ARTIFACTS_DIR / "ebay_e2_16_language_development_queue.csv"
MANIFEST_PATH = ARTIFACTS_DIR / "ebay_e2_16_language_development_manifest.json"
RAW_INTERNAL_PATH = ARTIFACTS_DIR / "ebay_e2_16_language_development_raw_internal.jsonl"

SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/{item_id}"
CATEGORY_ID = "183454"

CORPUS_VERSION = "ebay_e2_16_language_development_cohort_v1"

MAX_SEARCH_REQUESTS = 140
MAX_GETITEM_REQUESTS = 260
TARGET_ROWS = 200

# Historical certification/blind cohort files whose listing_item_id column
# must be fully excluded from this NEW development corpus.
HISTORICAL_FILES = [
    "ebay_manual_gold_labels.csv",
    "ebay_gold_development.csv",
    "ebay_gold_validation.csv",
    "ebay_gold_final_blind.csv",
    "ebay_d3_blind_review_queue.csv",
    "ebay_d3_coverage_blind.csv",
    "ebay_d3_fresh_observations.csv",
    "ebay_d3_precision_blind.csv",
    "ebay_d3_v3_coverage_certification_rows.csv",
    "ebay_d3_v3_high_false_positive_forensics.csv",
    "ebay_d3_v3_precision_certification_rows.csv",
    "ebay_d3_v4_fresh_blind_queue.csv",
    "ebay_d3_v5_fresh_blind_queue.csv",
    "ebay_e2_9b_fresh_blind_queue.csv",
    "ebay_e2_13_fresh_blind_queue.csv",
]

E214_PREDICTIONS_PATH = ARTIFACTS_DIR / "ebay_e2_14_fresh_blind_predictions.json"
E215_STUDY_PATH = ARTIFACTS_DIR / "ebay_e2_15_item_detail_language_study.json"

# Language strata. "term" is appended to the base query text; None means the
# ordinary (no language term) English-control formulation.
NON_LATIN_LANGUAGES = ["Japanese", "Korean", "Chinese"]
LATIN_FOREIGN_LANGUAGES = ["German", "French", "Spanish", "Italian", "Portuguese"]

STRATUM_ENGLISH_CONTROL = "ENGLISH_CONTROL"
STRATUM_NON_LATIN_FOREIGN = "NON_LATIN_FOREIGN"
STRATUM_LATIN_FOREIGN = "LATIN_SCRIPT_FOREIGN"
STRATUM_AMBIGUOUS = "AMBIGUOUS_DIFFICULT"

REVIEWER_VISIBLE_COLUMNS = [
    "row_id", "listing_item_id", "item_url", "listing_title", "condition",
    "buying_options_json", "seller_id", "image_url",
    "target_card_name", "target_set_name", "target_card_number", "target_treatment",
    "search_language_term",  # the QUERY term used, not the aspect result -- reviewer may see what
                              # search strategy surfaced the row, this is provenance, not ground truth,
                              # and carries no eBay-derived language claim.
    "human_truth_label", "human_language_if_known", "reviewer_id", "label_timestamp", "review_note",
]

FORBIDDEN_REVIEWER_COLUMNS = frozenset({
    "language_aspect_raw", "language_aspect_normalized", "language_aspect_present",
    "languagev1_state", "combined_policy_output", "localized_aspects_json",
})


def _load_env_and_token():
    cfg = load_ebay_env()
    tp = TokenProvider(cfg)
    return tp.get()


def _collect_historical_exclusions() -> dict[str, Any]:
    exact_ids: set[str] = set()
    counts: dict[str, int] = {}
    for name in HISTORICAL_FILES:
        path = ARTIFACTS_DIR / name
        if not path.exists():
            counts[name] = -1
            continue
        n = 0
        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            if "listing_item_id" not in (reader.fieldnames or []):
                counts[name] = -2  # no listing_item_id column
                continue
            for row in reader:
                v = str(row.get("listing_item_id") or "").strip()
                if v:
                    exact_ids.add(v)
                    n += 1
        counts[name] = n

    # E2.14 fresh blind predictions (JSON, not CSV)
    n214 = 0
    if E214_PREDICTIONS_PATH.exists():
        data = json.loads(E214_PREDICTIONS_PATH.read_text(encoding="utf-8"))
        for row in data.get("predictions", {}).values():
            v = str(row.get("listing_item_id") or "").strip()
            if v:
                exact_ids.add(v)
                n214 += 1
    counts["ebay_e2_14_fresh_blind_predictions.json"] = n214

    # E2.15 development study item IDs
    n215 = 0
    if E215_STUDY_PATH.exists():
        data = json.loads(E215_STUDY_PATH.read_text(encoding="utf-8"))
        for row in data.get("results", []):
            v = str(row.get("item_id") or "").strip()
            if v:
                exact_ids.add(v)
                n215 += 1
    counts["ebay_e2_15_item_detail_language_study.json"] = n215

    return {"exact_ids": exact_ids, "counts_per_file": counts, "total_excluded_ids": len(exact_ids)}


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
    except urllib.error.HTTPError as exc:
        budget.setdefault("search_errors", 0)
        budget["search_errors"] += 1
        return []
    except Exception:
        budget.setdefault("search_errors", 0)
        budget["search_errors"] += 1
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
        budget.setdefault("getitem_errors", 0)
        budget["getitem_errors"] += 1
        return None


def _extract_language_aspect(item: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    localized = item.get("localizedAspects") or []
    for a in localized:
        if isinstance(a, dict) and str(a.get("name") or "").strip().lower() == "language":
            return a.get("value"), {"localized_aspect_count": len(localized)}
    return None, {"localized_aspect_count": len(localized)}


def _stratum_for(term: str | None) -> str:
    if term is None:
        return STRATUM_ENGLISH_CONTROL
    if term in NON_LATIN_LANGUAGES:
        return STRATUM_NON_LATIN_FOREIGN
    if term in LATIN_FOREIGN_LANGUAGES:
        return STRATUM_LATIN_FOREIGN
    return STRATUM_AMBIGUOUS


def _looks_ambiguous(title: str) -> bool:
    t = title.lower()
    signals = ["lot", "bundle", "proxy", "custom", "damaged", "poor", "mixed", "set of"]
    return any(s in t for s in signals)


def cohort_fingerprint(rows: list[dict[str, Any]]) -> str:
    ids = sorted(f"{r['row_id']}:{r['listing_item_id']}" for r in rows)
    return hashlib.sha256("|".join(ids).encode()).hexdigest()


def build(pilot_limit: int = 70, seed: int = 2016) -> dict[str, Any]:
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
    candidates: list[dict[str, Any]] = []  # (card, search_term/stratum hint, listing summary)

    # Query plan: for each card (in shuffled order) issue an English-control
    # query, then rotate through non-Latin and Latin-script language terms so
    # strata fill roughly evenly across the pilot catalog rather than
    # depending on any one card's foreign-market supply.
    lang_terms_cycle = (
        [None, None] +
        [t for t in NON_LATIN_LANGUAGES] +
        [t for t in LATIN_FOREIGN_LANGUAGES]
    )

    for idx, ci in enumerate(order):
        if budget["search"] >= MAX_SEARCH_REQUESTS:
            break
        card = cards[ci]
        name = str(card["card_name"]).strip()
        number = str(card.get("card_number") or "").strip()
        set_name = str(card["set_name"]).strip()
        base = f"{name} {number} {set_name} Pokemon card"

        term = lang_terms_cycle[idx % len(lang_terms_cycle)]
        query_text = base if term is None else f"{base} {term}"
        results = _search(token, query_text, budget)
        for item in results:
            item_id = str(item.get("itemId") or "")
            if not item_id or item_id in seen_item_ids or item_id in exact_excluded:
                continue
            seen_item_ids.add(item_id)
            candidates.append({"card": card, "search_language_term": term, "listing": item})

    # getItem pass -- bounded, retains full localizedAspects for internal use.
    internal_rows: list[dict[str, Any]] = []
    rng.shuffle(candidates)
    for cand in candidates:
        if budget["getitem"] >= MAX_GETITEM_REQUESTS or len(internal_rows) >= TARGET_ROWS * 2:
            break
        listing = cand["listing"]
        item_id = str(listing.get("itemId") or "")
        item = _get_item(token, item_id, budget)
        if item is None:
            continue
        raw_lang, extra = _extract_language_aspect(item)
        normalized = normalize_language_aspect(raw_lang)
        title = str(item.get("title") or listing.get("title") or "")
        stratum = _stratum_for(cand["search_language_term"])
        if stratum == STRATUM_ENGLISH_CONTROL and _looks_ambiguous(title):
            stratum = STRATUM_AMBIGUOUS
        image_url = ""
        images = item.get("image") or {}
        if isinstance(images, dict):
            image_url = images.get("imageUrl") or ""
        if not image_url:
            image_url = str(listing.get("image", {}).get("imageUrl") or "") if isinstance(listing.get("image"), dict) else ""

        card = cand["card"]
        internal_rows.append({
            "row_id": f"e2_16_dev_{len(internal_rows):04d}",
            "listing_item_id": item_id,
            "item_url": item.get("itemWebUrl") or listing.get("itemWebUrl") or "",
            "listing_title": title,
            "condition": item.get("condition") or listing.get("condition") or "",
            "buying_options_json": json.dumps(item.get("buyingOptions") or listing.get("buyingOptions") or []),
            "seller_id": (item.get("seller") or {}).get("username") or "",
            "image_url": image_url,
            "canonical_card_id": card.get("canonical_card_id", ""),
            "card_variant_id": card.get("card_variant_id", ""),
            "target_card_name": card.get("card_name", ""),
            "target_set_name": card.get("set_name", ""),
            "target_card_number": card.get("card_number", ""),
            "target_treatment": card.get("treatment_key", ""),
            "search_language_term": cand["search_language_term"] or "",
            "development_stratum": stratum,
            "marketplace": item.get("marketplaceId") or "",
            "seller_country_context_only": (item.get("itemLocation") or {}).get("country", ""),
            # internal-only, hidden from reviewer:
            "language_aspect_raw": raw_lang,
            "language_aspect_normalized": normalized,
            "language_aspect_present": raw_lang is not None,
            "localized_aspect_count": extra.get("localized_aspect_count") if extra else 0,
            "capture_timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Balance selection toward stratum targets without forcing exact quotas.
    by_stratum: dict[str, list[dict[str, Any]]] = {}
    for row in internal_rows:
        by_stratum.setdefault(row["development_stratum"], []).append(row)

    quota = {
        STRATUM_ENGLISH_CONTROL: 90,
        STRATUM_NON_LATIN_FOREIGN: 70,
        STRATUM_LATIN_FOREIGN: 60,
        STRATUM_AMBIGUOUS: 30,
    }
    selected: list[dict[str, Any]] = []
    for stratum, cap in quota.items():
        pool = by_stratum.get(stratum, [])
        selected.extend(pool[:cap])
    # top up from any leftover pool up to TARGET_ROWS if under target
    if len(selected) < TARGET_ROWS:
        leftover = [r for rows in by_stratum.values() for r in rows if r not in selected]
        selected.extend(leftover[: TARGET_ROWS - len(selected)])

    for i, row in enumerate(selected):
        row["row_id"] = f"e2_16_dev_{i:04d}"

    # Write internal raw (full evidence, retained for E2.16A)
    RAW_INTERNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RAW_INTERNAL_PATH.open("w", encoding="utf-8") as fh:
        for row in selected:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Write reviewer-facing queue CSV -- NO language aspect fields.
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

    strata_counts = {s: len(by_stratum.get(s, [])) for s in quota}
    selected_strata_counts: dict[str, int] = {}
    for row in selected:
        selected_strata_counts[row["development_stratum"]] = selected_strata_counts.get(row["development_stratum"], 0) + 1

    languages_represented = sorted({
        row["language_aspect_normalized"] for row in selected if row["language_aspect_present"]
    })

    fingerprint = cohort_fingerprint(selected)
    manifest = {
        "version": CORPUS_VERSION,
        "development_only": True,
        "production_authority": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_fingerprint": fingerprint,
        "row_count": len(selected),
        "candidate_pool_size_before_selection": len(internal_rows),
        "strata_counts_selected": selected_strata_counts,
        "strata_counts_candidate_pool": strata_counts,
        "languages_represented_in_aspect_metadata": languages_represented,
        "getitem_request_count": budget["getitem"],
        "search_request_count": budget["search"],
        "search_errors": budget.get("search_errors", 0),
        "getitem_errors": budget.get("getitem_errors", 0),
        "language_aspect_present_count": sum(1 for r in selected if r["language_aspect_present"]),
        "language_aspect_present_rate": (
            sum(1 for r in selected if r["language_aspect_present"]) / len(selected) if selected else None
        ),
        "historical_exclusion": {
            "counts_per_file": exclusions["counts_per_file"],
            "total_excluded_ids": exclusions["total_excluded_ids"],
        },
        "review_session_id": None,  # set by the review server on first launch
        "reviewed_count": 0,
        "queue_path": str(QUEUE_PATH.relative_to(ROOT)),
        "internal_raw_path": str(RAW_INTERNAL_PATH.relative_to(ROOT)),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = build()
    print(json.dumps(result, indent=2))
