"""Universal Set Desirability v3 service layer.

Computes the price-independent Universal Set Desirability v3 payload for every
set from the persisted V2 subject rollups, together with the two independent
coverage axes and the Phase 7 set-value gate. Results are cached in-process:
inputs only change when the V2 component builder or the daily set-value
snapshot runs, so a long TTL is safe.

NOTE (migration): this computes v3 at read time from
``pokemon_set_desirability_component_scores``. Once a persistence pass is
approved, these rows should be precomputed into their own snapshot table and
this module becomes a thin reader. The payload shape is already final.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, TypeVar

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.public_read_retry import run_batch_read_with_retry
from backend.desirability.component_source import (
    COMPONENT_TABLE,
    DUPLICATE_CURRENT_COMPONENT_SOURCE_ROW,
    MISSING_CURRENT_COMPONENT_SOURCE_ROW,
    expected_source_versions,
    select_component_source_rows,
    selector_columns,
)
from backend.desirability.scoring_config import UNIVERSAL_SET_DESIRABILITY_VERSION
from backend.desirability.universal_set_desirability import (
    COVERAGE_FULL,
    assess_desirability_coverage,
    compute_universal_set_desirability,
    rank_universal_scores,
)
from backend.desirability.weighted_rip import evaluate_set_value_association, spearman

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 6 * 60 * 60
SET_VALUE_SCOPE = "standard"

# `subject_rollups_json` averages ~12 kB and the table holds ~6.4 MB of it. The
# PostgREST role runs under an 8s statement_timeout, and a COLD read of all 171
# current rows measured ~35s against production (the same read is ~10ms once the
# pages are in the buffer cache) - the cost is detoasting on a throttled volume,
# not the query plan. Selecting every row's JSONB in one request therefore could
# not finish inside the timeout, which is why the reader failed as 57014 rather
# than returning rows.
#
# So the read is split: the SELECTION runs on identity/scalar columns only (no
# TOAST, whole table, cheap), and only the rows the contract actually selects are
# hydrated with their JSONB, in chunks small enough to finish cold inside the
# timeout. Chunk size is deliberately conservative: ~200ms/row cold means 15 rows
# is ~3s, leaving headroom under 8s.
COMPONENT_HYDRATION_CHUNK_SIZE = 15
READ_MAX_ATTEMPTS = 4

# Whether the bundle was BUILT, not whether any set scored. See
# `get_universal_desirability_bundle` on why the two must stay distinguishable.
STATUS_OK = "ok"
STATUS_FAILED = "failed"

T = TypeVar("T")

_cache_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "built_at": 0.0,
    "payloads": None,
    "setValueAssociation": None,
    "sourceSelection": None,
}


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _read_with_retry(operation: Callable[[], T], *, operation_name: str) -> T:
    return run_batch_read_with_retry(
        operation, operation_name=operation_name, max_attempts=READ_MAX_ATTEMPTS
    )


def _paged_select(query_factory: Callable[[], Any], *, page_size: int = 1000) -> List[Dict[str, Any]]:
    """Page through a read, retrying each page independently.

    ``query_factory`` is called per attempt because a PostgREST builder carries
    the range it was last given; reusing one across a retry would re-issue the
    wrong window.
    """
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        offset = start
        page_rows = _read_with_retry(
            lambda offset=offset: list(
                (query_factory().range(offset, offset + page_size - 1).execute()).data or []
            ),
            operation_name=f"{COMPONENT_TABLE}.page[{offset}]",
        )
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        start += page_size
    return rows


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _load_current_component_rows() -> Dict[str, Any]:
    """The VERSION-EXACT component row per set, through the shared contract.

    This function used to be ``_load_latest_v2_rows`` and took the newest row per
    set by ``built_at``, preferring ``scoring_version`` only as a tiebreak. That
    matched three rows deep in the wrong place: the table is keyed on
    ``(set_id, scoring_version, hit_policy_version, composite_scoring_version,
    fan_popularity_snapshot_id, config_fingerprint)``, and ``scoring_version``
    agreeing says nothing about the other two. In production TODAY the newest row
    for 170 of 171 sets carries ``hit_policy_version = ..._v1`` while the code
    computes ``..._v2_coverage_cleanup`` - so the PUBLIC score was being computed
    from v1 inputs for all but one set. Recency is not agreement; it was the
    same defect Phase 8.1 repaired for CA7, still live on the public reader.

    The expected versions are NOT restated here. They are read through
    :mod:`backend.desirability.component_source`, which reads them from the
    modules that define them, so this reader cannot drift from what CA7 selects.
    """
    rows = _paged_select(
        lambda: (
            public_read_client.table(COMPONENT_TABLE)
            .select(
                selector_columns(
                    "set_desirability_score",
                    "hit_eligible_card_count",
                    "scored_hit_eligible_card_count",
                    "unique_subject_count",
                )
            )
            # Ordered only so the read is stable and paginates deterministically.
            # Selection does NOT depend on this order - that was the bug.
            .order("built_at", desc=True)
            .order("id", desc=False)
        )
    )
    # Selection runs on the light rows. It reads only version/identity columns, so
    # dropping the JSONB from this read cannot change which row is selected, which
    # sets are missing, or which are duplicated - the diagnostics below are the
    # same ones the single-read version produced.
    selection = select_component_source_rows(rows)
    hydrated = _hydrate_selected_rows(selection["selected"])
    # `exact_version_rows_found` counts what the CONTRACT selected; a row that was
    # selected but could not be hydrated is reported separately rather than
    # silently shrinking the selection count, so the two numbers disagreeing is
    # itself the signal.
    selection["counts"]["rows_hydrated"] = len(hydrated)
    selection["counts"]["selected_rows_not_hydrated"] = len(selection["selected"]) - len(hydrated)
    selection["selected"] = hydrated

    # A set with more than one exact-version row is an integrity error, not a
    # choice to make here: the duplicates differ in fan_popularity_snapshot_id or
    # config_fingerprint, so picking one would silently pick an input set. The
    # shared selector already withholds them from ``selected``; this makes the
    # withholding loud instead of merely quiet.
    for entry in selection["duplicates"]:
        logger.error(
            "[universal-desirability] INTEGRITY: %s (%s) has %s exact-version component rows; "
            "serving it is refused until exactly one remains. rows=%s",
            entry["set_name"], entry["set_id"], entry["row_count"],
            [row["id"] for row in entry["rows"]],
        )
    # Missing is reported, never back-filled from a near-version row.
    for entry in selection["missing"]:
        logger.warning(
            "[universal-desirability] %s (%s): %s - has %s. Reported unavailable.",
            entry["set_name"], entry["set_id"], entry["reason"],
            [version["hit_policy_version"] for version in entry["available_versions"]],
        )
    return selection


def _depth_input(v3: Mapping[str, Any], key: str) -> Any:
    return ((v3.get("component_inputs") or {}).get("chase_subject_depth") or {}).get(key)


def _hydrate_selected_rows(
    selected: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Attach ``subject_rollups_json``/``diagnostics_json`` to the selected rows.

    Fetched by primary key in small chunks, so the heavy TOAST read is scoped to
    the rows that were actually selected (171 of 512 today) and each request
    stays inside the statement timeout even with a cold cache.

    A row whose JSONB cannot be fetched is DROPPED, not served with empty
    rollups: ``compute_universal_set_desirability([])`` returns a real-looking
    0.0, so substituting an empty list would publish a fabricated score for a set
    whose inputs simply were not read. Dropping it makes the set absent from
    ``payloads``, which the API already renders as unavailable.
    """
    row_ids = sorted(str(row.get("id")) for row in selected.values() if row.get("id"))
    heavy_by_id: Dict[str, Mapping[str, Any]] = {}
    for chunk in _chunked(row_ids, COMPONENT_HYDRATION_CHUNK_SIZE):
        ids = list(chunk)
        fetched = _read_with_retry(
            lambda ids=ids: list(
                (
                    public_read_client.table(COMPONENT_TABLE)
                    .select("id,subject_rollups_json,diagnostics_json")
                    .in_("id", ids)
                    .execute()
                ).data
                or []
            ),
            operation_name=f"{COMPONENT_TABLE}.hydrate[{len(ids)}]",
        )
        for row in fetched:
            heavy_by_id[str(row.get("id"))] = row

    hydrated: Dict[str, Dict[str, Any]] = {}
    for set_id, row in selected.items():
        heavy = heavy_by_id.get(str(row.get("id")))
        if heavy is None:
            logger.error(
                "[universal-desirability] %s (%s): selected row %s could not be hydrated; "
                "withheld rather than scored from empty rollups.",
                row.get("set_name"), set_id, row.get("id"),
            )
            continue
        merged = dict(row)
        merged["subject_rollups_json"] = heavy.get("subject_rollups_json")
        merged["diagnostics_json"] = heavy.get("diagnostics_json")
        hydrated[set_id] = merged
    return hydrated


def _load_latest_set_values(set_ids: Sequence[str]) -> Dict[str, float]:
    """Latest set value per set, for the DIAGNOSTIC market association only.

    Chunked at 20 (x45 days = 900 rows/request) and retried, because the wider
    50-set chunk asked for 2250 ordered rows and exceeded the statement timeout.
    A failed chunk is skipped rather than abandoning the whole load: this feeds a
    descriptive correlation that gates nothing, so a partial sample degrades the
    diagnostic instead of the scores.
    """
    latest: Dict[str, float] = {}
    for chunk in _chunked(sorted(set_ids), 20):
        ids = list(chunk)
        try:
            rows = _read_with_retry(
                lambda ids=ids: list(
                    (
                        public_read_client.table("pokemon_set_value_daily_history")
                        .select("set_id,snapshot_date,set_value")
                        .in_("set_id", ids)
                        .eq("value_scope", SET_VALUE_SCOPE)
                        .order("snapshot_date", desc=True)
                        .limit(len(ids) * 45)
                        .execute()
                    ).data
                    or []
                ),
                operation_name=f"pokemon_set_value_daily_history[{len(ids)}]",
            )
        except Exception as exc:
            logger.warning("[universal-desirability] set value chunk failed, skipped: %s", exc)
            continue
        for row in rows:
            set_id = str(row.get("set_id") or "")
            value = _to_optional_float(row.get("set_value"))
            if set_id and set_id not in latest and value is not None and value > 0:
                latest[set_id] = value
    return latest


def _build_payloads() -> Dict[str, Any]:
    selection = _load_current_component_rows()
    v2_rows = selection["selected"]
    computed: List[Dict[str, Any]] = []
    for set_id, v2_row in v2_rows.items():
        diagnostics = v2_row.get("diagnostics_json") or {}
        coverage_audit = diagnostics.get("coverage_audit") or {}
        link_counts = diagnostics.get("hit_link_category_counts") or {}
        v3 = compute_universal_set_desirability(v2_row.get("subject_rollups_json") or [])
        coverage = assess_desirability_coverage(
            canonical_card_count=coverage_audit.get("canonical_card_count") or diagnostics.get("canonical_cards_seen"),
            hit_eligible_card_count=v2_row.get("hit_eligible_card_count"),
            scored_hit_eligible_card_count=v2_row.get("scored_hit_eligible_card_count"),
            unique_subject_count=v2_row.get("unique_subject_count"),
            unmatched_pokemon_hit_count=link_counts.get("unmatched_pokemon_hit_count"),
            true_missing_link_count=link_counts.get("true_missing_link_count"),
        )
        computed.append(
            {
                "set_id": set_id,
                "set_name": v2_row.get("set_name"),
                "set_canonical_key": v2_row.get("set_canonical_key"),
                "score": v3["score"],
                "components": v3["components"],
                "component_weights": v3["component_weights"],
                "weights_label": v3["weights_label"],
                "top_subjects": v3["top_subjects"],
                "distinct_eligible_subject_count": v3["distinct_eligible_subject_count"],
                # The compact depth diagnostics only. The raw rollups behind them
                # are megabytes and stay server-side; a public payload carries the
                # summary, never the inputs.
                "effective_subject_count": _depth_input(v3, "effective_subject_count"),
                "top1_share": _depth_input(v3, "top1_share"),
                "top3_share": _depth_input(v3, "top3_share"),
                "favorite_hit_coverage_raw": v3.get("favorite_hit_coverage_raw"),
                "version": v3["version"],
                "eligibility_policy_version": v3["eligibility_policy_version"],
                "coverage": coverage,
                "as_of": v2_row.get("built_at"),
                "prior_v2_score": _to_optional_float(v2_row.get("set_desirability_score")),
            }
        )

    full_rows = [row for row in computed if row["coverage"]["status"] == COVERAGE_FULL]
    rank_universal_scores(full_rows)

    set_values = _load_latest_set_values([row["set_id"] for row in full_rows])
    association_rows = [
        {"score": row["score"], "set_value": set_values.get(row["set_id"])}
        for row in full_rows
        if set_values.get(row["set_id"]) is not None
    ]
    prior_pairs = [
        (row["prior_v2_score"], set_values.get(row["set_id"]))
        for row in full_rows
        if row.get("prior_v2_score") is not None and set_values.get(row["set_id"]) is not None
    ]
    prior_rho = spearman([pair[0] for pair in prior_pairs], [pair[1] for pair in prior_pairs])
    association = evaluate_set_value_association(
        association_rows,
        prior_benchmark_spearman=round(prior_rho, 4) if prior_rho is not None else None,
    )

    payloads = {row["set_id"]: row for row in computed}
    return {
        "status": STATUS_OK,
        "payloads": payloads,
        "setValueAssociation": association,
        "sourceSelection": _source_selection_diagnostics(selection),
    }


def _source_selection_diagnostics(selection: Mapping[str, Any]) -> Dict[str, Any]:
    """Which rows powered this bundle, and which sets were refused and why.

    Internal diagnostics: deliberately NOT part of ``public_payload`` and not
    served by any API or frontend field. A set that is absent from ``payloads``
    is absent because it had no exact-version row or had several - and this says
    which, so "unavailable" can be diagnosed without re-querying.
    """
    return {
        "contract_version": selection["contract_version"],
        "expected_versions": expected_source_versions(),
        "counts": dict(selection["counts"]),
        "missing": [
            {
                "set_id": entry["set_id"],
                "set_name": entry["set_name"],
                "reason": MISSING_CURRENT_COMPONENT_SOURCE_ROW,
                "available_hit_policy_versions": [
                    version["hit_policy_version"] for version in entry["available_versions"]
                ],
            }
            for entry in selection["missing"]
        ],
        "duplicates": [
            {
                "set_id": entry["set_id"],
                "set_name": entry["set_name"],
                "reason": DUPLICATE_CURRENT_COMPONENT_SOURCE_ROW,
                "row_count": entry["row_count"],
            }
            for entry in selection["duplicates"]
        ],
    }


def _cached_bundle() -> Dict[str, Any]:
    return {
        "status": STATUS_OK,
        "payloads": _cache["payloads"],
        "setValueAssociation": _cache["setValueAssociation"],
        "sourceSelection": _cache["sourceSelection"],
    }


def get_universal_desirability_bundle(*, force_refresh: bool = False) -> Dict[str, Any]:
    """Return ``{"status", "payloads", "setValueAssociation", "sourceSelection"}``.

    ``setValueAssociation`` is descriptive context only; it never changes any
    score or weight. ``sourceSelection`` is internal diagnostics describing which
    component rows were selected and which sets were refused; no public field
    reads it.

    ``status`` distinguishes the two ways ``payloads`` can be empty, which the
    caller MUST NOT conflate: ``ok`` means the source was read and genuinely
    yielded nothing, while ``failed`` means the source was not read at all. They
    are the same value and opposite facts. Publishing a ``failed`` build renders
    every set "desirability unavailable" - a statement about the sets - when the
    truth is that a query timed out, which is exactly how the empty payload
    reached production.
    """
    now = time.time()
    with _cache_lock:
        if (
            not force_refresh
            and _cache["payloads"] is not None
            and now - _cache["built_at"] < CACHE_TTL_SECONDS
        ):
            return _cached_bundle()
    try:
        bundle = _build_payloads()
    except Exception:
        logger.exception("[universal-desirability] failed to build v3 payloads")
        with _cache_lock:
            if _cache["payloads"] is not None:
                return _cached_bundle()
        return {
            "status": STATUS_FAILED,
            "payloads": {},
            "setValueAssociation": None,
            "sourceSelection": None,
        }
    with _cache_lock:
        _cache["payloads"] = bundle["payloads"]
        _cache["setValueAssociation"] = bundle["setValueAssociation"]
        _cache["sourceSelection"] = bundle["sourceSelection"]
        _cache["built_at"] = now
    counts = (bundle["sourceSelection"] or {}).get("counts") or {}
    logger.info(
        "[universal-desirability] built %s payloads (version=%s) from %s exact-version rows "
        "(scanned=%s missing=%s duplicates=%s) set_value_association_spearman=%s (diagnostic only)",
        len(bundle["payloads"]),
        UNIVERSAL_SET_DESIRABILITY_VERSION,
        counts.get("exact_version_rows_found"),
        counts.get("rows_scanned"),
        counts.get("sets_missing_exact_version_row"),
        counts.get("sets_with_duplicate_exact_version_rows"),
        (bundle["setValueAssociation"] or {}).get("spearman"),
    )
    return bundle


PUBLIC_TOP_SUBJECT_LIMIT = 5


def _compact_top_subjects(subjects: Any) -> List[Dict[str, Any]]:
    """The few fields the UI renders, for the few subjects it shows.

    The stored rollups carry every subject with its full provenance. Shipping
    that to a browser is how a public payload becomes megabytes; the page draws
    a short "why this score" list, so that is what the contract carries.
    """
    rows = subjects if isinstance(subjects, list) else []
    compact: List[Dict[str, Any]] = []
    for subject in rows[:PUBLIC_TOP_SUBJECT_LIMIT]:
        if not isinstance(subject, Mapping):
            continue
        compact.append(
            {
                "subjectName": subject.get("subject_name"),
                "subjectDemand": subject.get("subject_demand"),
                "cardCount": subject.get("card_count"),
                "representativeCardName": subject.get("representative_card_name"),
                "bestRarityBucket": subject.get("best_rarity_bucket"),
                "slotWeight": subject.get("slot_weight"),
                "weightedContribution": subject.get("weighted_contribution"),
            }
        )
    return compact


def public_payload(row: Optional[Dict[str, Any]], association: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Shape one set's universal desirability for the public API."""
    if not isinstance(row, dict):
        return None
    coverage = row.get("coverage") or {}
    return {
        "score": row.get("score"),
        "rank": row.get("rank"),
        "percentile": row.get("percentile"),
        "rankedSetCount": row.get("ranked_set_count"),
        "version": row.get("version"),
        "eligibilityPolicyVersion": row.get("eligibility_policy_version"),
        "asOf": row.get("as_of"),
        "components": row.get("components"),
        "componentWeights": row.get("component_weights"),
        "weightsLabel": row.get("weights_label"),
        "topSubjects": _compact_top_subjects(row.get("top_subjects")),
        "distinctEligibleSubjectCount": row.get("distinct_eligible_subject_count"),
        "effectiveSubjectCount": row.get("effective_subject_count"),
        "top1Share": row.get("top1_share"),
        "top3Share": row.get("top3_share"),
        "favoriteHitCoverageRaw": row.get("favorite_hit_coverage_raw"),
        # Descriptive market-association context. Deliberately no
        # "cleared/blocked" flag: this correlation never gates the score.
        "setValueAssociation": association,
        "setValueCorrelation": (association or {}).get("spearman"),
        "coverage": coverage,
    }
