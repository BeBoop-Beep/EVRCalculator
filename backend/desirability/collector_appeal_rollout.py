"""The single preview/commit core for the Collector Appeal CA7 rollout.

WHY ONE MODULE
--------------
A preview is only trustworthy if it is the same code as the write. Two code
paths - one that reports and one that acts - drift, and the drift is invisible
precisely when it matters, because the preview keeps saying what it always said.

So there is exactly one pipeline:

    load_source_state(client)      # read-only, paginated, VERSION-EXACT
      -> build_update_plan(state)  # classify, cover, compute CA7, diagnose,
                                   # fingerprint, and BUILD THE PAYLOAD
        -> execute_plan(plan, client, commit=False|True)

``execute_plan`` is the **only** function in the codebase that may write these
rows. Dry-run and commit call it with the same already-built plan; the single
difference is the ``commit`` flag deciding whether the payload is handed to
Supabase. Nothing about the payload is recomputed for a write.

THREE DEFECTS THIS MODULE WAS REPAIRED TO PREVENT
-------------------------------------------------
1. **Invalid write identity.** The write was
   ``upsert(payloads, on_conflict="set_id")`` with payloads of
   ``{"set_id", "diagnostics_json"}``. ``set_id`` is not unique in this table -
   several hundred rows span 171 sets - so that conflict target does not exist and the
   payload does not identify a row. An upsert on a non-unique target does not
   update the row you meant; at best it errors, at worst it INSERTS a new row
   with null scores. Replaced by an update against the PRIMARY KEY:
   ``update({...}).eq("id", source_row_id)``, one row at a time, with an
   optimistic-concurrency predicate on ``updated_at``.

2. **Wrong source rows.** See ``component_source``: selection is now
   version-exact, and a set with no exact-version row is unavailable rather than
   silently served from a near-miss row.

3. **An approval token that did not cover what it approved.** The old manifest
   hashed set_id + built_at + score, so the generated payload could change while
   the manifest held still. The manifest now covers every input the payload is
   derived from, and the commit additionally pins the normalized payload hash.

READ-ONLY BY CONSTRUCTION
-------------------------
``load_source_state`` and ``build_update_plan`` take a client wrapped in
:class:`ReadOnlyClientGuard`, which raises on any mutating method. A dry-run
cannot write even by mistake, and the guard's call log is the evidence.

SCOPE OF THE PROPOSED WRITE
---------------------------
One JSONB column, ``diagnostics_json``, on rows that already exist. No score,
count, version or source column is touched; no row is inserted. The computed
value lives at ``diagnostics_json.collector_appeal_ca7`` - namespaced, because
the generic ``collector_appeal`` name already means Pure/Universal Desirability
in production and the two constructs must not share a key.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from backend.desirability.card_links import build_card_input_manifest, card_link_policy
from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_DIAGNOSTICS_KEY,
    COLLECTOR_APPEAL_METRIC_NAME,
    COLLECTOR_APPEAL_PRODUCT_STATUS,
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
from backend.desirability.component_source import (
    COMPONENT_PRIMARY_KEY,
    COMPONENT_SOURCE_COLUMNS,
    COMPONENT_TABLE,
    COMPONENT_UNIQUE_KEY,
    MISSING_CURRENT_COMPONENT_SOURCE_ROW,
    build_component_source_manifest,
    build_source_identity,
    expected_source_versions,
    rebuild_command_for,
    select_component_source_rows,
    source_identity_matches_row,
)
from backend.desirability.product_support import classify_product_support
from backend.desirability.pull_model import build_pull_model_manifest, pull_model_policy
from backend.desirability.rankability import availability
from backend.desirability.universal_set_desirability import (
    COVERAGE_FULL,
    assess_desirability_coverage,
    compute_universal_set_desirability,
)

ROLLOUT_VERSION = "collector_appeal_rollout_v2_exact_row"

# Score columns that this rollout must never touch. Asserted, not assumed.
PROTECTED_SCORE_COLUMNS = (
    "set_desirability_score",
    "chase_subject_strength",
    "chase_subject_depth",
    "accessible_favorite_hits",
    "special_pack_chase_appeal",
)

# The ONLY column the proposed write may contain. Anything else in a payload is
# a bug, and ``_assert_payload_shape`` raises rather than reporting it.
WRITABLE_COLUMNS = ("diagnostics_json",)

MUTATING_METHODS = ("insert", "upsert", "update", "delete", "rpc")


class WriteAttemptedError(RuntimeError):
    """Raised when read-only code touches a mutating client method."""


class StaleSourceRowError(RuntimeError):
    """Raised when a target row moved between the preview and the write."""


class WriteTargetError(RuntimeError):
    """Raised when a write predicate does not identify exactly one row."""


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
    page boundary is the classic way a 511-row table quietly becomes 1000 rows of
    something else, so the page ledger is returned rather than discarded.
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

    Reads EVERY component row - all versions - and then selects the
    version-exact ones. The full read is deliberate: the rows we reject are the
    evidence for WHY a set is unavailable, and a filtered query would leave a
    missing set indistinguishable from a set that does not exist.

    Read-only. The same query in preview and commit, so the preview cannot be
    reading a different world from the write.
    """
    result = paged_select_all(
        client.table(COMPONENT_TABLE).select(COMPONENT_SOURCE_COLUMNS).order("built_at", desc=True),
        page_size=page_size,
    )

    selection = select_component_source_rows(result["rows"])
    pull_model = pull_model_loader(client) if pull_model_loader else {}
    simulation_rows = simulation_loader(client) if simulation_loader else {}

    return {
        "selection": selection,
        "selected_rows": selection["selected"],
        "all_row_count": len(result["rows"]),
        "pagination": result["pagination"],
        "pull_model": pull_model,
        "simulation_rows": simulation_rows,
    }


def build_full_source_manifest(
    source_state: Mapping[str, Any],
    subjects_by_set: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Deterministic hashes of EVERY input the payload is derived from.

    The old manifest hashed set_id + built_at + score. That covers none of the
    subject rollups, coverage diagnostics, card links, composite demand, pull
    probabilities or simulation membership that CA7 actually consumes - so the
    payload could change completely while the approval token stayed valid. An
    approval that cannot detect a change to what it approved is decoration.

    Each component is hashed separately AND rolled into one top-level hash, so a
    mismatch says WHICH input moved rather than only THAT something did.
    """
    component = build_component_source_manifest(source_state.get("selected_rows") or {})
    pull = build_pull_model_manifest(source_state.get("pull_model") or {})
    cards = build_card_input_manifest(subjects_by_set or {})
    cohort = build_simulation_cohort_manifest(source_state.get("simulation_rows") or {})

    parts = {
        "component_rows": component,
        "pull_model": pull,
        "card_inputs": cards,
        "simulation_cohort": cohort,
        "policies": {
            "pull_model": pull_model_policy(),
            "card_links": card_link_policy(),
            "expected_source_versions": expected_source_versions(),
        },
    }
    blob = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return {
        "manifest_hash": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "algorithm": "sha256",
        "parts": parts,
    }


def build_simulation_cohort_manifest(simulation_rows: Mapping[str, Any]) -> Dict[str, Any]:
    """A hash of WHICH sets RIP ranks. Membership only, not their statistics.

    CA7 does not consume RIP's numbers, but the cohort determines which coverage
    gaps matter. A set entering or leaving the leaderboard changes the
    availability report even though no score moved.
    """
    ids = sorted(str(set_id) for set_id in simulation_rows)
    blob = json.dumps(ids, separators=(",", ":"))
    return {
        "cohort_size": len(ids),
        "manifest_hash": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "algorithm": "sha256",
        "set_ids": ids,
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
    subjects_by_set: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Classify, cover, compute CA7, diagnose, fingerprint, and build payloads.

    This is the whole decision. A committed run adds nothing to it.
    """
    expected = current_fingerprint()
    identity = build_collector_appeal_identity()
    selection = source_state["selection"]
    selected = source_state["selected_rows"]
    simulation_rows = source_state.get("simulation_rows") or {}

    pull_model = source_state.get("pull_model") or {}

    rows: List[Dict[str, Any]] = []
    for set_id in sorted(selected, key=str):
        rows.append(
            _plan_row(
                set_id=set_id,
                row=selected[set_id],
                identity=identity,
                expected_fingerprint=expected,
                subjects=(subject_builder(set_id) if subject_builder else None),
                rip_consumes=set_id in simulation_rows,
                pull_modeled=set_id in pull_model,
            )
        )

    # Sets with no exact-version row are UNAVAILABLE, never planned. They are
    # still CLASSIFIED and reported, so the catalogue totals stay whole: a set
    # that drops out of the plan must not also drop out of the census, or the
    # report answers "how many products are there?" with "however many we could
    # process today".
    unavailable_sources = []
    for entry in selection["missing"]:
        support = classify_product_support(
            set_canonical_key=entry.get("set_canonical_key"), set_name=entry.get("set_name")
        )
        unavailable_sources.append(
            {
                **entry,
                "product_support_type": support["product_support_type"],
                "booster_supported": support["supported"],
                "rip_consumes_row": entry["set_id"] in simulation_rows,
                "rebuild_command": rebuild_command_for(entry["set_id"], entry.get("set_name")),
            }
        )

    updates = [row for row in rows if row["would_update"]]
    _assert_no_score_changes(updates)
    _assert_payload_shape(updates)
    _assert_source_identity_agreement(rows, selected)

    manifest = build_full_source_manifest(source_state, subjects_by_set)

    plan = {
        "version": ROLLOUT_VERSION,
        "expected_fingerprint": expected,
        "collector_appeal_identity": identity,
        "source_contract": {
            "expected_versions": expected_source_versions(),
            "unique_key": list(COMPONENT_UNIQUE_KEY),
            "primary_key": COMPONENT_PRIMARY_KEY,
            "version_distribution": selection["version_distribution"],
            "counts": selection["counts"],
        },
        "source_manifest": manifest,
        "rows": rows,
        "updates": updates,
        "unavailable_sources": unavailable_sources,
        "duplicate_sources": selection["duplicates"],
        "write_strategy": describe_write_strategy(),
    }
    plan["counts"] = _plan_counts(rows, updates, unavailable_sources, simulation_rows)
    plan["normalized_payload_hash"] = normalized_payload_hash(plan)
    return plan


def _plan_row(
    *,
    set_id: str,
    row: Mapping[str, Any],
    identity: Mapping[str, Any],
    expected_fingerprint: str,
    subjects: Optional[Sequence[Mapping[str, Any]]],
    rip_consumes: bool,
    pull_modeled: bool = False,
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
        # These two reasons are kept apart because they call for different
        # fixes. "No pack model exists for this set" is a data-coverage gap;
        # "a pack model exists but no desirable subject matched it" is a
        # JOIN failure - a rarity key that does not map, or hit-eligible cards
        # with no desirability link. Reporting the second as the first sends
        # someone to build a pull model that is already there.
        unavailable_reason = (
            "dual_path_depth_unavailable_no_modeled_subject"
            if pull_modeled
            else "dual_path_depth_unavailable_no_pull_model"
        )

    if collector_appeal is None and unavailable_reason is None:
        warnings.append("collector_appeal_ca7 is None with no recorded reason")

    # --- proposed diagnostics ------------------------------------------
    # The block declares WHAT it is before it declares any number: a reader that
    # finds this in production must not have to infer whether it is the public
    # Collector Appeal (it is not).
    source_identity = build_source_identity(row)
    appeal_block: Dict[str, Any] = {
        "metric_name": COLLECTOR_APPEAL_METRIC_NAME,
        "product_status": COLLECTOR_APPEAL_PRODUCT_STATUS,
        "formula": "CA7",
        "not_the_public_collector_appeal_score": (
            "The public collector_appeal_score field is Pure/Universal "
            "Desirability, a different construct. This block is an internal "
            "candidate and is not served by any API or frontend contract."
        ),
    }
    appeal_block.update(identity)
    appeal_block["source_identity"] = source_identity
    appeal_block["value"] = round(collector_appeal, 6) if collector_appeal is not None else None
    appeal_block["available"] = collector_appeal is not None
    appeal_block["unavailable_reason"] = unavailable_reason
    appeal_block["inputs"] = {
        "roster_desirability_d": d_raw,
        "dual_path_depth_p": round(p_value, 6) if p_value is not None else None,
    }

    proposed_diagnostics = copy.deepcopy(current_diagnostics)
    proposed_diagnostics[COLLECTOR_APPEAL_DIAGNOSTICS_KEY] = appeal_block

    current_status = fingerprint_status(row, expected=expected_fingerprint)

    changed_fields = _diff_diagnostics(current_diagnostics, proposed_diagnostics, current_status)
    would_update = bool(changed_fields)

    stored_score = row.get("set_desirability_score")
    if support["supported"] and _to_float(stored_score) == 0.0:
        warnings.append("booster-supported product has a stored score of 0.0")
    if not support["supported"] and rip_consumes:
        warnings.append("unsupported product appears in the ranked simulation cohort")

    return {
        "set_id": set_id,
        "source_row_id": source_identity["component_row_id"],
        "source_updated_at": source_identity["updated_at"],
        "source_identity": source_identity,
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
        "proposed_fingerprint_status": FINGERPRINT_CURRENT,
        "would_update": would_update,
        "changed_fields": changed_fields,
        "diagnostics_only": all(
            field["field"].startswith("diagnostics_json") for field in changed_fields
        ),
        "current_diagnostics": current_diagnostics,
        "proposed_diagnostics": proposed_diagnostics,
        "rip_consumes_row": rip_consumes,
        "validation_warnings": warnings,
        # The payload is the SET clause only. The row is identified by primary
        # key in the predicate, never by a column inside the payload.
        "update_payload": ({"diagnostics_json": proposed_diagnostics} if would_update else None),
        "update_target": (
            {
                "id": source_identity["component_row_id"],
                "expected_updated_at": source_identity["updated_at"],
            }
            if would_update
            else None
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
        if key == COLLECTOR_APPEAL_DIAGNOSTICS_KEY:
            reason = {
                FINGERPRINT_MISSING: "Collector Appeal CA7 has never been computed for this row.",
            }.get(fp_status, "Stored Collector Appeal CA7 was computed under a different formula fingerprint.")
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


def _assert_payload_shape(updates: Sequence[Mapping[str, Any]]) -> None:
    """Every update must be one diagnostics column against one primary key.

    Catches the whole class of defect the old ``on_conflict="set_id"`` upsert
    belonged to: a payload carrying identity columns, or a target with no row ID,
    cannot address exactly one row.
    """
    for row in updates:
        payload = row.get("update_payload") or {}
        extra = set(payload) - set(WRITABLE_COLUMNS)
        if extra:
            raise AssertionError(
                f"update payload for {row['set_id']} carries non-writable columns {sorted(extra)}; "
                f"only {list(WRITABLE_COLUMNS)} may be written"
            )
        target = row.get("update_target") or {}
        if not target.get("id"):
            raise AssertionError(
                f"update target for {row['set_id']} has no source row ID - a write "
                "cannot be addressed by set_id, which is not unique in this table"
            )


def _assert_source_identity_agreement(
    rows: Sequence[Mapping[str, Any]], selected: Mapping[str, Mapping[str, Any]]
) -> None:
    """Every block's source identity must describe the row it will be stored on.

    THE invariant behind blocker #2. A v1 component row must never receive
    diagnostics certifying v2 coverage-cleanup inputs.
    """
    expected = expected_source_versions()
    for row in rows:
        source_row = selected.get(row["set_id"])
        if source_row is None:
            raise AssertionError(f"planned row {row['set_id']} has no selected source row")
        identity = row["source_identity"]
        if not source_identity_matches_row(identity, source_row):
            raise AssertionError(
                f"source identity for {row['set_id']} does not describe its source row"
            )
        for field, value in expected.items():
            if identity.get(field) != value:
                raise AssertionError(
                    f"source row for {row['set_id']} carries {field}={identity.get(field)!r} "
                    f"but the formula identity represents {value!r} - refusing to certify "
                    "inputs the row was not built under"
                )


def _plan_counts(
    rows: Sequence[Mapping[str, Any]],
    updates: Sequence[Mapping[str, Any]],
    unavailable_sources: Sequence[Mapping[str, Any]],
    simulation_rows: Mapping[str, Any],
) -> Dict[str, Any]:
    rip_consumed = [row for row in rows if row["rip_consumes_row"]]
    rip_available = [row for row in rip_consumed if row["collector_appeal_available"]]
    rip_unavailable = [row for row in rip_consumed if not row["collector_appeal_available"]]
    rip_missing_source = [entry for entry in unavailable_sources if entry.get("rip_consumes_row")]

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
        # --- exact-version source contract ------------------------------
        "exact_version_source_rows_available": len(rows),
        "exact_version_source_rows_missing": len(unavailable_sources),
        # --- RIP coverage (CA7, not Universal Desirability) --------------
        "rip_consumed_total": len(simulation_rows),
        "rip_consumed_collector_appeal_available": len(rip_available),
        "rip_consumed_collector_appeal_unavailable": len(rip_unavailable) + len(rip_missing_source),
        "rip_consumed_rows": len(rip_consumed),
        "rows_with_warnings": sum(1 for row in rows if row["validation_warnings"]),
    }


def rip_consumed_coverage(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """The exact CA7 availability split across the RIP-consumed cohort.

    Reported separately from Universal Desirability coverage because they are
    different facts: a set can have full Desirability coverage and no CA7 at all
    (no modeled pull data -> no Dual-Path Depth). Conflating them is what let a
    "ranked cohort fully covered" invariant pass while only 21 of 33 ranked sets
    could produce a CA7 value.
    """
    available: List[Dict[str, Any]] = []
    unavailable: List[Dict[str, Any]] = []
    for row in plan["rows"]:
        if not row["rip_consumes_row"]:
            continue
        entry = {
            "set_id": row["set_id"],
            "set_name": row["set_name"],
            "set_canonical_key": row["set_canonical_key"],
            "collector_appeal_ca7": row["collector_appeal_value"],
        }
        if row["collector_appeal_available"]:
            available.append(entry)
        else:
            unavailable.append({**entry, "reason": row["collector_appeal_unavailable_reason"]})

    for entry in plan.get("unavailable_sources") or []:
        if entry.get("rip_consumes_row"):
            unavailable.append(
                {
                    "set_id": entry["set_id"],
                    "set_name": entry.get("set_name"),
                    "set_canonical_key": entry.get("set_canonical_key"),
                    "collector_appeal_ca7": None,
                    "reason": MISSING_CURRENT_COMPONENT_SOURCE_ROW,
                }
            )

    return {
        "rip_consumed_total": plan["counts"]["rip_consumed_total"],
        "available": sorted(available, key=lambda entry: str(entry["set_name"] or entry["set_id"])),
        "unavailable": sorted(unavailable, key=lambda entry: str(entry["set_name"] or entry["set_id"])),
        "available_count": len(available),
        "unavailable_count": len(unavailable),
    }


def normalized_payload_hash(plan: Mapping[str, Any]) -> str:
    """Hash of the exact writes, normalized so two runs are comparable.

    Covers the TARGET as well as the payload: two plans that write identical
    diagnostics to different rows are not the same plan, and a hash that could
    not tell them apart would approve the wrong write.
    """
    entries = sorted(
        (
            {
                "id": (row["update_target"] or {}).get("id"),
                "expected_updated_at": (row["update_target"] or {}).get("expected_updated_at"),
                "payload": row["update_payload"],
            }
            for row in plan["rows"]
            if row["would_update"]
        ),
        key=lambda entry: str(entry["id"]),
    )
    blob = json.dumps(entries, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Cross-run determinism
# ---------------------------------------------------------------------------

# The verdicts a cross-run comparison can reach. Named so a caller branches on a
# constant rather than on a prose string.
DETERMINISM_IDENTICAL = "identical"
DETERMINISM_SOURCE_DRIFT = "source_drift"
DETERMINISM_NONDETERMINISTIC = "nondeterministic"
DETERMINISM_FORMULA_CHANGED = "formula_identity_changed"

# Fields that are EXPECTED to differ between two runs and are therefore excluded
# from every hash. If one of these ever reached hashed content, two runs of an
# unchanged source would disagree and determinism would be unprovable.
VOLATILE_ARTIFACT_FIELDS: Sequence[str] = ("generated_at",)


def compare_dry_run_artifacts(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compare two INDEPENDENTLY generated dry-run artifacts.

    This is a different question from invariant 17. That one builds the plan
    twice inside ONE process from ONE in-memory source read: it proves the build
    is a pure function of what was already loaded. It cannot see a fresh process,
    a fresh connection, a fresh read, or dict/JSON ordering that happens to be
    stable within a single interpreter. Only two separate runs test that, and
    Phase 8.1 never ran them - it reported the in-process check and left the
    cross-run one unexecuted, which is why this exists.

    The verdict deliberately separates two failures that look identical if you
    only compare payload hashes:

    * the SOURCE moved between runs (someone rebuilt a row) - the code is fine,
      and a changed source manifest is the correct, honest response;
    * the source held still and the payload moved anyway - that is real
      nondeterminism and a blocker.

    Collapsing those into "hashes differ" is how a genuine nondeterminism bug
    gets waved through as "the database probably changed".
    """
    fingerprint_match = previous.get("expected_fingerprint") == current.get("expected_fingerprint")
    manifest_match = _manifest_hash(previous) == _manifest_hash(current)
    payload_match = previous.get("normalized_payload_hash") == current.get("normalized_payload_hash")

    part_hashes = _compare_manifest_parts(previous, current)
    drifted_parts = sorted(name for name, entry in part_hashes.items() if not entry["match"])

    # Ordering/serialization: the write targets, in the order the artifact lists
    # them. Two runs that select the same rows but emit them in a different order
    # are not deterministic, even if the set of rows is equal.
    previous_targets = _artifact_targets(previous)
    current_targets = _artifact_targets(current)
    ordering_match = previous_targets == current_targets

    counts_match = previous.get("counts") == current.get("counts")

    if not fingerprint_match:
        verdict = DETERMINISM_FORMULA_CHANGED
    elif manifest_match and payload_match and ordering_match and counts_match:
        verdict = DETERMINISM_IDENTICAL
    elif not manifest_match:
        verdict = DETERMINISM_SOURCE_DRIFT
    else:
        # Source identical, output moved. Nothing else can explain this.
        verdict = DETERMINISM_NONDETERMINISTIC

    return {
        "verdict": verdict,
        "deterministic": verdict == DETERMINISM_IDENTICAL,
        "comparison_kind": "independent_cross_run",
        "checks": {
            "formula_fingerprint": {
                "match": fingerprint_match,
                "previous": previous.get("expected_fingerprint"),
                "current": current.get("expected_fingerprint"),
            },
            "source_manifest": {
                "match": manifest_match,
                "previous": _manifest_hash(previous),
                "current": _manifest_hash(current),
            },
            "normalized_payload_hash": {
                "match": payload_match,
                "previous": previous.get("normalized_payload_hash"),
                "current": current.get("normalized_payload_hash"),
            },
            "component_manifest_parts": part_hashes,
            "row_ordering_and_serialization": {
                "match": ordering_match,
                "previous_target_count": len(previous_targets),
                "current_target_count": len(current_targets),
            },
            "counts": {"match": counts_match},
        },
        "drifted_manifest_parts": drifted_parts,
        "volatile_fields_excluded_from_hashes": list(VOLATILE_ARTIFACT_FIELDS),
        "volatile_fields_observed_differing": sorted(
            field for field in VOLATILE_ARTIFACT_FIELDS
            if previous.get(field) != current.get(field)
        ),
        "interpretation": _determinism_interpretation(verdict, drifted_parts),
    }


def _determinism_interpretation(verdict: str, drifted_parts: Sequence[str]) -> str:
    if verdict == DETERMINISM_IDENTICAL:
        return (
            "Two independent runs of an unchanged source produced byte-identical "
            "hashes. Wall-clock metadata differed and did not reach hashed content."
        )
    if verdict == DETERMINISM_SOURCE_DRIFT:
        return (
            "The source manifest moved between runs "
            f"(parts: {', '.join(drifted_parts) or 'unknown'}). The inputs changed; "
            "a changed payload is the correct response, not evidence of nondeterminism."
        )
    if verdict == DETERMINISM_FORMULA_CHANGED:
        return "The formula fingerprint moved between runs. The calculation's identity is not stable."
    return (
        "The source manifest is IDENTICAL and the payload moved anyway. This is "
        "real nondeterminism in the build or serialization, and it is a blocker."
    )


def _manifest_hash(artifact: Mapping[str, Any]) -> Optional[str]:
    return (artifact.get("source_manifest") or {}).get("manifest_hash")


def _compare_manifest_parts(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> Dict[str, Dict[str, Any]]:
    previous_parts = ((previous.get("source_manifest") or {}).get("parts") or {})
    current_parts = ((current.get("source_manifest") or {}).get("parts") or {})
    names = sorted(set(previous_parts) | set(current_parts))
    compared: Dict[str, Dict[str, Any]] = {}
    for name in names:
        previous_hash = _part_hash(previous_parts.get(name))
        current_hash = _part_hash(current_parts.get(name))
        if previous_hash is None and current_hash is None:
            continue  # a policy block, not a hashed part
        compared[name] = {
            "match": previous_hash == current_hash,
            "previous": previous_hash,
            "current": current_hash,
        }
    return compared


def _part_hash(part: Any) -> Optional[str]:
    return part.get("manifest_hash") if isinstance(part, Mapping) else None


def _artifact_targets(artifact: Mapping[str, Any]) -> List[Any]:
    """Write targets in ARTIFACT ORDER - deliberately not re-sorted.

    Sorting here would hide exactly the defect this check exists to catch: a run
    that emits the same rows in a different order.
    """
    return [
        (row.get("update_target") or {}).get("id")
        for row in (artifact.get("products") or [])
        if row.get("would_update")
    ]


def describe_write_strategy() -> Dict[str, Any]:
    """The write this plan proposes, stated exactly. Never executed here."""
    return {
        "method": "update",
        "predicate": f"{COMPONENT_PRIMARY_KEY} = <source_row_id> AND updated_at = <expected_updated_at>",
        "statement": (
            f'client.table("{COMPONENT_TABLE}")'
            '.update({"diagnostics_json": proposed_diagnostics})'
            f'.eq("{COMPONENT_PRIMARY_KEY}", source_row_id)'
            '.eq("updated_at", expected_updated_at).execute()'
        ),
        "writable_columns": list(WRITABLE_COLUMNS),
        "rows_per_statement": 1,
        "inserts": "none - the row must already exist",
        "upsert": (
            "FORBIDDEN. set_id is not unique in this table (several rows per set), "
            "so on_conflict=\"set_id\" names no constraint and cannot identify a row."
        ),
        "concurrency": (
            "optimistic: updated_at is pinned in the predicate, so a row that moved "
            "since the preview matches zero rows and fails instead of overwriting."
        ),
        "zero_rows_returned": "fails - the target vanished or moved",
        "multiple_rows_returned": "fails - the predicate was not unique",
        "idempotent": (
            "yes - a second run re-reads state, finds the fingerprint current, and "
            "plans zero updates"
        ),
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
    expected_payload_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Send the plan's payload, or don't. That flag is the entire difference.

    A commit is refused unless the caller supplies the fingerprint, the source
    manifest AND the normalized payload hash it approved, and all three still
    match after the plan was rebuilt from freshly read state. Approval is for a
    specific set of changes against a specific state - not for whatever is in the
    table now.

    Each row is written by PRIMARY KEY, one statement at a time, with its
    expected ``updated_at`` in the predicate. Batching was removed with the
    upsert: a batch cannot carry a per-row concurrency token, and a partial batch
    failure cannot report which rows landed.
    """
    targets = [
        {"set_id": row["set_id"], "target": row["update_target"], "payload": row["update_payload"]}
        for row in plan["rows"]
        if row["would_update"]
    ]

    if not commit:
        return {
            "committed": False,
            "writes_performed": 0,
            "rows_targeted": len(targets),
            "target_set_ids": sorted(entry["set_id"] for entry in targets),
            "target_row_ids": sorted(str(entry["target"]["id"]) for entry in targets),
            "updated_row_ids": [],
            "failures": [],
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
    if expected_payload_hash is None or expected_payload_hash != normalized_payload_hash(plan):
        raise RuntimeError(
            "Refusing to commit: the rebuilt payload does not match the approved payload hash."
        )

    updated_row_ids: List[str] = []
    failures: List[Dict[str, Any]] = []
    for entry in targets:
        target = entry["target"]
        row_id = target["id"]
        if not row_id:
            failures.append({"set_id": entry["set_id"], "error": "missing source row id"})
            continue
        try:
            response = (
                client.table(COMPONENT_TABLE)
                .update(entry["payload"])
                .eq(COMPONENT_PRIMARY_KEY, row_id)
                .eq("updated_at", target["expected_updated_at"])
                .execute()
            )
        except Exception as error:  # noqa: BLE001 - reported per row, never swallowed
            failures.append({"set_id": entry["set_id"], "row_id": str(row_id), "error": str(error)})
            continue

        returned = list(getattr(response, "data", None) or [])
        if len(returned) == 0:
            failures.append(
                {
                    "set_id": entry["set_id"],
                    "row_id": str(row_id),
                    "error": "stale_or_missing_row",
                    "detail": (
                        "zero rows matched id + expected updated_at; the row moved since "
                        "the preview. Re-run the preview and re-approve."
                    ),
                }
            )
            continue
        if len(returned) > 1:
            # Cannot happen against a primary key - which is exactly why it is
            # checked. If it ever fires, the predicate is not what we think.
            failures.append(
                {
                    "set_id": entry["set_id"],
                    "row_id": str(row_id),
                    "error": "non_unique_write_predicate",
                    "detail": f"{len(returned)} rows matched a primary-key predicate",
                }
            )
            continue
        updated_row_ids.append(str(row_id))

    result = {
        "committed": True,
        "writes_performed": len(updated_row_ids),
        "rows_targeted": len(targets),
        "target_set_ids": sorted(entry["set_id"] for entry in targets),
        "target_row_ids": sorted(str(entry["target"]["id"]) for entry in targets),
        "updated_row_ids": sorted(updated_row_ids),
        "failures": failures,
        "partial": bool(failures) and bool(updated_row_ids),
    }
    if failures:
        raise PartialWriteError(result)
    return result


class PartialWriteError(RuntimeError):
    """Raised when any targeted row failed, carrying the exact rows that landed.

    A partial write is not an error to be retried blindly: some rows changed and
    some did not, and the operator needs the exact IDs of both. The result dict
    is attached rather than summarized into a message.
    """

    def __init__(self, result: Mapping[str, Any]) -> None:
        self.result = dict(result)
        super().__init__(
            f"partial write: {result['writes_performed']}/{result['rows_targeted']} rows updated; "
            f"updated_row_ids={result['updated_row_ids']}; failures={result['failures']}"
        )


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
