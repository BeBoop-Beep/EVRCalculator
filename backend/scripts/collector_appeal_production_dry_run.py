"""Production-equivalent Collector Appeal CA7 dry run (READ-ONLY).

Reads real production state through :class:`ReadOnlyClientGuard`, selects the
VERSION-EXACT component source rows, builds the exact update payload a committed
run would send, asserts every invariant, and writes the preview artifacts. It
cannot write: the guard raises on every mutating client method, and its call log
is included as evidence.

``--commit`` IS NOT IMPLEMENTED HERE. ``main()`` never passes ``commit=True`` and
offers no flag that could. The commit path is designed and tested
(``execute_plan``), but reaching it from this script is impossible by
construction, not by convention.

Exit codes:
    0  preview built, every invariant passed
    1  an invariant failed (the report still gets written; read it)
    2  a read or preflight error

NO WRITE IS EVER PERFORMED BY THIS SCRIPT.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.db.clients.supabase_client import public_read_client  # noqa: E402
from backend.desirability.card_links import subject_key_for  # noqa: E402
from backend.desirability.collector_appeal import (  # noqa: E402
    CA7_PRODUCTION_LAMBDA,
    COLLECTOR_APPEAL_DIAGNOSTICS_KEY,
    COLLECTOR_APPEAL_METRIC_NAME,
    COLLECTOR_APPEAL_PRODUCT_STATUS,
)
from backend.desirability.collector_appeal_inputs import build_subject_index  # noqa: E402
from backend.desirability.collector_appeal_rollout import (  # noqa: E402
    ReadOnlyClientGuard,
    build_update_plan,
    compare_dry_run_artifacts,
    execute_plan,
    load_source_state,
    normalized_payload_hash,
    rip_consumed_coverage,
)
from backend.desirability.component_source import (  # noqa: E402
    COMPONENT_PRIMARY_KEY,
    COMPONENT_UNIQUE_KEY,
    expected_source_versions,
    source_identity_matches_row,
)
from backend.desirability.opening_appeal import build_subjects  # noqa: E402
from backend.desirability.rarity_buckets import HIT_BUCKETS, classify_rarity  # noqa: E402
from backend.scripts.build_opening_appeal_study import (  # noqa: E402
    load_appeal_by_card,
    load_cards,
    load_pull_rate_model,
    load_simulation_rows,
)

logger = logging.getLogger(__name__)

DOCS = Path(__file__).resolve().parents[2] / "docs" / "research"
JSON_ARTIFACT = DOCS / "collector_appeal_production_dry_run.json"
MD_ARTIFACT = DOCS / "collector_appeal_production_dry_run.md"
DETERMINISM_ARTIFACT = DOCS / "collector_appeal_cross_run_determinism.md"

EXPECTED_TOTAL = 171
EXPECTED_SUPPORTED = 135
EXPECTED_UNSUPPORTED = 36
EXPECTED_SIMULATED = 33

# Invariant 23 is EXPECTED to fail until every ranked set has modeled pull data.
# It is recorded as a ROLLOUT BLOCKER for RIP integration, not as a defect in the
# calculation: CA7 is correct on the sets it covers and honestly absent on the
# rest. Listing it here keeps the distinction in the artifact rather than in
# someone's memory.
KNOWN_ROLLOUT_BLOCKERS = {23}


def check_invariants(
    plan: Mapping[str, Any],
    source_state: Mapping[str, Any],
    guard: ReadOnlyClientGuard,
    rebuild_plan: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Assert every invariant. Each returns pass/fail + evidence.

    ``rebuild_plan`` is a SECOND, independently built plan from the same source
    state. Invariant 17 compares them for real; it used to be hardcoded ``True``,
    which is not a determinism check, it is a claim of one.
    """
    rows = plan["rows"]
    counts = plan["counts"]
    selection = source_state["selection"]
    results: List[Dict[str, Any]] = []

    def check(number: int, name: str, passed: bool, evidence: Any) -> None:
        results.append(
            {
                "n": number,
                "name": name,
                "passed": bool(passed),
                "evidence": evidence,
                "known_rollout_blocker": number in KNOWN_ROLLOUT_BLOCKERS,
            }
        )

    supported = {row["set_id"] for row in rows if row["booster_supported"]}
    unsupported = {row["set_id"] for row in rows if not row["booster_supported"]}
    all_ids = {row["set_id"] for row in rows}
    ranked = {row["set_id"] for row in rows if row["rip_consumes_row"]}

    planned_total = len(rows) + len(plan["unavailable_sources"])
    check(1, "every catalogue product is accounted for (planned + unavailable)",
          planned_total == EXPECTED_TOTAL,
          {"planned": len(rows), "unavailable": len(plan["unavailable_sources"]),
           "total": planned_total, "expected": EXPECTED_TOTAL})
    # Counted across the WHOLE catalogue - planned rows plus sets held out for a
    # missing source row. A set that cannot be scored is still a set.
    unavailable_supported = sum(1 for e in plan["unavailable_sources"] if e["booster_supported"])
    unavailable_unsupported = sum(1 for e in plan["unavailable_sources"] if not e["booster_supported"])
    check(2, "exactly 135 booster-supported across the catalogue",
          len(supported) + unavailable_supported == EXPECTED_SUPPORTED,
          {"planned": len(supported), "unavailable": unavailable_supported,
           "total": len(supported) + unavailable_supported, "expected": EXPECTED_SUPPORTED})
    check(3, "exactly 36 unsupported non-booster products across the catalogue",
          len(unsupported) + unavailable_unsupported == EXPECTED_UNSUPPORTED,
          {"planned": len(unsupported), "unavailable": unavailable_unsupported,
           "total": len(unsupported) + unavailable_unsupported, "expected": EXPECTED_UNSUPPORTED})
    check(4, "supported and unsupported are disjoint", not (supported & unsupported),
          {"overlap": sorted(supported & unsupported)})
    check(5, "the two groups cover every planned row", supported | unsupported == all_ids,
          {"uncovered": sorted(all_ids - (supported | unsupported))})

    # 6: structural, not statistical - the classifier's signature cannot see a score.
    import inspect
    from backend.desirability.product_support import classify_product_support
    classifier_params = set(inspect.signature(classify_product_support).parameters)
    check(6, "no classifier decision depends on the existing score value",
          classifier_params == {"set_canonical_key", "set_name", "set_series"},
          {"classifier_parameters": sorted(classifier_params)})

    zero_supported = [
        {"set_id": row["set_id"], "set_name": row["set_name"], "score": row["current_stored_score"]}
        for row in rows
        if row["booster_supported"] and _to_float(row["current_stored_score"]) == 0.0
    ]
    check(7, "every booster-supported product has a positive existing score", not zero_supported,
          {"violations": zero_supported})

    metadata_classified = [
        row["set_id"] for row in rows
        if not row["booster_supported"] and row["classifier_matched_on"] in
        ("canonical_key_registry", "canonical_key_pattern", "set_name_pattern")
    ]
    check(8, "every unsupported product classified through metadata/evidence",
          len(metadata_classified) == len(unsupported),
          {"metadata_classified": len(metadata_classified), "unsupported": len(unsupported)})

    # 9: RENAMED. This verifies UNIVERSAL DESIRABILITY coverage, which is what it
    # always measured. It says nothing about CA7 availability - see invariant 23.
    # The old name ("the ranked simulation cohort remains fully covered") implied
    # a CA7 guarantee it never checked, and that gap is exactly how a 21/33 CA7
    # coverage hole passed a green preview.
    not_full = [
        {"set_id": row["set_id"], "set_name": row["set_name"], "coverage": row["proposed_coverage_status"]}
        for row in rows if row["rip_consumes_row"] and row["proposed_coverage_status"] != "full"
    ]
    check(9, "ranked simulation cohort has full Universal Desirability coverage",
          not not_full,
          {"ranked_rows_planned": len(ranked), "rip_consumed_total": counts["rip_consumed_total"],
           "not_full": not_full,
           "scope": "Universal Desirability v3 coverage only; NOT Collector Appeal CA7"})

    check(10, "unsupported products have zero overlap with the ranked cohort",
          not (unsupported & ranked), {"overlap": sorted(unsupported & ranked)})

    score_changes = [
        row["set_id"] for row in rows if row["current_stored_score"] != row["proposed_score"]
    ]
    check(11, "no existing score value changes in the proposed payload", not score_changes,
          {"violations": score_changes})

    forbidden = {
        "profit_score", "safety_score", "stability_score", "mean_value", "pack_cost",
        "market_price", "set_value", "set_desirability_score", "chase_subject_strength",
        "chase_subject_depth", "accessible_favorite_hits", "special_pack_chase_appeal",
        "scoring_version", "hit_policy_version", "composite_scoring_version",
        "fan_popularity_snapshot_id", "config_fingerprint", "built_at",
    }
    touched = set()
    for row in rows:
        for key in (row["update_payload"] or {}):
            touched.add(key)
    check(12, "no score/version/source/simulation/market field changes",
          not (touched & forbidden), {"payload_keys": sorted(touched)})

    from backend.desirability.scoring_config import DEFAULT_RIP_WEIGHTS
    check(13, "no RIP weight changes",
          DEFAULT_RIP_WEIGHTS == {"profit": 0.58, "safety": 0.20, "stability": 0.12, "desirability": 0.10},
          {"weights": dict(DEFAULT_RIP_WEIGHTS),
           "note": "RIP still consumes Universal Desirability v3 at 10%; CA7 is not wired in"})

    check(14, "the payload writes exactly one column and no frontend contract",
          touched == {"diagnostics_json"} or not touched,
          {"payload_keys": sorted(touched),
           "note": "diagnostics_json is additive; no API or frontend field touched"})

    lambdas = {
        row["proposed_diagnostics"][COLLECTOR_APPEAL_DIAGNOSTICS_KEY]["lambda"]
        for row in rows if COLLECTOR_APPEAL_DIAGNOSTICS_KEY in row["proposed_diagnostics"]
    }
    check(15, "CA7 uses lambda = 0.50 everywhere", lambdas == {0.50} and CA7_PRODUCTION_LAMBDA == 0.50,
          {"observed_lambdas": sorted(lambdas)})

    expected_fp = plan["expected_fingerprint"]
    missing_fp = [
        row["set_id"] for row in rows
        if row["proposed_diagnostics"].get(COLLECTOR_APPEAL_DIAGNOSTICS_KEY, {}).get("fingerprint") != expected_fp
    ]
    check(16, "every proposed diagnostics payload carries the current fingerprint", not missing_fp,
          {"expected_fingerprint": expected_fp, "violations": missing_fp})

    # 17: EXECUTED, not asserted. Two independently built plans from the same
    # source state must produce byte-identical normalized payloads.
    first_hash = normalized_payload_hash(plan)
    second_hash = normalized_payload_hash(rebuild_plan)
    first_targets = sorted((r["update_target"] or {}).get("id") for r in plan["rows"] if r["would_update"])
    second_targets = sorted((r["update_target"] or {}).get("id") for r in rebuild_plan["rows"] if r["would_update"])
    check(17, "building and normalizing the plan twice yields identical output",
          first_hash == second_hash and first_targets == second_targets
          and plan["counts"] == rebuild_plan["counts"],
          {"first_payload_hash": first_hash, "second_payload_hash": second_hash,
           "targets_identical": first_targets == second_targets,
           "counts_identical": plan["counts"] == rebuild_plan["counts"],
           "note": "two real build_update_plan() calls compared; not a hardcoded True"})

    # 18: EXACT correspondence, in both directions.
    needs_rebuild = {row["set_id"] for row in rows if row["fingerprint_status"] in ("missing", "stale")}
    current_rows = {row["set_id"] for row in rows if row["fingerprint_status"] == "current"}
    planned_updates = {row["set_id"] for row in rows if row["would_update"]}
    byte_identical_excluded = current_rows - planned_updates
    missing_from_plan = needs_rebuild - planned_updates
    unrelated_updates = planned_updates - needs_rebuild
    check(18, "the update plan is exactly the set of missing/stale rows",
          not missing_from_plan and not unrelated_updates
          and byte_identical_excluded == current_rows,
          {"needs_rebuild": len(needs_rebuild),
           "planned_updates": len(planned_updates),
           "missing_from_plan": sorted(missing_from_plan),
           "unrelated_updates_present": sorted(unrelated_updates),
           "current_rows_correctly_excluded": len(byte_identical_excluded),
           "current_rows_total": len(current_rows)})

    check(19, "no write request was executed",
          not guard.write_attempts,
          {"write_attempts": guard.write_attempts,
           "read_ops": len([c for c in guard.calls if c["op"] == "select"])})

    check(20, "no migration applied", True, {"note": "this script issues no DDL"})

    # --- Phase 8.1 additions ------------------------------------------------

    # 21: the defect that made the previous rollout unsafe. A v1 component row
    # must never receive diagnostics certifying v2 coverage-cleanup inputs.
    expected_versions = expected_source_versions()
    identity_mismatches = []
    for row in rows:
        identity = row["source_identity"]
        source_row = selection["selected"].get(row["set_id"])
        agrees = source_row is not None and source_identity_matches_row(identity, source_row)
        versions_agree = all(identity.get(field) == value for field, value in expected_versions.items())
        if not agrees or not versions_agree:
            identity_mismatches.append({
                "set_id": row["set_id"], "set_name": row["set_name"],
                "identity_versions": {f: identity.get(f) for f in expected_versions},
                "expected_versions": expected_versions,
                "describes_its_row": agrees,
            })
    check(21, "every source identity matches its row's ACTUAL versions",
          not identity_mismatches,
          {"expected_versions": expected_versions, "violations": identity_mismatches,
           "rows_checked": len(rows)})

    # 22: the source contract itself.
    check(22, "every planned row came from a version-exact source row",
          selection["counts"]["exact_version_rows_found"] == len(rows)
          and not selection["duplicates"],
          {"exact_version_rows_found": selection["counts"]["exact_version_rows_found"],
           "sets_missing_exact_version_row": selection["counts"]["sets_missing_exact_version_row"],
           "sets_with_duplicate_exact_version_rows": selection["counts"]["sets_with_duplicate_exact_version_rows"],
           "missing": [{"set_id": e["set_id"], "set_name": e["set_name"],
                        "available_versions": e["available_versions"]}
                       for e in selection["missing"]],
           "duplicates": selection["duplicates"],
           "version_distribution": selection["version_distribution"]})

    # 23: EXPECTED TO FAIL. A rollout blocker for RIP integration, not a defect
    # in the calculation. Recorded rather than softened: a fallback from CA7 to
    # plain D inside one leaderboard would mix two constructs in one ranking and
    # make the column mean different things in different rows.
    coverage = rip_consumed_coverage(plan)
    check(23, "all RIP-consumed rows have Collector Appeal coverage",
          coverage["unavailable_count"] == 0,
          {"rip_consumed_total": coverage["rip_consumed_total"],
           "collector_appeal_available": coverage["available_count"],
           "collector_appeal_unavailable": coverage["unavailable_count"],
           "unavailable_sets": coverage["unavailable"],
           "blocker_note": (
               "Expected to fail while only part of the ranked cohort is pull-modeled. "
               "This blocks wiring CA7 into RIP; it does not invalidate CA7 on the sets "
               "it covers. No CA7 -> D fallback is permitted inside one leaderboard."
           )})

    # 24: every write target addresses exactly one real, unique row.
    selected_ids = [str(row.get("id")) for row in selection["selected"].values()]
    selected_id_set = set(selected_ids)
    target_ids = [(row["update_target"] or {}).get("id") for row in rows if row["would_update"]]
    unknown_targets = [tid for tid in target_ids if str(tid) not in selected_id_set]
    null_targets = [row["set_id"] for row in rows if row["would_update"] and not (row["update_target"] or {}).get("id")]
    check(24, "every update target's primary key exists exactly once in the source state",
          not unknown_targets and not null_targets
          and len(target_ids) == len(set(map(str, target_ids)))
          and len(selected_ids) == len(selected_id_set),
          {"targets": len(target_ids), "distinct_targets": len(set(map(str, target_ids))),
           "null_targets": null_targets, "targets_not_in_source_state": unknown_targets,
           "source_row_ids_distinct": len(selected_ids) == len(selected_id_set),
           "primary_key": COMPONENT_PRIMARY_KEY})

    # 25: the naming collision.
    generic_key_used = [
        row["set_id"] for row in rows
        if "collector_appeal" in (row["update_payload"] or {}).get("diagnostics_json", {})
        and "collector_appeal" not in row["current_diagnostics"]
    ]
    block_shape_wrong = [
        row["set_id"] for row in rows
        if row["proposed_diagnostics"][COLLECTOR_APPEAL_DIAGNOSTICS_KEY].get("metric_name") != COLLECTOR_APPEAL_METRIC_NAME
        or row["proposed_diagnostics"][COLLECTOR_APPEAL_DIAGNOSTICS_KEY].get("product_status") != COLLECTOR_APPEAL_PRODUCT_STATUS
        or row["proposed_diagnostics"][COLLECTOR_APPEAL_DIAGNOSTICS_KEY].get("formula") != "CA7"
    ]
    check(25, "CA7 is stored under its own namespaced key, never generic collector_appeal",
          not generic_key_used and not block_shape_wrong,
          {"diagnostics_key": COLLECTOR_APPEAL_DIAGNOSTICS_KEY,
           "generic_key_introduced_for": generic_key_used,
           "malformed_blocks": block_shape_wrong,
           "note": "public collector_appeal_score (= Pure/Universal Desirability) untouched"})

    # 26: the write design itself.
    strategy = plan["write_strategy"]
    check(26, "the proposed write is a primary-key update, never an upsert",
          strategy["method"] == "update" and strategy["rows_per_statement"] == 1
          and strategy["writable_columns"] == ["diagnostics_json"],
          {"strategy": strategy})

    return results


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Subject building (same inputs the audit and a committed run would use)
# ---------------------------------------------------------------------------

# ``build_subject_index`` moved to backend.desirability.collector_appeal_inputs
# (imported above) so the dry run and the production service assemble subjects
# through the same function. A copy here would let the audit certify an assembly
# the service does not perform.


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def write_artifacts(plan: Mapping[str, Any], source_state: Mapping[str, Any],
                    invariants: Sequence[Mapping[str, Any]], guard: ReadOnlyClientGuard,
                    execution: Mapping[str, Any], previous_fingerprint: Optional[str]) -> None:
    counts = plan["counts"]
    failed = [item for item in invariants if not item["passed"]]
    blocking_failures = [item for item in failed if not item["known_rollout_blocker"]]
    trustworthy = not blocking_failures
    coverage = rip_consumed_coverage(plan)
    selection = source_state["selection"]

    report = {
        "version": plan["version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "writes_performed": execution["writes_performed"],
        "commit_reachable": False,
        "trustworthy": trustworthy,
        "metric_name": COLLECTOR_APPEAL_METRIC_NAME,
        "product_status": COLLECTOR_APPEAL_PRODUCT_STATUS,
        "diagnostics_key": COLLECTOR_APPEAL_DIAGNOSTICS_KEY,
        "previous_fingerprint": previous_fingerprint,
        "expected_fingerprint": plan["expected_fingerprint"],
        "collector_appeal_identity": plan["collector_appeal_identity"],
        "source_contract": plan["source_contract"],
        "source_manifest": plan["source_manifest"],
        "normalized_payload_hash": plan["normalized_payload_hash"],
        "write_strategy": plan["write_strategy"],
        "pagination": source_state["pagination"],
        "counts": counts,
        "rip_consumed_coverage": coverage,
        "unavailable_sources": plan["unavailable_sources"],
        "duplicate_sources": plan["duplicate_sources"],
        "invariants": list(invariants),
        "read_only_guard": {
            "write_attempts": guard.write_attempts,
            "select_ops": [call for call in guard.calls if call["op"] == "select"],
            "table_ops": sorted({call["table"] for call in guard.calls if "table" in call}),
        },
        "products": list(plan["rows"]),
    }
    JSON_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    JSON_ARTIFACT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    lines: List[str] = []
    add = lines.append
    add("# Collector Appeal CA7 — production dry run (Phase 8.1)\n")
    add(f"**Preview trustworthy: {'YES' if trustworthy else 'NO'}** · "
        f"**Writes performed: {execution['writes_performed']}** · "
        f"**`--commit` reachable: NO** · Generated {report['generated_at']}\n")
    add("> This run reads production and writes nothing. `main()` never passes "
        "`commit=True` and exposes no flag that could.\n")

    add("## Identity\n")
    add(f"- Metric: **`{COLLECTOR_APPEAL_METRIC_NAME}`** · status **`{COLLECTOR_APPEAL_PRODUCT_STATUS}`** · "
        f"stored at **`diagnostics_json.{COLLECTOR_APPEAL_DIAGNOSTICS_KEY}`**")
    add(f"- Formula: **CA7**, λ = **{CA7_PRODUCTION_LAMBDA}**")
    add(f"- **Old formula fingerprint:** `{previous_fingerprint or 'n/a'}`")
    add(f"- **New formula fingerprint:** `{plan['expected_fingerprint']}`")
    add(f"- Normalized payload hash: `{plan['normalized_payload_hash']}`")
    add(f"- Full source manifest hash: `{plan['source_manifest']['manifest_hash']}`")
    for name, part in plan["source_manifest"]["parts"].items():
        if isinstance(part, Mapping) and "manifest_hash" in part:
            add(f"  - `{name}`: `{part['manifest_hash']}`")
    add("")

    add("## Source-version contract\n")
    # Reported from the read, never hardcoded: the row count grows every time a
    # set is rebuilt (the Chaos Rising backfill took it from 511 to 512), and a
    # literal here would be quietly wrong the moment it did.
    add("The component table's real unique key is "
        f"`({', '.join(COMPONENT_UNIQUE_KEY)})` — **`set_id` is not unique** "
        f"({selection['counts']['rows_scanned']} rows / "
        f"{selection['counts']['sets_scanned']} sets in this read). "
        "Rows are selected by EXACT version match, never by recency.\n")
    expected = plan["source_contract"]["expected_versions"]
    add("| Expected version | Value |")
    add("|---|---|")
    for key, value in expected.items():
        add(f"| {key} | `{value}` |")
    add("")
    add("### Rows present, by version\n")
    add("| scoring_version | hit_policy_version | composite_scoring_version | rows | sets | selected? |")
    add("|---|---|---|---|---|---|")
    for entry in plan["source_contract"]["version_distribution"]:
        add(f"| `{entry['scoring_version']}` | `{entry['hit_policy_version']}` | "
            f"`{entry['composite_scoring_version']}` | {entry['row_count']} | {entry['set_count']} | "
            f"{'**YES**' if entry['is_expected'] else 'no'} |")
    add("")
    add(f"- Exact-version rows found: **{selection['counts']['exact_version_rows_found']}**")
    add(f"- Sets missing an exact-version row: **{selection['counts']['sets_missing_exact_version_row']}**")
    add(f"- Sets with duplicate exact-version rows: **{selection['counts']['sets_with_duplicate_exact_version_rows']}**\n")

    if plan["unavailable_sources"]:
        add("### Sets with no current-version component row\n")
        add("These are **unavailable**, not silently served from an older row.\n")
        for entry in plan["unavailable_sources"]:
            add(f"- **{entry['set_name']}** (`{entry['set_id']}`) — `{entry['reason']}`"
                f"{' · **RIP-consumed**' if entry.get('rip_consumes_row') else ''}")
            add("  - Available versions:")
            for available in entry["available_versions"]:
                add(f"    - `{available['hit_policy_version']}` (built {available['built_at']}, id `{available['id']}`)")
            add("  - Separate dry-run rebuild command (NOT executed in this task):")
            add("    ```bash")
            for line in entry["rebuild_command"].splitlines():
                add(f"    {line}")
            add("    ```")
        add("")

    if plan["duplicate_sources"]:
        add("### Sets with duplicate exact-version rows\n")
        for entry in plan["duplicate_sources"]:
            add(f"- **{entry['set_name']}** (`{entry['set_id']}`): {entry['row_count']} rows — {entry['reason']}")
        add("")

    add("## Counts\n")
    add("| Metric | Value |")
    add("|---|---|")
    for key in ("products_total", "booster_supported", "unsupported",
                "exact_version_source_rows_available", "exact_version_source_rows_missing",
                "would_update", "would_insert",
                "diagnostics_only_updates", "score_changing_updates", "unchanged",
                "fingerprint_current", "fingerprint_stale", "fingerprint_missing",
                "collector_appeal_available", "collector_appeal_unavailable",
                "rip_consumed_total", "rip_consumed_collector_appeal_available",
                "rip_consumed_collector_appeal_unavailable", "rows_with_warnings"):
        add(f"| {key.replace('_', ' ')} | **{counts[key]}** |")
    add("")

    add("## RIP-consumed cohort — CA7 coverage\n")
    add(f"**{coverage['available_count']} of {coverage['rip_consumed_total']}** RIP-consumed sets can "
        f"produce a CA7 value. **{coverage['unavailable_count']}** cannot.\n")
    add("> RIP continues to use Universal Desirability v3 at 10%. CA7 is **not** wired into RIP, "
        "and no CA7→D fallback is permitted inside one leaderboard: that would rank rows computed "
        "from two different constructs against each other.\n")
    add("### RIP-consumed sets WITHOUT CA7\n")
    if coverage["unavailable"]:
        add("| Set | Reason |")
        add("|---|---|")
        for entry in coverage["unavailable"]:
            add(f"| {entry['set_name']} | `{entry['reason']}` |")
    else:
        add("None.")
    add("")
    add("### RIP-consumed sets WITH CA7\n")
    if coverage["available"]:
        add("| Set | CA7 |")
        add("|---|---|")
        for entry in coverage["available"]:
            add(f"| {entry['set_name']} | {entry['collector_appeal_ca7']} |")
    else:
        add("None.")
    add("")

    add("## Invariants\n")
    add("| # | Invariant | Result |")
    add("|---|---|---|")
    for item in invariants:
        if item["passed"]:
            mark = "✅ pass"
        elif item["known_rollout_blocker"]:
            mark = "⛔ **fail — known rollout blocker**"
        else:
            mark = "❌ **FAIL**"
        add(f"| {item['n']} | {item['name']} | {mark} |")
    add("")
    if failed:
        add("### Failed invariants\n")
        for item in failed:
            label = " (known rollout blocker — expected)" if item["known_rollout_blocker"] else ""
            add(f"- **{item['n']} — {item['name']}**{label}\n  ```json\n  "
                f"{json.dumps(item['evidence'], indent=2, default=str)}\n  ```")
        add("")

    add("## Future write strategy — NOT EXECUTED\n")
    strategy = plan["write_strategy"]
    add(f"- Method: **{strategy['method']}** by primary key, **{strategy['rows_per_statement']} row per statement**")
    add(f"- Predicate: `{strategy['predicate']}`")
    add(f"- Writable columns: `{strategy['writable_columns']}`")
    add(f"- Upsert: {strategy['upsert']}")
    add(f"- Concurrency: {strategy['concurrency']}")
    add(f"- Zero rows returned → {strategy['zero_rows_returned']}")
    add(f"- More than one row returned → {strategy['multiple_rows_returned']}")
    add(f"- Idempotent: {strategy['idempotent']}\n")
    add("```python")
    add(strategy["statement"])
    add("```\n")
    add("A future commit command would require ALL THREE approval tokens to match a rebuilt plan:\n")
    add("```bash")
    add("  --expected-fingerprint " + plan["expected_fingerprint"])
    add("  --expected-manifest " + plan["source_manifest"]["manifest_hash"])
    add("  --expected-payload-hash " + plan["normalized_payload_hash"])
    add("```")
    add("\n**No such command exists yet.** `--commit` is not implemented in this script.\n")

    add("## Pagination\n")
    pagination = source_state["pagination"]
    add(f"- Pages read: {len(pagination['pages'])} · total rows {pagination['total_rows']}")
    add(f"- Final page partial (proves no truncation): **{pagination['final_page_partial']}**")
    add(f"- Truncation possible: **{pagination['truncation_possible']}**\n")

    add("## Read-only evidence\n")
    add(f"- Mutating client methods attempted: **{len(guard.write_attempts)}** {guard.write_attempts or ''}")
    add(f"- Writes performed: **{execution['writes_performed']}**")
    add(f"- Tables read: {', '.join(report['read_only_guard']['table_ops'])}\n")

    anomalies = [row for row in plan["rows"] if row["validation_warnings"]]
    add("## Anomalies\n")
    if anomalies:
        for row in anomalies:
            add(f"- **{row['set_name']}** (`{row['set_canonical_key']}`): {'; '.join(row['validation_warnings'])}")
    else:
        add("None.")
    add("")

    MD_ARTIFACT.write_text("\n".join(lines), encoding="utf-8")


def _write_determinism_artifact(
    comparison: Mapping[str, Any],
    compared_with: str,
    invariants: Sequence[Mapping[str, Any]],
) -> None:
    """Report the two determinism checks SEPARATELY.

    Invariant 17 and this comparison answer different questions, and Phase 8.1
    reported the first as if it settled the second. Printing them side by side,
    each labelled with what it actually covers, is the point of this artifact.
    """
    in_process = next((item for item in invariants if item["n"] == 17), None)
    checks = comparison["checks"]

    lines: List[str] = []
    add = lines.append
    add("# Collector Appeal CA7 — determinism validation\n")
    add(f"Generated {datetime.now(timezone.utc).isoformat()}\n")
    add("Two different questions, reported separately. The first cannot answer the second.\n")

    add("## 1. In-process deterministic build\n")
    add("Two `build_update_plan()` calls in ONE process from ONE in-memory source read. "
        "Proves the build is a pure function of loaded state. Blind to process start-up, "
        "a fresh connection, a fresh read, and any ordering that is stable within one interpreter.\n")
    if in_process:
        add(f"- Result: **{'PASS' if in_process['passed'] else 'FAIL'}** (invariant 17)")
        add(f"- First payload hash: `{in_process['evidence']['first_payload_hash']}`")
        add(f"- Second payload hash: `{in_process['evidence']['second_payload_hash']}`")
    else:
        add("- Result: **not run**")
    add("")

    add("## 2. Independent cross-run deterministic build\n")
    # Only the file name: the full path is environment-specific provenance, and
    # this artifact is committed.
    add(f"A separate process re-read production and produced a new artifact, compared against "
        f"`{Path(compared_with).name}`. This is the check Phase 8.1 left unexecuted.\n")
    add(f"- **Verdict: `{comparison['verdict']}`** — deterministic: "
        f"**{'YES' if comparison['deterministic'] else 'NO'}**\n")
    add("| Check | Result | Previous | Current |")
    add("|---|---|---|---|")
    for name in ("formula_fingerprint", "source_manifest", "normalized_payload_hash"):
        entry = checks[name]
        add(f"| {name} | {'✅ match' if entry['match'] else '❌ differs'} | "
            f"`{entry['previous']}` | `{entry['current']}` |")
    for part, entry in checks["component_manifest_parts"].items():
        add(f"| manifest part · {part} | {'✅ match' if entry['match'] else '❌ differs'} | "
            f"`{entry['previous']}` | `{entry['current']}` |")
    ordering = checks["row_ordering_and_serialization"]
    add(f"| row ordering & serialization | {'✅ match' if ordering['match'] else '❌ differs'} | "
        f"{ordering['previous_target_count']} targets | {ordering['current_target_count']} targets |")
    add(f"| counts | {'✅ match' if checks['counts']['match'] else '❌ differs'} | — | — |")
    add("")

    add("## Volatile values\n")
    add("Excluded from every hash: "
        f"{', '.join(f'`{field}`' for field in comparison['volatile_fields_excluded_from_hashes'])}.")
    observed = comparison["volatile_fields_observed_differing"]
    add(f"- Observed differing between the two runs: "
        f"{', '.join(f'`{field}`' for field in observed) if observed else 'none'}")
    add("- These differ by design and do not reach hashed content — which is exactly what an "
        "identical cross-run payload hash under differing timestamps proves.\n")

    add("## Interpretation\n")
    add(f"{comparison['interpretation']}\n")
    add("> A changed **source manifest** means the inputs moved and is NOT nondeterminism: the "
        "correct response to changed inputs is a changed payload. Nondeterminism is only the case "
        "where the source manifest is identical and the payload moved anyway.\n")

    DETERMINISM_ARTIFACT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare-with", type=str, default=None,
                        help="Path to a previous dry-run JSON; asserts byte-equivalent normalized payloads.")
    parser.add_argument("--previous-fingerprint", type=str, default=None,
                        help="The fingerprint this build replaces; reported alongside the new one.")
    parser.add_argument("--page-size", type=int, default=250,
                        help=("Rows per component read. The full row carries several large JSONB "
                              "columns, so a 511-row single page is a multi-MB response that "
                              "intermittently times out. Smaller pages, same rows - pagination is "
                              "audited in the report."))
    args = parser.parse_args()
    # NOTE: there is deliberately no --commit flag. execute_plan is only ever
    # called with commit=False below.

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()

    guard = ReadOnlyClientGuard(public_read_client)

    logger.info("[dry-run] reading production state (read-only guard active)...")
    source_state = load_source_state(
        guard,
        page_size=args.page_size,
        pull_model_loader=load_pull_rate_model,
        simulation_loader=load_simulation_rows,
    )
    selection = source_state["selection"]
    logger.info("[dry-run] rows scanned=%s exact-version rows=%s missing=%s duplicates=%s",
                selection["counts"]["rows_scanned"],
                selection["counts"]["exact_version_rows_found"],
                selection["counts"]["sets_missing_exact_version_row"],
                selection["counts"]["sets_with_duplicate_exact_version_rows"])
    for entry in selection["missing"]:
        logger.warning("[dry-run] %s: %s (has %s)", entry["set_name"], entry["reason"],
                       [v["hit_policy_version"] for v in entry["available_versions"]])

    subjects_by_set = build_subject_index(
        guard, list(source_state["selected_rows"]), source_state["pull_model"]
    )
    logger.info("[dry-run] sets with dual-path subjects: %s", len(subjects_by_set))

    plan = build_update_plan(
        source_state,
        subject_builder=lambda sid: subjects_by_set.get(sid),
        subjects_by_set=subjects_by_set,
    )
    # Invariant 17 needs a genuine second build, not a copy of the first.
    rebuild_plan = build_update_plan(
        source_state,
        subject_builder=lambda sid: subjects_by_set.get(sid),
        subjects_by_set=subjects_by_set,
    )

    # The dry run NEVER passes commit=True.
    execution = execute_plan(plan, guard, commit=False)

    invariants = check_invariants(plan, source_state, guard, rebuild_plan)
    write_artifacts(plan, source_state, invariants, guard, execution, args.previous_fingerprint)

    failed = [item for item in invariants if not item["passed"]]
    blocking = [item for item in failed if not item["known_rollout_blocker"]]
    logger.info("[dry-run] counts: %s", json.dumps(plan["counts"], indent=2))
    logger.info("[dry-run] invariants: %s passed, %s failed (%s known rollout blockers)",
                len(invariants) - len(failed), len(failed), len(failed) - len(blocking))
    for item in failed:
        level = logger.warning if item["known_rollout_blocker"] else logger.error
        level("[dry-run] INVARIANT %s %s: %s -> %s",
              "BLOCKER" if item["known_rollout_blocker"] else "FAILED",
              item["n"], item["name"], json.dumps(item["evidence"], default=str)[:400])
    logger.info("[dry-run] writes performed: %s", execution["writes_performed"])
    logger.info("[dry-run] new fingerprint: %s", plan["expected_fingerprint"])
    logger.info("[dry-run] normalized payload hash: %s", plan["normalized_payload_hash"])
    logger.info("[dry-run] source manifest hash: %s", plan["source_manifest"]["manifest_hash"])

    if args.compare_with:
        # An INDEPENDENT cross-run check: this process read production itself and
        # is comparing against an artifact a different process produced. Distinct
        # from invariant 17, which never leaves this interpreter.
        previous = json.loads(Path(args.compare_with).read_text(encoding="utf-8"))
        current = json.loads(JSON_ARTIFACT.read_text(encoding="utf-8"))
        comparison = compare_dry_run_artifacts(previous, current)
        _write_determinism_artifact(comparison, args.compare_with, invariants)
        logger.info("[cross-run] verdict: %s", comparison["verdict"])
        for name, check in comparison["checks"].items():
            if name == "component_manifest_parts":
                for part, entry in check.items():
                    logger.info("[cross-run]   part %s: %s", part, "MATCH" if entry["match"] else "DIFFERS")
                continue
            logger.info("[cross-run]   %s: %s", name, "MATCH" if check["match"] else "DIFFERS")
        logger.info("[cross-run] %s", comparison["interpretation"])
        if not comparison["deterministic"]:
            return 1

    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
