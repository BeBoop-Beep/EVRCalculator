"""Historical Overall RIP replay for the FROZEN Collector Appeal candidates. READ-ONLY.

WHAT THIS ANSWERS
-----------------
Three questions, in this order:

  1. Held completely fixed, how does the H-only Collector Appeal candidate
     behave inside Overall RIP across every compatible historical snapshot?
  2. At 90/10, 92.5/7.5 and 95/5, which appeal weight passes the CANONICAL
     guardrails most robustly?
  3. Is the ``min_top5_overlap`` gate detecting real leaderboard distortion, or
     is it sometimes firing on 5-item boundary quantization? (Diagnostics only -
     no guardrail is changed here.)

THE COLLECTOR APPEAL CANDIDATE IS NEVER ADJUSTED TO IMPROVE ANY NUMBER BELOW.
Collector Appeal and Overall RIP are separate constructs. If a correctly built
appeal metric destabilises a blend, that is a fact about the blend's weight, not
a reason to make the appeal metric more financial.

WHAT MAKES A SNAPSHOT COMPATIBLE
--------------------------------
``publication_status = 'complete'`` AND ``financial_rip_version`` equal to the
CANONICAL Financial RIP version. Financial RIP V2 snapshots are EXCLUDED, not
converted: the guardrails are defined against the canonical financial ranking,
and scoring a V3-era candidate against a V2 baseline would describe neither
model. Excluded dates are listed with their reason.

COMPOSITION MATCHES CANONICAL OVERALL RIP EXACTLY
-------------------------------------------------
``clamp(w_financial*F + w_appeal*A, 0, 100)`` rounded to 4dp - the arithmetic
``weighted_rip.compute_overall_rip_v7`` performs, with only the weights varying.
A unit test asserts this function reproduces ``compute_overall_rip_v7`` exactly
at the canonical 90/10 weights, so the sensitivity cannot drift into a private
scoring convention.

WHAT THIS DOES NOT DO
---------------------
Write a row. Publish. Rerun a simulation. Change any version, weight, guardrail
or formula. Promote anything. A test asserts no write call exists here.

D/H ARE HELD FIXED ACROSS DATES - A REAL LIMITATION
----------------------------------------------------
The published RIP history stores the financial half per date but no per-date
D/H. Collector Appeal is computed once from the frozen published-state cohort
and held constant while the FINANCIAL side varies. That is the right test for
"does this blend sit safely inside the guardrails as the financial ranking
moves?" and the wrong test for "did Collector Appeal itself drift?". The second
needs an appeal history that does not exist yet.

USAGE
-----
    python -m backend.scripts.audit_collector_appeal_v4_historical_replay \
        --json docs/research/collector_appeal_v4_historical_replay.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_PRODUCTION_GUARDRAILS,
    OVERALL_RIP_V7_WEIGHTS,
)
from backend.research import validation_stats as stats
from backend.research.collector_appeal_v4_candidates import (
    FROZEN_CANDIDATE_KEY,
    FROZEN_H_ONLY_KEY,
    candidate_registry,
    frozen_candidate_identity,
    frozen_h_only_identity,
)
from backend.scripts.audit_collector_appeal_v4_candidates import load_published_cohort

# The appeal weights under test. 0.10 is the CANONICAL production weight and is
# included as its own reference column; 0.075 and 0.05 are the research
# alternatives. Pre-registered here rather than swept: there is no search loop.
APPEAL_WEIGHT_GRID: Tuple[float, ...] = (0.10, 0.075, 0.05)

# The models replayed. The H-only candidate is the subject; V3 is the production
# control that shows what the guardrails look like today; D-only is the floor
# case that shows how much of any breach is desirability rather than this model.
REPLAY_KEYS = (
    "baseline_A_v3",
    FROZEN_H_ONLY_KEY,
    FROZEN_CANDIDATE_KEY,
    "D_only",
)
SUBJECT_KEY = FROZEN_H_ONLY_KEY

# Diagnostic k values reported ALONGSIDE the production gate. The production
# gate remains k = 5 and is not changed here.
DIAGNOSTIC_TOP_K: Tuple[int, ...] = (5, 7, 10)

# Rank-Biased Overlap persistence. p = 0.9 weights roughly the top 10 positions,
# which is the region the top-5 gate is trying to protect. Pre-registered.
RBO_PERSISTENCE = 0.9


# ---------------------------------------------------------------------------
# composition
# ---------------------------------------------------------------------------


def compose_overall(financial: float, appeal: float, appeal_weight: float) -> float:
    """The canonical Overall RIP composition, with the appeal weight as a parameter.

    Mirrors ``weighted_rip.compute_overall_rip_v7`` exactly: weighted sum,
    clamped to [0, 100], rounded to 4 decimal places. The financial weight is
    ``1 - appeal_weight`` so the two always partition the score.
    """
    financial_weight = 1.0 - appeal_weight
    score = financial_weight * float(financial) + appeal_weight * float(appeal)
    return round(max(0.0, min(100.0, score)), 4)


# ---------------------------------------------------------------------------
# rank-weighted agreement (research-only; no repo implementation existed)
# ---------------------------------------------------------------------------


def rank_biased_overlap(
    baseline: Mapping[str, Optional[float]],
    variant: Mapping[str, Optional[float]],
    *,
    persistence: float = RBO_PERSISTENCE,
) -> Optional[float]:
    """Depth-normalized Rank-Biased Overlap over the full cohort. RESEARCH-ONLY.

    WHY THIS EXISTS. ``top_k_overlap`` answers "how many of the top k are still
    in the top k?" - a set-membership question with no notion of nearness. Over a
    22-set cohort at k = 5 it can only take the values 0.0, 0.2, 0.4, 0.6, 0.8,
    1.0, so a set moving from rank 5 to rank 6 costs the same 0.20 as a set
    moving from rank 5 to rank 22. This metric instead compares the two orderings
    at EVERY depth and weights shallow depths most heavily, so a near-miss at the
    boundary scores as a near-miss.

    DEFINITION, stated precisely because this is a research implementation and
    the normalization is NOT the one in the original paper:

        A_d   = |top_d(baseline) INTERSECT top_d(variant)| / d
        RBO_n = sum_{d=1..n} p^(d-1) * A_d  /  sum_{d=1..n} p^(d-1)

    i.e. the geometrically-weighted MEAN of the depth agreements over the depths
    that actually exist. Webber, Moffat & Zobel (2010) define
    ``RBO = (1-p) * sum_{d=1..inf} p^(d-1) * A_d`` over infinite lists; truncating
    that sum at a finite n leaves it bounded by ``1 - p^n``, so two IDENTICAL
    22-item rankings would score 0.90 rather than 1.0 and every reported value
    would be depressed by an amount that depends on cohort size. Dividing by the
    same partial sum removes that artifact, and the result reads as intended:
    1.0 = identical orderings, 0.0 = disjoint at every depth, and the value is
    comparable across cohorts of different sizes.

    ``p`` is the persistence in [0, 1): higher p looks deeper. At p = 0.9 roughly
    the first 10 positions carry the bulk of the weight, which is the region the
    top-5 gate is trying to protect.

    This is a DIAGNOSTIC. It is not a guardrail, and nothing here proposes making
    it one.
    """
    if not 0.0 <= persistence < 1.0:
        raise ValueError("persistence must be in [0, 1)")
    base_ranks = stats.dense_ranks(baseline)
    variant_ranks = stats.dense_ranks(variant)
    base_order = [k for k, _ in sorted(
        ((k, r) for k, r in base_ranks.items() if r is not None), key=lambda kv: kv[1]
    )]
    variant_order = [k for k, _ in sorted(
        ((k, r) for k, r in variant_ranks.items() if r is not None), key=lambda kv: kv[1]
    )]
    n = min(len(base_order), len(variant_order))
    if n == 0:
        return None
    base_seen: set = set()
    variant_seen: set = set()
    overlap = 0
    total = 0.0
    weight_total = 0.0
    for depth in range(1, n + 1):
        left, right = base_order[depth - 1], variant_order[depth - 1]
        # Count the intersection incrementally rather than rebuilding two sets
        # per depth: at depth d the new pair can add at most 2 to the overlap.
        if left == right:
            overlap += 1
        else:
            if left in variant_seen:
                overlap += 1
            if right in base_seen:
                overlap += 1
        base_seen.add(left)
        variant_seen.add(right)
        weight = persistence ** (depth - 1)
        total += weight * (overlap / depth)
        weight_total += weight
    return round(total / weight_total, 6) if weight_total else None


def boundary_diagnostics(
    baseline: Mapping[str, Optional[float]],
    variant: Mapping[str, Optional[float]],
) -> Dict[str, Any]:
    """Is a top-5 overlap drop a real distortion, or a k-boundary crossing?

    Reports, for every set that leaves the baseline top 5:
      * where it actually landed, and
      * whether it stayed within the top 7 / top 10 - i.e. whether it "left the
        top 5" by moving one place or by being genuinely demoted.

    Also reports movement CONFINED to the financial top 5 and top 10, which is
    the distortion the top-5 gate is presumably trying to catch. A gate firing
    while average top-5 movement is under one rank is firing on quantization.
    """
    base_ranks = stats.dense_ranks(baseline)
    variant_ranks = stats.dense_ranks(variant)
    ranked = [k for k, r in base_ranks.items() if r is not None]

    def movement_within(k: int) -> Optional[float]:
        members = [key for key in ranked if int(base_ranks[key]) <= k]
        if not members:
            return None
        return round(
            sum(abs(int(base_ranks[key]) - int(variant_ranks[key])) for key in members)
            / len(members),
            4,
        )

    leavers = []
    for key in ranked:
        if int(base_ranks[key]) <= 5 and int(variant_ranks[key]) > 5:
            leavers.append(
                {
                    "set": key,
                    "financialRank": int(base_ranks[key]),
                    "overallRank": int(variant_ranks[key]),
                    "stillInTop7": int(variant_ranks[key]) <= 7,
                    "stillInTop10": int(variant_ranks[key]) <= 10,
                    "placesLost": int(variant_ranks[key]) - int(base_ranks[key]),
                }
            )
    return {
        "top5Leavers": leavers,
        "allLeaversStayedInTop7": all(item["stillInTop7"] for item in leavers) if leavers else None,
        "maxPlacesLostByATop5Set": max((item["placesLost"] for item in leavers), default=0),
        "meanAbsMovementWithinFinancialTop5": movement_within(5),
        "meanAbsMovementWithinFinancialTop10": movement_within(10),
        "rankBiasedOverlap": rank_biased_overlap(baseline, variant),
    }


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------


def fetch_snapshots() -> Dict[str, Any]:
    """Every complete public RIP snapshot and its rows. READ-ONLY."""
    from backend.db.clients.supabase_client import public_read_client as client

    snapshots = (
        client.table("pokemon_public_rip_leaderboard_snapshots")
        .select(
            "id,market_date,publication_status,eligible_cohort_count,"
            "overall_rip_version,financial_rip_version,ca7_version,cohort_version"
        )
        .order("market_date")
        .execute()
    ).data or []

    out: Dict[str, Any] = {"snapshots": [], "excluded": []}
    for snapshot in snapshots:
        if snapshot["publication_status"] != "complete":
            out["excluded"].append(
                {"marketDate": snapshot["market_date"],
                 "reason": f"publication_status={snapshot['publication_status']}"}
            )
            continue
        if snapshot["financial_rip_version"] != CANONICAL_FINANCIAL_RIP_VERSION:
            out["excluded"].append(
                {
                    "marketDate": snapshot["market_date"],
                    "reason": "incompatible financial rip version "
                              f"{snapshot['financial_rip_version']!r} "
                              f"(canonical is {CANONICAL_FINANCIAL_RIP_VERSION!r})",
                }
            )
            continue
        rows = (
            client.table("pokemon_public_rip_leaderboard_rows")
            .select("set_canonical_key,financial_rip_score,financial_rip_rank")
            .eq("snapshot_id", snapshot["id"])
            .execute()
        ).data or []
        out["snapshots"].append({**snapshot, "rows": rows})
    return out


# ---------------------------------------------------------------------------
# per-date evaluation
# ---------------------------------------------------------------------------


def replay_one_date(
    rows: Sequence[Mapping[str, Any]],
    appeal_by_key: Mapping[str, Optional[float]],
    appeal_weight: float,
) -> Dict[str, Any]:
    """The four canonical guardrails plus diagnostics, for one date and weight.

    Guardrail thresholds are READ from ``OVERALL_RIP_PRODUCTION_GUARDRAILS``,
    never restated, so this tool cannot report against a weaker bar than the
    agreed one.
    """
    guardrails = OVERALL_RIP_PRODUCTION_GUARDRAILS

    financial: Dict[str, float] = {}
    overall: Dict[str, float] = {}
    missing: List[str] = []
    for row in rows:
        key = row["set_canonical_key"]
        financial[key] = float(row["financial_rip_score"])
        appeal = appeal_by_key.get(key)
        if appeal is None:
            missing.append(key)
            continue
        overall[key] = compose_overall(financial[key], float(appeal), appeal_weight)

    if missing:
        return {"unavailable": True, "missingAppealFor": sorted(missing)}

    comparison = stats.rank_comparison(financial, overall)
    absolute = [abs(v) for v in comparison["rankDeltas"].values()]
    n = len(absolute) or 1
    share5 = sum(1 for a in absolute if a >= 5) / n

    checks = {
        "spearman": (comparison["spearman"], guardrails["min_spearman_vs_financial_only"], "min"),
        "top5Overlap": (comparison["top5Overlap"], guardrails["min_top5_overlap"], "min"),
        "meanAbsRankDelta": (
            comparison["meanAbsRankDelta"], guardrails["max_mean_absolute_rank_movement"], "max"
        ),
        "shareMoving5Plus": (share5, guardrails["max_share_moving_5_plus_ranks"], "max"),
    }
    results = {
        name: {
            "value": value,
            "threshold": threshold,
            "passes": None if value is None else (
                value >= threshold if direction == "min" else value <= threshold
            ),
            "margin": None if value is None else round(
                (value - threshold) if direction == "min" else (threshold - value), 6
            ),
        }
        for name, (value, threshold, direction) in checks.items()
    }

    diagnostics = {
        f"top{k}Overlap": stats.rank_comparison(financial, overall, top_k=(k,))[f"top{k}Overlap"]
        for k in DIAGNOSTIC_TOP_K
    }
    diagnostics.update(boundary_diagnostics(financial, overall))

    return {
        "n": len(overall),
        "spearman": comparison["spearman"],
        "top5Overlap": comparison["top5Overlap"],
        "meanAbsRankDelta": comparison["meanAbsRankDelta"],
        "medianAbsRankDelta": comparison["medianAbsRankDelta"],
        "maxAbsRankDelta": comparison["maxAbsRankDelta"],
        "shareMoving5Plus": round(share5, 4),
        "countMoving1Plus": sum(1 for a in absolute if a >= 1),
        "countMoving2Plus": sum(1 for a in absolute if a >= 2),
        "countMoving3Plus": sum(1 for a in absolute if a >= 3),
        "countMoving5Plus": sum(1 for a in absolute if a >= 5),
        "checks": results,
        "allPass": all(check["passes"] for check in results.values()),
        "failing": [name for name, check in results.items() if check["passes"] is False],
        "diagnostics": diagnostics,
        "largestGainers": comparison["largestGainers"],
        "largestLosers": comparison["largestLosers"],
    }


def _summarize(series: Sequence[Optional[float]]) -> Dict[str, Optional[float]]:
    values = [float(v) for v in series if v is not None]
    if not values:
        return {"min": None, "median": None, "max": None, "mean": None}
    return {
        "min": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "max": round(max(values), 6),
        "mean": round(statistics.fmean(values), 6),
    }


def summarize(dates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    usable = [d for d in dates if not d.get("unavailable")]
    failing = [d for d in usable if not d["allPass"]]
    worst = min(usable, key=lambda d: d["checks"]["spearman"]["margin"], default=None)
    return {
        "compatibleDates": len(usable),
        "datesPassingAllGuardrails": len(usable) - len(failing),
        "passRate": round((len(usable) - len(failing)) / len(usable), 4) if usable else None,
        "spearman": _summarize([d["spearman"] for d in usable]),
        "top5Overlap": _summarize([d["top5Overlap"] for d in usable]),
        "top7Overlap": _summarize([d["diagnostics"]["top7Overlap"] for d in usable]),
        "top10Overlap": _summarize([d["diagnostics"]["top10Overlap"] for d in usable]),
        "rankBiasedOverlap": _summarize(
            [d["diagnostics"]["rankBiasedOverlap"] for d in usable]
        ),
        "meanAbsRankDelta": _summarize([d["meanAbsRankDelta"] for d in usable]),
        "medianAbsRankDelta": _summarize([d["medianAbsRankDelta"] for d in usable]),
        "maxAbsRankDelta": _summarize([d["maxAbsRankDelta"] for d in usable]),
        "shareMoving5Plus": _summarize([d["shareMoving5Plus"] for d in usable]),
        "countMoving1Plus": _summarize([d["countMoving1Plus"] for d in usable]),
        "countMoving2Plus": _summarize([d["countMoving2Plus"] for d in usable]),
        "countMoving3Plus": _summarize([d["countMoving3Plus"] for d in usable]),
        "countMoving5Plus": _summarize([d["countMoving5Plus"] for d in usable]),
        "meanMovementWithinFinancialTop5": _summarize(
            [d["diagnostics"]["meanAbsMovementWithinFinancialTop5"] for d in usable]
        ),
        "meanMovementWithinFinancialTop10": _summarize(
            [d["diagnostics"]["meanAbsMovementWithinFinancialTop10"] for d in usable]
        ),
        "failingDates": [
            {"marketDate": d["marketDate"], "failing": d["failing"],
             "margins": {name: d["checks"][name]["margin"] for name in d["failing"]}}
            for d in failing
        ],
        "worstDateBySpearmanMargin": (
            None if worst is None else {
                "marketDate": worst["marketDate"],
                "spearman": worst["spearman"],
                "spearmanMargin": worst["checks"]["spearman"]["margin"],
                "failing": worst["failing"],
                "allMargins": {n: c["margin"] for n, c in worst["checks"].items()},
            }
        ),
    }


def build_report(fetched: Mapping[str, Any]) -> Dict[str, Any]:
    cohort = load_published_cohort()
    registry = candidate_registry()
    appeal: Dict[str, Dict[str, Optional[float]]] = {
        key: {
            row["canonicalKey"]: registry[key]["scorer"](row["D"], row["H"], row["P"])
            for row in cohort
        }
        for key in REPLAY_KEYS
    }

    replays: Dict[str, Dict[str, Any]] = {}
    for weight in APPEAL_WEIGHT_GRID:
        label = f"appeal_{weight:g}"
        replays[label] = {"appealWeight": weight, "financialWeight": 1.0 - weight, "models": {}}
        for key in REPLAY_KEYS:
            dates = [
                {"marketDate": snapshot["market_date"],
                 **replay_one_date(snapshot["rows"], appeal[key], weight)}
                for snapshot in fetched["snapshots"]
            ]
            replays[label]["models"][key] = {"perDate": dates, "summary": summarize(dates)}

    return {
        "subject": SUBJECT_KEY,
        "hOnlyCandidate": frozen_h_only_identity(),
        "h70p30Candidate": frozen_candidate_identity(),
        "canonicalOverallVersion": CANONICAL_OVERALL_RIP_VERSION,
        "canonicalFinancialVersion": CANONICAL_FINANCIAL_RIP_VERSION,
        "canonicalWeights": dict(OVERALL_RIP_V7_WEIGHTS),
        "guardrails": dict(OVERALL_RIP_PRODUCTION_GUARDRAILS),
        "appealWeightGrid": list(APPEAL_WEIGHT_GRID),
        "rboPersistence": RBO_PERSISTENCE,
        "limitation": (
            "D/H are held fixed at the published-state cohort across all dates; "
            "the published RIP history stores no per-date appeal inputs. This "
            "measures the stability of the blend as the FINANCIAL ranking moves, "
            "not the stability of Collector Appeal itself."
        ),
        "compatibleSnapshotCount": len(fetched["snapshots"]),
        "excludedSnapshots": fetched["excluded"],
        "replays": replays,
    }


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def print_report(report: Mapping[str, Any]) -> None:
    print(f"\nHistorical Overall RIP weight sensitivity")
    print(f"subject: {report['hOnlyCandidate']['version']}")
    print(f"  fingerprint {report['hOnlyCandidate']['fingerprint'][:16]}...")
    print(f"guardrails (read from config): {report['guardrails']}")
    print(f"compatible snapshots: {report['compatibleSnapshotCount']}")
    for entry in report["excludedSnapshots"]:
        print(f"   excluded {entry['marketDate']}: {entry['reason']}")

    for label, replay in report["replays"].items():
        weight = replay["appealWeight"]
        print(f"\n{'='*100}")
        print(f"APPEAL WEIGHT {weight:.3g}  ({replay['financialWeight']:.4g} financial)")
        print("=" * 100)
        for key, block in replay["models"].items():
            print(f"\n--- {key} ---")
            head = (
                f"{'date':<13}{'rho':>9}{'top5':>7}{'top7':>7}{'top10':>7}{'rbo':>8}"
                f"{'meanMv':>8}{'maxMv':>7}{'>=5':>7}{'pass':>6}  failing"
            )
            print(head)
            for entry in block["perDate"]:
                if entry.get("unavailable"):
                    print(f"{entry['marketDate']:<13} unavailable")
                    continue
                diagnostics = entry["diagnostics"]
                print(
                    f"{entry['marketDate']:<13}{entry['spearman']:>9.4f}"
                    f"{entry['top5Overlap']:>7.2f}{diagnostics['top7Overlap']:>7.2f}"
                    f"{diagnostics['top10Overlap']:>7.2f}{diagnostics['rankBiasedOverlap']:>8.4f}"
                    f"{entry['meanAbsRankDelta']:>8.2f}{entry['maxAbsRankDelta']:>7}"
                    f"{entry['shareMoving5Plus']:>7.2f}"
                    f"{'YES' if entry['allPass'] else 'NO':>6}  {','.join(entry['failing'])}"
                )
            summary = block["summary"]
            print(
                f"  PASS {summary['datesPassingAllGuardrails']}/{summary['compatibleDates']}"
                f"  (rate {summary['passRate']})"
            )
            for name in ("spearman", "top5Overlap", "top7Overlap", "top10Overlap",
                         "rankBiasedOverlap", "meanAbsRankDelta", "shareMoving5Plus"):
                stat = summary[name]
                print(f"    {name:<20} min {stat['min']}  med {stat['median']}  max {stat['max']}")
            worst = summary["worstDateBySpearmanMargin"]
            if worst:
                print(
                    f"    worst date {worst['marketDate']}: rho={worst['spearman']} "
                    f"(margin {worst['spearmanMargin']:+}), failing={worst['failing'] or 'none'}"
                )
            print(
                f"    movement within financial top5 "
                f"{summary['meanMovementWithinFinancialTop5']['min']}-"
                f"{summary['meanMovementWithinFinancialTop5']['max']}"
                f" | top10 {summary['meanMovementWithinFinancialTop10']['min']}-"
                f"{summary['meanMovementWithinFinancialTop10']['max']}"
            )

    print("\n" + "=" * 100)
    print("PRACTICAL INFLUENCE OF THE SUBJECT CANDIDATE BY WEIGHT (mean across dates)")
    print("=" * 100)
    head = (
        f"{'weight':<10}{'pass':>8}{'rho med':>10}{'meanMv':>9}{'medMv':>8}{'maxMv':>8}"
        f"{'n>=1':>8}{'n>=2':>8}{'n>=3':>8}{'n>=5':>8}{'top5':>8}{'rbo':>8}"
    )
    print(head)
    for label, replay in report["replays"].items():
        summary = replay["models"][SUBJECT_KEY]["summary"]
        print(
            f"{replay['appealWeight']:<10.3g}"
            f"{summary['datesPassingAllGuardrails']}/{summary['compatibleDates']:<5}"
            f"{summary['spearman']['median']:>10.4f}"
            f"{summary['meanAbsRankDelta']['mean']:>9.2f}"
            f"{summary['medianAbsRankDelta']['mean']:>8.2f}"
            f"{summary['maxAbsRankDelta']['mean']:>8.2f}"
            f"{summary['countMoving1Plus']['mean']:>8.2f}"
            f"{summary['countMoving2Plus']['mean']:>8.2f}"
            f"{summary['countMoving3Plus']['mean']:>8.2f}"
            f"{summary['countMoving5Plus']['mean']:>8.2f}"
            f"{summary['top5Overlap']['mean']:>8.2f}"
            f"{summary['rankBiasedOverlap']['mean']:>8.4f}"
        )

    print("\n--- Top-5 boundary diagnosis (subject candidate at the canonical 0.10) ---")
    canonical_label = f"appeal_{OVERALL_RIP_V7_WEIGHTS['collector_appeal']:g}"
    for entry in report["replays"][canonical_label]["models"][SUBJECT_KEY]["perDate"]:
        if entry.get("unavailable"):
            continue
        diagnostics = entry["diagnostics"]
        leavers = diagnostics["top5Leavers"]
        if not leavers:
            continue
        detail = ", ".join(
            f"{item['set']} #{item['financialRank']}->#{item['overallRank']}"
            f"{' (still top7)' if item['stillInTop7'] else ''}"
            for item in leavers
        )
        print(
            f"  {entry['marketDate']}  top5={entry['top5Overlap']:.2f} "
            f"top7={diagnostics['top7Overlap']:.2f} rbo={diagnostics['rankBiasedOverlap']:.4f} "
            f"top5move={diagnostics['meanAbsMovementWithinFinancialTop5']}  {detail}"
        )
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_out", help="write the full report here")
    args = parser.parse_args(argv)

    report = build_report(fetch_snapshots())
    print_report(report)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
