from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.market_date_quality import market_index_accepted_dates
from backend.db.services.market_publication_gate import (
    MarketForcePublishRejected,
    add_market_gate_args,
    enforce_market_publication_gate,
    resolve_market_publication_date,
)
from backend.db.services.pokemon_market_rollout_preparation import (
    prepare_market_rollout_candidate,
    staged_rollout_root_ids,
)
from backend.db.services.pokemon_market_index_service import (
    build_market_index_history,
    persist_index_rows,
)
from backend.db.services.pokemon_market_rollout_cohort import (
    MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE,
    resolve_market_root_cohort,
)
from backend.db.services.pokemon_market_rollout_index import (
    build_rollout_market_index_rows,
    persist_rollout_market_index_rows,
)
from backend.db.services.price_storage_v2_integration import (
    PUBLIC_ROOT_CANDIDATE_SOURCES,
    PUBLIC_ROOT_SOURCES,
    public_root_materialization,
)
from backend.domain.pokemon.market_index import (
    CHASE_INDEX_KEY,
    INDEX_KEYS,
    MARKET_INDEX_CONTRACT_VERSION,
    MARKET_INDEX_METHODOLOGY_VERSION,
    RAW_INDEX_KEY,
)
from backend.scripts.pokemon_snapshot_builders import get_client

# This RPC finalizes the current canonical Market-root materialization. Price
# Storage V2 remains a separate, operator-gated workflow and is not attached to
# this publisher.
ROLLOUT_REFRESH_RPC = "refresh_pokemon_market_public_rollout_daily_snapshots_v1"
PUBLIC_ROLLOUT_TABLE = "pokemon_market_public_era_rollout_v1"
SOURCE_TABLE = "pokemon_set_value_daily_history"


def parser():
    p = argparse.ArgumentParser(description="Build chain-linked Pokemon Market index history")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    p.add_argument("--market-date")
    p.add_argument("--backfill", action="store_true")
    p.add_argument("--from-date")
    add_market_gate_args(p)
    p.add_argument(
        "--force-publish",
        action="store_true",
        help="Rejected for Market publication; Market Date Quality cannot be overridden",
    )
    return p


def _canonical_checklist_source(scope: str) -> str:
    return (
        "card_variant_price_observations_near_mint_latest_as_of_day:"
        f"{scope}:canonical_checklist"
    )


def _postcutover_authority_value_materialization(
    root_ids: list[str], source_rows: list[dict], day: str, *, allow_candidate: bool,
) -> dict:
    """Validate the exact Sep-10+ Market authority value inputs.

    After the canonical root-authority cutover, membership is no longer defined
    by rollout certification. The public rollout finalizer intentionally writes
    FINAL provenance only for roots that satisfy its live coverage/publishable
    predicates; other authority roots retain the canonical-checklist Standard /
    Top-10 value rows that Market Date Quality evaluates. Requiring every one of
    those roots to carry rollout FINAL provenance therefore shrinks the source
    contract below the frozen Market authority.

    This helper does NOT broadly accept generic Price Storage/member rows. For
    an authority root/scope pair it accepts only:
      * canonical public-root FINAL/backfill provenance,
      * the established canonical-checklist value source, or
      * canonical public-root candidate provenance in preview mode only.

    Every accepted pair must have a positive value and priced-card count. The
    downstream rollout index builder independently rechecks the same full root
    cohort and positive-value invariant before persistence.
    """
    roots = {str(value) for value in root_ids if value}
    expected = {(root, scope) for root in roots for scope in PUBLIC_ROOT_SOURCES}
    materialized: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    seen: set[tuple[str, str]] = set()
    unsupported: list[list[str]] = []

    for row in source_rows:
        root = str(row.get("set_id") or "")
        scope = str(row.get("value_scope") or "")
        key = (root, scope)
        if root not in roots or scope not in PUBLIC_ROOT_SOURCES:
            continue
        if str(row.get("snapshot_date") or "")[:10] != day:
            continue
        if key in seen:
            duplicates.add(key)
        seen.add(key)

        source = str(row.get("source") or "")
        accepted_sources = set(PUBLIC_ROOT_SOURCES[scope])
        accepted_sources.add(_canonical_checklist_source(scope))
        if allow_candidate:
            accepted_sources.update(PUBLIC_ROOT_CANDIDATE_SOURCES[scope])
        if source not in accepted_sources:
            unsupported.append([root, scope, source])
            continue

        try:
            value = float(row.get("set_value") or 0)
            priced_count = int(row.get("priced_card_count") or 0)
        except (TypeError, ValueError):
            continue
        if value > 0 and priced_count > 0:
            materialized.add(key)

    missing = sorted(expected - materialized)
    return {
        "ready": not missing and not duplicates,
        "rootCount": len(roots),
        "materializedPairCount": len(materialized),
        "missingRootScopePairs": [list(pair) for pair in missing],
        "duplicatePairs": [list(pair) for pair in sorted(duplicates)],
        "unsupportedSourcePairs": unsupported,
        "allowCandidate": allow_candidate,
        "sourceContract": "canonical_market_root_authority_values_v1",
    }


def _rollout_source_materialization(client, market_date: str, *, allow_candidate: bool = False) -> dict:
    """Validate the source rows used by the current-day Market index.

    Before the Sep-10 root-authority cutover, preserve the historical rollout
    provenance contract exactly: preview may accept candidate provenance and a
    commit requires FINAL/backfill provenance for every staged rollout pair.

    Sep 10+ membership comes from ``pokemon_market_root_authority``. The rollout
    finalizer can legitimately finalize fewer roots than that authority (for
    example 137 Standard / 124 Top-10 on Sep 15 while authority held 155). For
    those dates, source readiness therefore follows the exact authority value
    contract above rather than incorrectly treating FINAL provenance coverage as
    membership. The stricter rollout-provenance result remains attached as
    diagnostics and generic/member-only Price Storage sources remain rejected.

    Root membership is resolved through ``staged_rollout_root_ids`` and never
    through the valuation-backed ``pokemon_market_public_rollout_root_sets_v1``
    view.
    """
    day = str(market_date)[:10]
    root_ids = staged_rollout_root_ids(client, day)
    source_rows: list[dict] = []
    for offset in range(0, len(root_ids), 100):
        source_rows.extend(
            client.table(SOURCE_TABLE)
            .select(
                "set_id,value_scope,snapshot_date,source,set_value,priced_card_count"
            )
            .in_("set_id", root_ids[offset:offset + 100])
            .eq("snapshot_date", day)
            .in_("value_scope", ["standard", "top10"])
            .execute().data or []
        )

    provenance = public_root_materialization(
        root_ids, source_rows, day, allow_candidate=allow_candidate,
    )
    if day < MARKET_ROOT_AUTHORITY_TABLE_CUTOVER_DATE:
        return provenance

    authority_values = _postcutover_authority_value_materialization(
        root_ids, source_rows, day, allow_candidate=allow_candidate,
    )
    candidate_aware = public_root_materialization(
        root_ids, source_rows, day, allow_candidate=True,
    )
    final_only = public_root_materialization(
        root_ids, source_rows, day, allow_candidate=False,
    )
    return {
        **authority_values,
        # Keep provenance observable without letting its partial coverage
        # redefine the frozen authority membership.
        "provenanceState": candidate_aware["provenanceState"],
        "provenanceReadyForRequestedMode": provenance["ready"],
        "finalProvenanceComplete": final_only["ready"],
        "provenanceMaterializedPairCount": candidate_aware["materializedPairCount"],
        "provenanceMissingRootScopePairs": candidate_aware["missingRootScopePairs"],
        "provenanceDuplicatePairs": candidate_aware["duplicatePairs"],
    }


def build(client, *, market_date=None, backfill=False, from_date=None, commit=False, accepted_dates=None):
    # Historical/backfill behavior remains the legacy full-history builder.
    # Normal daily publication is incremental once staged era rollout is active:
    # existing history stays immutable and the activation-day cohort change is
    # neutralized explicitly instead of being misreported as price performance.
    rollout_refresh = None
    if market_date and not backfill:
        day = str(market_date)[:10]
        if not commit:
            # Dry-run/preview: candidate provenance is an acceptable input.
            # Zero writes ever happen on this path; report the provenance
            # state explicitly so callers never mistake a preview for a
            # publishable result.
            materialization = _rollout_source_materialization(client, day, allow_candidate=True)
            rollout_refresh = {
                "status": "preview",
                **materialization,
            }
            if not materialization["ready"]:
                raise RuntimeError(
                    "public root source is not materialized (preview, candidate provenance "
                    "allowed); refusing member-only index inputs"
                )
        else:
            # Commit: candidate-only rows still trigger the canonical finalizer.
            # Pre-cutover this remains strict FINAL provenance. Sep 10+ the
            # helper additionally recognizes positive canonical-checklist rows
            # for exact authority roots, which are the intentional fallback for
            # roots the finalizer cannot promote under its live coverage rules.
            materialization = _rollout_source_materialization(client, day, allow_candidate=False)
            if not materialization["ready"]:
                response = client.rpc(
                    ROLLOUT_REFRESH_RPC,
                    {"p_market_date": day},
                ).execute()
                rollout_refresh = getattr(response, "data", None)
                materialization = _rollout_source_materialization(client, day, allow_candidate=False)
                if not materialization["ready"]:
                    raise RuntimeError(
                        "public root source remains incomplete after rollout finalizer "
                        f"(provenanceState={materialization['provenanceState']})"
                    )
            else:
                rollout_refresh = {"status": "already_materialized", **materialization}
            if not materialization["ready"]:
                raise RuntimeError("public root source is not materialized; refusing member-only index inputs")
        rows = build_rollout_market_index_rows(client, market_date=day)
        persisted = persist_rollout_market_index_rows(client, rows) if commit else 0
    else:
        rows = build_market_index_history(
            client,
            through_date=market_date,
            accepted_dates=accepted_dates,
        )
        if from_date:
            rows = [row for row in rows if row["market_date"] >= from_date]
        persisted = persist_index_rows(client, rows) if commit else 0

    latest = {
        key: next((row for row in reversed(rows) if row["index_key"] == key), None)
        for key in INDEX_KEYS
    }
    source_fp = "|".join(
        str(latest[key].get("source_generation_fingerprint"))
        for key in INDEX_KEYS
        if latest[key]
    )
    eligible = resolve_market_root_cohort(client, market_date=market_date)
    return {
        "contractVersion": MARKET_INDEX_CONTRACT_VERSION,
        "methodologyVersion": MARKET_INDEX_METHODOLOGY_VERSION,
        "indexKeys": list(INDEX_KEYS),
        "firstDate": min((row["market_date"] for row in rows), default=None),
        "lastDate": max((row["market_date"] for row in rows), default=None),
        "rowsBuilt": len(rows),
        "rowsPersisted": persisted,
        "eligibleSetCountCurrent": len(eligible),
        "rawCurrentBasketValue": latest[RAW_INDEX_KEY].get("basket_value") if latest[RAW_INDEX_KEY] else None,
        "rawCurrentCardCount": latest[RAW_INDEX_KEY].get("card_count") if latest[RAW_INDEX_KEY] else None,
        "chaseCurrentBasketValue": latest[CHASE_INDEX_KEY].get("basket_value") if latest[CHASE_INDEX_KEY] else None,
        "chaseCurrentCardCount": latest[CHASE_INDEX_KEY].get("card_count") if latest[CHASE_INDEX_KEY] else None,
        "sourceGenerationFingerprint": source_fp,
        "rolloutRefresh": rollout_refresh,
        "warnings": [],
        "errors": [],
    }


def main():
    args = parser().parse_args()
    client = get_client()
    if args.force_publish:
        exc = MarketForcePublishRejected()
        print(json.dumps({"errors": [str(exc)]}, sort_keys=True))
        raise SystemExit(2) from exc
    if args.backfill:
        candidate_date = args.market_date
        preparation = {"status": "not_applicable", "reason": "historical_backfill"}
    else:
        try:
            candidate_date = resolve_market_publication_date(client, args.market_date)
            preparation = prepare_market_rollout_candidate(
                client, candidate_date, commit=bool(args.commit),
            )
        except Exception as exc:
            print(json.dumps({"errors": [f"Market rollout candidate preparation failed ({exc})"]}, sort_keys=True))
            raise SystemExit(3) from exc
    try:
        gate = enforce_market_publication_gate(
            client,
            commit=bool(args.commit),
            market_date=candidate_date,
            force_publish=bool(args.force_publish),
            entry_point="Pokemon Market index history",
        )
    except MarketForcePublishRejected as exc:
        print(json.dumps({"errors": [str(exc)]}, sort_keys=True))
        raise SystemExit(2) from exc
    if not gate.proceed:
        raise SystemExit(gate.exit_code)

    try:
        accepted = market_index_accepted_dates(client, through_date=candidate_date)
    except Exception as exc:
        print(json.dumps({"errors": [
            f"Market Date Quality history unavailable ({exc}); refusing to run "
            f"chain-link math without it"
        ]}, sort_keys=True))
        raise SystemExit(3) from exc
    if gate.decision.market_date:
        accepted.add(str(gate.decision.market_date)[:10])
    market_date = candidate_date or gate.decision.market_date
    try:
        summary = build(
            client, market_date=market_date, backfill=args.backfill,
            from_date=args.from_date, commit=args.commit, accepted_dates=accepted,
        )
    except Exception as exc:
        print(json.dumps({"errors": [str(exc)]}, sort_keys=True))
        raise SystemExit(1) from exc
    summary["marketQualityStatus"] = gate.decision.status
    summary["candidatePreparation"] = preparation
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
