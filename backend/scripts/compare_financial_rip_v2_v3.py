"""Compare Financial RIP V2 against Financial RIP V3 across the current cohort.

WHAT THIS ANSWERS
-----------------
V3 changes what the financial score measures: from 60% Profit / 25% Safety /
15% Stability to a six-component profile of the actual outcome distribution.
That WILL move ranks. This report exists so the movement can be inspected and
explained set by set before and after the cutover, rather than discovered as a
surprise on a public leaderboard.

It reports, per set: both scores, both ranks, the deltas, every V3 component
score, the raw metrics that produced them, availability, the simulation run and
price used, and the jackpot-dependence diagnostics that explain a large mover.

AUDIT CASES, NOT EXPECTED ANSWERS
---------------------------------
Four sets are worth reading carefully because they exercise different corners of
the model. They are listed as CASES; nothing is asserted about them and no score
is hardcoded. The report prints what the current simulations actually say:

  * Journey Together      - should benefit where its realistic upper tail is
                            strong relative to cost even if its extreme jackpot
                            is not.
  * Ascended Heroes       - should show weak Realistic Upside at the current
                            price when P95 sits below cost, while still showing
                            strong Jackpot Upside.
  * Phantasmal Flames     - may show strong Jackpot Upside, but must NOT reach a
                            high overall V3 purely on one or two extreme cards;
                            Jackpot Upside is capped at 10 points and Base
                            Economics excludes the top 1%.
  * Perfect Order         - a general reference case.

A directional expectation that the data contradicts is a finding to investigate,
not a number to force.

P05 IS NOT A V3 INPUT
---------------------
The report prints P05 alongside so the claim is checkable: a set with a lower
P05 and otherwise identical V3 inputs must have an identical V3 score.

READ-ONLY. Writes nothing to the database.

USAGE
-----
    python -m backend.scripts.compare_financial_rip_v2_v3
    python -m backend.scripts.compare_financial_rip_v2_v3 --json comparison.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V3_VERSION,
)
from backend.desirability.scoring_config import FINANCIAL_RIP_V2_VERSION
from backend.desirability.weighted_rip import spearman

logger = logging.getLogger(__name__)

# Sets to surface in a dedicated section of the report. Presence here changes
# nothing about how a set is scored or ranked.
AUDIT_CASE_NAMES = (
    "Perfect Order",
    "Journey Together",
    "Ascended Heroes",
    "Phantasmal Flames",
)


def _finite(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _assign_ranks(entries: List[Dict[str, Any]], score_key: str, rank_key: str) -> None:
    """Descending rank with a deterministic set-id tie-break."""
    scored = [entry for entry in entries if _finite(entry.get(score_key)) is not None]
    scored.sort(key=lambda entry: (-(_finite(entry.get(score_key)) or 0.0), str(entry.get("setId") or "")))
    for entry in entries:
        entry[rank_key] = None
    for rank, entry in enumerate(scored, start=1):
        entry[rank_key] = rank


def load_rows() -> List[Dict[str, Any]]:
    from backend.db.clients.supabase_client import public_read_client

    response = (
        public_read_client.table("explore_rip_statistics_latest")
        .select("*")
        .order("run_at", desc=True)
        .limit(500)
        .execute()
    )
    rows = list(getattr(response, "data", None) or [])
    seen: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        target_id = str(row.get("set_id") or row.get("target_id") or "")
        if target_id and target_id not in seen:
            seen[target_id] = row
    return list(seen.values())


def _v2_score(row: Mapping[str, Any]) -> Optional[float]:
    """Financial RIP V2 = 0.60*Profit + 0.25*Safety + 0.15*Stability.

    Computed through the SAME canonical function the publication path uses, so
    the comparison cannot accidentally grade V3 against a reimplementation of V2.
    """
    from backend.desirability.weighted_rip import compute_financial_rip

    result = compute_financial_rip(
        {
            "profit": row.get("profit_score"),
            "safety": row.get("safety_score"),
            "stability": row.get("stability_score"),
        }
    )
    return _finite(result.get("score"))


def build_rows(raw_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for row in raw_rows:
        payload = _parse_payload(row.get("financial_rip_v3_payload"))
        components = payload.get("components") or {}
        disclosures = payload.get("distributionDisclosures") or {}
        depth = payload.get("depthAndRobustness") or {}

        def _raw(component: str, field: str) -> Optional[float]:
            block = components.get(component) or {}
            return _finite((block.get("raw") or {}).get(field))

        v3_available = bool(payload) and payload.get("status") == "ready"
        entries.append(
            {
                "set": str(row.get("set_name") or row.get("name") or row.get("set_id") or "unknown"),
                "setId": str(row.get("set_id") or row.get("target_id") or ""),
                "canonicalKey": row.get("canonical_key"),
                "v2Score": _v2_score(row),
                "v3Score": _finite(payload.get("score")) if v3_available else None,
                "v3Available": v3_available,
                "v3UnavailableReason": None if v3_available else (
                    payload.get("statusReason") or "no_financial_rip_v3_payload_on_latest_run"
                ),
                "calculationRunId": row.get("calculation_run_id"),
                "runAt": row.get("run_at"),
                "packCost": _finite(row.get("pack_cost")),
                "components": {
                    key: _finite((components.get(key) or {}).get("score"))
                    for key in FINANCIAL_RIP_V3_COMPONENT_ORDER
                },
                "raw": {
                    "trueWinProbability": _raw("true_win_frequency", "trueWinProbability"),
                    "typicalRetentionRatio": _raw("typical_retention", "typicalRetentionRatio"),
                    "averageRetentionGivenLoss": _raw("loss_resilience", "averageRetentionGivenLoss"),
                    "hardLossProbability": _raw("loss_resilience", "hardLossProbability"),
                    "p95ThresholdRatio": _raw("realistic_upside", "p95ThresholdRatio"),
                    "realisticTailMeanRatio": _raw("realistic_upside", "realisticTailMeanRatio"),
                    "p99ThresholdRatio": _raw("jackpot_upside", "p99ThresholdRatio"),
                    "jackpotTailMeanRatio": _raw("jackpot_upside", "jackpotTailMeanRatio"),
                    "totalRtpRatio": _raw("base_economic_efficiency", "totalRtpRatio"),
                    "baseRtpExcludingTop1Pct": _raw("base_economic_efficiency", "baseRtpExcludingTop1Pct"),
                    "jackpotValueShare": _raw("base_economic_efficiency", "jackpotValueShare"),
                    # Printed so the "P05 does not affect V3" claim is checkable
                    # against real data, not only against a unit test.
                    "p05Value": _finite(disclosures.get("p05Value")),
                },
                "jackpotDependence": {
                    "jackpotValueShare": _finite(depth.get("jackpotValueShare")),
                    "top1EvShare": _finite(depth.get("top1EvShare")),
                    "top2EvShare": _finite(depth.get("top2EvShare")),
                    "effectiveChaseCount": _finite(depth.get("effectiveChaseCount")),
                    "concentrationLabel": depth.get("concentrationLabel"),
                },
                "clippedInputs": list(
                    (payload.get("estimationDiagnostics") or {}).get("clippedInputs") or []
                ),
                "v2Pillars": {
                    "profit": _finite(row.get("profit_score")),
                    "safety": _finite(row.get("safety_score")),
                    "stability": _finite(row.get("stability_score")),
                },
            }
        )

    _assign_ranks(entries, "v2Score", "v2Rank")
    _assign_ranks(entries, "v3Score", "v3Rank")
    for entry in entries:
        v2, v3 = entry.get("v2Score"), entry.get("v3Score")
        entry["scoreDelta"] = round(v3 - v2, 4) if v2 is not None and v3 is not None else None
        r2, r3 = entry.get("v2Rank"), entry.get("v3Rank")
        # Positive = the set moved UP (toward rank 1) under V3.
        entry["rankDelta"] = (r2 - r3) if r2 is not None and r3 is not None else None
    return entries


def _pairwise_component_correlations(entries: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Spearman between every pair of V3 components.

    A pair near |rho| = 1 is two components measuring one axis, which silently
    overweights that axis. Report-only: nothing here re-tunes a weight.
    """
    keys = list(FINANCIAL_RIP_V3_COMPONENT_ORDER)
    pairs: List[Dict[str, Any]] = []
    for index, left in enumerate(keys):
        for right in keys[index + 1:]:
            xs: List[float] = []
            ys: List[float] = []
            for entry in entries:
                left_value = _finite((entry.get("components") or {}).get(left))
                right_value = _finite((entry.get("components") or {}).get(right))
                if left_value is None or right_value is None:
                    continue
                xs.append(left_value)
                ys.append(right_value)
            rho = spearman(xs, ys)
            pairs.append(
                {
                    "components": [left, right],
                    "n": len(xs),
                    "spearman": round(rho, 4) if rho is not None else None,
                    "redundancyFlag": bool(rho is not None and abs(rho) > 0.80),
                }
            )
    return pairs


def build_report(raw_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    entries = build_rows(raw_rows)
    paired = [
        entry
        for entry in entries
        if entry.get("v2Score") is not None and entry.get("v3Score") is not None
    ]
    rank_spearman = spearman(
        [entry["v2Score"] for entry in paired],
        [entry["v3Score"] for entry in paired],
    )
    movers = sorted(
        (entry for entry in entries if entry.get("rankDelta") is not None),
        key=lambda entry: entry["rankDelta"],
        reverse=True,
    )
    clip_counts: Dict[str, int] = {}
    for entry in entries:
        for metric in entry["clippedInputs"]:
            clip_counts[metric] = clip_counts.get(metric, 0) + 1

    unavailable = [
        {
            "set": entry["set"],
            "reason": entry["v3UnavailableReason"],
            "remediation": (
                "Re-run the simulation. V3 is not backfillable from stored "
                "percentiles: the realistic-tail and top-1% conditional means "
                "require the original outcome vector."
            ),
        }
        for entry in entries
        if not entry["v3Available"]
    ]

    return {
        "v2Version": FINANCIAL_RIP_V2_VERSION,
        "v3Version": FINANCIAL_RIP_V3_VERSION,
        "v3NormalizationVersion": FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
        "setCount": len(entries),
        "comparableSetCount": len(paired),
        "rows": entries,
        "spearmanV2VsV3": round(rank_spearman, 4) if rank_spearman is not None else None,
        "componentCorrelations": _pairwise_component_correlations(paired),
        "largestPositiveRankMovers": movers[:10],
        "largestNegativeRankMovers": list(reversed(movers))[:10],
        "clippingCounts": clip_counts,
        "missingDataCount": len(unavailable),
        "unavailableSets": unavailable,
        "auditCases": [
            entry for entry in entries if entry["set"] in AUDIT_CASE_NAMES
        ],
    }


def _fmt(value: Optional[float], decimals: int = 2) -> str:
    return "—" if value is None else f"{value:,.{decimals}f}"


def print_report(report: Mapping[str, Any]) -> None:
    print("=" * 118)
    print("FINANCIAL RIP V2 vs V3 — COMPARISON")
    print("=" * 118)
    print(f"V2: {report['v2Version']}")
    print(f"V3: {report['v3Version']}  ({report['v3NormalizationVersion']})")
    print(f"Sets: {report['setCount']}   Comparable: {report['comparableSetCount']}")
    print(f"Spearman(V2, V3): {_fmt(report['spearmanV2VsV3'], 4)}")
    print()

    header = f"{'Set':<28}{'V2':>7}{'#V2':>5}{'V3':>7}{'#V3':>5}{'dScore':>8}{'dRank':>7}  {'Run date':<12}{'Cost':>7}"
    print(header)
    print("-" * len(header))
    for entry in sorted(
        report["rows"], key=lambda item: (item.get("v3Rank") is None, item.get("v3Rank") or 0)
    ):
        print(
            f"{entry['set'][:27]:<28}"
            f"{_fmt(entry['v2Score'], 1):>7}"
            f"{(entry['v2Rank'] or '—'):>5}"
            f"{_fmt(entry['v3Score'], 1):>7}"
            f"{(entry['v3Rank'] or '—'):>5}"
            f"{_fmt(entry['scoreDelta'], 1):>8}"
            f"{(entry['rankDelta'] if entry['rankDelta'] is not None else '—'):>7}"
            f"  {str(entry['runAt'] or '')[:10]:<12}"
            f"{_fmt(entry['packCost'], 2):>7}"
        )

    print()
    print("COMPONENT SCORES")
    comp_header = f"{'Set':<28}" + "".join(f"{key[:9]:>11}" for key in FINANCIAL_RIP_V3_COMPONENT_ORDER)
    print(comp_header)
    print("-" * len(comp_header))
    for entry in report["rows"]:
        if not entry["v3Available"]:
            continue
        print(
            f"{entry['set'][:27]:<28}"
            + "".join(
                f"{_fmt(entry['components'].get(key), 1):>11}"
                for key in FINANCIAL_RIP_V3_COMPONENT_ORDER
            )
        )

    print()
    print("AUDIT CASES (reported, never asserted)")
    print("-" * 118)
    for entry in report["auditCases"]:
        print(f"{entry['set']}:")
        if not entry["v3Available"]:
            print(f"  V3 unavailable — {entry['v3UnavailableReason']}")
            continue
        raw = entry["raw"]
        print(
            f"  V2 {_fmt(entry['v2Score'], 1)} (#{entry['v2Rank']})  ->  "
            f"V3 {_fmt(entry['v3Score'], 1)} (#{entry['v3Rank']})  "
            f"rank delta {entry['rankDelta']}"
        )
        print(
            f"  true-win {_fmt(raw['trueWinProbability'], 4)}  "
            f"P50/cost {_fmt(raw['typicalRetentionRatio'], 3)}  "
            f"P95/cost {_fmt(raw['p95ThresholdRatio'], 3)}  "
            f"95-99 mean/cost {_fmt(raw['realisticTailMeanRatio'], 3)}"
        )
        print(
            f"  P99/cost {_fmt(raw['p99ThresholdRatio'], 3)}  "
            f"top-1% mean/cost {_fmt(raw['jackpotTailMeanRatio'], 3)}  "
            f"jackpot value share {_fmt(raw['jackpotValueShare'], 4)}"
        )
        print(
            f"  total RTP {_fmt(raw['totalRtpRatio'], 3)}  "
            f"base RTP (ex top 1%) {_fmt(raw['baseRtpExcludingTop1Pct'], 3)}  "
            f"P05 {_fmt(raw['p05Value'], 2)} (NOT a V3 input)"
        )
        print(f"  depth: {entry['jackpotDependence']['concentrationLabel']}")

    print()
    print("LARGEST RANK MOVERS (positive = moved up under V3)")
    for entry in report["largestPositiveRankMovers"][:5]:
        print(f"  +{entry['rankDelta']:>3}  {entry['set']}")
    for entry in report["largestNegativeRankMovers"][:5]:
        print(f"  {entry['rankDelta']:>4}  {entry['set']}")

    print()
    print("COMPONENT PAIRWISE SPEARMAN")
    for pair in report["componentCorrelations"]:
        flag = "  <-- redundancy flag" if pair["redundancyFlag"] else ""
        print(f"  {pair['components'][0]:<26} x {pair['components'][1]:<26} {_fmt(pair['spearman'], 3):>7}{flag}")

    if report["clippingCounts"]:
        print()
        print("SATURATION / CLIPPING COUNTS")
        for metric, count in sorted(report["clippingCounts"].items(), key=lambda item: -item[1]):
            print(f"  {metric:<34} {count}")

    if report["unavailableSets"]:
        print()
        print(f"V3 UNAVAILABLE ({report['missingDataCount']} sets)")
        for entry in report["unavailableSets"]:
            print(f"  - {entry['set']}: {entry['reason']}")
        print()
        print("  Rerun, per set:")
        print("      python -m backend.jobs.evr_runner --set <canonical_key> --input-source db")
    print("=" * 118)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", default=None, help="Write the report as JSON.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        rows = load_rows()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED to read explore_rip_statistics_latest: {exc}", file=sys.stderr)
        return 2

    report = build_report(rows)
    print_report(report)

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, default=str)
        print(f"\nWrote {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
