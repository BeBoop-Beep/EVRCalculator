"""Read-only diagnostic: root-causes missing/degraded slim-contract data.

Phase 5C (see audit_pokemon_set_slim_contract_health.py) fixed shell payload
size. It also surfaced three data-completeness gaps that are NOT size
problems: market/top-chase is empty for ~170/171 sets, pull-rates is empty
for ~149/171 sets, and shell falls back to its empty-identity shape for
~138/171 sets. This script determines *why*, per set, by reading the
relevant source tables directly (never rebuilding, never writing) and
classifying each set into one root-cause bucket per contract.

READ_ONLY_DIAGNOSTIC = True — every call in this module is a read. It never
inserts/updates/deletes/upserts, never calls an RPC, and never invokes a
snapshot builder function that writes. It only reads:
  - pokemon_set_market_dashboard_snapshot_latest (top-chase source)
  - pokemon_set_page_snapshot_latest (shell + pull-rates source; payload_json
    is only read for the small subset of sets that already have a row, to
    check for the pull_rate_assumptions field)
  - pokemon_canonical_cards / cards / card_variants (canonical/variant mapping)
  - card_variant_price_observations (near-mint price source, scoped to a
    specific set's variant_ids — never an unscoped table scan)
  - calculation_history_trend (simulation/RIP snapshot coverage proxy)

Usage:
    python backend/scripts/diagnose_pokemon_set_slim_contract_completeness.py
    python backend/scripts/diagnose_pokemon_set_slim_contract_completeness.py --limit 10
    python backend/scripts/diagnose_pokemon_set_slim_contract_completeness.py --set-ids perfectOrder,shroudedFable
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

READ_ONLY_DIAGNOSTIC = True  # This script must never insert/update/delete/rebuild.

TOP_CHASE_DEFAULT_WINDOW = "30d"
TOP_CHASE_FALLBACK_WINDOW = "365d"

# Heuristic only (name-substring match) — used to flag sets where a slim
# contract may legitimately not apply (side-collections, promo-only
# products) rather than representing a real data gap. False positives/
# negatives are expected; this is a diagnostic hint, not ground truth.
_SPECIAL_SUBSET_NAME_PATTERNS = (
    "black star promo",
    "trainer gallery",
    "shiny vault",
    "mcdonald",
    "pop series",
    "best of game",
    "futsal collection",
    "classic collection",
    "trainer kit",
    "starter set",
    "dragon vault",
    "southern islands",
    "pokemon go",
    "pokémon go",
)


# ---------------------------------------------------------------------------
# Pure helpers — no DB/network access, unit-tested in
# backend/tests/unit/scripts/test_diagnose_pokemon_set_slim_contract_completeness.py
# ---------------------------------------------------------------------------


def is_special_subset_name(name: Any) -> bool:
    """Best-effort heuristic: does this set's name look like a promo/side
    collection rather than a standalone mainline product?"""
    text = str(name or "").strip().lower()
    if not text:
        return False
    return any(pattern in text for pattern in _SPECIAL_SUBSET_NAME_PATTERNS)


def classify_top_chase_root_cause(
    *,
    has_dashboard_30d: bool,
    has_dashboard_365d: bool,
    top_chase_cards_count: int,
    top_chase_history_count: int,
    source_observation_count: int,
    canonical_card_count: int,
    variant_count: int,
    is_special_subset: bool,
) -> str:
    """Classify why market/top-chase has no usable data for one set.

    Checked in priority order against pokemon_set_market_dashboard_snapshot_latest
    (the only source get_pokemon_set_top_chase_snapshot_payload reads): a
    dashboard row missing entirely outranks an empty-cards row, which
    outranks a wrong-window row, which outranks an empty-histories row.
    """
    if has_dashboard_30d and top_chase_cards_count > 0 and top_chase_history_count > 0:
        return "healthy"
    if not has_dashboard_30d and not has_dashboard_365d:
        return "missing_market_dashboard_snapshot_row"
    if top_chase_cards_count == 0:
        if is_special_subset:
            return "special_subset_not_applicable"
        if canonical_card_count == 0 or variant_count == 0:
            return "canonical_variant_mapping_missing"
        if source_observation_count == 0:
            return "source_observations_missing"
        return "source_observations_exist_but_snapshot_not_built"
    if not has_dashboard_30d and has_dashboard_365d:
        # The dominant real-world case (see Phase 5D audit): the builder has
        # only ever been run with the default 365d window, so no 30d row
        # exists even though top_chase_cards_json is already populated under
        # the 365d row. This is still the DB row's classification — Phase 5E
        # added a read-path fallback so get_pokemon_set_top_chase_snapshot_payload
        # itself already serves this data correctly; see
        # is_top_chase_endpoint_repairable_from_365d below.
        return "dashboard_row_wrong_window_key"
    if top_chase_history_count == 0:
        return "cards_exist_but_histories_empty"
    return "unknown"


def is_top_chase_endpoint_repairable_from_365d(top_chase_root_cause: str) -> bool:
    """True when get_pokemon_set_top_chase_snapshot_payload's 365d fallback
    (added Phase 5E) already serves this set's stored cards/histories
    correctly at the endpoint level, even though the underlying
    pokemon_set_market_dashboard_snapshot_latest row is still classified as
    wrong-window (this diagnostic never mutates DB rows, so that
    classification doesn't change until a future rebuild)."""
    return top_chase_root_cause == "dashboard_row_wrong_window_key"


def classify_pull_rates_root_cause(
    *,
    has_page_snapshot: bool,
    has_pull_rate_assumptions: bool,
    has_simulation_snapshot: bool,
    is_special_subset: bool,
) -> str:
    """Classify why pull-rates has no usable data for one set.

    get_pokemon_set_pull_rates_snapshot_payload reads only
    pokemon_set_page_snapshot_latest.payload_json's pull_rate_assumptions/
    pullRateAssumptions field — there is no dedicated pull-rates source
    table today.
    """
    if has_page_snapshot and has_pull_rate_assumptions:
        return "healthy"
    if not has_page_snapshot:
        if is_special_subset:
            return "special_subset_not_applicable"
        if not has_simulation_snapshot:
            return "missing_simulation_snapshot"
        return "missing_page_snapshot_row"
    if is_special_subset:
        return "special_subset_not_applicable"
    return "source_exists_but_payload_builder_does_not_read_it"


def classify_shell_root_cause(
    *,
    has_page_snapshot: bool,
    has_split_shell_columns: bool,
    has_simulation_snapshot: bool,
    is_special_subset: bool,
) -> str:
    """Classify why shell falls back to its empty-identity shape for one set.

    get_pokemon_set_shell_snapshot_payload reads only the small split
    columns on pokemon_set_page_snapshot_latest — never payload_json.
    """
    if has_page_snapshot and has_split_shell_columns:
        return "healthy"
    if has_page_snapshot and not has_split_shell_columns:
        return "page_snapshot_row_missing_split_columns"
    if is_special_subset:
        return "special_subset_not_applicable"
    if not has_simulation_snapshot:
        return "missing_simulation_snapshot"
    return "no_page_snapshot_row"


_ACTION_PRIORITY: Tuple[Tuple[str, str], ...] = (
    ("shell", "missing_simulation_snapshot"),
    ("pull_rates", "missing_simulation_snapshot"),
    ("shell", "page_snapshot_row_missing_split_columns"),
    ("shell", "no_page_snapshot_row"),
    ("pull_rates", "missing_page_snapshot_row"),
    ("top_chase", "dashboard_row_wrong_window_key"),
    ("top_chase", "missing_market_dashboard_snapshot_row"),
    ("pull_rates", "source_exists_but_payload_builder_does_not_read_it"),
    ("top_chase", "canonical_variant_mapping_missing"),
    ("top_chase", "source_observations_missing"),
    ("top_chase", "source_observations_exist_but_snapshot_not_built"),
    ("top_chase", "cards_exist_but_histories_empty"),
)

_ACTION_LABELS: Dict[str, str] = {
    "shell:page_snapshot_row_missing_split_columns": "rebuild_page_snapshot_split_columns",
    "shell:no_page_snapshot_row": "rebuild_page_snapshot",
    "pull_rates:missing_page_snapshot_row": "rebuild_page_snapshot",
    "top_chase:missing_market_dashboard_snapshot_row": "build_market_dashboard_snapshot",
    "shell:missing_simulation_snapshot": "run_simulation_pipeline_then_rebuild_snapshots",
    "pull_rates:missing_simulation_snapshot": "run_simulation_pipeline_then_rebuild_snapshots",
    "top_chase:dashboard_row_wrong_window_key": "rebuild_market_dashboard_snapshot_with_30d_window",
    "pull_rates:source_exists_but_payload_builder_does_not_read_it": "extend_page_snapshot_builder_for_pull_rate_assumptions",
    "top_chase:canonical_variant_mapping_missing": "repair_canonical_variant_mapping",
    "top_chase:source_observations_missing": "backfill_price_observations",
    "top_chase:source_observations_exist_but_snapshot_not_built": "rebuild_market_dashboard_snapshot",
    "top_chase:cards_exist_but_histories_empty": "backfill_top_chase_card_daily_history",
}


def recommend_next_action(
    *,
    top_chase_root_cause: str,
    pull_rates_root_cause: str,
    shell_root_cause: str,
) -> str:
    """Pick the single highest-leverage next action for one set.

    Priority favors the deepest/most foundational blocker first: a missing
    simulation snapshot blocks shell and pull-rates entirely and must be
    fixed before anything downstream can be rebuilt, so it outranks a
    page-snapshot rebuild (cheap once simulation data exists), which
    outranks the top-chase window-key fix (Phase 5D's single biggest lever
    by set count — see dashboard_row_wrong_window_key), which outranks the
    smaller per-contract gaps.
    """
    root_causes = {"top_chase": top_chase_root_cause, "pull_rates": pull_rates_root_cause, "shell": shell_root_cause}
    for contract, cause in _ACTION_PRIORITY:
        if root_causes.get(contract) == cause:
            return _ACTION_LABELS[f"{contract}:{cause}"]

    all_causes = set(root_causes.values())
    if all_causes <= {"healthy"}:
        return "no_action_needed"
    if all_causes <= {"healthy", "special_subset_not_applicable"}:
        return "no_action_special_subset"
    return "investigate_further"


# ---------------------------------------------------------------------------
# Bulk read-only source fetchers
# ---------------------------------------------------------------------------


def _paged_fetch(query_factory, *, page_size: int = 1000, max_rows: int = 200_000) -> List[Dict[str, Any]]:
    """Page through a postgrest query (which silently caps at ~1000 rows per
    call) via .range(), returning every row. Read-only; never used with an
    unbounded/unscoped query on a large observation table (see module
    docstring) — only on small-to-medium reference tables."""
    rows: List[Dict[str, Any]] = []
    offset = 0
    while offset < max_rows:
        batch = query_factory().range(offset, offset + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def fetch_market_dashboard_index(client) -> Dict[str, Dict[str, Any]]:
    """One row per set_id, merging its 30d/365d pokemon_set_market_dashboard_snapshot_latest rows."""
    rows = _paged_fetch(
        lambda: client.table("pokemon_set_market_dashboard_snapshot_latest").select(
            "set_id,window_key,top_chase_cards_json,top_chase_card_histories_json"
        )
    )
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        set_id = str(row.get("set_id") or "")
        if not set_id:
            continue
        entry = index.setdefault(
            set_id,
            {
                "has_30d": False,
                "has_365d": False,
                "cards_30d": 0,
                "cards_365d": 0,
                "history_30d": 0,
                "history_365d": 0,
            },
        )
        window_key = str(row.get("window_key") or "")
        cards = row.get("top_chase_cards_json") or []
        histories = row.get("top_chase_card_histories_json") or {}
        history_count = sum(1 for points in histories.values() if points) if isinstance(histories, dict) else 0
        if window_key == TOP_CHASE_DEFAULT_WINDOW:
            entry["has_30d"] = True
            entry["cards_30d"] = len(cards)
            entry["history_30d"] = history_count
        elif window_key == TOP_CHASE_FALLBACK_WINDOW:
            entry["has_365d"] = True
            entry["cards_365d"] = len(cards)
            entry["history_365d"] = history_count
    return index


def fetch_page_snapshot_index(client) -> Dict[str, Dict[str, Any]]:
    """One row per set_id: whether pokemon_set_page_snapshot_latest exists and
    whether its split (shell) columns are populated. Never reads payload_json
    here — that column is large and only fetched per-set in
    fetch_pull_rate_assumptions_presence below."""
    rows = _paged_fetch(
        lambda: client.table("pokemon_set_page_snapshot_latest").select("set_id,set_identity_json,title_card_json")
    )
    index: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        set_id = str(row.get("set_id") or "")
        if not set_id:
            continue
        index[set_id] = {
            "has_page_snapshot": True,
            "has_split_shell_columns": bool(row.get("set_identity_json")) and bool(row.get("title_card_json")),
        }
    return index


def fetch_pull_rate_assumptions_presence(client, set_ids: List[str]) -> Dict[str, bool]:
    """Per-set check of payload_json.pull_rate_assumptions — only called for
    the (typically small) set of ids that already have a page snapshot row,
    since payload_json is the full multi-hundred-KB legacy page payload."""
    presence: Dict[str, bool] = {}
    for set_id in set_ids:
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                result = (
                    client.table("pokemon_set_page_snapshot_latest")
                    .select("set_id,payload_json")
                    .eq("set_id", set_id)
                    .limit(1)
                    .execute()
                )
                row = (result.data or [{}])[0] if result.data else {}
                payload_json = row.get("payload_json") or {}
                raw = payload_json.get("pull_rate_assumptions") or payload_json.get("pullRateAssumptions")
                presence[set_id] = bool(raw)
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001 - diagnostic tool, retry then report
                last_exc = exc
                time.sleep(1.5)
        if last_exc is not None:
            presence[set_id] = False
    return presence


def fetch_canonical_card_counts(client) -> Dict[str, int]:
    rows = _paged_fetch(lambda: client.table("pokemon_canonical_cards").select("set_id"))
    counts: Dict[str, int] = {}
    for row in rows:
        set_id = str(row.get("set_id") or "")
        if set_id:
            counts[set_id] = counts.get(set_id, 0) + 1
    return counts


def fetch_variant_counts_and_ids(client) -> Tuple[Dict[str, int], Dict[str, List[str]]]:
    """Join legacy cards(set_id) -> card_variants(card_id) to approximate a
    variant count and variant-id list per set (used only to scope the
    per-set price-observation existence check below to a small id list)."""
    card_rows = _paged_fetch(lambda: client.table("cards").select("id,set_id"))
    set_id_by_card_id = {str(r["id"]): str(r.get("set_id") or "") for r in card_rows if r.get("id") is not None}

    variant_rows = _paged_fetch(lambda: client.table("card_variants").select("id,card_id"))
    variant_ids_by_set: Dict[str, List[str]] = {}
    for row in variant_rows:
        card_id = str(row.get("card_id") or "")
        set_id = set_id_by_card_id.get(card_id)
        variant_id = row.get("id")
        if not set_id or variant_id is None:
            continue
        variant_ids_by_set.setdefault(set_id, []).append(str(variant_id))

    counts = {set_id: len(ids) for set_id, ids in variant_ids_by_set.items()}
    return counts, variant_ids_by_set


def fetch_simulation_set_ids(client) -> Set[str]:
    rows = _paged_fetch(
        lambda: client.table("calculation_history_trend").select("target_id,target_type").eq("target_type", "set")
    )
    return {str(row.get("target_id") or "") for row in rows if row.get("target_id")}


def fetch_source_observation_count(client, variant_ids: List[str], *, condition_id: str, cap: int = 200) -> int:
    """Existence-scoped, capped observation count for one set's variant_ids —
    never an unscoped scan of card_variant_price_observations (that table is
    large enough that even a plain count() times out; see module docstring).
    Only called for sets with zero top_chase_cards_json entries, so this
    runs for a small handful of sets per full audit run, not all 171."""
    if not variant_ids:
        return 0
    try:
        result = (
            client.table("card_variant_price_observations")
            .select("card_variant_id")
            .in_("card_variant_id", variant_ids[:500])
            .eq("condition_id", condition_id)
            .gt("market_price", 0)
            .limit(cap)
            .execute()
        )
        return len(result.data or [])
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Per-set diagnosis
# ---------------------------------------------------------------------------

CSV_FIELDNAMES: List[str] = [
    "set_id",
    "set_name",
    "canonical_key",
    "pokemon_api_set_id",
    "era",
    "missing_top_chase",
    "top_chase_root_cause",
    "top_chase_endpoint_repairable_from_365d",
    "has_market_dashboard_30d",
    "has_market_dashboard_365d",
    "top_chase_cards_count",
    "top_chase_history_count",
    "source_observation_count",
    "canonical_card_count",
    "variant_count",
    "missing_pull_rates",
    "pull_rates_root_cause",
    "has_pull_rate_source",
    "has_simulation_snapshot",
    "missing_shell",
    "shell_root_cause",
    "has_page_snapshot",
    "has_split_shell_columns",
    "recommended_next_action",
    "warnings",
]


def diagnose_set(
    set_row: Dict[str, Any],
    *,
    dashboard_index: Dict[str, Dict[str, Any]],
    page_snapshot_index: Dict[str, Dict[str, Any]],
    pull_rate_presence: Dict[str, bool],
    canonical_counts: Dict[str, int],
    variant_counts: Dict[str, int],
    variant_ids_by_set: Dict[str, List[str]],
    simulation_set_ids: Set[str],
    client,
    condition_id: str,
) -> Dict[str, Any]:
    set_id = str(set_row.get("id") or "")
    name = set_row.get("name")
    is_special = is_special_subset_name(name)

    dash = dashboard_index.get(set_id, {})
    has_30d = bool(dash.get("has_30d"))
    has_365d = bool(dash.get("has_365d"))
    cards_count = dash.get("cards_30d") if has_30d else dash.get("cards_365d", 0)
    history_count = dash.get("history_30d") if has_30d else dash.get("history_365d", 0)
    canonical_count = canonical_counts.get(set_id, 0)
    variant_count = variant_counts.get(set_id, 0)

    source_observation_count = 0
    if cards_count == 0 and (has_30d or has_365d):
        source_observation_count = fetch_source_observation_count(
            client, variant_ids_by_set.get(set_id, []), condition_id=condition_id
        )

    top_chase_cause = classify_top_chase_root_cause(
        has_dashboard_30d=has_30d,
        has_dashboard_365d=has_365d,
        top_chase_cards_count=cards_count,
        top_chase_history_count=history_count,
        source_observation_count=source_observation_count,
        canonical_card_count=canonical_count,
        variant_count=variant_count,
        is_special_subset=is_special,
    )

    page = page_snapshot_index.get(set_id, {})
    has_page_snapshot = bool(page.get("has_page_snapshot"))
    has_split_shell_columns = bool(page.get("has_split_shell_columns"))
    has_simulation_snapshot = set_id in simulation_set_ids
    has_pull_rate_assumptions = bool(pull_rate_presence.get(set_id, False))

    pull_rates_cause = classify_pull_rates_root_cause(
        has_page_snapshot=has_page_snapshot,
        has_pull_rate_assumptions=has_pull_rate_assumptions,
        has_simulation_snapshot=has_simulation_snapshot,
        is_special_subset=is_special,
    )
    shell_cause = classify_shell_root_cause(
        has_page_snapshot=has_page_snapshot,
        has_split_shell_columns=has_split_shell_columns,
        has_simulation_snapshot=has_simulation_snapshot,
        is_special_subset=is_special,
    )
    next_action = recommend_next_action(
        top_chase_root_cause=top_chase_cause,
        pull_rates_root_cause=pull_rates_cause,
        shell_root_cause=shell_cause,
    )

    warnings: List[str] = []
    if top_chase_cause == "dashboard_row_wrong_window_key" and history_count == 0:
        warnings.append("top_chase_card_histories_json is also empty despite cards being present")

    return {
        "set_id": set_id,
        "set_name": name,
        "canonical_key": set_row.get("canonical_key"),
        "pokemon_api_set_id": set_row.get("pokemon_api_set_id"),
        "era": set_row.get("era_name") or set_row.get("era"),
        "missing_top_chase": top_chase_cause != "healthy",
        "top_chase_root_cause": top_chase_cause,
        "top_chase_endpoint_repairable_from_365d": is_top_chase_endpoint_repairable_from_365d(top_chase_cause),
        "has_market_dashboard_30d": has_30d,
        "has_market_dashboard_365d": has_365d,
        "top_chase_cards_count": cards_count,
        "top_chase_history_count": history_count,
        "source_observation_count": source_observation_count,
        "canonical_card_count": canonical_count,
        "variant_count": variant_count,
        "missing_pull_rates": pull_rates_cause != "healthy",
        "pull_rates_root_cause": pull_rates_cause,
        "has_pull_rate_source": has_pull_rate_assumptions,
        "has_simulation_snapshot": has_simulation_snapshot,
        "missing_shell": shell_cause != "healthy",
        "shell_root_cause": shell_cause,
        "has_page_snapshot": has_page_snapshot,
        "has_split_shell_columns": has_split_shell_columns,
        "recommended_next_action": next_action,
        "warnings": "; ".join(warnings),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _load_sets(*, limit: Optional[int], set_ids: Optional[List[str]]) -> List[Dict[str, Any]]:
    from backend.db.services.pokemon_sets_catalog_service import get_pokemon_sets_catalog_payload

    catalog = get_pokemon_sets_catalog_payload()
    sets = list(catalog.get("sets") or [])

    if set_ids:
        wanted = {value.strip().lower() for value in set_ids if value.strip()}
        sets = [
            set_row
            for set_row in sets
            if str(set_row.get("id") or "").lower() in wanted
            or str(set_row.get("canonical_key") or "").lower() in wanted
            or str(set_row.get("slug") or "").lower() in wanted
            or str(set_row.get("pokemon_api_set_id") or "").lower() in wanted
        ]

    if limit is not None:
        sets = sets[:limit]

    return sets


def run_diagnosis(*, limit: Optional[int] = None, set_ids: Optional[List[str]] = None, verbose: bool = True) -> List[Dict[str, Any]]:
    assert READ_ONLY_DIAGNOSTIC is True, "This diagnostic must never run with mutations enabled."

    from backend.db.services.pokemon_public_snapshot_service import TOP_CHASE_NEAR_MINT_CONDITION_ID, public_read_client

    sets = _load_sets(limit=limit, set_ids=set_ids)
    total = len(sets)
    if verbose:
        print(f"Loaded {total} sets. Fetching bulk read-only indices...")

    dashboard_index = fetch_market_dashboard_index(public_read_client)
    page_snapshot_index = fetch_page_snapshot_index(public_read_client)
    canonical_counts = fetch_canonical_card_counts(public_read_client)
    variant_counts, variant_ids_by_set = fetch_variant_counts_and_ids(public_read_client)
    simulation_set_ids = fetch_simulation_set_ids(public_read_client)
    pull_rate_presence = fetch_pull_rate_assumptions_presence(
        public_read_client, [set_row["id"] for set_row in sets if set_row.get("id") in page_snapshot_index]
    )

    rows: List[Dict[str, Any]] = []
    for index, set_row in enumerate(sets, start=1):
        started = time.perf_counter()
        row = diagnose_set(
            set_row,
            dashboard_index=dashboard_index,
            page_snapshot_index=page_snapshot_index,
            pull_rate_presence=pull_rate_presence,
            canonical_counts=canonical_counts,
            variant_counts=variant_counts,
            variant_ids_by_set=variant_ids_by_set,
            simulation_set_ids=simulation_set_ids,
            client=public_read_client,
            condition_id=TOP_CHASE_NEAR_MINT_CONDITION_ID,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        rows.append(row)
        if verbose:
            print(f"[{index}/{total}] {row['set_name']} - action={row['recommended_next_action']} - {elapsed_ms}ms")
    return rows


def write_outputs(rows: List[Dict[str, Any]], *, csv_path: Path, json_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, default=str)


def print_summary(rows: List[Dict[str, Any]]) -> None:
    total = len(rows)
    print("\n=== Pokemon set slim-contract completeness diagnosis summary ===")
    print(f"Total sets checked: {total}")

    for label, field in (
        ("Top-chase root causes", "top_chase_root_cause"),
        ("Pull-rates root causes", "pull_rates_root_cause"),
        ("Shell root causes", "shell_root_cause"),
    ):
        print(f"\n{label}:")
        counts: Dict[str, int] = {}
        for row in rows:
            counts[row[field]] = counts.get(row[field], 0) + 1
        for cause, count in sorted(counts.items(), key=lambda item: item[1], reverse=True):
            print(f"  {cause:50s} {count}/{total}")

    print("\nRecommended next actions:")
    action_counts: Dict[str, int] = {}
    for row in rows:
        action_counts[row["recommended_next_action"]] = action_counts.get(row["recommended_next_action"], 0) + 1
    for action, count in sorted(action_counts.items(), key=lambda item: item[1], reverse=True):
        print(f"  {action:50s} {count}/{total}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Root-cause missing/degraded Pokemon slim-contract data (read-only)."
    )
    parser.add_argument("--limit", type=int, default=None, help="Only diagnose the first N sets.")
    parser.add_argument(
        "--set-ids",
        default=None,
        help="Comma-separated set ids/canonical keys/slugs/pokemon_api_set_ids to limit the run to.",
    )
    parser.add_argument(
        "--csv-path",
        default=str(REPO_ROOT / "backend" / "logs" / "pokemon_set_slim_contract_completeness_diagnosis.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--json-path",
        default=str(REPO_ROOT / "backend" / "logs" / "pokemon_set_slim_contract_completeness_diagnosis.json"),
        help="Output JSON path.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress the per-set progress lines.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    set_ids = [value for value in (args.set_ids.split(",") if args.set_ids else [])]

    started = time.perf_counter()
    rows = run_diagnosis(limit=args.limit, set_ids=set_ids or None, verbose=not args.quiet)
    elapsed_s = round(time.perf_counter() - started, 1)

    write_outputs(rows, csv_path=Path(args.csv_path), json_path=Path(args.json_path))
    print_summary(rows)
    print(f"\nWrote {len(rows)} rows to {args.csv_path} and {args.json_path} in {elapsed_s}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
