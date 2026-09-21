"""Operator entry points for the Financial V5 / Overall V14 candidate path.

EXPLICIT AND NON-DEFAULT. Nothing here is imported by, or attached to, the current scheduled
publication (``run_daily_opening_publication.py`` keeps publishing V4/V12). Every command is a
DRY RUN unless ``--commit`` is passed; the read-only ``shadow`` command has no commit mode at all.

    python -m backend.scripts.run_financial_v5_candidate finalize-v5   [--market-date D] [--commit]
    python -m backend.scripts.run_financial_v5_candidate build-v14     [--market-date D] [--commit]
    python -m backend.scripts.run_financial_v5_candidate ranking-v2    [--market-date D] [--commit]
    python -m backend.scripts.run_financial_v5_candidate best-open-v3  [--market-date D] [--commit]
    python -m backend.scripts.run_financial_v5_candidate readiness     [--market-date D]
    python -m backend.scripts.run_financial_v5_candidate shadow        [--market-date D]   # read-only

Commit paths fail closed by design: ``--commit`` for V14/Ranking V2/Best-Open V3 requires persisted V5
(which needs the V5 schema to have landed) and reports "not ready" truthfully until then.
The candidate is never activated by any command here; there is no pointer or selector operation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "logs" / "v5_candidate"


def _client():
    from backend.scripts.pokemon_snapshot_builders import get_client

    return get_client()


def resolve_date(client: Any, explicit: Optional[str]) -> str:
    from backend.scripts.audit_opening_analytics_publication import resolve_market_date

    market_date, error = resolve_market_date(client, explicit)
    if error or not market_date:
        raise SystemExit(f"cannot resolve a promoted market date: {error}")
    return str(market_date)


def resolve_cohort_date(client: Any, explicit: Optional[str], *, lookback_days: int = 14) -> Dict[str, Any]:
    """The promoted date AND the latest date whose opening-simulation cohort actually passes the gate.

    The promoted date can run ahead of the simulations (today's runs have not happened yet); the
    freshness gate correctly refuses such a date. Read-only shadow work therefore uses the most recent
    date whose whole supported cohort is current, and reports both dates rather than hardcoding one.
    """
    from datetime import date, timedelta

    from backend.db.services.opening_simulation_gate import evaluate_opening_simulation_freshness

    promoted = resolve_date(client, explicit)
    attempts = []
    start = date.fromisoformat(promoted)
    for back in range(0, lookback_days + 1):
        day = (start - timedelta(days=back)).isoformat()
        report = evaluate_opening_simulation_freshness(client, market_date=day)
        attempts.append({"date": day, "ok": bool(report.ok), "error": report.error})
        if report.ok:
            return {"promotedDate": promoted, "cohortDate": day, "attempts": attempts}
        if explicit:
            break
    raise SystemExit("no date within %d days has a complete current simulation cohort: %s"
                     % (lookback_days, attempts))


def _write_json(name: str, market_date: str, payload: Any) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}_{market_date}.json"
    path.write_text(json.dumps(payload, indent=1, default=str, allow_nan=False), encoding="utf-8")
    return path


def cmd_finalize_v5(client: Any, args: argparse.Namespace) -> Dict[str, Any]:
    """Exact-artifact V5 finalization. Dry-run captures evidence locally; --commit writes V5 columns only."""
    from backend.db.services.sealed_product_financial_v5_finalization_service import finalize_financial_rip_v5

    dates = resolve_cohort_date(client, args.market_date)
    market_date = dates["cohortDate"]
    print(json.dumps({"promotedDate": dates["promotedDate"], "cohortDate": market_date}), file=sys.stderr)
    evidence: Dict[str, Dict[str, Any]] = {}
    report = finalize_financial_rip_v5(client, market_date=market_date, dry_run=not args.commit,
                                       evidence_sink=evidence)
    _write_json("finalize_v5_report", market_date, report)
    _write_json("finalize_v5_evidence", market_date, evidence)
    summary = {k: report[k] for k in ("status", "marketDate", "dryRun", "cohortRunCount", "rowsConsidered",
                                      "rowsReady", "rowsUnavailable", "unavailableReasons", "rowsSkipped",
                                      "artifactLoads", "distributionBuilds", "cohortComplete", "elapsedMs")}
    print(json.dumps(summary, indent=1, default=str))
    return report


def cmd_shadow(client: Any, args: argparse.Namespace) -> Dict[str, Any]:
    """READ-ONLY live shadow: V5 -> V14 -> Ranking V2 (Full Market) -> contract V12 -> readiness. No writes."""
    from backend.db.services import v5_shadow_runner as sr
    from backend.db.services.public_rip_publication_contract import candidate_publication_identity
    from backend.db.services.v5_v14_candidate_readiness import evaluate_v5_v14_candidate_readiness

    dates = resolve_cohort_date(client, args.market_date)
    md = dates["cohortDate"]
    def collector_bundle_with_retry():
        from backend.db.services.collector_appeal_service import get_collector_appeal_bundle

        last = None
        for attempt in range(1, 5):
            try:
                return get_collector_appeal_bundle(force_refresh=attempt > 1)
            except Exception as exc:  # transient PostgREST/httpx read timeouts on the ~11 MB paged read
                last = exc
                print(f"collector bundle attempt {attempt} failed: {type(exc).__name__}", file=sys.stderr)
                time.sleep(5 * attempt)
        raise last

    shadow = sr.run_shadow(client, market_date=md, collector_bundle_fn=collector_bundle_with_retry)
    rows = shadow["v5Rows"]
    v4 = {str(r["sealed_product_id"]): float(r["financial_rip_v4_score"]) for r in rows if r.get("financial_rip_v4_score") is not None}
    v5 = {str(r["sealed_product_id"]): float(r["financial_rip_v5_score"]) for r in rows}
    v12 = {str(r["sealed_product_id"]): float(r["overall_rip_v12_score"]) for r in rows if r.get("overall_rip_v12_score") is not None}
    v14 = {r["sealed_product_id"]: float(r["score"]) for r in shadow["candidate"]["rows"] if r["score"] is not None}
    contracts = sr.build_contract_v12_targets(shadow)
    problems = sr.contract_v12_problems(contracts)
    fm = shadow["fullMarket"]
    ranking_summary = {"id": "shadow-in-memory", "ranking_method_version": shadow["ranking"]["rankingMethodVersion"],
                       "overall_rip_v14_version": shadow["candidate"]["run"]["model_version"],
                       "financial_rip_v5_version": shadow["candidate"]["run"]["financial_version"],
                       "ranked_under_v14_authority": True, "eligible_cohort_count": fm["rankedCount"]}
    readiness = evaluate_v5_v14_candidate_readiness(
        expected_row_count=len(rows), v5_finalization_report=shadow["v5Report"], v14_candidate=shadow["candidate"],
        v14_validation=shadow["v14Validation"], ranking_v2=ranking_summary, best_open_v3=None,
        contract_v12_samples=contracts, require_best_open_v3=False)
    stable = sorted(shadow["candidate"]["rows"], key=lambda r: (r["rank"] is None, r["rank"]))
    report = {
        "dates": dates, "cohort": {"runs": len(set(shadow["runByset"].values())), "sets": len(shadow["runByset"]),
                                    "productRows": len(rows)},
        "v5Report": {k: v for k, v in shadow["v5Report"].items() if k not in ("results",)},
        "v14Validation": shadow["v14Validation"], "v14Run": shadow["candidate"]["run"],
        "collectorVersions": sorted({str((a or {}).get("version")) for a in shadow["appeal"].values()}),
        "chaseVersions": sorted({str((a or {}).get("version")) for a in shadow["accessibility"].values()}),
        "rankingV2FullMarket": {k: fm[k] for k in ("targetBudget", "eligibleCount", "rankedCount", "excludedCount", "unrankableCount", "familyCoverage")},
        "financialV4vsV5": sr.compare_models(v4, v5, label="financial_v4_vs_v5"),
        "overallV12vsV14": sr.compare_models(v12, v14, label="overall_v12_vs_v14"),
        "srTypicalCorrelation": None,
        "contractV12": {"targets": len(contracts), "problems": problems[:20], "problemCount": len(problems)},
        "readiness": readiness, "candidateIdentity": candidate_publication_identity(),
        "elapsedSeconds": shadow["elapsedSeconds"]}
    try:
        import numpy as np
        sr_s = [float(r["financial_rip_v5_payload"]["components"]["shortfall_resilience"]["score"]) for r in rows]
        ty = [float(r["financial_rip_v5_payload"]["components"]["typical_retention"]["score"]) for r in rows]
        report["srTypicalCorrelation"] = float(np.corrcoef(sr_s, ty)[0, 1])
    except Exception as exc:  # monitoring item only
        report["srTypicalCorrelation"] = "unavailable: %s" % exc
    report["highWinRegime"] = {"maxProductPWin": max(float(((r.get("financial_rip_v5_payload") or {}).get("components") or {}).get("true_win_frequency", {}).get("raw", {}).get("trueWinProbability") or 0) for r in rows)}
    _write_json("shadow_report", md, report)
    _write_json("shadow_fullmarket_ranking", md, fm["rows"])
    print(json.dumps({k: report[k] for k in ("dates", "cohort", "v14Validation", "rankingV2FullMarket", "contractV12")}, indent=1, default=str))
    print(json.dumps({"readyChecks": {k: v["ok"] for k, v in readiness["checks"].items()}, "candidateReady": readiness["candidateReady"],
                      "reasons": readiness["reasons"], "canonicalImpact": readiness["canonicalImpact"]}, indent=1))
    return {"status": "ok"}


COMMANDS = {"finalize-v5": cmd_finalize_v5, "shadow": cmd_shadow}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=sorted(COMMANDS) + ["build-v14", "ranking-v2", "best-open-v3", "readiness", "shadow"])
    parser.add_argument("--market-date", default=None, help="explicit promoted market date (default: resolved)")
    parser.add_argument("--commit", action="store_true",
                        help="perform writes (default is a read-only dry run); not accepted by 'shadow'/'readiness'")
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.commit and args.command in ("shadow", "readiness"):
        raise SystemExit(f"'{args.command}' is read-only and has no commit mode")
    started = time.perf_counter()
    handler = COMMANDS.get(args.command)
    if handler is None:
        raise SystemExit(f"'{args.command}' is registered in a later step of this module")
    result = handler(_client(), args)
    print(f"elapsed {time.perf_counter() - started:.1f}s", file=sys.stderr)
    return 0 if (result or {}).get("status") in (None, "ok") else 1


if __name__ == "__main__":
    sys.exit(main())
