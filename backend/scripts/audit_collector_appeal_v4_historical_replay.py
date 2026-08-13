"""Historical Overall RIP replay for the FROZEN Collector Appeal V4 candidate. READ-ONLY.

WHAT THIS ANSWERS
-----------------
Today's single-date sensitivity put the candidate at Spearman 0.9548 against a
Financial-only ranking - 0.005 above the 0.95 guardrail. One date cannot tell
you whether that is a comfortable position or a coin flip. This script replays
the candidate against EVERY compatible complete historical public RIP snapshot
and reports the four canonical guardrails per date.

WHAT MAKES A SNAPSHOT COMPATIBLE
--------------------------------
``publication_status = 'complete'`` AND the snapshot's ``financial_rip_version``
equals the CANONICAL Financial RIP version. Snapshots built on Financial RIP V2
are EXCLUDED, not converted: the guardrails are defined against the canonical
financial ranking, and scoring a V3-era candidate against a V2 baseline would
report a number that describes neither model. Excluded dates are listed with
their reason rather than silently dropped.

WHAT THIS DOES NOT DO
---------------------
Write a row. Publish. Rerun a simulation. Change any version, weight, guardrail
or formula. Promote anything. A test asserts no write call exists here.

D/H/P ARE HELD FIXED ACROSS DATES - AND THAT IS A REAL LIMITATION
------------------------------------------------------------------
The published RIP history stores the financial half per date but not a per-date
D/H/P. Collector Appeal is therefore computed once, from the frozen
published-state cohort, and held constant while the FINANCIAL side varies by
date. That is the right test for the question being asked ("does a 90/10 blend
sit safely inside the guardrails as the financial ranking moves?") and the wrong
test for "did Collector Appeal itself drift?". The second question needs an
appeal history that does not exist yet; it is reported as a limitation, not
papered over.

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
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    OVERALL_RIP_PRODUCTION_GUARDRAILS,
    OVERALL_RIP_V7_WEIGHTS,
)
from backend.research import validation_stats as stats
from backend.research.collector_appeal_v4_candidates import (
    FROZEN_ABLATION_KEY,
    FROZEN_CANDIDATE_KEY,
    candidate_registry,
    frozen_candidate_identity,
)
from backend.scripts.audit_collector_appeal_v4_candidates import load_published_cohort

# The models replayed. The frozen candidate is the subject; V3 is the production
# control that tells you what the guardrails look like today; Financial-only is
# the baseline the guardrails are stated against.
REPLAY_KEYS = (
    "baseline_A_v3",
    FROZEN_CANDIDATE_KEY,
    FROZEN_ABLATION_KEY,
    "D_only",
)


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
            .select("set_canonical_key,financial_rip_score,financial_rip_rank,overall_rip_score")
            .eq("snapshot_id", snapshot["id"])
            .execute()
        ).data or []
        out["snapshots"].append({**snapshot, "rows": rows})
    return out


def replay_one_date(
    rows: Sequence[Mapping[str, Any]],
    appeal_by_key: Mapping[str, Optional[float]],
) -> Dict[str, Any]:
    """The four canonical guardrails for one snapshot, one appeal model.

    Guardrail thresholds are READ from ``OVERALL_RIP_PRODUCTION_GUARDRAILS``, never
    restated, so this tool cannot report against a weaker bar than the agreed one.
    """
    guardrails = OVERALL_RIP_PRODUCTION_GUARDRAILS
    w_fin = OVERALL_RIP_V7_WEIGHTS["financial_rip"]
    w_ca = OVERALL_RIP_V7_WEIGHTS["collector_appeal"]

    financial: Dict[str, float] = {}
    overall: Dict[str, float] = {}
    missing: List[str] = []
    for row in rows:
        key = row["set_canonical_key"]
        appeal = appeal_by_key.get(key)
        financial[key] = float(row["financial_rip_score"])
        if appeal is None:
            missing.append(key)
            continue
        overall[key] = w_fin * float(row["financial_rip_score"]) + w_ca * float(appeal)

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
    return {
        "n": len(overall),
        "spearman": comparison["spearman"],
        "top5Overlap": comparison["top5Overlap"],
        "meanAbsRankDelta": comparison["meanAbsRankDelta"],
        "maxAbsRankDelta": comparison["maxAbsRankDelta"],
        "shareMoving5Plus": round(share5, 4),
        "checks": results,
        "allPass": all(check["passes"] for check in results.values()),
        "failing": [name for name, check in results.items() if check["passes"] is False],
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

    per_date: Dict[str, List[Dict[str, Any]]] = {key: [] for key in REPLAY_KEYS}
    for snapshot in fetched["snapshots"]:
        for key in REPLAY_KEYS:
            result = replay_one_date(snapshot["rows"], appeal[key])
            per_date[key].append({"marketDate": snapshot["market_date"], **result})

    summary: Dict[str, Any] = {}
    for key, dates in per_date.items():
        usable = [d for d in dates if not d.get("unavailable")]
        summary[key] = {
            "datesEvaluated": len(usable),
            "datesPassingAllGuardrails": sum(1 for d in usable if d["allPass"]),
            "datesFailingAny": [d["marketDate"] for d in usable if not d["allPass"]],
            "spearman": _summarize([d["spearman"] for d in usable]),
            "top5Overlap": _summarize([d["top5Overlap"] for d in usable]),
            "meanAbsRankDelta": _summarize([d["meanAbsRankDelta"] for d in usable]),
            "maxAbsRankDelta": _summarize([d["maxAbsRankDelta"] for d in usable]),
            "shareMoving5Plus": _summarize([d["shareMoving5Plus"] for d in usable]),
            "minSpearmanMargin": _summarize(
                [d["checks"]["spearman"]["margin"] for d in usable]
            )["min"],
        }

    return {
        "candidate": frozen_candidate_identity(),
        "canonicalOverallVersion": CANONICAL_OVERALL_RIP_VERSION,
        "canonicalFinancialVersion": CANONICAL_FINANCIAL_RIP_VERSION,
        "weights": dict(OVERALL_RIP_V7_WEIGHTS),
        "guardrails": dict(OVERALL_RIP_PRODUCTION_GUARDRAILS),
        "limitation": (
            "D/H/P are held fixed at the published-state cohort across all dates; "
            "the published RIP history stores no per-date appeal inputs. This "
            "measures the stability of a 90/10 blend as the FINANCIAL ranking "
            "moves, not the stability of Collector Appeal itself."
        ),
        "compatibleSnapshotCount": len(fetched["snapshots"]),
        "excludedSnapshots": fetched["excluded"],
        "perDate": per_date,
        "summary": summary,
    }


def print_report(report: Mapping[str, Any]) -> None:
    print(f"\nHistorical Overall RIP replay - {report['candidate']['version']}")
    print(f"fingerprint {report['candidate']['fingerprint'][:16]}...")
    print(f"weights {report['weights']}  guardrails {report['guardrails']}")
    print(f"compatible snapshots: {report['compatibleSnapshotCount']}")
    if report["excludedSnapshots"]:
        print("excluded:")
        for entry in report["excludedSnapshots"]:
            print(f"   {entry['marketDate']}: {entry['reason']}")

    for key, dates in report["perDate"].items():
        print(f"\n--- {key} ---")
        head = f"{'date':<13}{'rho':>9}{'top5':>7}{'meanMv':>8}{'maxMv':>7}{'>=5':>7}{'pass':>6}  failing"
        print(head)
        for entry in dates:
            if entry.get("unavailable"):
                print(f"{entry['marketDate']:<13} unavailable: {entry['missingAppealFor'][:3]}")
                continue
            print(
                f"{entry['marketDate']:<13}{entry['spearman']:>9.4f}{entry['top5Overlap']:>7.2f}"
                f"{entry['meanAbsRankDelta']:>8.2f}{entry['maxAbsRankDelta']:>7}"
                f"{entry['shareMoving5Plus']:>7.2f}"
                f"{'YES' if entry['allPass'] else 'NO':>6}  {','.join(entry['failing'])}"
            )
        summary = report["summary"][key]
        print(
            f"  spearman min/med/max = {summary['spearman']['min']}/"
            f"{summary['spearman']['median']}/{summary['spearman']['max']}"
            f"   tightest margin above 0.95: {summary['minSpearmanMargin']}"
        )
        print(
            f"  top5 {summary['top5Overlap']['min']}-{summary['top5Overlap']['max']}"
            f" | meanMove {summary['meanAbsRankDelta']['min']}-{summary['meanAbsRankDelta']['max']}"
            f" | >=5 share {summary['shareMoving5Plus']['min']}-{summary['shareMoving5Plus']['max']}"
        )
        print(
            f"  {summary['datesPassingAllGuardrails']}/{summary['datesEvaluated']} dates pass all four"
            + (f"; FAILING: {summary['datesFailingAny']}" if summary["datesFailingAny"] else "")
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
