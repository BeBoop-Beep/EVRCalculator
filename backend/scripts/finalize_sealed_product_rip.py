"""Attach Collector Appeal + Overall RIP V8 to a coordinated Stage 1 cohort.

WHEN YOU NEED THIS
------------------
An EVR simulation persists a sealed product's FINANCIAL half immediately and
completely: distribution statistics, product market cost and Financial RIP V3.
It deliberately does NOT resolve Collector Appeal, because the canonical
Collector Appeal service builds one bundle for ALL sets and caches it in-process,
while simulations run one subprocess per set - so resolving it per set paid the
full ~105 s cold build once per set and cached nothing.

Those rows are therefore written with:

    collector_appeal_score   NULL
    collector_appeal_version NULL
    overall_rip_score        NULL
    overall_rip_rankable     false
    overall_rip_payload      the canonical Overall RIP V8 "unavailable" result

and the run summary reports ``collectorAppealStatus="pending_batch_enrichment"``.

The daily opening publication runs this finalization automatically, once, after
freshness verification. Run this script when you simulated a set by hand and want
its Overall RIP attached without waiting for the nightly job.

    python backend/scripts/finalize_sealed_product_rip.py
    python backend/scripts/finalize_sealed_product_rip.py --market-date 2026-08-15
    python backend/scripts/finalize_sealed_product_rip.py --set surgingSparks

NOTES ON --set
--------------
``--set`` narrows which sets are ENRICHED. It does not narrow the Collector
Appeal build: the bundle is canonical and is computed across all sets by
construction, so a one-set finalization costs the same build as a full one. It is
a scoping flag, not a speed flag - there is no cheaper single-set appeal, and
inventing one would be a second Collector Appeal formula.

COMPARISON SCOPE
----------------
Sealed-product scores are comparable WITHIN A PRODUCT FAMILY ONLY (box vs box,
bundle vs bundle, sleeved vs sleeved). Cross-format ranking is not validated. The
report prints the contract it was finalized under.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("finalize_sealed_product_rip")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--market-date",
        default=None,
        help="Coordinated market date (YYYY-MM-DD). Default: the promoted market date.",
    )
    parser.add_argument(
        "--set",
        dest="sets",
        nargs="*",
        default=None,
        help="Canonical set keys to enrich. Default: every supported opening set.",
    )
    parser.add_argument(
        "--allow-unverified-cohort",
        action="store_true",
        help=(
            "Finalize the sets that ARE current even when other sets are stale. "
            "Off by default so a partial day is never written as a coordinated one."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print the raw report as JSON.")
    args = parser.parse_args()

    from backend.db.clients.supabase_client import supabase
    from backend.db.services.sealed_product_rip_finalization_service import (
        finalize_sealed_product_rip,
    )
    from backend.scripts.audit_opening_analytics_publication import resolve_market_date

    resolved, date_error = resolve_market_date(supabase, args.market_date)
    if date_error or not resolved:
        print(f"cannot start: {date_error or 'no promoted market date could be resolved'}")
        return 2

    report = finalize_sealed_product_rip(
        supabase,
        market_date=resolved,
        canonical_keys=args.sets,
        require_verified_cohort=not args.allow_unverified_cohort,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"market_date            = {report['marketDate']}")
        print(f"status                 = {report['status']}")
        if report.get("error"):
            print(f"error                  = {report['error']}")
        print(f"sets finalized         = {report['setCount']} of {report['cohortSetCount']} in cohort")
        print(f"rows considered        = {report['rowsConsidered']}")
        print(f"rows finalized         = {report['rowsFinalized']}")
        print(f"rows CA unavailable    = {report['rowsCollectorAppealUnavailable']}")
        print(f"rows skipped           = {report['rowsSkipped']}")
        print(f"collector appeal build = {report['collectorAppealBundleMs']} ms "
              f"({report['collectorAppealBundleBuilds']} build)")
        print(f"total                  = {report['elapsedMs']} ms")
        print(f"comparison scope       = {report['comparisonScope']} "
              f"(crossFormatComparable={report['crossFormatComparable']})")

    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
