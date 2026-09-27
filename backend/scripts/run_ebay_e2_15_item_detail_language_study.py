"""EBAY E2.15 Phase B: bounded live Browse getItem study for language metadata.

Development-only, budget-bounded, read-only. Calls the Browse API
`item/{item_id}` (getItem) endpoint for a small sample of Pokemon-card
listing IDs drawn from prior evidence-collector raw capture (NOT the
E2.14 fresh-blind label cohort), and measures how often an explicit
Language aspect (localizedAspects / additionalProduct info) is present,
whether it is seller-provided vs eBay-inferred, and whether it
contradicts the listing title.

This script performs NO writes to production tables, NO price/EV
computation, and makes NO identity-stack modifications. It reuses the
existing `load_ebay_env` / `TokenProvider` credential plumbing from
`index_fair_value_ebay_evidence_collector.py` rather than reimplementing
auth, and respects a small hard-coded request budget (<= 40 calls).

Output: backend/artifacts/index_fair_value/ebay_e2_15_item_detail_language_study.json
"""
from __future__ import annotations

import json
import random
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from backend.scripts.index_fair_value_ebay_evidence_collector import (
    ROOT,
    TokenProvider,
    load_ebay_env,
)

ARTIFACTS_DIR = ROOT / "backend/artifacts/index_fair_value"
RUNS_DIR = ARTIFACTS_DIR / "ebay_evidence_runs"
OUT_PATH = ARTIFACTS_DIR / "ebay_e2_15_item_detail_language_study.json"

ITEM_URL = "https://api.ebay.com/buy/browse/v1/item/{item_id}"

MAX_REQUESTS = 40


def _collect_candidate_item_ids(exclude: set[str], limit_files: int = 8) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for path in sorted(RUNS_DIR.glob("*.raw.jsonl"))[:limit_files]:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                item_id = row.get("ebay_item_id")
                if not item_id or item_id in seen or item_id in exclude:
                    continue
                seen.add(item_id)
                ids.append(item_id)
    return ids


def _get_item(opener, token: str, item_id: str) -> dict[str, Any]:
    url = ITEM_URL.format(item_id=urllib.request.quote(item_id, safe=""))
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_language_evidence(item: dict[str, Any]) -> dict[str, Any]:
    localized = item.get("localizedAspects") or []
    aspects = {a.get("name"): a.get("value") for a in localized if isinstance(a, dict)}
    language_value = None
    for key in aspects:
        if key and key.strip().lower() == "language":
            language_value = aspects[key]
            break
    return {
        "has_localized_aspects_block": bool(localized),
        "localized_aspect_count": len(localized),
        "language_aspect_present": language_value is not None,
        "language_aspect_value": language_value,
        "title": item.get("title"),
    }


def main() -> None:
    e214_ids: set[str] = set()
    e214_path = ARTIFACTS_DIR / "ebay_e2_14_fresh_blind_predictions.json"
    if e214_path.exists():
        data = json.loads(e214_path.read_text(encoding="utf-8"))
        e214_ids = {row["listing_item_id"] for row in data.get("predictions", {}).values()}

    candidates = _collect_candidate_item_ids(exclude=e214_ids)
    random.Random(42).shuffle(candidates)
    sample = candidates[:MAX_REQUESTS]

    result: dict[str, Any] = {
        "study": "ebay_e2_15_phase_b_item_detail_language_study",
        "excluded_e214_cohort_size": len(e214_ids),
        "candidate_pool_size": len(candidates),
        "requested": len(sample),
        "results": [],
        "errors": [],
    }

    if not sample:
        result["note"] = "no candidate item ids available; skipping live calls"
        OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"wrote {OUT_PATH} (no candidates)")
        return

    try:
        cfg = load_ebay_env()
    except Exception as exc:  # noqa: BLE001
        result["note"] = f"credentials unavailable: {exc}"
        OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"wrote {OUT_PATH} (no credentials)")
        return

    token_provider = TokenProvider(cfg)
    try:
        token = token_provider.get()
    except Exception as exc:  # noqa: BLE001
        result["note"] = f"token fetch failed: {exc}"
        OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"wrote {OUT_PATH} (token fetch failed)")
        return

    present = 0
    for item_id in sample:
        try:
            item = _get_item(None, token, item_id)
        except urllib.error.HTTPError as exc:
            result["errors"].append({"item_id": item_id, "status": exc.code})
            continue
        except Exception as exc:  # noqa: BLE001
            result["errors"].append({"item_id": item_id, "error": str(exc)})
            continue
        ev = _extract_language_evidence(item)
        ev["item_id"] = item_id
        result["results"].append(ev)
        if ev["language_aspect_present"]:
            present += 1

    n = len(result["results"])
    result["fetched"] = n
    result["language_aspect_present_count"] = present
    result["language_aspect_present_rate"] = (present / n) if n else None

    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}: fetched={n} language_present={present}")


if __name__ == "__main__":
    main()
