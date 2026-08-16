"""Controlled experiment: does pack count alone move Financial RIP V3?

The observational audit compares real products at real prices, where economics
and pack count vary together. This isolates them.

For one set, take the finished pack vector X and score three products whose
ECONOMICS ARE IDENTICAL by construction:

    Y1  at cost 1*C
    Y6  at cost 6*C
    Y36 at cost 36*C

Every one of these has the same expected value per dollar, the same RTP, and is
built from the same pack model. A scale that is unit-agnostic would score them
nearly the same. Any systematic gap is the pack-calibrated anchors reacting to
opening SIZE rather than to economics.

Read-only. Persists nothing. Changes no formula.

    python backend/scripts/audit_stage1_pack_count_control.py --sets surgingSparks destinedRivals
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from backend.calculations.evr.financial_rip_v3 import build_financial_rip_v3
from backend.calculations.evr.financial_rip_v3_config import FINANCIAL_RIP_V3_COMPONENT_ORDER
from backend.calculations.evr.sealed_product_distribution import (
    build_stage1_product_distributions,
    extract_pack_outcome_vector,
)
from backend.calculations.packCalcsRefractored import calculate_pack_stats
from backend.db.services.evr_input_preparation_service import EVRInputPreparationService
from backend.jobs.evr_runner import _resolve_set_config
from backend.simulations import calculate_pack_simulations

PACK_COUNTS = (1, 6, 36)


def run_for_set(canonical_key: str) -> Dict[str, Any]:
    config_cls, canonical = _resolve_set_config(canonical_key)
    config = config_cls()
    set_name = str(getattr(config, "SET_NAME", canonical))
    prepared = EVRInputPreparationService().prepare_for_set(config, canonical, set_name)
    frame = prepared["dataframe"]

    _results, _summary, _top, pack_price = calculate_pack_stats(frame, config)
    sim_results, _pack_metrics = calculate_pack_simulations(frame, config)

    x = extract_pack_outcome_vector(sim_results)
    built = build_stage1_product_distributions(
        x, pack_counts=list(PACK_COUNTS), canonical_set_key=canonical
    )
    cost = float(pack_price)

    entries: List[Dict[str, Any]] = []
    for count in PACK_COUNTS:
        y = built["distributions"][count]
        payload = build_financial_rip_v3(y, cost * count)
        entries.append(
            {
                "packCount": count,
                "cost": round(cost * count, 4),
                "score": payload.get("score"),
                "components": {
                    component: (payload.get("components") or {}).get(component, {}).get("score")
                    for component in FINANCIAL_RIP_V3_COMPONENT_ORDER
                },
                "rawInputs": {
                    metric: record.get("raw")
                    for metric, record in ((payload.get("audit") or {}).get("normalizedInputs") or {}).items()
                },
                "clippedInputs": (payload.get("estimationDiagnostics") or {}).get("clippedInputs"),
                "totalRtpRatio": (payload.get("distributionDisclosures") or {}).get("totalRtpRatio"),
            }
        )
    return {"canonicalKey": canonical, "packCost": cost, "entries": entries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sets", nargs="+", required=True)
    parser.add_argument("--json", default="tmp/stage1_pack_count_control.json")
    args = parser.parse_args()

    report = [run_for_set(key) for key in args.sets]
    with open(args.json, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    for entry in report:
        print(f"\n=== {entry['canonicalKey']} (pack cost ${entry['packCost']:.2f}) ===")
        print("packs | cost | RTP | FinRIP | " + " | ".join(FINANCIAL_RIP_V3_COMPONENT_ORDER))
        for row in entry["entries"]:
            comps = " | ".join(f"{row['components'][c]:.2f}" for c in FINANCIAL_RIP_V3_COMPONENT_ORDER)
            print(f"{row['packCount']:5d} | {row['cost']:8.2f} | {row['totalRtpRatio']:.4f} | {row['score']:.2f} | {comps}")
        base = entry["entries"][0]["score"]
        for row in entry["entries"][1:]:
            print(f"  delta vs 1-pack at identical RTP: packs={row['packCount']} {row['score'] - base:+.2f} points")
    print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
