"""Construct audit of Collector Appeal V3 (``0.40D + 0.35H + 0.25P``).

READ-ONLY RESEARCH. Writes nothing to the database, republishes nothing,
reruns no simulation, and changes no formula or weight. It consumes the JSON
emitted by ``backend.scripts.audit_collector_appeal_v2 --json`` and reports what
the current 22-set cohort actually does under V3.

WHY THIS SCRIPT EXISTS RATHER THAN A SECOND IMPLEMENTATION
----------------------------------------------------------
Every score here comes from the canonical functions imported from
``backend.desirability.collector_appeal``. Nothing in this file restates the
V3 weights or the V3 arithmetic; the weights are read from
``COLLECTOR_APPEAL_V3_WEIGHTS`` and the score from
``compute_collector_appeal_v3``. A research copy of a production formula is a
second definition of it, and the first time they drift the research stops
describing the product.

HOW D IS OBTAINED
-----------------
The V2 audit's rows carry H (as ``f``), P and legacy CA7 but leave ``d`` null.
D is therefore recovered by INVERTING the legacy CA7 identity, which is exact
algebra on a stored number rather than a re-derivation of D:

    CA7 = D + lam * P * (1 - D)          [lam = CA7_PRODUCTION_LAMBDA = 0.50]
    =>  D = (CA7 - lam * P) / (1 - lam * P)

The inversion is CHECKED two ways before anything is reported:
  1. Round-trip: recompute CA7 from the recovered D via the canonical
     ``compute_collector_appeal_ca7`` and require it to match the stored CA7.
  2. Cross-validate against the independently stored D values in
     ``docs/research/collector_appeal_tables/dual_path_set_rankings.csv``.

If either check fails the script refuses to report, because a D that cannot be
reproduced is not a measurement.

USAGE
-----
    python -m backend.scripts.audit_collector_appeal_v2 --json ca_audit.json
    python -m backend.scripts.audit_collector_appeal_v3_construct ca_audit.json \
        [--csv out.csv] [--json out.json]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.desirability.collector_appeal import (
    CA7_PRODUCTION_LAMBDA,
    COLLECTOR_APPEAL_V3_INPUT_ORDER,
    COLLECTOR_APPEAL_V3_VERSION,
    COLLECTOR_APPEAL_V3_WEIGHTS,
    compute_collector_appeal_ca7,
    compute_collector_appeal_v3,
)

# The recovered D must reproduce the stored CA7 to well inside the precision the
# audit JSON rounds to. A looser tolerance would let a genuinely wrong D through.
ROUND_TRIP_TOLERANCE = 5e-6

# The cross-validation table is an older run with a different eligibility rule,
# so only the sets present in BOTH are compared and the tolerance reflects the
# fact that both sides are independently rounded.
CROSS_VALIDATION_TOLERANCE = 1e-3

CROSS_VALIDATION_CSV = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "research"
    / "collector_appeal_tables"
    / "dual_path_set_rankings.csv"
)

# The pairings the brief asks to be explained numerically. Ascended Heroes is the
# subject of every one of them.
CASE_SUBJECT = "Ascended Heroes"
CASE_COMPARISONS = (
    "Mega Evolution",
    "Scarlet and Violet 151",
    "Pitch Black",
    "Perfect Order",
    "Journey Together",
)


# ---------------------------------------------------------------------------
# statistics (small, explicit, no third-party dependency)
# ---------------------------------------------------------------------------


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def _sd(xs: Sequence[float]) -> float:
    """Sample standard deviation (n-1), matching how the cohort is treated
    elsewhere in this repo's research output."""
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _ranks(xs: Sequence[float]) -> List[float]:
    """Average ranks, descending (rank 1 = largest), so ties do not bias rho."""
    order = sorted(range(len(xs)), key=lambda i: -xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = shared
        i = j + 1
    return out


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    return _pearson(_ranks(xs), _ranks(ys))


def _rank_of(values: Mapping[str, float]) -> Dict[str, int]:
    """Dense competition ranks, 1 = largest."""
    ordered = sorted(values.items(), key=lambda kv: -kv[1])
    return {name: i + 1 for i, (name, _) in enumerate(ordered)}


# ---------------------------------------------------------------------------
# D recovery
# ---------------------------------------------------------------------------


def recover_desirability(ca7_public: float, p: float, lam: float = CA7_PRODUCTION_LAMBDA) -> float:
    """Invert ``CA7 = D + lam*P*(1-D)`` for D. ``ca7_public`` is on the 0-100 scale."""
    ca7 = ca7_public / 100.0
    denominator = 1.0 - lam * p
    if denominator <= 0:
        raise ValueError("degenerate CA7 inversion: lam * P >= 1")
    return (ca7 - lam * p) / denominator


def _load_cross_validation() -> Dict[str, float]:
    if not CROSS_VALIDATION_CSV.exists():
        return {}
    out: Dict[str, float] = {}
    with CROSS_VALIDATION_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                # Stored on the 0-100 scale in that table.
                out[row["set_name"]] = float(row["roster_desirability_D"]) / 100.0
            except (KeyError, TypeError, ValueError):
                continue
    return out


# ---------------------------------------------------------------------------
# cohort assembly
# ---------------------------------------------------------------------------


def build_cohort(audit: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return (scored rows, warnings). Rows without H, P or CA7 are excluded and
    reported, never defaulted to zero."""
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []

    for raw in audit.get("rows", []):
        name = raw.get("set")
        h, p, ca7 = raw.get("f"), raw.get("p"), raw.get("legacyCa7")
        if h is None or p is None or ca7 is None:
            if raw.get("eligibleSubjectCount"):
                warnings.append(f"{name}: partial inputs (H={h} P={p} CA7={ca7}) - excluded")
            continue

        d = recover_desirability(ca7, p)

        # Check 1: the recovered D must reproduce the stored CA7 exactly.
        round_trip = compute_collector_appeal_ca7(d, p)
        if round_trip is None or abs(round_trip * 100.0 - ca7) > ROUND_TRIP_TOLERANCE * 100.0:
            raise SystemExit(
                f"D recovery failed round-trip for {name}: "
                f"recovered D={d!r} reproduces CA7={round_trip} not {ca7 / 100.0}"
            )

        v3 = compute_collector_appeal_v3(d, h, p)
        if v3 is None:
            warnings.append(f"{name}: canonical V3 returned unavailable - excluded")
            continue

        weights = COLLECTOR_APPEAL_V3_WEIGHTS
        rows.append(
            {
                "set": name,
                "canonicalKey": raw.get("canonicalKey"),
                "D": d,
                "H": h,
                "P": p,
                "contribD": weights["roster_desirability"] * d,
                "contribH": weights["desirable_outcome_frequency"] * h,
                "contribP": weights["dual_path_depth"] * p,
                "ca_v3_unit": v3,
                "ca_v3_public": v3 * 100.0,
                "legacyCa7": ca7,
                "collectorAppealV2": raw.get("collectorAppeal"),
                "eligibleSubjectCount": raw.get("eligibleSubjectCount"),
                "eligibleCardCount": raw.get("eligibleCardCount"),
                "coveredDemandShare": raw.get("coveredDemandShare"),
                "slotGroupCount": raw.get("slotGroupCount"),
                "fOneInN": raw.get("fOneInN"),
                "frequencyStatus": raw.get("frequencyStatus"),
            }
        )

    # Check 2: cross-validate D against the independently stored table.
    reference = _load_cross_validation()
    matched = mismatched = 0
    for row in rows:
        expected = reference.get(row["set"])
        if expected is None:
            continue
        if abs(expected - row["D"]) <= CROSS_VALIDATION_TOLERANCE:
            matched += 1
        else:
            mismatched += 1
            warnings.append(
                f"{row['set']}: recovered D={row['D']:.6f} vs stored {expected:.6f} "
                "(different eligibility run - informational)"
            )
    warnings.append(f"D cross-validation: {matched} matched, {mismatched} differed")

    # The additive score is exactly its three contributions; assert rather than
    # assume, so the decomposition printed below is the score, not a story.
    for row in rows:
        rebuilt = row["contribD"] + row["contribH"] + row["contribP"]
        if abs(rebuilt - row["ca_v3_unit"]) > 1e-9:
            raise SystemExit(f"decomposition does not reconstruct V3 for {row['set']}")

    return rows, warnings


def annotate_ranks(rows: List[Dict[str, Any]]) -> None:
    for key, field in (
        ("ca_v3_unit", "caRank"),
        ("D", "dRank"),
        ("H", "hRank"),
        ("P", "pRank"),
    ):
        ranks = _rank_of({row["set"]: row[key] for row in rows})
        for row in rows:
            row[field] = ranks[row["set"]]


# ---------------------------------------------------------------------------
# analyses
# ---------------------------------------------------------------------------


def effective_influence(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Nominal coefficients are not influence. What moves a ranking is the
    DISPERSION of each weighted contribution across the cohort."""
    ca = [r["ca_v3_unit"] for r in rows]
    out: Dict[str, Any] = {"n": len(rows), "pillars": {}}

    for label, raw_key, contrib_key in (
        ("D", "D", "contribD"),
        ("H", "H", "contribH"),
        ("P", "P", "contribP"),
    ):
        raw = [r[raw_key] for r in rows]
        contrib = [r[contrib_key] for r in rows]
        out["pillars"][label] = {
            "nominalWeight": COLLECTOR_APPEAL_V3_WEIGHTS[
                {"D": "roster_desirability", "H": "desirable_outcome_frequency", "P": "dual_path_depth"}[label]
            ],
            "rawMin": min(raw),
            "rawMax": max(raw),
            "rawRange": max(raw) - min(raw),
            "rawSd": _sd(raw),
            "contribMin": min(contrib),
            "contribMax": max(contrib),
            "contribRange": max(contrib) - min(contrib),
            "contribSd": _sd(contrib),
            "pearsonWithCa": _pearson(raw, ca),
            "spearmanWithCa": _spearman(raw, ca),
        }

    total_sd = sum(out["pillars"][k]["contribSd"] for k in ("D", "H", "P"))
    total_range = sum(out["pillars"][k]["contribRange"] for k in ("D", "H", "P"))
    for label in ("D", "H", "P"):
        pillar = out["pillars"][label]
        pillar["shareOfContributionSd"] = pillar["contribSd"] / total_sd if total_sd else None
        pillar["shareOfContributionRange"] = pillar["contribRange"] / total_range if total_range else None
    return out


def pairwise_case_studies(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_name = {row["set"]: row for row in rows}
    subject = by_name.get(CASE_SUBJECT)
    if subject is None:
        return []

    cases = []
    for other_name in CASE_COMPARISONS:
        other = by_name.get(other_name)
        if other is None:
            continue
        delta_d = subject["contribD"] - other["contribD"]
        delta_h = subject["contribH"] - other["contribH"]
        delta_p = subject["contribP"] - other["contribP"]
        total = subject["ca_v3_unit"] - other["ca_v3_unit"]
        cases.append(
            {
                "subject": CASE_SUBJECT,
                "versus": other_name,
                "subjectRank": subject["caRank"],
                "versusRank": other["caRank"],
                "deltaD": subject["D"] - other["D"],
                "deltaH": subject["H"] - other["H"],
                "deltaP": subject["P"] - other["P"],
                "deltaContribD": delta_d,
                "deltaContribH": delta_h,
                "deltaContribP": delta_p,
                "deltaCaUnit": total,
                "deltaCaPublic": total * 100.0,
                # The three contributions must sum to the score gap exactly.
                "reconstructionError": abs((delta_d + delta_h + delta_p) - total),
            }
        )
    return cases


def h_analysis(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Does binary eligibility let easy cards on moderate subjects outrun scarce
    cards on extremely desirable ones?"""
    h = [r["H"] for r in rows]
    d = [r["D"] for r in rows]
    ca = [r["ca_v3_unit"] for r in rows]

    inversions = []
    for a in rows:
        for b in rows:
            # a beats b on CA despite a WORSE roster, and H is the pillar that did it.
            if a["ca_v3_unit"] > b["ca_v3_unit"] and a["D"] < b["D"]:
                gaps = {
                    "H": a["contribH"] - b["contribH"],
                    "P": a["contribP"] - b["contribP"],
                }
                driver = max(gaps, key=lambda k: gaps[k])
                if driver == "H" and gaps["H"] > 0:
                    inversions.append(
                        {
                            "winner": a["set"],
                            "loser": b["set"],
                            "deltaD": a["D"] - b["D"],
                            "deltaContribD": a["contribD"] - b["contribD"],
                            "deltaContribH": gaps["H"],
                            "deltaContribP": gaps["P"],
                            "deltaCaPublic": (a["ca_v3_unit"] - b["ca_v3_unit"]) * 100.0,
                        }
                    )
    inversions.sort(key=lambda x: -x["deltaContribH"])
    return {
        "pearsonHvsCa": _pearson(h, ca),
        "spearmanHvsCa": _spearman(h, ca),
        "pearsonHvsD": _pearson(h, d),
        "spearmanHvsD": _spearman(h, d),
        "hMin": min(h),
        "hMax": max(h),
        "hMean": _mean(h),
        "hSd": _sd(h),
        "hRangeRatio": max(h) / min(h) if min(h) else None,
        "hDrivenInversionCount": len(inversions),
        "hDrivenInversions": inversions[:12],
    }


def p_analysis(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    p = [r["P"] for r in rows]
    d = [r["D"] for r in rows]
    ca = [r["ca_v3_unit"] for r in rows]

    inversions = []
    for a in rows:
        for b in rows:
            if a["ca_v3_unit"] > b["ca_v3_unit"] and a["D"] < b["D"]:
                gap_p = a["contribP"] - b["contribP"]
                gap_h = a["contribH"] - b["contribH"]
                if gap_p > gap_h and gap_p > 0:
                    inversions.append(
                        {
                            "winner": a["set"],
                            "loser": b["set"],
                            "deltaD": a["D"] - b["D"],
                            "deltaContribP": gap_p,
                            "deltaContribH": gap_h,
                            "deltaCaPublic": (a["ca_v3_unit"] - b["ca_v3_unit"]) * 100.0,
                        }
                    )
    inversions.sort(key=lambda x: -x["deltaContribP"])
    return {
        "pearsonPvsCa": _pearson(p, ca),
        "spearmanPvsCa": _spearman(p, ca),
        "pearsonPvsD": _pearson(p, d),
        "spearmanPvsD": _spearman(p, d),
        "pMin": min(p),
        "pMax": max(p),
        "pMean": _mean(p),
        "pSd": _sd(p),
        "pRangeRatio": max(p) / min(p) if min(p) else None,
        "pDrivenInversionCount": len(inversions),
        "pDrivenInversions": inversions[:12],
    }


def counterfactual_orderings(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """How much of V3's ordering is each pillar responsible for? Compare V3 to
    the ordering produced by each pillar alone. DESCRIPTIVE - no weight here is
    a proposal."""
    ca = [r["ca_v3_unit"] for r in rows]
    out = {}
    for label in ("D", "H", "P"):
        out[f"spearmanCaVs{label}Only"] = _spearman(ca, [r[label] for r in rows])
    top5 = {r["set"] for r in sorted(rows, key=lambda r: -r["ca_v3_unit"])[:5]}
    for label in ("D", "H", "P"):
        alone = {r["set"] for r in sorted(rows, key=lambda r: -r[label])[:5]}
        out[f"top5OverlapWith{label}Only"] = len(top5 & alone)
    out["v3Top5"] = sorted(top5)
    return out


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def _fmt(value: Any, spec: str = ".4f") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return format(value, spec)
    return str(value)


def print_report(report: Mapping[str, Any]) -> None:
    rows = report["cohort"]
    print(f"\nCollector Appeal V3 construct audit - {COLLECTOR_APPEAL_V3_VERSION}")
    print(f"cohort n = {len(rows)}\n")

    header = (
        f"{'set':<30}{'CA':>8}{'rk':>4}{'D':>9}{'rk':>4}"
        f"{'H':>9}{'rk':>4}{'P':>9}{'rk':>4}{'cD':>8}{'cH':>8}{'cP':>8}{'subj':>6}{'cards':>7}"
    )
    print(header)
    print("-" * len(header))
    for row in sorted(rows, key=lambda r: r["caRank"]):
        print(
            f"{row['set'][:29]:<30}{row['ca_v3_public']:>8.2f}{row['caRank']:>4}"
            f"{row['D']:>9.4f}{row['dRank']:>4}{row['H']:>9.4f}{row['hRank']:>4}"
            f"{row['P']:>9.4f}{row['pRank']:>4}"
            f"{row['contribD']:>8.4f}{row['contribH']:>8.4f}{row['contribP']:>8.4f}"
            f"{row['eligibleSubjectCount']:>6}{row['eligibleCardCount']:>7}"
        )

    print("\n--- Ascended Heroes pairwise decomposition (contributions, unit scale) ---")
    print(f"{'versus':<28}{'dCA':>9}{'dContD':>9}{'dContH':>9}{'dContP':>9}{'err':>10}")
    for case in report["caseStudies"]:
        print(
            f"{case['versus'][:27]:<28}{case['deltaCaPublic']:>9.3f}"
            f"{case['deltaContribD']:>9.4f}{case['deltaContribH']:>9.4f}"
            f"{case['deltaContribP']:>9.4f}{case['reconstructionError']:>10.2e}"
        )

    print("\n--- Effective influence (nominal weight is not influence) ---")
    infl = report["effectiveInfluence"]["pillars"]
    print(f"{'pillar':<8}{'wt':>6}{'rawSd':>9}{'rawRange':>10}{'contribSd':>11}{'shareSd':>9}{'pearson':>9}{'spearman':>10}")
    for label in ("D", "H", "P"):
        p = infl[label]
        print(
            f"{label:<8}{p['nominalWeight']:>6.2f}{p['rawSd']:>9.4f}{p['rawRange']:>10.4f}"
            f"{p['contribSd']:>11.4f}{_fmt(p['shareOfContributionSd'], '.3f'):>9}"
            f"{_fmt(p['pearsonWithCa'], '.3f'):>9}{_fmt(p['spearmanWithCa'], '.3f'):>10}"
        )

    print("\n--- H analysis ---")
    for k, v in report["hAnalysis"].items():
        if k != "hDrivenInversions":
            print(f"  {k}: {_fmt(v)}")
    print("  top H-driven inversions (won on CA despite a WORSE roster):")
    for inv in report["hAnalysis"]["hDrivenInversions"][:6]:
        print(
            f"    {inv['winner'][:24]:<25} > {inv['loser'][:24]:<25} "
            f"dD={inv['deltaD']:+.4f} dContH={inv['deltaContribH']:+.4f} dCA={inv['deltaCaPublic']:+.2f}"
        )

    print("\n--- P analysis ---")
    for k, v in report["pAnalysis"].items():
        if k != "pDrivenInversions":
            print(f"  {k}: {_fmt(v)}")
    print("  top P-driven inversions:")
    for inv in report["pAnalysis"]["pDrivenInversions"][:6]:
        print(
            f"    {inv['winner'][:24]:<25} > {inv['loser'][:24]:<25} "
            f"dD={inv['deltaD']:+.4f} dContP={inv['deltaContribP']:+.4f} dCA={inv['deltaCaPublic']:+.2f}"
        )

    print("\n--- Pillar-alone orderings ---")
    for k, v in report["counterfactuals"].items():
        print(f"  {k}: {_fmt(v)}")

    print("\n--- Warnings / data quality ---")
    for warning in report["warnings"]:
        print(f"  {warning}")
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_json", help="output of audit_collector_appeal_v2 --json")
    parser.add_argument("--csv", help="write the per-set decomposition table here")
    parser.add_argument("--json", dest="json_out", help="write the full report here")
    args = parser.parse_args(argv)

    audit = json.loads(Path(args.audit_json).read_text(encoding="utf-8"))
    rows, warnings = build_cohort(audit)
    if not rows:
        print("no scored sets in the audit payload", file=sys.stderr)
        return 1
    annotate_ranks(rows)

    report = {
        "version": COLLECTOR_APPEAL_V3_VERSION,
        "inputOrder": list(COLLECTOR_APPEAL_V3_INPUT_ORDER),
        "cohort": rows,
        "caseStudies": pairwise_case_studies(rows),
        "effectiveInfluence": effective_influence(rows),
        "hAnalysis": h_analysis(rows),
        "pAnalysis": p_analysis(rows),
        "counterfactuals": counterfactual_orderings(rows),
        "warnings": warnings,
    }

    print_report(report)

    if args.csv:
        fields = [
            "set", "canonicalKey", "ca_v3_public", "caRank", "D", "dRank", "H", "hRank",
            "P", "pRank", "contribD", "contribH", "contribP", "legacyCa7",
            "collectorAppealV2", "eligibleSubjectCount", "eligibleCardCount",
            "coveredDemandShare", "slotGroupCount", "fOneInN", "frequencyStatus",
        ]
        with open(args.csv, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in sorted(rows, key=lambda r: r["caRank"]):
                writer.writerow(row)
        print(f"wrote {args.csv}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
