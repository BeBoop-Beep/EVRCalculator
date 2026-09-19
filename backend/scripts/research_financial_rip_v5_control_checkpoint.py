"""Read-only, per-product checkpoint for the full fused V4/V12 control cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.calculations.evr.best_open_price_v2_fused import DualBestOpenPriceSearch
from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.research_financial_rip_v5_best_open import PROMPT2, ROOT, atomic_json
import backend.scripts.research_best_open_price_v2 as research_v2

CHECKPOINT = ROOT / "logs/financial_rip_v5_best_open_v2_control_checkpoint.json"
OUTPUT = ROOT / "docs/research/financial_rip_v5_best_open_v2_control.json"
METHOD = "fused_v2_exact_cent_single_q_parity_batch_v1"


def run(*, resume: bool = False, restart: bool = False,
        checkpoint: Path = CHECKPOINT) -> dict:
    if resume and restart:
        raise ValueError("resume and restart are mutually exclusive")
    prompt2 = json.loads(PROMPT2.read_text(encoding="utf-8"))["states"][0]
    snapshot = prompt2["snapshot"]
    authority = {
        "sourceSnapshotId": snapshot["id"],
        "sourceFingerprint": snapshot["cohort_fingerprint"],
        "sourceAuthorityFingerprint": "faad453f7d29eff1831fb2e212a13dad7d9d553536dc283af90c9bfbd53e48b0",
        "methodVersion": "budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12",
        "searchMethodIdentity": METHOD,
    }
    if resume:
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        for key, expected in authority.items():
            if payload.get(key) != expected:
                raise RuntimeError(f"checkpoint authority mismatch: {key}")
    elif checkpoint.exists() and not restart:
        raise RuntimeError("checkpoint exists; specify --resume or --restart")
    else:
        payload = {**authority, "status": "incomplete", "products": []}
    completed = {row["sealedProductId"] for row in payload["products"]}
    previous_search_class = research_v2.DualBestOpenPriceSearch
    research_v2.DualBestOpenPriceSearch = DualBestOpenPriceSearch

    def save(row):
        payload["products"].append(row)
        atomic_json(checkpoint, payload)
        print(f"control thresholds {len(payload['products'])}/138: {row['sealedProductId']}", flush=True)

    # The source guard validates the entire frozen cohort before any search.
    try:
        result = research_v2.run(
            get_client(), source_snapshot_id=authority["sourceSnapshotId"],
            expected_source_authority_fingerprint=authority["sourceAuthorityFingerprint"],
            skip_product_ids=completed, checkpoint_callback=save,
            enable_quantity_prefetch=True,
        )
    finally:
        research_v2.DualBestOpenPriceSearch = previous_search_class
    if result["status"] != "complete":
        payload["status"] = "incomplete"
    elif len(payload["products"]) == 138 and all(r["resolved"] for r in payload["products"]):
        payload["status"] = "complete"
        atomic_json(OUTPUT, payload)
    atomic_json(checkpoint, payload)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    run(resume=args.resume, restart=args.restart)
