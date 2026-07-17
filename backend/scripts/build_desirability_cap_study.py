"""Cap selection for the Overall RIP desirability adjustment.

Compares CAP=3 against CAP=5 across every set with a valid Financial RIP and
reports the guardrails that decide which ships. Read-only: it writes no rows and
never mutates the shipping cap. The selected value is set by hand in
``scoring_config.DESIRABILITY_ADJUSTMENT_CAP`` once this report is read.

Guardrails (a cap ships only if ALL pass):
  1. No adjustment exceeds the configured cap.
  2. Median absolute adjustment <= 2.5.
  3. Financial RIP < 40 cannot become Overall RIP > 50 via desirability.
  4. A set >= 10 Financial RIP points behind another cannot overtake it on
     desirability alone.
  5. Five largest positive/negative adjustments reported.
  6. Score movement reported separately from rank movement.
  7. Material rank reversals enumerated for manual explanation.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.desirability.scoring_config import DESIRABILITY_ADJUSTMENT_CAP_CANDIDATES
from backend.desirability.weighted_rip import compute_financial_rip, compute_overall_rip

logger = logging.getLogger(__name__)

MEDIAN_ABS_ADJUSTMENT_LIMIT = 2.5
LOW_FINANCIAL_RIP = 40.0
HIGH_OVERALL_RIP = 50.0
OVERTAKE_GAP = 10.0


def _rank(rows: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    scored = [row for row in rows if row.get(key) is not None]
    scored.sort(key=lambda row: (-(row[key]), str(row.get("set_name") or "")))
    return {str(row["set_id"]): rank for rank, row in enumerate(scored, start=1)}


def evaluate_cap(rows: List[Dict[str, Any]], cap: float) -> Dict[str, Any]:
    """Every guardrail for one cap, over rows that have a valid Financial RIP."""
    entries: List[Dict[str, Any]] = []
    for row in rows:
        pillars = {
            "profit": row.get("profit_score"),
            "safety": row.get("safety_score"),
            "stability": row.get("stability_score"),
        }
        financial = compute_financial_rip(pillars)
        if financial.get("score") is None:
            continue
        overall = compute_overall_rip(pillars, row.get("desirability_score"), cap=cap)
        adjustment_payload = overall.get("desirabilityAdjustment") or {}
        entries.append(
            {
                "set_id": row.get("set_id"),
                "set_name": row.get("set_name"),
                "financial_rip": financial["score"],
                "desirability": row.get("desirability_score"),
                "raw_adjustment": adjustment_payload.get("rawAdjustment"),
                "adjustment": adjustment_payload.get("adjustment"),
                "clamped": adjustment_payload.get("clamped"),
                "overall_rip": overall.get("score"),
            }
        )

    adjusted = [entry for entry in entries if entry["adjustment"] is not None]
    abs_adjustments = [abs(entry["adjustment"]) for entry in adjusted]
    median_abs = statistics.median(abs_adjustments) if abs_adjustments else 0.0
    max_abs = max(abs_adjustments) if abs_adjustments else 0.0

    financial_ranks = _rank(entries, "financial_rip")
    overall_ranks = _rank(entries, "overall_rip")
    for entry in entries:
        set_id = str(entry["set_id"])
        entry["financial_rank"] = financial_ranks.get(set_id)
        entry["overall_rank"] = overall_ranks.get(set_id)
        entry["rank_delta"] = (
            entry["financial_rank"] - entry["overall_rank"]
            if entry["financial_rank"] and entry["overall_rank"]
            else None
        )

    # Guardrail 3
    low_to_high = [
        entry for entry in adjusted
        if entry["financial_rip"] < LOW_FINANCIAL_RIP and entry["overall_rip"] > HIGH_OVERALL_RIP
    ]

    # Guardrail 4: a set >=10 Financial points behind that ends up ahead.
    overtakes: List[Dict[str, Any]] = []
    for behind in adjusted:
        for ahead in adjusted:
            if behind["set_id"] == ahead["set_id"]:
                continue
            gap = ahead["financial_rip"] - behind["financial_rip"]
            if gap >= OVERTAKE_GAP and behind["overall_rip"] > ahead["overall_rip"]:
                overtakes.append(
                    {
                        "overtaker": behind["set_name"],
                        "overtaken": ahead["set_name"],
                        "financial_gap": round(gap, 4),
                        "overtaker_overall": behind["overall_rip"],
                        "overtaken_overall": ahead["overall_rip"],
                    }
                )

    by_adjustment = sorted(adjusted, key=lambda entry: entry["adjustment"], reverse=True)
    reversals = [
        entry for entry in entries
        if entry["rank_delta"] is not None and abs(entry["rank_delta"]) >= 1
    ]
    reversals.sort(key=lambda entry: abs(entry["rank_delta"]), reverse=True)

    guardrails = {
        "1_no_adjustment_exceeds_cap": max_abs <= cap + 1e-9,
        "2_median_abs_adjustment_within_limit": median_abs <= MEDIAN_ABS_ADJUSTMENT_LIMIT,
        "3_no_low_financial_becomes_high_overall": not low_to_high,
        "4_no_desirability_only_overtake_across_10pt_gap": not overtakes,
    }
    positive = [entry for entry in adjusted if entry["adjustment"] > 0]
    return {
        "cap": cap,
        "n": len(entries),
        "guardrails": guardrails,
        "passes": all(guardrails.values()),
        # Every set's desirability sits above the 50 baseline in the current
        # data, so the adjustment is positive for all of them. Reported because
        # a "bounded +/- adjustment" that is never negative behaves as a bonus,
        # which is a different product claim from the one the formula implies.
        "positive_adjustment_count": len(positive),
        "negative_adjustment_count": len(adjusted) - len(positive),
        "min_desirability": min((entry["desirability"] for entry in adjusted), default=None),
        "median_abs_adjustment": round(median_abs, 4),
        "max_abs_adjustment": round(max_abs, 4),
        "clamped_count": sum(1 for entry in adjusted if entry["clamped"]),
        "guardrail_3_violations": low_to_high,
        "guardrail_4_violations": overtakes[:20],
        "top_5_positive_adjustments": by_adjustment[:5],
        "top_5_negative_adjustments": by_adjustment[-5:][::-1],
        "rank_reversals": reversals[:20],
        "rank_changed_count": sum(1 for entry in entries if entry.get("rank_delta")),
        "entries": entries,
    }


def load_rows(pillars_json: Optional[str] = None) -> List[Dict[str, Any]]:
    """Live rows: simulated pillars + Universal Set Desirability per set.

    ``pillars_json`` accepts a pre-fetched list of
    ``{set_id, set_name, profit_score, safety_score, stability_score}`` rows.
    The `explore_rip_statistics_latest` view is a ~6s windowed query against an
    8s statement_timeout, so on a cold cache it cannot be read through PostgREST
    at all; this lets the study run from a direct SQL extract of the same rows
    instead of blocking on it. The desirability bundle is still read live.
    """
    from backend.db.services.universal_set_desirability_service import (
        get_universal_desirability_bundle,
    )

    if pillars_json:
        stats_rows = json.loads(Path(pillars_json).read_text(encoding="utf-8"))
    else:
        from backend.db.clients.supabase_client import public_read_client
        from backend.db.services.public_read_retry import run_batch_read_with_retry

        stats = run_batch_read_with_retry(
            lambda: (
                public_read_client.table("explore_rip_statistics_latest")
                .select("set_id,set_name,profit_score,safety_score,stability_score")
                .execute()
            ),
            operation_name="cap_study.explore_rip_statistics_latest",
        )
        stats_rows = stats.data or []

    bundle = get_universal_desirability_bundle()
    if bundle.get("status") != "ok":
        raise RuntimeError("universal desirability bundle failed to build; cap study aborted")
    payloads = bundle.get("payloads") or {}

    rows: List[Dict[str, Any]] = []
    for row in stats_rows:
        set_id = str(row.get("set_id"))
        universal = payloads.get(set_id) or {}
        coverage = (universal.get("coverage") or {}).get("status")
        rows.append(
            {
                "set_id": set_id,
                "set_name": universal.get("set_name") or row.get("set_name") or set_id,
                "profit_score": row.get("profit_score"),
                "safety_score": row.get("safety_score"),
                "stability_score": row.get("stability_score"),
                "desirability_score": universal.get("score") if coverage == "full" else None,
            }
        )
    return rows


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Compare desirability adjustment caps")
    parser.add_argument("--json-out", help="Write the full report to this path")
    parser.add_argument(
        "--pillars-json",
        help="Pre-fetched simulation pillar rows, bypassing the slow rip-statistics view",
    )
    args = parser.parse_args()

    rows = load_rows(args.pillars_json)
    report = {
        "candidates": [evaluate_cap(rows, cap) for cap in DESIRABILITY_ADJUSTMENT_CAP_CANDIDATES],
        "median_abs_adjustment_limit": MEDIAN_ABS_ADJUSTMENT_LIMIT,
    }
    # The literal shipping rule: cap 5 ships ONLY if every guardrail passes;
    # otherwise cap 3. Not "the largest that passes" - cap 3 is the stated
    # fallback and ships whether or not it clears the median limit, because the
    # alternative to a capped adjustment is no adjustment at all.
    cap_5 = next((entry for entry in report["candidates"] if entry["cap"] == 5.0), None)
    report["recommended_cap"] = 5.0 if (cap_5 and cap_5["passes"]) else 3.0
    report["recommendation_rule"] = (
        "Ship cap 5 only if every guardrail passes; otherwise ship cap 3."
    )

    for entry in report["candidates"]:
        print(f"\n=== CAP {entry['cap']} === n={entry['n']} passes={entry['passes']}")
        print("guardrails:", json.dumps(entry["guardrails"], indent=2))
        print("median_abs_adjustment:", entry["median_abs_adjustment"],
              "max_abs:", entry["max_abs_adjustment"], "clamped:", entry["clamped_count"])
        print("rank_changed_count:", entry["rank_changed_count"])
        print("top_5_positive:", json.dumps(
            [{k: e[k] for k in ("set_name", "financial_rip", "desirability", "adjustment", "overall_rip")}
             for e in entry["top_5_positive_adjustments"]], indent=2))
        print("top_5_negative:", json.dumps(
            [{k: e[k] for k in ("set_name", "financial_rip", "desirability", "adjustment", "overall_rip")}
             for e in entry["top_5_negative_adjustments"]], indent=2))
        print("guardrail_3_violations:", len(entry["guardrail_3_violations"]))
        print("guardrail_4_violations:", len(entry["guardrail_4_violations"]))
        print("rank_reversals:", json.dumps(
            [{k: e[k] for k in ("set_name", "financial_rank", "overall_rank", "rank_delta", "adjustment")}
             for e in entry["rank_reversals"]], indent=2))
    print("\nRECOMMENDED_CAP:", report["recommended_cap"])

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print("wrote", args.json_out)


if __name__ == "__main__":
    main()
