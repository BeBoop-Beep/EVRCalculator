"""Repair Prompt 3 vintage predecessor/successor variant identities.

Vintage sets (Base/WOTC, Gym, Neo) carry obsolete "predecessor" physical
variant identities with ``edition IS NULL`` alongside the correct explicit
``first``/``unlimited`` "successor" variants for the same canonical card.
This script derives predecessor -> successor mappings from live semantic
queries (never a hardcoded UUID list), merges predecessor price history into
the successor's history using the existing source-winner rule, repairs the
derived tables that assume one physical instrument per canonical/edition
pair, and performs a narrowly scoped pilot re-projection for the two sets
that already publish precomputed daily state (Fossil, Neo Genesis).

Dry-run is the default-safe mode. Writes require ``--commit`` and use only
the service-role client. This module makes zero live-database connections
on its own; ``main()`` is the only place a real client is constructed.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

from backend.db.clients.supabase_client import create_service_role_client


LOG = logging.getLogger("market_explorer_vintage_predecessor_repair")

# --- Table / RPC names -------------------------------------------------
CANONICAL_TABLE = "pokemon_canonical_cards"
CARDS_TABLE = "cards"
VARIANTS_TABLE = "card_variants"
SETS_TABLE = "sets"
OBSERVATIONS_TABLE = "card_variant_price_observations"
MONTHLY_ROLLUP_TABLE = "card_variant_price_monthly_rollups"
INTERVAL_TABLE = "pokemon_card_variant_market_price_intervals"
TOP_HITS_TABLE = "card_market_top_hits_by_edition_latest"
DAILY_STATES_TABLE = "pokemon_market_explorer_card_daily_states"
CACHE_TABLE = "pokemon_market_explorer_query_cache"
CACHE_STATE_TABLE = "pokemon_market_explorer_cache_state"
MERGE_LEDGER_TABLE = "pokemon_market_explorer_variant_merge_ledger"

# RPCs the repair calls. Several of these do not exist yet in the deployed
# schema -- see the module-level NOTE below and section M of the Prompt 3
# report for what must be created before a real --commit run.
REFRESH_INTERVAL_RPC = "refresh_pokemon_card_variant_market_price_intervals"
MERGE_OBSERVATIONS_RPC = "merge_pokemon_card_variant_price_observations"  # NEEDS CREATION
RETIRE_VARIANT_RPC = "retire_pokemon_card_variant_predecessor"  # NEEDS CREATION
REBUILD_TOP_HITS_RPC = "rebuild_pokemon_card_market_top_hits_by_edition"  # NEEDS CREATION
REPROJECT_DAILY_STATES_RPC = "reproject_pokemon_market_explorer_card_daily_states"  # NEEDS CREATION

SUCCESSOR_EDITIONS = {"first", "1st-edition", "1st edition", "unlimited"}
UNLIMITED_EDITIONS = {"unlimited"}
FIRST_EDITIONS = {"first", "1st-edition", "1st edition"}

# Sets excluded wholesale: generic edition=NULL variants here are still
# live, distinct instruments (observations continuing through the present),
# not stale predecessors of an explicit-edition successor.
EXCLUDED_GENERIC_SET_NAMES = {"base", "base set 2"}

# Pilot sets: the only two sets whose precomputed daily-state projection is
# already published and therefore need row-level re-projection.
PILOT_PROJECTION_SET_NAMES = {"fossil", "neo genesis"}


def _fold(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _paged(query_factory, *, page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(query_factory().range(start, start + page_size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


@dataclass
class Mapping:
    predecessor_variant_id: str
    successor_variant_id: str
    canonical_card_id: str
    set_id: str
    set_name: str
    successor_edition: str  # "first" | "unlimited"


@dataclass
class Rejection:
    canonical_card_id: str
    set_id: str
    reason: str
    candidate_variant_ids: list[str] = field(default_factory=list)


@dataclass
class Summary:
    dry_run: bool
    sets_considered: int = 0
    predecessor_candidates: int = 0
    mappings_resolved: int = 0
    mappings_by_edition: dict[str, int] = field(default_factory=dict)
    excluded_generic_count: int = 0
    excluded_machamp_count: int = 0
    ambiguous_rejections: int = 0
    already_merged_skipped: int = 0
    observations_examined: int = 0
    observations_collided: int = 0
    observations_predecessor_wins: int = 0
    observations_price_matched_collisions: int = 0
    observations_price_differing_collisions: int = 0
    variants_retired: int = 0
    monthly_rollups_touched: int = 0
    intervals_regenerated: int = 0
    top_hits_rebuilt: int = 0
    pilot_projection_rows_touched: dict[str, int] = field(default_factory=dict)
    cache_entries_invalidated: int = 0
    repair_generation_after: int | None = None
    failures: int = 0
    elapsed_seconds: float = 0.0


# --- Exclusion rules -----------------------------------------------------

def is_excluded_generic_set(set_name: str) -> bool:
    """Base and Base Set 2 generic edition=NULL variants are still live
    instruments receiving current observations -- never a stale predecessor.
    """
    return _fold(set_name) in EXCLUDED_GENERIC_SET_NAMES


def is_excluded_machamp_first_edition(card_name: str, card_number: str, set_name: str,
                                       edition: str) -> bool:
    """Base Set Machamp #8 explicit 1st-edition is a legitimate distinct
    printing/instrument, not a predecessor of anything -- it must never be
    treated as a merge candidate (predecessor or successor).
    """
    return (
        _fold(set_name) == "base"
        and _fold(card_name) == "machamp"
        and str(card_number or "").lstrip("0") == "8"
        and _fold(edition) in FIRST_EDITIONS
    )


def is_excluded_variant(*, set_name: str, card_name: str, card_number: str,
                        edition: str) -> bool:
    if is_excluded_generic_set(set_name) and not edition:
        return True
    if is_excluded_machamp_first_edition(card_name, card_number, set_name, edition):
        return True
    return False


# --- Mapping resolution ---------------------------------------------------

def classify_predecessor_successor_mappings(
    client: Any, *, set_ids: Sequence[str] = (),
) -> tuple[list[Mapping], list[Rejection], int, int]:
    """Derive predecessor -> successor mappings from live semantic state.

    A predecessor is a ``card_variants`` row with ``edition IS NULL`` whose
    parent ``cards`` row is linked (1:1, by ``card_id``) to a successor row
    with an explicit edition in {first, unlimited} for the *same* card. Both
    candidacy pools are grouped by ``card_id``; a mapping is only accepted
    when exactly one predecessor and exactly one same-edition-class
    successor exist for that card. Anything else is collected as a
    rejection instead of guessed.
    """
    sets_query = client.table(SETS_TABLE).select("id,name")
    if set_ids:
        sets_query = sets_query.in_("id", list(set_ids))
    sets = _paged(lambda: sets_query)
    sets_by_id = {str(row["id"]): row.get("name") for row in sets}

    cards = _paged(lambda: client.table(CARDS_TABLE).select("id,set_id,name,card_number")
                   .in_("set_id", list(sets_by_id)) if sets_by_id else
                   client.table(CARDS_TABLE).select("id,set_id,name,card_number"))
    cards_by_id = {str(row["id"]): row for row in cards}

    variants = _paged(lambda: client.table(VARIANTS_TABLE)
                      .select("id,card_id,edition")
                      .in_("card_id", list(cards_by_id)) if cards_by_id else
                      client.table(VARIANTS_TABLE).select("id,card_id,edition"))

    predecessors_by_card: dict[str, list[str]] = {}
    successors_by_card: dict[str, dict[str, list[str]]] = {}
    excluded_generic = 0
    excluded_machamp = 0

    for row in variants:
        card_id = str(row.get("card_id"))
        card = cards_by_id.get(card_id)
        if not card:
            continue
        set_row_name = sets_by_id.get(str(card.get("set_id"))) or ""
        edition = row.get("edition")
        edition_fold = _fold(edition)
        variant_id = str(row["id"])

        if is_excluded_variant(set_name=set_row_name, card_name=card.get("name"),
                               card_number=card.get("card_number"), edition=edition):
            if not edition:
                excluded_generic += 1
            else:
                excluded_machamp += 1
            continue

        if not edition:
            predecessors_by_card.setdefault(card_id, []).append(variant_id)
        elif edition_fold in FIRST_EDITIONS:
            successors_by_card.setdefault(card_id, {}).setdefault("first", []).append(variant_id)
        elif edition_fold in UNLIMITED_EDITIONS:
            successors_by_card.setdefault(card_id, {}).setdefault("unlimited", []).append(variant_id)

    mappings: list[Mapping] = []
    rejections: list[Rejection] = []

    for card_id, predecessor_ids in predecessors_by_card.items():
        card = cards_by_id[card_id]
        set_id = str(card.get("set_id"))
        set_name = sets_by_id.get(set_id) or ""
        successor_pool = successors_by_card.get(card_id, {})
        successor_ids_flat = [vid for ids in successor_pool.values() for vid in ids]

        if len(predecessor_ids) != 1:
            rejections.append(Rejection(
                canonical_card_id=card_id, set_id=set_id,
                reason="multiple_predecessor_candidates",
                candidate_variant_ids=sorted(predecessor_ids),
            ))
            continue
        if not successor_ids_flat:
            rejections.append(Rejection(
                canonical_card_id=card_id, set_id=set_id,
                reason="no_successor_candidate",
                candidate_variant_ids=sorted(predecessor_ids),
            ))
            continue
        if len(successor_ids_flat) != 1:
            rejections.append(Rejection(
                canonical_card_id=card_id, set_id=set_id,
                reason="multiple_successor_candidates",
                candidate_variant_ids=sorted(successor_ids_flat),
            ))
            continue

        edition_label = "first" if successor_pool.get("first") else "unlimited"
        mappings.append(Mapping(
            predecessor_variant_id=predecessor_ids[0],
            successor_variant_id=successor_ids_flat[0],
            canonical_card_id=card_id,
            set_id=set_id,
            set_name=set_name,
            successor_edition=edition_label,
        ))

    return mappings, rejections, excluded_generic, excluded_machamp


def apply_allowlist(mappings: list[Mapping], allowlist: Sequence[str]) -> list[Mapping]:
    """Testability hook: restrict resolved mappings to explicit predecessor
    variant UUIDs. Never used to *add* mappings that weren't independently
    derived above -- only to narrow scope for a bounded/testable run.
    """
    if not allowlist:
        return mappings
    allowed = set(allowlist)
    return [m for m in mappings if m.predecessor_variant_id in allowed]


# --- Idempotency -----------------------------------------------------------

def already_merged_predecessor_ids(client: Any, predecessor_ids: Sequence[str]) -> set[str]:
    if not predecessor_ids:
        return set()
    rows = _paged(lambda: client.table(MERGE_LEDGER_TABLE)
                  .select("predecessor_variant_id")
                  .in_("predecessor_variant_id", list(predecessor_ids)))
    return {str(row["predecessor_variant_id"]) for row in rows}


# --- Observation collision resolution ---------------------------------------

def resolve_observation_winners(
    predecessor_observations: Iterable[dict[str, Any]],
    successor_observations: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Mirror the backfill script's source-winner rule: for observations
    that collide on (successor_variant, condition, source, captured_date),
    keep the row with the later ``created_at``, tie-broken by observation
    id. Returns (winners_to_write, losers_to_discard) among the
    predecessor rows that had a colliding successor counterpart; the
    non-colliding predecessor observations are the caller's responsibility
    to carry over untouched.
    """
    successor_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in successor_observations:
        key = (row.get("card_variant_id"), row.get("condition_id"), row.get("source"),
               row.get("captured_date"))
        successor_by_key[key] = row

    winners: list[dict[str, Any]] = []
    losers: list[dict[str, Any]] = []
    for row in predecessor_observations:
        key = (row.get("_successor_variant_id"), row.get("condition_id"), row.get("source"),
               row.get("captured_date"))
        existing = successor_by_key.get(key)
        if existing is None:
            continue  # not a collision; caller re-parents it untouched
        pred_rank = (row.get("created_at"), str(row.get("id")))
        succ_rank = (existing.get("created_at"), str(existing.get("id")))
        if pred_rank > succ_rank:
            winners.append(row)
        else:
            losers.append(row)
    return winners, losers


# --- Derived-table repair phases --------------------------------------------

def merge_observations(client: Any, *, commit: bool, mapping: Mapping,
                       summary: Summary) -> None:
    predecessor_obs = _paged(lambda: client.table(OBSERVATIONS_TABLE)
                             .select("id,card_variant_id,condition_id,source,captured_date,"
                                    "market_price,created_at")
                             .eq("card_variant_id", mapping.predecessor_variant_id))
    for row in predecessor_obs:
        row["_successor_variant_id"] = mapping.successor_variant_id
    successor_obs = _paged(lambda: client.table(OBSERVATIONS_TABLE)
                           .select("id,card_variant_id,condition_id,source,captured_date,"
                                  "market_price,created_at")
                           .eq("card_variant_id", mapping.successor_variant_id))

    summary.observations_examined += len(predecessor_obs)
    winners, losers = resolve_observation_winners(predecessor_obs, successor_obs)
    summary.observations_collided += len(winners) + len(losers)
    summary.observations_predecessor_wins += len(winners)
    for winner in winners:
        key = (winner.get("_successor_variant_id"), winner.get("condition_id"),
               winner.get("source"), winner.get("captured_date"))
        existing = next((r for r in successor_obs
                         if (r.get("card_variant_id"), r.get("condition_id"), r.get("source"),
                             r.get("captured_date")) == key), None)
        if existing is not None and existing.get("market_price") == winner.get("market_price"):
            summary.observations_price_matched_collisions += 1
        else:
            summary.observations_price_differing_collisions += 1

    if not commit:
        return
    client.rpc(MERGE_OBSERVATIONS_RPC, {
        "p_predecessor_variant_id": mapping.predecessor_variant_id,
        "p_successor_variant_id": mapping.successor_variant_id,
        "p_winning_observation_ids": [str(row["id"]) for row in winners],
        "p_discarded_observation_ids": [str(row["id"]) for row in losers],
    }).execute()


def regenerate_monthly_rollups(client: Any, *, commit: bool, variant_ids: Sequence[str],
                               summary: Summary) -> None:
    """Regenerate/invalidate monthly rollups for successor variants whose
    merged history changed. Uses a delete-and-recompute-on-read style
    invalidation consistent with rollup tables elsewhere in the repo
    (rollups are derived, never hand-edited).
    """
    if not variant_ids:
        return
    summary.monthly_rollups_touched += len(variant_ids)
    if not commit:
        return
    client.table(MONTHLY_ROLLUP_TABLE).delete().in_("card_variant_id", list(variant_ids)).execute()


def regenerate_intervals(client: Any, *, commit: bool, variant_ids: Sequence[str],
                         summary: Summary) -> None:
    if not variant_ids:
        return
    if not commit:
        summary.intervals_regenerated += len(variant_ids)
        return
    response = client.rpc(REFRESH_INTERVAL_RPC, {"p_card_variant_ids": list(variant_ids)}).execute()
    summary.intervals_regenerated += int(response.data or 0)


def rebuild_top_hits(client: Any, *, commit: bool, set_ids: Sequence[str],
                     summary: Summary) -> None:
    if not set_ids:
        return
    if not commit:
        rows = _paged(lambda: client.table(TOP_HITS_TABLE).select("id").in_("set_id", list(set_ids)))
        summary.top_hits_rebuilt += len(rows)
        return
    response = client.rpc(REBUILD_TOP_HITS_RPC, {"p_set_ids": list(set_ids)}).execute()
    summary.top_hits_rebuilt += int(response.data or 0)


def retire_predecessor_variants(client: Any, *, commit: bool, mappings: Sequence[Mapping],
                                summary: Summary) -> None:
    """Soft-retire each merged predecessor variant. This calls a dedicated
    RPC rather than issuing a raw UPDATE because there is no existing
    soft-delete column convention on ``card_variants`` visible in this
    repo -- see report section M. The RPC is expected to (a) mark the
    predecessor row retired/pointing at its successor and (b) write a
    ``pokemon_market_explorer_variant_merge_ledger`` row so reruns are
    idempotent.
    """
    for mapping in mappings:
        summary.variants_retired += 1
        if not commit:
            continue
        client.rpc(RETIRE_VARIANT_RPC, {
            "p_predecessor_variant_id": mapping.predecessor_variant_id,
            "p_successor_variant_id": mapping.successor_variant_id,
        }).execute()
        client.table(MERGE_LEDGER_TABLE).upsert({
            "predecessor_variant_id": mapping.predecessor_variant_id,
            "successor_variant_id": mapping.successor_variant_id,
        }).execute()


def repair_pilot_projections(client: Any, *, commit: bool, mappings: Sequence[Mapping],
                             summary: Summary) -> None:
    """Re-project ``pokemon_market_explorer_card_daily_states`` rows, scoped
    STRICTLY to Fossil and Neo Genesis -- the only two sets with an already
    published pilot projection. Every other affected vintage set has no
    published daily-state rows yet, so there is nothing to re-project there.
    """
    pilot_mappings = [m for m in mappings if _fold(m.set_name) in PILOT_PROJECTION_SET_NAMES]
    by_set: dict[str, list[Mapping]] = {}
    for mapping in pilot_mappings:
        by_set.setdefault(mapping.set_name, []).append(mapping)

    for set_name, set_mappings in by_set.items():
        set_id = set_mappings[0].set_id
        if not commit:
            rows = _paged(lambda sid=set_id: client.table(DAILY_STATES_TABLE)
                         .select("id").eq("set_id", sid))
            summary.pilot_projection_rows_touched[set_name] = len(rows)
            continue
        response = client.rpc(REPROJECT_DAILY_STATES_RPC, {
            "p_set_id": set_id,
            "p_predecessor_variant_ids": [m.predecessor_variant_id for m in set_mappings],
            "p_successor_variant_ids": [m.successor_variant_id for m in set_mappings],
        }).execute()
        summary.pilot_projection_rows_touched[set_name] = int(response.data or 0)


def invalidate_targeted_caches(client: Any, *, commit: bool, mappings: Sequence[Mapping],
                               summary: Summary) -> None:
    """Invalidate only the L2 cache rows whose ``normalized_spec.setIds``
    intersects the repaired sets (a Fossil-only custom cache and the mixed
    Fossil+Neo Genesis cache), plus increment ``repair_generation`` on
    ``pokemon_market_explorer_cache_state`` for the 'cards' asset only.

    The existing ``invalidate_pokemon_market_explorer_query_cache`` RPC
    (see backend/db/services/market_explorer_query_planner.py) is a
    blanket, date-scoped invalidation across every cached query for every
    asset -- broader than needed here. This performs targeted row-level
    invalidation instead so unrelated cached queries are left untouched.
    """
    affected_set_ids = {m.set_id for m in mappings if _fold(m.set_name) in PILOT_PROJECTION_SET_NAMES}
    if not affected_set_ids:
        return

    rows = _paged(lambda: client.table(CACHE_TABLE).select("query_fingerprint,normalized_spec"))
    targeted_fingerprints = [
        str(row["query_fingerprint"]) for row in rows
        if affected_set_ids & set(str(sid) for sid in (row.get("normalized_spec") or {}).get("setIds") or [])
    ]
    summary.cache_entries_invalidated += len(targeted_fingerprints)

    if not commit:
        return
    for fingerprint in targeted_fingerprints:
        client.table(CACHE_TABLE).update({"status": "stale"}).eq(
            "query_fingerprint", fingerprint).execute()

    current = list((client.table(CACHE_STATE_TABLE).select("repair_generation")
                   .eq("asset", "cards").limit(1).execute()).data or [])
    next_generation = int((current[0].get("repair_generation") or 0) if current else 0) + 1
    client.table(CACHE_STATE_TABLE).update({"repair_generation": next_generation}).eq(
        "asset", "cards").execute()
    summary.repair_generation_after = next_generation


# --- Orchestration -----------------------------------------------------------

def run_repair(
    client: Any,
    *,
    commit: bool,
    set_ids: Sequence[str] = (),
    predecessor_allowlist: Sequence[str] = (),
) -> dict[str, Any]:
    started = time.monotonic()
    summary = Summary(dry_run=not commit)

    try:
        mappings, rejections, excluded_generic, excluded_machamp = classify_predecessor_successor_mappings(
            client, set_ids=set_ids)
        mappings = apply_allowlist(mappings, predecessor_allowlist)
        summary.excluded_generic_count = excluded_generic
        summary.excluded_machamp_count = excluded_machamp

        summary.sets_considered = len({m.set_id for m in mappings})
        summary.predecessor_candidates = len(mappings) + len(rejections)
        summary.ambiguous_rejections = len(rejections)

        already_merged = already_merged_predecessor_ids(
            client, [m.predecessor_variant_id for m in mappings])
        summary.already_merged_skipped = sum(
            1 for m in mappings if m.predecessor_variant_id in already_merged)
        pending = [m for m in mappings if m.predecessor_variant_id not in already_merged]

        summary.mappings_resolved = len(pending)
        for mapping in pending:
            summary.mappings_by_edition[mapping.successor_edition] = (
                summary.mappings_by_edition.get(mapping.successor_edition, 0) + 1)

        for mapping in pending:
            merge_observations(client, commit=commit, mapping=mapping, summary=summary)

        successor_ids = sorted({m.successor_variant_id for m in pending})
        regenerate_monthly_rollups(client, commit=commit, variant_ids=successor_ids, summary=summary)
        regenerate_intervals(client, commit=commit, variant_ids=successor_ids, summary=summary)
        rebuild_top_hits(client, commit=commit,
                         set_ids=sorted({m.set_id for m in pending}), summary=summary)
        retire_predecessor_variants(client, commit=commit, mappings=pending, summary=summary)
        repair_pilot_projections(client, commit=commit, mappings=pending, summary=summary)
        invalidate_targeted_caches(client, commit=commit, mappings=pending, summary=summary)
    except Exception as exc:
        summary.failures += 1
        LOG.error(json.dumps({"event": "repair_failed", "error": str(exc)}, sort_keys=True))

    summary.elapsed_seconds = round(time.monotonic() - started, 3)
    result = asdict(summary)
    result["rejections"] = [asdict(r) for r in rejections] if not commit else result.get("rejections", [])
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Plan the repair; perform no writes.")
    mode.add_argument("--commit", action="store_true", help="Execute the repair via service-role RPCs.")
    parser.add_argument("--set-id", action="append", default=[],
                        help="Limit mapping derivation to a set UUID; repeatable.")
    parser.add_argument("--predecessor-id", action="append", default=[],
                        help="Restrict to explicit predecessor variant UUIDs; repeatable.")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = build_parser().parse_args()
    report = run_repair(
        create_service_role_client(), commit=bool(args.commit),
        set_ids=args.set_id, predecessor_allowlist=args.predecessor_id,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
