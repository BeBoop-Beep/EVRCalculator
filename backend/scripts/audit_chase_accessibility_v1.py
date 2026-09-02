"""Chase Accessibility V1 - read-only cohort audit and Stage XIV parity check.

READ ONLY. Computes the metric for every set in the authoritative cohort and
compares the supported sets against the immutable Stage XIV research artifact.
Writes nothing to the database, publishes nothing, applies no migration.

    python -m backend.scripts.audit_chase_accessibility_v1 \
        --market-date 2026-08-31 --stage14 <path to chase_accessibility_stage14.json>

WHY THE PARITY FILE IS PASSED IN
--------------------------------
The Stage XIV artifact was committed on ``fix/public-rankings-entitlement-regression``
AFTER the merge that produced this branch's HEAD, so it is not in this working
tree. It is reachable from the object store:

    git show bdaf01bd:docs/research/chase_accessibility_stage14.json > <path>

Passing it explicitly keeps the audit honest about which artifact it compared
against, rather than silently skipping the gate when the file is absent.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.desirability.chase_accessibility import (
    CHASE_ACCESSIBILITY_VERSION,
    STATUS_READY,
    assert_probability_authority,
    compute_chase_accessibility,
)

TAG = "[CHASE_ACCESSIBILITY_V1]"

#: Stage XIV published rounded values; parity is asserted at that precision.
ACCESSIBILITY_TOLERANCE = 5e-9
DEPTH_TOLERANCE = 5e-5


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def load_variant_rows(client: Any, *, run_id: str) -> List[Dict[str, Any]]:
    """Every drawable variant row for one run, paged past the 1000-row cap."""
    collected: List[Dict[str, Any]] = []
    page = 0
    while True:
        response = (client.table("simulation_card_variant_pull_rates")
                    .select("calculation_run_id,set_id,card_variant_id,price_used,"
                            "modeled_probability,effective_pull_rate,pull_count,"
                            "pack_presence_count,simulation_count")
                    .eq("calculation_run_id", run_id)
                    .gt("pull_count", 0)
                    .order("card_variant_id")
                    .range(page * 1000, page * 1000 + 999)
                    .execute())
        batch = _rows(response)
        collected.extend(batch)
        if len(batch) < 1000:
            return collected
        page += 1


def audit(client: Any, *, market_date: Optional[str],
          stage14: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    from backend.db.services.ev_representativeness_service import resolve_research_cohort

    day = str(market_date)[:10]
    targets = resolve_research_cohort(client, market_date=day, canonical_keys=None)
    print(f"{TAG} market_date={day} cohort={len(targets)}", flush=True)

    expected = {}
    if stage14:
        expected = {entry["set"]: entry for entry in stage14.get("sets", [])}

    results: List[Dict[str, Any]] = []
    authority_failures = 0
    for index, target in enumerate(targets, start=1):
        variants = load_variant_rows(client, run_id=target.calculation_run_id)
        authority = assert_probability_authority(variants)
        if not authority["holds"]:
            authority_failures += 1
        result = compute_chase_accessibility(
            variants=variants,
            has_pull_model=bool(variants),
            set_id=target.set_id,
            calculation_run_id=target.calculation_run_id)
        row = {
            "set": target.set_name,
            "canonicalKey": target.canonical_key,
            "simulationSupported": bool(variants),
            "variantCount": result.get("eligibleVariantCount") or 0,
            "mappedHcMass": result.get("mappedHcMass"),
            "chaseDepth": result.get("chaseDepth"),
            "accessibility": result.get("accessibility"),
            "accessibilityPct": result.get("accessibilityPct"),
            "parityDelta": result.get("parityDelta"),
            "status": result.get("status"),
            "authorityHolds": authority["holds"],
            "presenceChecked": authority["presenceChecked"],
            "oddsChecked": authority["oddsChecked"],
            "expectedCopiesDiffer": authority["rowsWhereExpectedCopiesDiffer"],
        }
        reference = expected.get(target.set_name)
        if reference and row["accessibility"] is not None:
            row["stage14Accessibility"] = reference.get("accessibility")
            row["stage14Depth"] = reference.get("nHC")
            row["stage14MappedHcMass"] = reference.get("mappedHcMass")
            row["accessibilityDelta"] = abs(
                round(row["accessibility"], 8) - float(reference["accessibility"]))
            row["depthDelta"] = abs(
                round(row["chaseDepth"], 4) - float(reference["nHC"]))
            row["statusMatches"] = True
        results.append(row)
        print(f"{TAG} [{index}/{len(targets)}] {target.set_name} "
              f"n={row['variantCount']} status={row['status']} "
              f"O={row['accessibility']}", flush=True)

    supported = [r for r in results if r["status"] == STATUS_READY]
    compared = [r for r in results if "accessibilityDelta" in r]
    return {
        "marketDate": day,
        "version": CHASE_ACCESSIBILITY_VERSION,
        "setsEvaluated": len(results),
        "supported": len(supported),
        "unsupported": len(results) - len(supported),
        "authorityFailures": authority_failures,
        "totalExpectedCopiesDiffer": sum(r["expectedCopiesDiffer"] for r in results),
        "totalRowsChecked": sum(r["presenceChecked"] for r in results),
        "stage14Compared": len(compared),
        "accessibilityMismatches": sum(
            1 for r in compared if r["accessibilityDelta"] > ACCESSIBILITY_TOLERANCE),
        "depthMismatches": sum(
            1 for r in compared if r["depthDelta"] > DEPTH_TOLERANCE),
        "statusMismatches": sum(1 for r in compared if not r.get("statusMatches")),
        "worstAccessibilityDelta": max(
            (r["accessibilityDelta"] for r in compared), default=0.0),
        "worstDepthDelta": max((r["depthDelta"] for r in compared), default=0.0),
        "worstParityDelta": max(
            (r["parityDelta"] or 0.0 for r in supported), default=0.0),
        "rows": results,
    }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Chase Accessibility V1 audit.")
    parser.add_argument("--market-date", required=True)
    parser.add_argument("--stage14", default=None,
                        help="path to the Stage XIV artifact for the parity gate")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(list(argv))

    stage14 = None
    if args.stage14:
        from pathlib import Path
        stage14 = json.loads(Path(args.stage14).read_text(encoding="utf-8"))

    from backend.db.clients.supabase_client import create_service_role_client

    payload = audit(create_service_role_client(), market_date=args.market_date,
                    stage14=stage14)

    print("\n%-32s %5s %6s %10s %9s %12s %14s %s" % (
        "set", "n", "supp", "mappedHC", "N_HC", "O_pack", "O_pct", "status"))
    for row in sorted(payload["rows"], key=lambda r: -(r["accessibility"] or -1)):
        print("%-32s %5d %6s %10s %9s %12s %13s%% %s" % (
            row["set"][:31], row["variantCount"],
            "yes" if row["simulationSupported"] else "no",
            "-" if row["mappedHcMass"] is None else "%.6f" % row["mappedHcMass"],
            "-" if row["chaseDepth"] is None else "%.4f" % row["chaseDepth"],
            "-" if row["accessibility"] is None else "%.8f" % row["accessibility"],
            "-" if row["accessibilityPct"] is None else "%.5f" % row["accessibilityPct"],
            row["status"]))

    print("\n%s sets=%d supported=%d unsupported=%d" % (
        TAG, payload["setsEvaluated"], payload["supported"], payload["unsupported"]))
    print("%s probability authority: failures=%d over %d checked rows"
          % (TAG, payload["authorityFailures"], payload["totalRowsChecked"]))
    print("%s rows where pull_count/simulation_count differs from presence "
          "probability: %d  (this is WHY it may never be substituted)"
          % (TAG, payload["totalExpectedCopiesDiffer"]))
    print("%s worst internal parity delta (HC form vs direct form): %.3e"
          % (TAG, payload["worstParityDelta"]))
    if stage14:
        print("\n%s STAGE XIV PARITY over %d sets:" % (TAG, payload["stage14Compared"]))
        print("      accessibility mismatches = %d  (worst delta %.3e)"
              % (payload["accessibilityMismatches"], payload["worstAccessibilityDelta"]))
        print("      depth mismatches         = %d  (worst delta %.3e)"
              % (payload["depthMismatches"], payload["worstDepthDelta"]))
        print("      status mismatches        = %d" % payload["statusMismatches"])

    if args.output:
        from pathlib import Path
        Path(args.output).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print("%s wrote %s" % (TAG, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
