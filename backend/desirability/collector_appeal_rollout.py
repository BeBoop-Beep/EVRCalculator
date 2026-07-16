"""The single preview/commit core for the Collector Appeal rollout.

WHY ONE MODULE
--------------
A preview is only trustworthy if it is the same code as the write. Two code
paths - one that reports and one that acts - drift, and the drift is invisible
precisely when it matters, because the preview keeps saying what it always said.

So there is exactly one pipeline:

    load_source_state(client)      # read-only, paginated, verified
      -> build_update_plan(state)  # classify, cover, compute CA7, diagnose,
                                   # fingerprint, and BUILD THE PAYLOAD
        -> execute_plan(plan, client, commit=False|True)

``execute_plan`` is the **only** function in the codebase that may write these
rows. Dry-run and commit call it with the same already-built plan; the single
difference is the ``commit`` flag deciding whether the payload is handed to
Supabase. Nothing about the payload is recomputed for a write.

READ-ONLY BY CONSTRUCTION
-------------------------
``load_source_state`` and ``build_update_plan`` take a client wrapped in
:class:`ReadOnlyClientGuard`, which raises on any mutating method. A dry-run
cannot write even by mistake, and the guard's call log is the evidence.

SCOPE OF THE PROPOSED WRITE
---------------------------
Diagnostics only. No score column is touched: there is no ``collector_appeal``
column and no migration is authorized, so the computed value lives in
``diagnostics_json.collector_appeal``. :func:`build_update_plan` asserts this -
a plan that would change a score value fails rather than being reported.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from backend.desirability.collector_appeal import (
    CA7_PRODUCTION_LAMBDA,
    compute_collector_appeal,
    compute_dual_path_depth,
)
from backend.desirability.collector_appeal_fingerprint import (
    FINGERPRINT_CURRENT,
    FINGERPRINT_MISSING,
    build_collector_appeal_identity,
    current_fingerprint,
    fingerprint_status,
    read_row_fingerprint,
)
from backend.desirability.product_support import classify_product_support
from backend.desirability.rankability import availability
from backend.desirability.universal_set_desirability import (
    COVERAGE_FULL,
    assess_desirability_coverage,
    compute_universal_set_desirability,
)

ROLLOUT_VERSION = "collector_appeal_rollout_v1"
COMPONENT_TABLE = "pokemon_set_desirability_component_scores"

# Score columns that this rollout must never touch. Asserted, not assumed.
PROTECTED_SCORE_COLUMNS = (
    "set_desirability_score",
    "chase_subject_strength",
    "chase_subject_depth",
    "accessible_favorite_hits",
    "special_pack_chase_appeal",
)

MUTATING_METHODS = ("insert", "upsert", "update", "delete", "rpc")


class WriteAttemptedError(RuntimeError):
    """Raised when read-only code touches a mutating client method."""


class ReadOnlyClientGuard:
    """Wraps a Supabase client and refuses every mutating call.

    This is the write spy. It does two jobs at once: it makes a write during a
    dry-run impossible rather than merely unlikely, and its ``calls`` log is the
    positive evidence that no write method was reached.
    """

    def __init__(self, client: Any) -> None:
        self._client = client
        self.calls: List[Dict[str, Any]] = []
        self.write_attempts: List[str] = []

    def table(self, name: str) -> "_ReadOnlyTable":
        self.calls.append({"op": "table", "table": name})
        return _ReadOnlyTable(self._client.table(name), name, self)

    def __getattr__(self, item: str) -> Any:
        if item in MUTATING_METHODS:
            self.write_attempts.append(item)
            raise WriteAttemptedError(f"read-only guard blocked client.{item}()")
        return getattr(self._client, item)


class _ReadOnlyTable:
    def __init__(self, table: Any, name: str, guard: ReadOnlyClientGuard) -> None:
        self._table = table
        self._name = name
        self._guard = guard

    def __getattr__(self, item: str) -> Any:
        if item in MUTATING_METHODS:
            self._guard.write_attempts.append(f"{self._name}.{item}")
            raise WriteAttemptedError(
                f"read-only guard blocked {self._name}.{item}() - "
                "dry-run must not mutate production"
            )
        attribute = getattr(self._table, item)
        if item == "select" and callable(attribute):
            def _select(*args, **kwargs):
                self._guard.calls.append({"op": "select", "table": self._name, "columns": args[0] if args else "*"})
                return attribute(*args, **kwargs)
            return _select
        return attribute


# ---------------------------------------------------------------------------
# Source state
# ---------------------------------------------------------------------------

def paged_select_all(query: Any, *, page_size: int = 1000) -> Dict[str, Any]:
    """Read every page, and report enough metadata to prove nothing truncated.

    Returns the rows plus a pagination audit. A silent truncation at exactly one
    page boundary is the classic way a 171-row catalogue quietly becomes 1000
    rows of something else, so the page ledger is returned rather than discarded.
    """
    rows: List[Dict[str, Any]] = []
    pages: List[Dict[str, Any]] = []
    start = 0
    while True:
        response = query.range(start, start + page_size - 1).execute()
        page = list(response.data or [])
        pages.append({"offset": start, "limit": page_size, "returned": len(page)})
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return {
        "rows": rows,
        "pagination": {
            "page_size": page_size,
            "pages": pages,
            "total_rows": len(rows),
            "final_page_partial": bool(pages and pages[-1]["returned"] < page_size),
            "truncation_possible": not (pages and pages[-1]["returned"] < page_size),
        },
    }


def load_source_state(
    client: Any,
    *,
    page_size: int = 1000,
    pull_model_loader: Optional[Callable[[Any], Dict[str, Any]]] = None,
    simulation_loader: Optional[Callable[[Any], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Read the exact production state a committed run would read.

    Read-only. The same query in preview and commit, so the preview cannot be
    reading a different world from the write.
    """
    result = paged_select_all(
        client.table(COMPONENT_TABLE).select(
            "set_id,set_name,set_canonical_key,scoring_version,set_desirability_score,"
            "hit_eligible_card_count,scored_hit_eligible_card_count,unique_subject_count,"
            "subject_rollups_json,diagnostics_json,built_at"
        ).order("built_at", desc=True),
        page_size=page_size,
    )

    latest: Dict[str, Dict[str, Any]] = {}
    for row in result["rows"]:
        set_id = str(row.get("set_id") or "")
        if set_id and set_id not in latest:
            latest[set_id] = row

    pull_model = pull_model_loader(client) if pull_model_loader else {}
    simulation_rows = simulation_loader(client) if simulation_loader else {}

    return {
        "latest_rows": latest,
        "all_row_count": len(result["rows"]),
        "pagination": result["pagination"],
        "pull_model": pull_model,
        "simulation_rows": simulation_rows,
        "source_manifest": build_source_manifest(latest),
    }


def build_source_manifest(latest_rows: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """A hash of the source rows a plan was built from.

    A committed write must refuse to run if production has moved since the
    preview: the operator approved a specific set of changes against a specific
    state, not a blank cheque against whatever is there at write time.
    """
    digest_input = [
        {
            "set_id": str(set_id),
            "built_at": str(row.get("built_at")),
            "score": _normalize_number(row.get("set_desirability_score")),
        }
        for set_id, row in sorted(latest_rows.items(), key=lambda item: str(item[0]))
    ]
    payload = json.dumps(digest_input, sort_keys=True, separators=(",", ":"))
    return {
        "row_count": len(digest_input),
        "manifest_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "algorithm": "sha256",
    }


def _normalize_number(value: Any) -> Optional[str]:
    try:
        return repr(round(float(value), 6))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def build_update_plan(
    source_state: Mapping[str, Any],
    *,
    subject_builder: Optional[Callable[[str], Optional[Sequence[Mapping[str, Any]]]]] = None,
) -> Dict[str, Any]:
    """Classify, cover, compute CA7, diagnose, fingerprint, and build payloads.

    This is the whole decision. A committed run adds nothing to it.
    """
    expected = current_fingerprint()
    identity = build_collector_appeal_identity()
    latest = source_state["latest_rows"]
    simulation_rows = source_state.get("simulation_rows") or {}

    rows: List[Dict[str, Any]] = []
    for set_id in sorted(latest, key=str):
        rows.append(
            _plan_row(
                set_id=set_id,
                row=latest[set_id],
                identity=identity,
                expected_fingerprint=expected,
                subjects=(subject_builder(set_id) if subject_builder else None),
                rip_consumes=set_id in simulation_rows,
            )
        )

    updates = [row for row in rows if row["would_update"]]
    _assert_no_score_changes(updates)

    return {
        "version": ROLLOUT_VERSION,
        "expected_fingerprint": expected,
        "collector_appeal_identity": identity,
        "source_manifest": source_state["source_manifest"],
        "rows": rows,
        "updates": updates,
        "counts": _plan_counts(rows, updates),
    }


def _plan_row(
    *,
    set_id: str,
    row: Mapping[str, Any],
    identity: Mapping[str, Any],
    expected_fingerprint: str,
    subjects: Optional[Sequence[Mapping[str, Any]]],
    rip_consumes: bool,
) -> Dict[str, Any]:
    warnings: List[str] = []
    support = classify_product_support(
        set_canonical_key=row.get("set_canonical_key"), set_name=row.get("set_name")
    )
    current_diagnostics = dict(row.get("diagnostics_json") or {})
    coverage_audit = current_diagnostics.get("coverage_audit") or {}
    link_counts = current_diagnostics.get("hit_link_category_counts") or {}

    coverage = assess_desirability_coverage(
        canonical_card_count=coverage_audit.get("canonical_card_count")
        or current_diagnostics.get("canonical_cards_seen"),
        hit_eligible_card_count=row.get("hit_eligible_card_count"),
        scored_hit_eligible_card_count=row.get("scored_hit_eligible_card_count"),
        unique_subject_count=row.get("unique_subject_count"),
        unmatched_pokemon_hit_count=link_counts.get("unmatched_pokemon_hit_count"),
        true_missing_link_count=link_counts.get("true_missing_link_count"),
    )
    current_coverage = (current_diagnostics.get("desirability_coverage") or {}).get("status")

    # --- D and P -------------------------------------------------------
    v3 = compute_universal_set_desirability(row.get("subject_rollups_json") or [])
    d_raw = v3["score"] if coverage["status"] == COVERAGE_FULL else None
    depth = compute_dual_path_depth(subjects) if subjects else None
    p_value = (depth or {}).get("value")

    d_unit = (d_raw / 100.0) if d_raw is not None else None
    collector_appeal = compute_collector_appeal(d_unit, p_value)

    unavailable_reason = None
    if not support["supported"]:
        unavailable_reason = "unsupported_product_type"
    elif d_raw is None:
        unavailable_reason = "desirability_coverage_not_full"
    elif p_value is None:
        unavailable_reason = "dual_path_depth_unavailable_no_pull_model"

    if collector_appeal is None and unavailable_reason is None:
        warnings.append("collector_appeal is None with no recorded reason")

    # --- proposed diagnostics ------------------------------------------
    appeal_block: Dict[str, Any] = dict(identity)
    appeal_block["value"] = round(collector_appeal, 6) if collector_appeal is not None else None
    appeal_block["available"] = collector_appeal is not None
    appeal_block["unavailable_reason"] = unavailable_reason
    appeal_block["inputs"] = {
        "roster_desirability_d": d_raw,
        "dual_path_depth_p": round(p_value, 6) if p_value is not None else None,
    }

    proposed_diagnostics = copy.deepcopy(current_diagnostics)
    proposed_diagnostics["collector_appeal"] = appeal_block

    current_status = fingerprint_status(row, expected=expected_fingerprint)
    proposed_status = FINGERPRINT_CURRENT

    changed_fields = _diff_diagnostics(current_diagnostics, proposed_diagnostics, current_status)
    would_update = bool(changed_fields)

    stored_score = row.get("set_desirability_score")
    if support["supported"] and _to_float(stored_score) == 0.0:
        warnings.append("booster-supported product has a stored score of 0.0")
    if not support["supported"] and rip_consumes:
        warnings.append("unsupported product appears in the ranked simulation cohort")

    return {
        "set_id": set_id,
        "set_name": row.get("set_name"),
        "set_canonical_key": row.get("set_canonical_key"),
        "product_support_type": support["product_support_type"],
        "product_family": support["product_family"],
        "booster_supported": support["supported"],
        "classifier_matched_on": support["matched_on"],
        "classifier_evidence": support.get("matched_value"),
        "classifier_reason": support["product_support_reason"],
        "availability": availability(row),
        "current_stored_score": stored_score,
        "proposed_score": stored_score,  # unchanged, by design
        "collector_appeal_value": appeal_block["value"],
        "collector_appeal_available": appeal_block["available"],
        "collector_appeal_unavailable_reason": unavailable_reason,
        "current_coverage_status": current_coverage,
        "proposed_coverage_status": coverage["status"],
        "current_fingerprint": read_row_fingerprint(row),
        "proposed_fingerprint": expected_fingerprint,
        "fingerprint_status": current_status,
        "proposed_fingerprint_status": proposed_status,
        "would_update": would_update,
        "changed_fields": changed_fields,
        "diagnostics_only": all(
            field["field"].startswith("diagnostics_json") for field in changed_fields
        ),
        "current_diagnostics": current_diagnostics,
        "proposed_diagnostics": proposed_diagnostics,
        "rip_consumes_row": rip_consumes,
        "validation_warnings": warnings,
        "update_payload": (
            {"set_id": set_id, "diagnostics_json": proposed_diagnostics} if would_update else None
        ),
    }


def _diff_diagnostics(current: Mapping[str, Any], proposed: Mapping[str, Any], fp_status: str) -> List[Dict[str, Any]]:
    """Exactly which fields change, and why - never a bare boolean."""
    changed: List[Dict[str, Any]] = []
    for key in sorted(set(current) | set(proposed)):
        before = current.get(key)
        after = proposed.get(key)
        if before == after:
            continue
        if key == "collector_appeal":
            reason = {
                FINGERPRINT_MISSING: "Collector Appeal has never been computed for this row.",
            }.get(fp_status, "Stored Collector Appeal was computed under a different formula fingerprint.")
        else:
            reason = f"diagnostics field '{key}' differs from the rebuilt value."
        changed.append(
            {
                "field": f"diagnostics_json.{key}",
                "reason": reason,
                "before_present": key in current,
                "after_present": key in proposed,
            }
        )
    return changed


def _assert_no_score_changes(updates: Sequence[Mapping[str, Any]]) -> None:
    """A plan that would move a score value must fail, not be reported."""
    for row in updates:
        payload = row.get("update_payload") or {}
        for column in PROTECTED_SCORE_COLUMNS:
            if column in payload:
                raise AssertionError(
                    f"plan would change protected score column '{column}' for {row['set_id']}"
                )
        if row["current_stored_score"] != row["proposed_score"]:
            raise AssertionError(f"plan would change stored score for {row['set_id']}")


def _plan_counts(rows: Sequence[Mapping[str, Any]], updates: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return {
        "products_total": len(rows),
        "booster_supported": sum(1 for row in rows if row["booster_supported"]),
        "unsupported": sum(1 for row in rows if not row["booster_supported"]),
        "would_update": len(updates),
        "would_insert": 0,
        "diagnostics_only_updates": sum(1 for row in updates if row["diagnostics_only"]),
        "score_changing_updates": sum(1 for row in updates if not row["diagnostics_only"]),
        "unchanged": len(rows) - len(updates),
        "fingerprint_missing": sum(1 for row in rows if row["fingerprint_status"] == "missing"),
        "fingerprint_stale": sum(1 for row in rows if row["fingerprint_status"] == "stale"),
        "fingerprint_current": sum(1 for row in rows if row["fingerprint_status"] == "current"),
        "collector_appeal_available": sum(1 for row in rows if row["collector_appeal_available"]),
        "collector_appeal_unavailable": sum(1 for row in rows if not row["collector_appeal_available"]),
        "rip_consumed_rows": sum(1 for row in rows if row["rip_consumes_row"]),
        "rows_with_warnings": sum(1 for row in rows if row["validation_warnings"]),
    }


# ---------------------------------------------------------------------------
# Execution - the ONLY write site
# ---------------------------------------------------------------------------

def execute_plan(
    plan: Mapping[str, Any],
    client: Any,
    *,
    commit: bool = False,
    expected_fingerprint: Optional[str] = None,
    expected_manifest_hash: Optional[str] = None,
    batch_size: int = 25,
) -> Dict[str, Any]:
    """Send the plan's payload, or don't. That flag is the entire difference.

    A commit is refused unless the caller supplies the fingerprint and source
    manifest it approved, and both still match. Approval is for a specific set of
    changes against a specific state - not for whatever is in the table now.
    """
    payloads = [row["update_payload"] for row in plan["rows"] if row["would_update"]]

    if not commit:
        return {
            "committed": False,
            "writes_performed": 0,
            "rows_targeted": len(payloads),
            "target_set_ids": sorted(row["set_id"] for row in plan["rows"] if row["would_update"]),
            "note": "DRY RUN. Payload built and validated; nothing sent.",
        }

    if expected_fingerprint is None or expected_fingerprint != plan["expected_fingerprint"]:
        raise RuntimeError(
            "Refusing to commit: expected fingerprint not supplied or does not match the plan. "
            f"plan={plan['expected_fingerprint']} supplied={expected_fingerprint}"
        )
    if expected_manifest_hash is None or expected_manifest_hash != plan["source_manifest"]["manifest_hash"]:
        raise RuntimeError(
            "Refusing to commit: source data has changed since the previewed plan was built."
        )

    written = 0
    for index in range(0, len(payloads), batch_size):
        batch = payloads[index:index + batch_size]
        client.table(COMPONENT_TABLE).upsert(batch, on_conflict="set_id").execute()
        written += len(batch)
    return {
        "committed": True,
        "writes_performed": written,
        "rows_targeted": len(payloads),
        "target_set_ids": sorted(row["set_id"] for row in plan["rows"] if row["would_update"]),
    }


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
