"""Audit the D/F/P Collector Appeal against legacy CA7, and V6 against V5.

WHAT THIS ANSWERS
-----------------
Two changes land together, and each moves ranks for a different reason:

  1. Collector Appeal's formula gains the Desirable Outcome Frequency term:
         CA7 = D + 0.50 * P * (1 - D)
         CA  = D + 0.50 * (0.60F + 0.40P) * (1 - D)
  2. Overall RIP reweights from 90/10 to 80/20 and swaps CA7 for the new CA:
         V5 = 0.90 * FinancialRipV3 + 0.10 * CA7
         V6 = 0.80 * FinancialRipV3 + 0.20 * CA

Reporting them together, per set, is what makes it possible to say WHICH change
moved a set - a rank delta alone cannot distinguish "its appeal formula changed"
from "appeal got twice the weight".

DIAGNOSTICS ARE NOT A TUNING LOOP
---------------------------------
The correlations below are descriptive. The 0.60/0.40 structural split and the
0.50 headroom gain are construct decisions and are NOT adjusted because one
configuration produces a preferred ranking. Choosing weights by the rankings
they produce is fitting, and it would make every subsequent comparison
meaningless.

The four audit-case sets are printed in a dedicated section because they
exercise different corners of the model. Nothing is asserted about them and no
expected number is hardcoded; the report prints what the data says.

READ-ONLY. Writes nothing, applies no SQL, rebuilds no snapshot.

USAGE
-----
    python -m backend.scripts.audit_collector_appeal_v2
    python -m backend.scripts.audit_collector_appeal_v2 --json report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_CA7_VERSION,
    COLLECTOR_APPEAL_DUAL_PATH_WEIGHT,
    COLLECTOR_APPEAL_FREQUENCY_WEIGHT,
    COLLECTOR_APPEAL_HEADROOM_GAIN,
    COLLECTOR_APPEAL_V2_FORMULA_EXPRESSION,
    COLLECTOR_APPEAL_V2_VERSION,
)
from backend.desirability.scoring_config import (
    OVERALL_RIP_V6_VERSION,
    OVERALL_RIP_V6_WEIGHTS,
)
from backend.desirability.weighted_rip import spearman

logger = logging.getLogger(__name__)

AUDIT_CASE_NAMES = (
    "Perfect Order",
    "Journey Together",
    "Ascended Heroes",
    "Phantasmal Flames",
)

# The six Financial RIP V3 components, for the F-vs-financial correlations. If
# F correlated strongly with a financial component, the 20% Collector Appeal
# term would partly be re-weighting a signal Financial RIP already carries -
# a finding to surface, not to auto-correct.
V3_COMPONENT_KEYS = (
    "true_win_frequency",
    "typical_retention",
    "loss_resilience",
    "realistic_upside",
    "jackpot_upside",
    "base_economic_efficiency",
)


def _finite(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _assign_ranks(entries: List[Dict[str, Any]], score_key: str, rank_key: str) -> None:
    """Descending rank with a deterministic set-id tie-break."""
    scored = [entry for entry in entries if _finite(entry.get(score_key)) is not None]
    scored.sort(
        key=lambda entry: (-(_finite(entry.get(score_key)) or 0.0), str(entry.get("setId") or ""))
    )
    for entry in entries:
        entry[rank_key] = None
    for rank, entry in enumerate(scored, start=1):
        entry[rank_key] = rank


def load_targets() -> List[Dict[str, Any]]:
    """The ranked targets the publication path builds.

    Reads through ``get_rip_statistics_targets_payload`` rather than querying
    tables directly, so the audit describes the objects that would actually be
    published - including the Collector Appeal bundle, the V6 blend and the
    ranks - rather than a parallel reconstruction of them.
    """
    from backend.db.services.explore_rip_statistics_service import (
        get_rip_statistics_targets_payload,
    )

    payload = get_rip_statistics_targets_payload()
    return list(payload.get("targets") or [])


def build_rows(targets: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for target in targets:
        opening = target.get("openingExperience") or {}
        appeal = opening.get("collectorAppeal") or {}
        legacy_ca7 = opening.get("legacyCollectorAppealCA7") or {}
        frequency = opening.get("desirableOutcomeFrequency") or {}
        dual_path = opening.get("dualPathDepth") or {}
        roster = opening.get("rosterDesirability") or {}
        inputs = appeal.get("inputs") or {}
        coverage = opening.get("coverage") or {}

        financial_v3 = target.get("financialRipV3") or {}
        v3_components = financial_v3.get("components") or {}

        rows.append(
            {
                "set": str(target.get("name") or target.get("target_id") or "unknown"),
                "setId": str(target.get("target_id") or ""),
                "canonicalKey": target.get("canonical_key") or target.get("canonicalKey"),
                # --- the three Collector Appeal inputs ----------------------
                "d": _finite(inputs.get("rosterDesirability")),
                "dScore": _finite(roster.get("score")),
                "f": _finite(frequency.get("rawValue")),
                "fOneInN": _finite(frequency.get("impliedOddsOneInN")),
                "p": _finite(dual_path.get("rawValue")),
                "structuralOpeningAppeal": _finite(appeal.get("structuralOpeningAppeal")),
                "headroomBonus": _finite(appeal.get("headroomBonus")),
                # --- appeal scores, old and new -----------------------------
                "legacyCa7": _finite(legacy_ca7.get("score")),
                "collectorAppeal": _finite(appeal.get("score")),
                # --- financial + overall ------------------------------------
                "financialRipV3": _finite(financial_v3.get("score")),
                "overallRipV5": _finite((target.get("overallRipV5") or {}).get("score")),
                "overallRipV6": _finite((target.get("overallRipV6") or {}).get("score")),
                "v3Components": {
                    key: _finite((v3_components.get(key) or {}).get("score"))
                    for key in V3_COMPONENT_KEYS
                },
                # --- coverage / availability --------------------------------
                "eligibleSubjectCount": frequency.get("eligibleSubjectCount"),
                "eligibleCardCount": frequency.get("eligibleCardCount"),
                "coveredDemandShare": _finite(frequency.get("coveredDemandShare")),
                "slotGroupCount": frequency.get("slotGroupCount"),
                "frequencyStatus": frequency.get("status"),
                "availabilityReason": "; ".join(
                    str(reason) for reason in (coverage.get("reasons") or [])
                )
                or None,
                "pullModelAvailable": coverage.get("pullModelAvailable"),
            }
        )

    _assign_ranks(rows, "legacyCa7", "legacyCa7Rank")
    _assign_ranks(rows, "collectorAppeal", "collectorAppealRank")
    _assign_ranks(rows, "overallRipV5", "overallRipV5Rank")
    _assign_ranks(rows, "overallRipV6", "overallRipV6Rank")

    for row in rows:
        old, new = row.get("legacyCa7"), row.get("collectorAppeal")
        row["collectorAppealDelta"] = round(new - old, 4) if old is not None and new is not None else None
        old_rank, new_rank = row.get("legacyCa7Rank"), row.get("collectorAppealRank")
        # Positive = moved UP (toward rank 1).
        row["collectorAppealRankDelta"] = (
            old_rank - new_rank if old_rank is not None and new_rank is not None else None
        )
        v5, v6 = row.get("overallRipV5"), row.get("overallRipV6")
        row["overallDelta"] = round(v6 - v5, 4) if v5 is not None and v6 is not None else None
        v5_rank, v6_rank = row.get("overallRipV5Rank"), row.get("overallRipV6Rank")
        row["overallRankDelta"] = (
            v5_rank - v6_rank if v5_rank is not None and v6_rank is not None else None
        )
    return rows


def _paired(rows: Sequence[Mapping[str, Any]], left, right):
    xs: List[float] = []
    ys: List[float] = []
    for row in rows:
        a, b = left(row), right(row)
        if a is None or b is None:
            continue
        xs.append(a)
        ys.append(b)
    rho = spearman(xs, ys)
    return {"n": len(xs), "spearman": round(rho, 4) if rho is not None else None}


def build_report(targets: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = build_rows(targets)
    scored = [row for row in rows if row.get("collectorAppeal") is not None]

    appeal_movers = sorted(
        (row for row in rows if row.get("collectorAppealRankDelta") is not None),
        key=lambda row: row["collectorAppealRankDelta"],
        reverse=True,
    )
    overall_movers = sorted(
        (row for row in rows if row.get("overallRankDelta") is not None),
        key=lambda row: row["overallRankDelta"],
        reverse=True,
    )

    component_correlations = {
        key: _paired(scored, lambda r: r["f"], lambda r, k=key: (r["v3Components"] or {}).get(k))
        for key in V3_COMPONENT_KEYS
    }

    unavailable = [
        {
            "set": row["set"],
            "reason": row.get("availabilityReason") or row.get("frequencyStatus"),
            "pullModelAvailable": row.get("pullModelAvailable"),
            "coveredDemandShare": row.get("coveredDemandShare"),
        }
        for row in rows
        if row.get("collectorAppeal") is None
    ]

    from backend.desirability.collector_appeal_fingerprint import current_fingerprint

    return {
        "collectorAppealVersion": COLLECTOR_APPEAL_V2_VERSION,
        "collectorAppealFormula": COLLECTOR_APPEAL_V2_FORMULA_EXPRESSION,
        "legacyCollectorAppealVersion": COLLECTOR_APPEAL_CA7_VERSION,
        "overallRipVersion": OVERALL_RIP_V6_VERSION,
        "overallRipWeights": dict(OVERALL_RIP_V6_WEIGHTS),
        "structuralWeights": {
            "desirableOutcomeFrequency": COLLECTOR_APPEAL_FREQUENCY_WEIGHT,
            "dualPathDepth": COLLECTOR_APPEAL_DUAL_PATH_WEIGHT,
            "headroomGain": COLLECTOR_APPEAL_HEADROOM_GAIN,
        },
        "formulaFingerprint": current_fingerprint(),
        "setCount": len(rows),
        "scoredSetCount": len(scored),
        "rows": rows,
        "largestCollectorAppealMovers": {
            "up": appeal_movers[:10],
            "down": list(reversed(appeal_movers))[:10],
        },
        "largestOverallMovers": {
            "up": overall_movers[:10],
            "down": list(reversed(overall_movers))[:10],
        },
        "correlations": {
            "dVsF": _paired(scored, lambda r: r["d"], lambda r: r["f"]),
            "dVsP": _paired(scored, lambda r: r["d"], lambda r: r["p"]),
            "fVsP": _paired(scored, lambda r: r["f"], lambda r: r["p"]),
            "legacyCa7VsCollectorAppeal": _paired(
                scored, lambda r: r["legacyCa7"], lambda r: r["collectorAppeal"]
            ),
            "overallV5VsV6": _paired(
                scored, lambda r: r["overallRipV5"], lambda r: r["overallRipV6"]
            ),
            "fVsFinancialRipV3Components": component_correlations,
            "note": (
                "Descriptive only. These never tune the 0.60/0.40 structural "
                "split, the 0.50 headroom gain, or the 80/20 Overall RIP weights."
            ),
        },
        "coverageFailures": unavailable,
        "missingPullModelCount": sum(
            1 for row in rows if row.get("pullModelAvailable") is False
        ),
        "auditCases": [row for row in rows if row["set"] in AUDIT_CASE_NAMES],
    }


def _fmt(value: Optional[float], decimals: int = 2) -> str:
    return "—" if value is None else f"{value:,.{decimals}f}"


def _fmt_delta(value: Optional[int]) -> str:
    return "—" if value is None else f"{value:+d}"


def print_report(report: Mapping[str, Any]) -> None:
    print("=" * 124)
    print("COLLECTOR APPEAL (D/F/P) vs LEGACY CA7  —  OVERALL RIP V6 (80/20) vs V5 (90/10)")
    print("=" * 124)
    print(f"Collector Appeal : {report['collectorAppealVersion']}")
    print(f"Formula          : {report['collectorAppealFormula']}")
    print(f"Overall RIP      : {report['overallRipVersion']}  {report['overallRipWeights']}")
    print(f"Fingerprint      : {report['formulaFingerprint'][:32]}…")
    print(f"Sets: {report['setCount']}   With a Collector Appeal: {report['scoredSetCount']}")
    print()

    header = (
        f"{'Set':<26}{'D':>7}{'F':>8}{'1-in-N':>9}{'P':>7}"
        f"{'CA7':>8}{'CA':>8}{'dCA':>7}{'#CA7':>6}{'#CA':>6}"
        f"{'FinV3':>8}{'V5':>8}{'V6':>8}{'dRank':>7}"
    )
    print(header)
    print("-" * len(header))
    for row in sorted(
        report["rows"],
        key=lambda item: (item.get("overallRipV6Rank") is None, item.get("overallRipV6Rank") or 0),
    ):
        print(
            f"{row['set'][:25]:<26}"
            f"{_fmt(row['d'], 3):>7}"
            f"{_fmt(row['f'], 4):>8}"
            f"{_fmt(row['fOneInN'], 1):>9}"
            f"{_fmt(row['p'], 3):>7}"
            f"{_fmt(row['legacyCa7'], 1):>8}"
            f"{_fmt(row['collectorAppeal'], 1):>8}"
            f"{_fmt(row['collectorAppealDelta'], 1):>7}"
            f"{(row['legacyCa7Rank'] or '—'):>6}"
            f"{(row['collectorAppealRank'] or '—'):>6}"
            f"{_fmt(row['financialRipV3'], 1):>8}"
            f"{_fmt(row['overallRipV5'], 1):>8}"
            f"{_fmt(row['overallRipV6'], 1):>8}"
            f"{_fmt_delta(row['overallRankDelta']):>7}"
        )

    print()
    print("AUDIT CASES (reported, never asserted)")
    print("-" * 124)
    for row in report["auditCases"]:
        print(f"{row['set']}  [{row.get('canonicalKey')}]")
        if row["collectorAppeal"] is None:
            print(f"  Collector Appeal unavailable — {row.get('availabilityReason')}")
            continue
        print(
            f"  D={_fmt(row['d'], 4)}  F={_fmt(row['f'], 4)} (~1 in {_fmt(row['fOneInN'], 1)})  "
            f"P={_fmt(row['p'], 4)}  structural={_fmt(row['structuralOpeningAppeal'], 4)}  "
            f"headroomBonus={_fmt(row['headroomBonus'], 4)}"
        )
        print(
            f"  CA7 {_fmt(row['legacyCa7'], 2)} (#{row['legacyCa7Rank']})  ->  "
            f"CA {_fmt(row['collectorAppeal'], 2)} (#{row['collectorAppealRank']})   "
            f"delta {_fmt(row['collectorAppealDelta'], 2)}"
        )
        print(
            f"  V5 {_fmt(row['overallRipV5'], 2)} (#{row['overallRipV5Rank']})  ->  "
            f"V6 {_fmt(row['overallRipV6'], 2)} (#{row['overallRipV6Rank']})   "
            f"rank delta {_fmt_delta(row['overallRankDelta'])}"
        )
        print(
            f"  eligible subjects={row['eligibleSubjectCount']}  cards={row['eligibleCardCount']}  "
            f"coverage={_fmt(row['coveredDemandShare'], 3)}  slots={row['slotGroupCount']}"
        )

    print()
    print("LARGEST COLLECTOR APPEAL MOVERS (positive = moved up)")
    for row in report["largestCollectorAppealMovers"]["up"][:5]:
        print(f"  {_fmt_delta(row['collectorAppealRankDelta']):>4}  {row['set']}")
    for row in report["largestCollectorAppealMovers"]["down"][:5]:
        print(f"  {_fmt_delta(row['collectorAppealRankDelta']):>4}  {row['set']}")

    print()
    print("LARGEST OVERALL RIP MOVERS (V5 -> V6, positive = moved up)")
    for row in report["largestOverallMovers"]["up"][:5]:
        print(f"  {_fmt_delta(row['overallRankDelta']):>4}  {row['set']}")
    for row in report["largestOverallMovers"]["down"][:5]:
        print(f"  {_fmt_delta(row['overallRankDelta']):>4}  {row['set']}")

    print()
    print("CORRELATIONS (descriptive only)")
    correlations = report["correlations"]
    for key in ("dVsF", "dVsP", "fVsP", "legacyCa7VsCollectorAppeal", "overallV5VsV6"):
        entry = correlations[key]
        print(f"  {key:<28} n={entry['n']:<4} spearman={_fmt(entry['spearman'], 3)}")
    print("  F vs Financial RIP V3 components:")
    for key, entry in correlations["fVsFinancialRipV3Components"].items():
        print(f"    {key:<28} n={entry['n']:<4} spearman={_fmt(entry['spearman'], 3)}")

    if report["coverageFailures"]:
        print()
        print(f"COVERAGE FAILURES ({len(report['coverageFailures'])})")
        for entry in report["coverageFailures"]:
            print(
                f"  - {entry['set']}: {entry['reason']} "
                f"(pull model: {entry['pullModelAvailable']}, coverage: {_fmt(entry['coveredDemandShare'], 3)})"
            )
    print(f"\nSets with no pull model: {report['missingPullModelCount']}")
    print("=" * 124)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", default=None, help="Write the report as JSON.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        targets = load_targets()
    except Exception as exc:  # noqa: BLE001 - a read failure must be reported, not masked
        print(f"FAILED to build the RIP targets payload: {exc}", file=sys.stderr)
        return 2

    report = build_report(targets)
    print_report(report)

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, default=str)
        print(f"\nWrote {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
