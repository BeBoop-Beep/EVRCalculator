"""P5B.1: plan and (optionally) capture one bounded eBay batch for the paired cohort.

Reuses the P4A adaptive capture (shallow search + selective getItem) unchanged.  The only P5B
parameter difference is stop_sellers=5 so the frozen SUFFICIENT depth (>=5 sellers) is reachable.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from backend.scripts import p5b_cohort_builder as cb

OUT = cb.OUT


def used_card_ids() -> set[str]:
    used: set[str] = set()
    for path in OUT.glob("p5b_batch*_manifest.json"):
        used |= set(json.loads(path.read_text(encoding="utf-8"))["canonical_card_ids"])
    p4 = OUT / "ebay_daily_pricing_targets_2026-09-19.json"
    for path in OUT.glob("ebay_p4a_*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        used |= {t["canonical_card_id"] for t in data.get("targets", [])}
    return used


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--market-date", default="2026-09-20")
    parser.add_argument("--quotas", type=json.loads, required=True, help="JSON quotas for select_cohort")
    parser.add_argument("--request-cap", type=int, default=330)
    parser.add_argument("--details-per-target", type=int, default=8)
    parser.add_argument("--capture", action="store_true", help="perform live eBay calls")
    args = parser.parse_args(argv)
    universe = json.load(gzip.open(OUT / f"p5b_universe_{args.market_date}.json.gz", "rt"))["rows"]
    rows = cb.select_cohort(universe, args.market_date, args.quotas, exclude=used_card_ids())
    manifest = cb.manifest_for([cb.to_target(r) for r in rows], args.market_date)
    path = OUT / f"p5b_batch{args.batch}_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from collections import Counter
    print(json.dumps({"manifest": str(path), "targets": len(rows),
                      "strata": Counter(r["stratum"] for r in rows)}, default=dict, indent=2))
    if args.capture:
        from backend.scripts.run_ebay_p4a_adaptive_development import collect
        result = collect(manifest, target_count=len(rows), request_cap=args.request_cap,
                         details_per_target=args.details_per_target, stop_sellers=5)
        (OUT / f"p5b_batch{args.batch}_run.json").write_text(json.dumps(
            {"batch": args.batch, "run_id": result["run_id"], "requests_attempted": result["requests_attempted"],
             "requests_successful": result["requests_successful"], "requests_failed": result["requests_failed"],
             "retries": result["retries"], "target_count": len(result["targets"])}, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"run_id": result["run_id"], "requests_attempted": result["requests_attempted"],
                          "failed": result["requests_failed"], "retries": result["retries"]}, indent=2))


if __name__ == "__main__":
    main()
