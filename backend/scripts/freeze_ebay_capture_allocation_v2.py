"""EBAY_E2_12: freezes CAPTURE-ALLOCATION-v2, a policy-blind capture/
allocation contract for a FUTURE certification cohort.

This is NOT a capture script -- it does not call eBay. It records the
allocation CONTRACT (query forms, per-card cap, page/listing budget,
exclusion logic, sampling method) so a future capture run is reproducible
and independently auditable before any new blind cohort exists.

The contract is unchanged from the existing, already-proven-policy-blind
E2.9B machinery except for exactly one parameter: ROWS_PER_CARD_V2 (8,
raised from 6). Everything else -- query generation
(index_fair_value_ebay_evidence_collector.generate_queries), historical
exclusion (capture_ebay_e2_9b_fresh_blind.load_historical_item_ids /
load_historical_relist_fingerprints), and stratified deterministic sampling
(capture_ebay_d3_v4_fresh_blind.stratified_sample) -- is reused verbatim.
None of it reads D3-v5, IMAGE-v2, COMBINED-v1/v2 output, or any human label.
"""
from __future__ import annotations

import hashlib
import json
import inspect
from datetime import datetime, timezone

from backend.scripts import index_fair_value_ebay_evidence_collector as collector
from backend.scripts import capture_ebay_d3_v4_fresh_blind as capture_v4
from backend.scripts import capture_ebay_e2_9b_fresh_blind as capture_e29b
from backend.scripts.ebay_gold_access import OUT

FREEZE_OUTPUT_PATH = OUT / "ebay_capture_allocation_v2_freeze_manifest.json"

ROWS_PER_CARD_V2 = 8
COHORT_NAME = "d1_70"
MAX_REQUESTS_PER_RUN = 1000
MAX_PAGES_PER_SEARCH = 3
MAX_LISTINGS_PER_TARGET = 200


def _source_hash(module) -> str:
    return hashlib.sha256(inspect.getsource(module).encode()).hexdigest()


def build_manifest() -> dict:
    # capture_e29b.HISTORICAL_ID_FILES was authored to exclude everything
    # BEFORE E2.9B; a future post-E2.9B capture must additionally exclude
    # E2.9B's own queue (now itself historical evidence) -- appended here,
    # not edited into the frozen E2.9B module.
    historical_files = capture_e29b.HISTORICAL_ID_FILES + [capture_e29b.D2M_URL_FILE, "ebay_e2_9b_fresh_blind_queue.csv"]
    return {
        "version": "ebay_capture_allocation_v2",
        "rows_per_card": ROWS_PER_CARD_V2,
        "cohort_name": COHORT_NAME,
        "coverage_universe": 70,
        "request_budget": {
            "max_requests_per_run": MAX_REQUESTS_PER_RUN,
            "max_pages_per_search": MAX_PAGES_PER_SEARCH,
            "max_listings_per_target": MAX_LISTINGS_PER_TARGET,
        },
        "query_generation_source": "index_fair_value_ebay_evidence_collector.generate_queries",
        "query_generation_fingerprint": _source_hash(collector),
        "sampling_method": "capture_ebay_d3_v4_fresh_blind.stratified_sample "
                            "(deterministic per-card SHA-256 ordering of eligible listings)",
        "sampling_source_fingerprint": _source_hash(capture_v4),
        "historical_exclusion_files": historical_files,
        "historical_exclusion_source_fingerprint": _source_hash(capture_e29b),
        "excludes_evidence_used_in": ["D2", "D3", "V4", "V5", "E2.6", "E2.7", "E2.8", "E2.9", "E2.9A", "E2.9B", "E2.9C", "E2.10", "E2.11"],
        "availability_classes": {
            "EXHAUSTED": "0 surviving unique candidates after historical/relist exclusion",
            "LOW_AVAILABILITY": "1-19 surviving unique candidates",
            "MEDIUM_AVAILABILITY": "20-49 surviving unique candidates",
            "HIGH_AVAILABILITY": ">=50 surviving unique candidates",
        },
        "exhausted_card_policy": "an EXHAUSTED card is sampled at 0 rows, never padded or substituted; "
                                  "coverage denominator remains 70 regardless.",
        "independent_of": [
            "D3-v5 output", "IMAGE-v2 output", "COMBINED-IDENTITY-v1/v2 output", "any human label",
        ],
        "production_authority": False,
        "certifies_nothing_by_itself": True,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }


def policy_fingerprint(manifest: dict) -> str:
    material = {k: v for k, v in manifest.items() if k != "frozen_at"}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> dict:
    manifest = build_manifest()
    manifest["allocation_fingerprint"] = policy_fingerprint(manifest)
    FREEZE_OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
