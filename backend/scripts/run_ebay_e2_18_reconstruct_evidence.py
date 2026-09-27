"""Bounded, resumable historical getItem and frozen OCR-v3 reconstruction.

Historical cohorts are consumed. This writes evidence artifacts only; it does
not load human truth or score policy outcomes.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from backend.scripts import ebay_e2_17d_ocr_v3_hangul_recalibration as ocr
from backend.scripts import ebay_image_retrieval_verifier as image_v2
from backend.scripts.build_ebay_e2_17c_small_japanese_holdout import _load_env_and_token
from backend.scripts.ebay_language_policy_v1 import extract_language_aspect, normalize_language_value

OUT = Path(__file__).resolve().parents[1] / "artifacts/index_fair_value"
QUEUE = {
    "E2.14": "ebay_e2_13_fresh_blind_queue.csv",
    "V4": "ebay_d3_v4_fresh_blind_queue.csv",
    "V5": "ebay_d3_v5_fresh_blind_queue.csv",
    "E2.9B": "ebay_e2_9b_fresh_blind_queue.csv",
}
MAX_TASK_GETITEM_REQUESTS = 200


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_frozen_sources() -> None:
    original = json.loads((OUT / "ebay_image_retrieval_verifier_v2_freeze_manifest.json").read_text())
    ocr_manifest = json.loads((OUT / "ebay_e2_17d_ocr_v3_freeze_manifest.json").read_text())
    if image_v2.source_sha256() != original["verifier_source_sha256"]:
        raise RuntimeError("EBAY_E2_18_BLOCKED_FROZEN_AUTHORITY_MISMATCH_IMAGE_V2")
    if ocr.compute_source_fingerprint() != ocr_manifest["source_fingerprint_sha256"]:
        raise RuntimeError("EBAY_E2_18_BLOCKED_FROZEN_AUTHORITY_MISMATCH_OCR_V3")


def inputs(cohort: str) -> list[dict[str, str]]:
    with (OUT / QUEUE[cohort]).open(encoding="utf-8", newline="") as handle:
        # Explicit projection: no reviewer label, note, or adjudication field
        # is passed to evidence reconstruction.
        return [{"row_id": r["benchmark_row_id"], "listing_item_id": r["listing_item_id"],
                 "image_url": r["image_url"]} for r in csv.DictReader(handle)]


def artifact_path(cohort: str, kind: str) -> Path:
    return OUT / f"ebay_e2_18_{cohort.lower().replace('.', '_')}_{kind}_evidence.jsonl"


def read_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    ids = [r["row_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError(f"duplicate evidence row in {path}")
    return {r["row_id"]: r for r in rows}


def append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def getitem(token: str, row: dict) -> dict:
    url = "https://api.ebay.com/buy/browse/v1/item/" + urllib.parse.quote(row["listing_item_id"], safe="")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token,
                                                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                                                "Accept": "application/json"})
    status: int | str
    aspects = None
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status = response.status
            item = json.loads(response.read())
            aspects = item.get("localizedAspects")
    except urllib.error.HTTPError as exc:
        status = exc.code
    except Exception as exc:
        status = type(exc).__name__
    raw = extract_language_aspect(aspects)
    return {"row_id": row["row_id"], "listing_item_id": row["listing_item_id"],
            "localizedAspects": aspects, "raw_language_value": raw,
            "normalized_provider_language": normalize_language_value(raw),
            "fetch_status": status, "fetch_timestamp": now()}


def reconstruct_provider(cohort: str, budget: int) -> dict:
    verify_frozen_sources()
    rows = inputs(cohort)
    path = artifact_path(cohort, "provider")
    existing = read_existing(path)
    token = _load_env_and_token() if budget and len(existing) < len(rows) else ""
    for row in rows:
        if row["row_id"] in existing:
            if existing[row["row_id"]]["listing_item_id"] != row["listing_item_id"]:
                raise RuntimeError("provider row binding changed")
            continue
        if budget <= 0:
            break
        record = getitem(token, row)
        append(path, record)
        existing[row["row_id"]] = record
        budget -= 1
        if len(existing) % 25 == 0:
            print(cohort, "provider", len(existing), "/", len(rows), flush=True)
    return {"cohort": cohort, "attempted": len(existing), "total": len(rows), "remaining_budget": budget}


def reconstruct_ocr(cohort: str) -> dict:
    verify_frozen_sources()
    rows = inputs(cohort)
    path = artifact_path(cohort, "ocr_v3")
    existing = read_existing(path)
    pending = [r for r in rows if r["row_id"] not in existing]
    if not pending:
        return {"cohort": cohort, "attempted": len(existing), "total": len(rows)}
    reader_ja, reader_ko, _ = ocr.build_readers()
    for row in pending:
        image = b""
        status: int | str
        try:
            req = urllib.request.Request(row["image_url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as response:
                status = response.status
                image = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
        except Exception as exc:
            status = type(exc).__name__
        if image:
            with tempfile.TemporaryDirectory() as tmp:
                image_path = Path(tmp) / "listing.jpg"
                image_path.write_bytes(image)
                evidence = ocr.run_ocr_v3(reader_ja, reader_ko, str(image_path), row["row_id"])
        else:
            evidence = ocr.OcrV3Evidence(row_id=row["row_id"], error="image_fetch_unavailable")
        state, reason = ocr.ocr_v3_decision(evidence)
        record = {"row_id": row["row_id"], "listing_item_id": row["listing_item_id"],
                  "image_url": row["image_url"], "image_fetch_status": status,
                  "image_sha256": hashlib.sha256(image).hexdigest() if image else None,
                  "fetch_timestamp": now(), "ocr_v3_state": state, "reason_code": reason,
                  "evidence": dataclasses.asdict(evidence)}
        append(path, record)
        existing[row["row_id"]] = record
        if len(existing) % 25 == 0:
            print(cohort, "ocr", len(existing), "/", len(rows), flush=True)
    return {"cohort": cohort, "attempted": len(existing), "total": len(rows)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", choices=list(QUEUE), required=True)
    parser.add_argument("--provider-budget", type=int, default=0)
    parser.add_argument("--ocr", action="store_true")
    args = parser.parse_args()
    if args.provider_budget < 0 or args.provider_budget > MAX_TASK_GETITEM_REQUESTS:
        raise SystemExit("provider budget must be between 0 and 200")
    print(json.dumps(reconstruct_provider(args.cohort, args.provider_budget)))
    if args.ocr:
        print(json.dumps(reconstruct_ocr(args.cohort)))
