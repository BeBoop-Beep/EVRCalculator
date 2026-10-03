"""Read-only preregistered forward diagnostics for the FV-S3 prospective shadow cohort.

This runner never calls providers and never writes to the database. It reads immutable
shadow publications/outcomes plus the frozen Core Panel manifest, assembles exact
condition-stable forward rows, and delegates all statistics to the preregistered
`index_fair_value_shadow_evaluation_v1.forward_diagnostics` implementation.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts import index_fair_value_shadow_anchor_v1 as anchor_mod  # noqa: E402
from backend.scripts import index_fair_value_shadow_evaluation_v1 as evaluation  # noqa: E402
from backend.scripts import run_index_fair_value_sold_clearing_anchor_v1 as s2  # noqa: E402

PUBLICATIONS = "fair_value_shadow_anchor_publications_v1"
OUTCOMES = "fair_value_shadow_evaluation_outcomes_v1"


class ForwardDiagnosticsError(RuntimeError):
    pass


def _chunks(values: list[str], size: int = 50) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _paged(factory: Any, page: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = list(factory().range(start, start + page - 1).execute().data or [])
        rows.extend(dict(r) for r in batch)
        if len(batch) < page:
            return rows
        start += page


def fetch_publications(db: Any, evaluation_date: date) -> list[dict[str, Any]]:
    return _paged(lambda: db.table(PUBLICATIONS)
        .select(
            "publication_id,canonical_card_id,card_variant_id,evaluation_date,"
            "information_cutoff,source_commit,status,evidence_status,median"
        )
        .eq("evaluation_date", evaluation_date.isoformat())
        .eq("evidence_status", anchor_mod.STATUS_PROSPECTIVE)
        .order("canonical_card_id"))


def fetch_outcomes(db: Any, publication_ids: list[str], horizons: tuple[int, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk in _chunks(publication_ids):
        rows.extend(
            dict(r) for r in (
                db.table(OUTCOMES)
                .select(
                    "publication_id,horizon_days,comparison_date,comparison_market_price_usd,"
                    "comparison_price_source,baseline_market_price_usd,anchor_usd_at_publication,"
                    "forward_market_change_pct,divergence_at_publication,outcome_status"
                )
                .in_("publication_id", chunk)
                .in_("horizon_days", list(horizons))
                .execute().data or []
            )
        )
    return rows


def assemble_forward_rows(
    *,
    panel: Mapping[str, Any],
    publications: list[Mapping[str, Any]],
    outcomes: list[Mapping[str, Any]],
    horizon_days: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    panel_by = {str(r["canonical_card_id"]): r for r in panel["rows"]}
    pubs_by_id = {str(r["publication_id"]): dict(r) for r in publications}
    outcome_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    duplicate_outcomes: list[tuple[str, int]] = []
    for row in outcomes:
        key = (str(row["publication_id"]), int(row["horizon_days"]))
        if key in outcome_by_key:
            duplicate_outcomes.append(key)
        outcome_by_key[key] = dict(row)
    if duplicate_outcomes:
        raise ForwardDiagnosticsError(f"DUPLICATE_OUTCOME_KEYS count={len(duplicate_outcomes)}")

    rows: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for pid, pub in sorted(pubs_by_id.items(), key=lambda kv: str(kv[1]["canonical_card_id"])):
        cid = str(pub["canonical_card_id"])
        panel_row = panel_by.get(cid)
        if panel_row is None:
            reasons["PANEL_CARD_MISSING"] += 1
            continue
        if str(pub.get("card_variant_id") or "") != str(panel_row["card_variant_id"]):
            raise ForwardDiagnosticsError(f"CARD_VARIANT_MISMATCH cid={cid}")
        if str(pub.get("status") or "") != "ANCHORED":
            reasons["ANCHOR_INSUFFICIENT"] += 1
            continue
        h0 = outcome_by_key.get((pid, 0))
        hh = outcome_by_key.get((pid, horizon_days))
        if h0 is None:
            reasons["H0_MISSING"] += 1
            continue
        if hh is None:
            reasons["HORIZON_MISSING"] += 1
            continue
        if str(h0.get("outcome_status") or "") != "COMPLETE":
            reasons["H0_NOT_COMPLETE"] += 1
            continue
        if str(hh.get("outcome_status") or "") != "COMPLETE":
            reasons["HORIZON_NOT_COMPLETE"] += 1
            continue
        rows.append({
            "publication_id": pid,
            "canonical_card_id": cid,
            "anchor_usd": pub.get("median"),
            "market_t0_usd": h0.get("comparison_market_price_usd"),
            "market_th_usd": hh.get("comparison_market_price_usd"),
            "cluster": str(panel_row["root_set_id"]),
            "root_set_id": str(panel_row["root_set_id"]),
            "set_name": panel_row.get("set_name"),
            "era": panel_row.get("era"),
            "price_band": panel_row.get("price_band"),
        })
        reasons["USABLE"] += 1

    coverage = {
        "panel_count": len(panel["rows"]),
        "publication_count": len(publications),
        "outcome_row_count": len(outcomes),
        "usable_rows": len(rows),
        "excluded_reasons": dict(sorted(reasons.items())),
        "root_set_clusters": len({r["cluster"] for r in rows}),
    }
    return rows, coverage


def stratified_forward_diagnostics(rows: list[Mapping[str, Any]], horizon_days: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, floor in evaluation.STRATA_FLOORS_USD:
        subset = [
            r for r in rows
            if evaluation._num(r.get("market_t0_usd")) is not None
            and float(r["market_t0_usd"]) >= floor
        ]
        out[name] = evaluation.forward_diagnostics(subset, horizon_days=horizon_days)
    return out


def run(*, db: Any, evaluation_date: date, horizon_days: int) -> dict[str, Any]:
    if horizon_days not in (1, 7, 30):
        raise ForwardDiagnosticsError("horizon_days must be one of 1, 7, 30")
    panel = s2.load_panel()
    publications = fetch_publications(db, evaluation_date)
    if not publications:
        raise ForwardDiagnosticsError("NO_PROSPECTIVE_PUBLICATIONS")
    cutoffs = sorted({str(r["information_cutoff"]) for r in publications})
    source_commits = sorted({str(r["source_commit"]) for r in publications})
    if len(cutoffs) != 1:
        raise ForwardDiagnosticsError(f"MULTIPLE_INFORMATION_CUTOFFS count={len(cutoffs)}")
    ids = [str(r["publication_id"]) for r in publications]
    outcomes = fetch_outcomes(db, ids, (0, horizon_days))
    rows, coverage = assemble_forward_rows(
        panel=panel,
        publications=publications,
        outcomes=outcomes,
        horizon_days=horizon_days,
    )
    return {
        "study": "FV_S3_PROSPECTIVE_FORWARD_DIAGNOSTICS_V1",
        "preregistration_version": evaluation.PREREGISTRATION["preregistration_version"],
        "rule_under_test": evaluation.PREREGISTRATION["rule_under_test"],
        "evaluation_date": evaluation_date.isoformat(),
        "horizon_days": horizon_days,
        "information_cutoff": cutoffs[0],
        "source_commits": source_commits,
        "coverage": coverage,
        "diagnostics_by_market_stratum": stratified_forward_diagnostics(rows, horizon_days),
        "provider_calls": 0,
        "provider_credits_used": 0,
        "database_writes": 0,
        "public_price_writes": 0,
        "blended_values_produced": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-date", type=date.fromisoformat, required=True)
    parser.add_argument("--horizon-days", type=int, choices=(1, 7, 30), required=True)
    args = parser.parse_args(argv)

    from backend.db.clients.supabase_client import create_service_role_client
    raw = create_service_role_client()
    db = s2.ReadOnlyClient(raw)
    result = run(db=db, evaluation_date=args.evaluation_date, horizon_days=args.horizon_days)
    result["database_read_requests"] = len(db.read_requests)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
