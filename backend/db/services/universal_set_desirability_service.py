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
from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.db.clients.supabase_client import public_read_client
from backend.desirability.scoring_config import UNIVERSAL_SET_DESIRABILITY_VERSION
from backend.desirability.set_components import SCORING_VERSION as V2_SCORING_VERSION
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

_cache_lock = threading.Lock()
_cache: Dict[str, Any] = {"built_at": 0.0, "payloads": None, "setValueAssociation": None}


def _to_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _paged_select(query: Any, *, page_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        response = query.range(start, start + page_size - 1).execute()
        page_rows = list(response.data or [])
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
        start += page_size
    return rows


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _load_latest_v2_rows() -> Dict[str, Dict[str, Any]]:
    rows = _paged_select(
        public_read_client.table("pokemon_set_desirability_component_scores")
        .select(
            "set_id,set_name,set_canonical_key,scoring_version,set_desirability_score,"
            "hit_eligible_card_count,scored_hit_eligible_card_count,unique_subject_count,"
            "subject_rollups_json,diagnostics_json,built_at"
        )
        .order("built_at", desc=True)
    )
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        set_id = str(row.get("set_id") or "")
        if not set_id:
            continue
        kept = latest.get(set_id)
        if kept is None:
            latest[set_id] = row
        elif row.get("scoring_version") == V2_SCORING_VERSION and kept.get("scoring_version") != V2_SCORING_VERSION:
            latest[set_id] = row
    return latest


def _load_latest_set_values(set_ids: Sequence[str]) -> Dict[str, float]:
    latest: Dict[str, float] = {}
    for chunk in _chunked(sorted(set_ids), 50):
        try:
            rows = (
                public_read_client.table("pokemon_set_value_daily_history")
                .select("set_id,snapshot_date,set_value")
                .in_("set_id", list(chunk))
                .eq("value_scope", SET_VALUE_SCOPE)
                .order("snapshot_date", desc=True)
                .limit(len(chunk) * 45)
                .execute()
            )
        except Exception as exc:
            logger.warning("[universal-desirability] set value load failed: %s", exc)
            return latest
        for row in rows.data or []:
            set_id = str(row.get("set_id") or "")
            value = _to_optional_float(row.get("set_value"))
            if set_id and set_id not in latest and value is not None and value > 0:
                latest[set_id] = value
    return latest


def _build_payloads() -> Dict[str, Any]:
    v2_rows = _load_latest_v2_rows()
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
                "effective_subject_count": (
                    (v3["component_inputs"].get("chase_subject_depth") or {}).get("effective_subject_count")
                ),
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
    return {"payloads": payloads, "setValueAssociation": association}


def get_universal_desirability_bundle(*, force_refresh: bool = False) -> Dict[str, Any]:
    """Return ``{"payloads": {set_id: payload}, "setValueAssociation": ...}`` (cached).

    ``setValueAssociation`` is descriptive context only; it never changes any
    score or weight.
    """
    now = time.time()
    with _cache_lock:
        if (
            not force_refresh
            and _cache["payloads"] is not None
            and now - _cache["built_at"] < CACHE_TTL_SECONDS
        ):
            return {"payloads": _cache["payloads"], "setValueAssociation": _cache["setValueAssociation"]}
    try:
        bundle = _build_payloads()
    except Exception:
        logger.exception("[universal-desirability] failed to build v3 payloads")
        with _cache_lock:
            if _cache["payloads"] is not None:
                return {"payloads": _cache["payloads"], "setValueAssociation": _cache["setValueAssociation"]}
        return {"payloads": {}, "setValueAssociation": None}
    with _cache_lock:
        _cache["payloads"] = bundle["payloads"]
        _cache["setValueAssociation"] = bundle["setValueAssociation"]
        _cache["built_at"] = now
    logger.info(
        "[universal-desirability] built %s payloads (version=%s) set_value_association_spearman=%s (diagnostic only)",
        len(bundle["payloads"]),
        UNIVERSAL_SET_DESIRABILITY_VERSION,
        (bundle["setValueAssociation"] or {}).get("spearman"),
    )
    return bundle


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
        "topSubjects": row.get("top_subjects"),
        "distinctEligibleSubjectCount": row.get("distinct_eligible_subject_count"),
        "effectiveSubjectCount": row.get("effective_subject_count"),
        # Descriptive market-association context. Deliberately no
        # "cleared/blocked" flag: this correlation never gates the score.
        "setValueAssociation": association,
        "setValueCorrelation": (association or {}).get("spearman"),
        "coverage": coverage,
    }
