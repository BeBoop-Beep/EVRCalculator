"""Publish a new complete private Budget Ranking authority, once, if ready."""

from __future__ import annotations

import argparse
import json
import logging
import math
import platform
import subprocess
import time
import itertools
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION, BUDGET_COMPARISON_SCOPE_VERSION,
    BUDGET_NORMALIZED_RANKING_METHOD_VERSION, BUDGET_TYPE_FULL_MARKET,
    BUDGET_TYPE_STANDARD, CANONICAL_BUDGET_BANDS, FULL_MARKET_ROUNDING_RULE_VERSION,
)
from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.budget_product_ranking_authority import (
    EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION, EXPECTED_CHASE_ACCESSIBILITY_VERSION,
    EXPECTED_COLLECTOR_APPEAL_VERSION, EXPECTED_FINANCIAL_RIP_VERSION,
    EXPECTED_OVERALL_RIP_V12_VERSION, EXPECTED_OVERALL_RIP_VERSION,
    MIN_MAPPED_HC_MASS_FOR_BUDGET_V12,
)
from backend.desirability.scoring_config import (
    CANONICAL_OVERALL_RIP_VERSION, OVERALL_RIP_V12_VERSION,
)
from backend.db.services.budget_product_ranking_readiness import (
    BudgetRankingStatus, EXIT_CODES, ReadinessResult, resolve_budget_ranking_readiness,
)
from backend.scripts.build_budget_normalized_product_rankings import (
    FINANCIAL_DOMINANCE_WARN_RATE, UTILIZATION_CORRELATION_WARN,
    build_rankings_for_cohort, build_v12_shadow_rankings_for_cohort, publish_rankings,
    to_publication_payload,
)

logger = logging.getLogger("budget-ranking-publication")
TOLERANCE = 0.01
UTIL_TOLERANCE = 0.000001
REPORT_FIELDS = (
    "status started_at finished_at previous_price_as_of selected_price_as_of promoted_market_date "
    "snapshot_id eligible_cohort_count set_count family_count source_run_count budget_cohort_counts "
    "row_count full_market_budget full_market_count max_eligible_sku_price ranking_method_version "
    "allocation_method_version comparison_scope_version full_market_rounding_rule_version "
    "financial_rip_version overall_rip_version collector_appeal_version source_calculation_run_ids "
    "cohort_fingerprint candidate_authorities gate_results health_diagnostics warnings failure_reason "
    "failed_gate build_duration_ms publish_duration_ms verification_duration_ms duration_ms"
).split()


def _load_latest_snapshot(client: Any) -> Optional[Dict[str, Any]]:
    latest = list((client.table("budget_product_ranking_latest").select("*")
                   .eq("ranking_method_version", BUDGET_NORMALIZED_RANKING_METHOD_VERSION)
                   .eq("allocation_method_version", ALLOCATION_METHOD_VERSION)
                   .limit(1).execute().data or []))
    if not latest:
        return None
    rows = list((client.table("budget_product_ranking_snapshots").select("*")
                 .eq("id", str(latest[0]["snapshot_id"])).limit(1).execute().data or []))
    return rows[0] if rows else None


def _base_report() -> Dict[str, Any]:
    report = {key: None for key in REPORT_FIELDS}
    report.update({"gate_results": [], "health_diagnostics": {}, "warnings": [], "candidate_authorities": [], "budget_cohort_counts": {}, "source_calculation_run_ids": []})
    report["started_at"] = datetime.now(timezone.utc).isoformat()
    report.update({
        "ranking_method_version": BUDGET_NORMALIZED_RANKING_METHOD_VERSION,
        "allocation_method_version": ALLOCATION_METHOD_VERSION,
        "comparison_scope_version": BUDGET_COMPARISON_SCOPE_VERSION,
        "full_market_rounding_rule_version": FULL_MARKET_ROUNDING_RULE_VERSION,
        "financial_rip_version": EXPECTED_FINANCIAL_RIP_VERSION,
        "overall_rip_version": EXPECTED_OVERALL_RIP_VERSION,
        "collector_appeal_version": EXPECTED_COLLECTOR_APPEAL_VERSION,
    })
    return report


def _gate(name: str, passed: bool, reason: Optional[str] = None) -> Dict[str, Any]:
    return {"gate": name, "passed": passed, "reason": reason}


def validate_publication_payload(snapshot: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Pure hard-gate validation shared by dry-run and commit paths."""
    failures: List[Dict[str, Any]] = []
    cohorts: Dict[tuple, List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        cohorts[(float(row["target_budget"]), str(row["budget_type"]))].append(row)
    expected = {(float(b), BUDGET_TYPE_STANDARD) for b in CANONICAL_BUDGET_BANDS}
    expected.add((float(snapshot["full_market_budget"]), BUDGET_TYPE_FULL_MARKET))
    if set(cohorts) != expected or len(cohorts) != len(expected):
        failures.append(_gate("canonical_cohorts", False, "expected exactly %d standard bands and Full Market" % len(CANONICAL_BUDGET_BANDS)))
    identities = [(r["sealed_product_id"], r["target_budget"], r["budget_type"]) for r in rows]
    if len(identities) != len(set(identities)):
        failures.append(_gate("unique_identity", False, "duplicate product/budget/type"))
    for key, group in cohorts.items():
        count = len(group)
        sizes = {int(r["budget_cohort_size"]) for r in group}
        ranks = {int(r["budget_rank"]) for r in group}
        financial = {int(r["financial_only_rank"]) for r in group}
        if sizes != {count} or ranks != set(range(1, count + 1)) or financial != set(range(1, count + 1)):
            failures.append(_gate("cohort_integrity", False, "noncontiguous ranks/cohort size at %s" % (key,)))
        for row in group:
            required = ("financial_rip_v4_score", "overall_rip_v10_score", "collector_appeal_score", "chance_to_recover_capital", "budget_tier", "source_calculation_run_id")
            if any(row.get(k) is None for k in required) or int(row.get("quantity") or 0) < 1:
                failures.append(_gate("required_values", False, "missing required value at %s" % (key,)))
                break
            if abs(float(row["actual_committed_capital"]) + float(row["unused_capital"]) - float(row["target_budget"])) >= TOLERANCE:
                failures.append(_gate("capital_reconciliation", False, "capital equation failed")); break
            if abs(float(row["capital_utilization"]) + float(row["unused_capital_percent"]) - 1.0) >= UTIL_TOLERANCE:
                failures.append(_gate("utilization_complement", False, "utilization equation failed")); break
    full = cohorts.get((float(snapshot["full_market_budget"]), BUDGET_TYPE_FULL_MARKET), [])
    n = int(snapshot["eligible_cohort_count"])
    anchor = math.ceil(float(snapshot["max_eligible_sku_price"]) / 50.0) * 50.0
    if len(full) != n or float(snapshot["full_market_budget"]) != anchor:
        failures.append(_gate("full_market_coverage", False, "Full Market is not dynamic N/N or anchor is wrong"))
    for row in rows:
        metadata = (row.get("full_market_anchor"), row.get("max_eligible_sku_price"), row.get("full_market_rounding_rule"), row.get("full_market_rounding_increment"), row.get("full_market_rounding_rule_version"))
        if row["budget_type"] == BUDGET_TYPE_FULL_MARKET:
            if any(value is None for value in metadata) or float(row["full_market_anchor"]) != float(snapshot["full_market_budget"]):
                failures.append(_gate("full_market_metadata", False, "Full Market provenance incomplete")); break
        elif any(value is not None for value in metadata):
            failures.append(_gate("standard_metadata", False, "Full Market metadata on standard row")); break
    return failures


def health_diagnostics(results: Mapping[str, Any]) -> tuple[Dict[str, Any], List[str]]:
    """Warning-only daily diagnostics; neither threshold blocks publication."""
    utilization = []
    for key, block in results["budgets"].items():
        rho = block.get("utilizationRankSpearman")
        if rho is not None:
            utilization.append({"budget": key, "spearman": rho, "warning": abs(rho) > UTILIZATION_CORRELATION_WARN})
    dominance_rate = results.get("financialDominanceInversionRate")
    comparable = inversions = 0
    if dominance_rate is None:
        for block in results["budgets"].values():
            for left, right in itertools.combinations(block.get("rows") or [], 2):
                def metrics(row: Mapping[str, Any]) -> tuple[float, ...]:
                    committed = float(row["actualCommittedCapital"])
                    return (
                        float(row["expectedValue"]) / committed,
                        float(row["medianValue"]) / committed,
                        float(row["chanceToRecoverCapital"]),
                        float(row["lossResilience"]),
                    )
                try:
                    a, b = metrics(left), metrics(right)
                except (KeyError, TypeError, ValueError):
                    continue
                a_dom = all(x >= y - 1e-9 for x, y in zip(a, b)) and any(x > y + 1e-9 for x, y in zip(a, b))
                b_dom = all(y >= x - 1e-9 for x, y in zip(a, b)) and any(y > x + 1e-9 for x, y in zip(a, b))
                if not (a_dom or b_dom):
                    continue
                comparable += 1
                dominator, dominated = (left, right) if a_dom else (right, left)
                if int(dominator["financialOnlyRank"]) > int(dominated["financialOnlyRank"]):
                    inversions += 1
        dominance_rate = (inversions / comparable) if comparable else None
    warnings = []
    if dominance_rate is not None and dominance_rate > FINANCIAL_DOMINANCE_WARN_RATE:
        warnings.append("financial dominance inversion rate exceeds %.2f%%" % (100 * FINANCIAL_DOMINANCE_WARN_RATE))
    warnings.extend("capital utilization/rank Spearman warning at %s" % item["budget"] for item in utilization if item["warning"])
    return ({
        "financial_dominance_inversion_rate": dominance_rate,
        "financial_dominance_comparable_pairs": comparable,
        "financial_dominance_inversions": inversions,
        "financial_dominance_warn_rate": FINANCIAL_DOMINANCE_WARN_RATE,
        "utilization_rank_spearman": utilization,
        "utilization_correlation_warn": UTILIZATION_CORRELATION_WARN,
        "periodic_research_audit_due": bool(warnings),
    }, warnings)


def verify_persisted_snapshot(client: Any, snapshot_id: str, snapshot: Mapping[str, Any], expected_rows: Sequence[Mapping[str, Any]]) -> List[str]:
    snapshots = list((client.table("budget_product_ranking_snapshots").select("*").eq("id", snapshot_id).limit(1).execute().data or []))
    latest = list((client.table("budget_product_ranking_latest").select("*").eq("ranking_method_version", snapshot["ranking_method_version"]).eq("allocation_method_version", snapshot["allocation_method_version"]).limit(1).execute().data or []))
    rows = list((client.table("budget_product_ranking_rows").select("*").eq("snapshot_id", snapshot_id).execute().data or []))
    failures = []
    if not snapshots: failures.append("returned snapshot UUID does not exist")
    if not latest or str(latest[0].get("snapshot_id")) != snapshot_id or str(latest[0].get("market_date")) != str(snapshot["market_date"]): failures.append("latest pointer mismatch")
    if len(rows) != len(expected_rows): failures.append("persisted row count mismatch")
    if snapshots:
        persisted = snapshots[0]
        for key in ("ranking_method_version", "allocation_method_version", "comparison_scope_version", "financial_rip_version", "overall_rip_version", "collector_appeal_version", "eligible_cohort_count", "full_market_budget", "max_eligible_sku_price", "full_market_rounding_rule_version"):
            if str(persisted.get(key)) != str(snapshot.get(key)): failures.append("snapshot %s mismatch" % key)
    failures.extend(item["reason"] or item["gate"] for item in validate_publication_payload(snapshot, rows))
    expected_runs = {str(r["source_calculation_run_id"]) for r in expected_rows}
    if {str(r.get("source_calculation_run_id")) for r in rows} != expected_runs: failures.append("source run set mismatch")
    if {str(r.get("price_as_of")) for r in rows} != {str(snapshot["pinned_price_as_of"])}: failures.append("price authority mismatch")
    return failures


def validate_v12_publication_payload(v12_results: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Pure hard-gate validation for an EXPLICIT V12 budget candidate.

    ``v12_results`` is the dict returned by
    :func:`backend.scripts.build_budget_normalized_product_rankings.build_v12_shadow_rankings_for_cohort`.
    This function performs NO I/O and NEVER mutates its input or calls any
    publish/RPC path — it exists purely to decide whether a V12 candidate is
    fit to publish, for a caller who chooses to persist it separately (not
    performed by this repository session; see the Gate F migration, which is
    created but not applied).

    Refuses publication when: the resolved authority still declares V10
    (``overall_rip_version`` on the V10 cohort authority is not the expected
    V10 string, i.e. a caller accidentally passed a non-budget-V10-resolved
    cohort into the V12 path); any ranked row is missing/wrong on Overall
    V12 / Financial V4 / Collector V5 / Chase Accessibility / transform
    version identity; the Accessibility run used for any set does not match
    the cohort's own exact-run authority (``v12Readiness`` reports it
    ineligible); ``mapped_hc_mass < MIN_MAPPED_HC_MASS_FOR_BUDGET_V12`` for
    any set backing a ranked row; an eligible row (financial-rankable,
    Accessibility-ready set) failed to become V12-rankable; a ranked row is
    missing its V12 rank/cohort-size fields; or a mix of V10-labelled and
    V12-labelled ranked rows appears in the same budget cohort (rows must
    carry `overallRipV12Rankable is True` to have been ranked at all under
    :data:`SORT_AUTHORITY_V12`, but this is re-verified here rather than
    trusted).
    """
    failures: List[Dict[str, Any]] = []
    authority = v12_results.get("authority") or {}
    v12_readiness = v12_results.get("v12Readiness") or {}
    accessibility = v12_results.get("accessibilityResolution") or {}

    if authority.get("overallRipVersion") != EXPECTED_OVERALL_RIP_VERSION:
        failures.append(_gate("v12_base_cohort_authority", False,
                               "candidate cohort authority is not the expected V10-resolved base cohort"))
    if authority.get("financialRipVersion") != EXPECTED_FINANCIAL_RIP_VERSION:
        failures.append(_gate("v12_financial_version", False, "financial_rip_version mismatch"))
    if authority.get("collectorAppealVersion") != EXPECTED_COLLECTOR_APPEAL_VERSION:
        failures.append(_gate("v12_collector_version", False, "collector_appeal_version mismatch"))
    if v12_readiness.get("overallRipV12Version") != EXPECTED_OVERALL_RIP_V12_VERSION:
        failures.append(_gate("v12_overall_version", False, "overall_rip_v12_version mismatch"))
    if v12_readiness.get("chaseAccessibilityVersion") != EXPECTED_CHASE_ACCESSIBILITY_VERSION:
        failures.append(_gate("v12_accessibility_version", False, "chase_accessibility_version mismatch"))
    if v12_readiness.get("transformVersion") != EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION:
        failures.append(_gate("v12_transform_version", False, "chase_accessibility_transform_version mismatch"))
    if accessibility.get("chaseAccessibilityVersion") not in (None, EXPECTED_CHASE_ACCESSIBILITY_VERSION):
        failures.append(_gate("v12_accessibility_authority_mix", False, "accessibility batch read carries an unexpected version"))
    if v12_readiness.get("unexpectedAuthorityMix"):
        failures.append(_gate("v12_accessibility_authority_mix", False, "accessibility batch read carries an unexpected version"))
    if not v12_readiness.get("allSetsEligible", False):
        ineligible = sorted(sid for sid, entry in (v12_readiness.get("perSet") or {}).items() if not entry.get("eligible"))
        failures.append(_gate("v12_set_eligibility", False, "sets ineligible for V12 authority: %s" % ineligible))
    for set_id, entry in (v12_readiness.get("perSet") or {}).items():
        if not entry.get("eligible"):
            continue
        mass = (accessibility.get("bySet") or {}).get(set_id, {}).get("mappedHcMass") if accessibility.get("bySet") else None
        # bySet is stripped from accessibilityResolution before it reaches this
        # function; mapped-HC-mass sufficiency was already enforced by
        # `resolve_v12_budget_authority_readiness` (>= MIN_MAPPED_HC_MASS_FOR_BUDGET_V12)
        # to produce `eligible: True` in the first place. Re-check defensively
        # only when the raw value happens to still be present.
        if mass is not None:
            try:
                if float(mass) < MIN_MAPPED_HC_MASS_FOR_BUDGET_V12:
                    failures.append(_gate("v12_mapped_hc_mass", False, "set %s below minimum mapped_hc_mass" % set_id))
            except (TypeError, ValueError):
                failures.append(_gate("v12_mapped_hc_mass", False, "set %s has non-numeric mapped_hc_mass" % set_id))

    seen_gates = {f["gate"] for f in failures}
    for key, block in (v12_results.get("budgets") or {}).items():
        rows = block.get("rows") or []
        size = len(rows)
        ranks = {int(r.get("budgetRank")) for r in rows if r.get("budgetRank") is not None}
        if len(ranks) != size or (size and ranks != set(range(1, size + 1))):
            if "v12_cohort_integrity" not in seen_gates:
                failures.append(_gate("v12_cohort_integrity", False, "noncontiguous V12 ranks at %s" % key)); seen_gates.add("v12_cohort_integrity")
        for row in rows:
            if row.get("overallRipV12Rankable") is not True or row.get("overallRipV12Score") is None:
                if "v12_mixed_authority_rows" not in seen_gates:
                    failures.append(_gate("v12_mixed_authority_rows", False, "a non-V12-rankable row was ranked at %s" % key)); seen_gates.add("v12_mixed_authority_rows")
            if row.get("overallRipV12Version") != EXPECTED_OVERALL_RIP_V12_VERSION:
                if "v12_row_version" not in seen_gates:
                    failures.append(_gate("v12_row_version", False, "ranked row missing/wrong overallRipV12Version at %s" % key)); seen_gates.add("v12_row_version")
            if row.get("budgetRank") is None or row.get("budgetCohortSize") is None:
                if "v12_missing_rank_fields" not in seen_gates:
                    failures.append(_gate("v12_missing_rank_fields", False, "ranked row missing budgetRank/budgetCohortSize at %s" % key)); seen_gates.add("v12_missing_rank_fields")
        for entry in block.get("unrankable") or []:
            sid = entry.get("sealedProductId")
            row = next((r for r in rows if r.get("sealedProductId") == sid), None)
            if row is not None and "v12_unrankable_eligible_row" not in seen_gates:
                failures.append(_gate("v12_unrankable_eligible_row", False, "row %s reported unrankable but also present in ranked rows" % sid)); seen_gates.add("v12_unrankable_eligible_row")

    if int(v12_results.get("productCount") or -1) != len(authority.get("calculationRunIds") or []) and authority.get("productCount") is not None:
        if int(v12_results.get("productCount") or -1) != int(authority.get("productCount")):
            failures.append(_gate("v12_cohort_size_mismatch", False, "V12 build product count does not match the base cohort's authority product count"))

    return failures


def run_v12_dry_run(*, client: Any, products: Sequence[Mapping[str, Any]], authority: Mapping[str, Any]) -> Dict[str, Any]:
    """EXPLICIT V12 candidate validation. NEVER writes anything.

    Builds the V12 shadow ranking for the given (already V10-authority
    resolved) cohort and validates it with :func:`validate_v12_publication_payload`.
    There is no ``commit`` parameter and no code path here calls
    ``publish_rankings`` or any RPC — this function is validate-only by
    construction, matching the task's explicit instruction that V12 mode
    must be testable/callable but must never actually publish anything.
    """
    started = time.perf_counter()
    v12_results = build_v12_shadow_rankings_for_cohort(client, products, authority)
    failures = validate_v12_publication_payload(v12_results)
    report = {
        "mode": "v12_explicit_validation_only",
        "passed": not failures,
        "gate_results": failures or [_gate("v12_ranking_payload", True)],
        "overall_rip_v12_version": EXPECTED_OVERALL_RIP_V12_VERSION,
        "chase_accessibility_version": EXPECTED_CHASE_ACCESSIBILITY_VERSION,
        "chase_accessibility_transform_version": EXPECTED_CHASE_ACCESSIBILITY_TRANSFORM_VERSION,
        "eligible_set_ids": (v12_results.get("v12Readiness") or {}).get("eligibleSetIds"),
        "product_count": v12_results.get("productCount"),
        "batch_accessibility_read_count": v12_results.get("batchAccessibilityReadCount"),
        "duration_ms": round((time.perf_counter() - started) * 1000),
    }
    return {"report": report, "results": v12_results}


def default_budget_sort_authority_is_v12() -> bool:
    """True when the CANONICAL Overall RIP authority (backend-wide, not a
    budget-specific constant) is V12.

    This is the ONE place the default/normal budget publisher path asks "is
    V12 canonical right now" - reusing `CANONICAL_OVERALL_RIP_VERSION`
    (`backend.desirability.scoring_config`), never a second, budget-local
    cutover switch. `EXPECTED_OVERALL_RIP_VERSION` /
    `EXPECTED_OVERALL_RIP_V12_VERSION` in `budget_product_ranking_authority.py`
    stay fixed identity strings (the V10-resolved BASE cohort's required
    version, and the V12 candidate's required version, respectively) - neither
    of those changes here or ever should; only which candidate the default
    path additionally builds and reports on does.
    """
    return CANONICAL_OVERALL_RIP_VERSION == OVERALL_RIP_V12_VERSION


def run(*, commit: bool, force_price_as_of: Optional[str] = None, client: Any = None, now: Optional[datetime] = None) -> tuple[int, Dict[str, Any]]:
    started = time.perf_counter(); report = _base_report()
    client = client or create_service_role_client()
    latest = _load_latest_snapshot(client)
    report["previous_price_as_of"] = (latest or {}).get("pinned_price_as_of")
    readiness = resolve_budget_ranking_readiness(client, latest_snapshot=latest, force_price_as_of=force_price_as_of, now=now)
    report.update({"status": readiness.status.value, "selected_price_as_of": readiness.selected_price_as_of, "promoted_market_date": readiness.promoted_market_date, "candidate_authorities": readiness.candidate_authorities, "gate_results": readiness.gate_results, "failure_reason": readiness.failure_reason, "failed_gate": readiness.failed_gate})
    if readiness.status != BudgetRankingStatus.PUBLISHED:
        return _finish(report, readiness.status, started)
    build_start = time.perf_counter()
    try:
        results = build_rankings_for_cohort(client, readiness.products, readiness.authority)
        snapshot, rows = to_publication_payload(results)
    except Exception as exc:
        report.update({"failure_reason": str(exc), "failed_gate": "ranking_build"})
        return _finish(report, BudgetRankingStatus.HEALTH_GATE_BLOCKED, started)
    report["build_duration_ms"] = round((time.perf_counter() - build_start) * 1000)
    failures = validate_publication_payload(snapshot, rows)
    report["gate_results"].extend(failures or [_gate("ranking_payload", True)])
    diagnostics, warnings = health_diagnostics(results); report["health_diagnostics"] = diagnostics; report["warnings"] = warnings
    report.update({
        "eligible_cohort_count": results["productCount"], "set_count": len({r["set_id"] for r in rows}),
        "family_count": len({r["product_family"] for r in rows}), "source_run_count": len(readiness.authority["calculationRunIds"]),
        "source_calculation_run_ids": readiness.authority["calculationRunIds"], "row_count": len(rows),
        "budget_cohort_counts": {k: v["rankedCount"] for k, v in results["budgets"].items()},
        "full_market_budget": snapshot["full_market_budget"], "full_market_count": sum(r["budget_type"] == BUDGET_TYPE_FULL_MARKET for r in rows),
        "max_eligible_sku_price": snapshot["max_eligible_sku_price"], "cohort_fingerprint": snapshot["cohort_fingerprint"],
    })
    # Canonical-authority V12 shadow validation (Phase 11 cutover wiring).
    # ADDITIVE and REPORT-ONLY: never affects `failures`/gate outcome above,
    # never changes which rows `publish_rankings` below actually persists (the
    # V10-shaped RPC/table write path is untouched by this task), and never
    # substitutes a V12 number under a V10 label or vice versa. It reuses
    # `run_v12_dry_run`'s validator rather than a second implementation. This
    # is what "default budget sort/readiness authority" means to now report
    # honestly: whether the SAME cohort this run already resolved is ALSO
    # V12-rankable under the backend-wide canonical selector.
    report["default_sort_authority"] = (
        EXPECTED_OVERALL_RIP_V12_VERSION if default_budget_sort_authority_is_v12()
        else EXPECTED_OVERALL_RIP_VERSION
    )
    if default_budget_sort_authority_is_v12():
        try:
            v12 = run_v12_dry_run(client=client, products=readiness.products, authority=readiness.authority)
            report["v12_canonical_validation"] = v12["report"]
        except Exception as exc:  # never let the additive V12 check fail the V10 publication path
            report["v12_canonical_validation"] = {"passed": False, "error": str(exc)}
    if failures:
        report.update({"failure_reason": failures[0]["reason"], "failed_gate": failures[0]["gate"]})
        return _finish(report, BudgetRankingStatus.HEALTH_GATE_BLOCKED, started)
    if not commit:
        # PUBLISHED means publish-eligible on dry-run; no write is attempted.
        return _finish(report, BudgetRankingStatus.PUBLISHED, started)
    publish_start = time.perf_counter()
    try:
        snapshot_id = publish_rankings(client, results)
    except Exception as exc:
        report.update({"failure_reason": str(exc), "failed_gate": "publication_rpc", "publish_duration_ms": round((time.perf_counter() - publish_start) * 1000)})
        return _finish(report, BudgetRankingStatus.PUBLICATION_FAILED, started)
    report["publish_duration_ms"] = round((time.perf_counter() - publish_start) * 1000); report["snapshot_id"] = snapshot_id
    verify_start = time.perf_counter(); verify_failures = verify_persisted_snapshot(client, snapshot_id, snapshot, rows)
    report["verification_duration_ms"] = round((time.perf_counter() - verify_start) * 1000)
    if verify_failures:
        report.update({"failure_reason": "; ".join(verify_failures), "failed_gate": "post_publish_verification"})
        return _finish(report, BudgetRankingStatus.POST_PUBLISH_VERIFICATION_FAILED, started)
    return _finish(report, BudgetRankingStatus.PUBLISHED, started)


def _finish(report: Dict[str, Any], status: BudgetRankingStatus, started: float) -> tuple[int, Dict[str, Any]]:
    report["status"] = status.value; report["finished_at"] = datetime.now(timezone.utc).isoformat(); report["duration_ms"] = round((time.perf_counter() - started) * 1000)
    return EXIT_CODES[status], report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true"); mode.add_argument("--commit", action="store_true")
    parser.add_argument("--force-price-as-of"); parser.add_argument("--json-report", default="logs/budget_product_ranking_publication.json")
    args = parser.parse_args(argv)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    logger.info("budget-ranking start head=%s host=%s mode=%s", head, platform.node(), "commit" if args.commit else "dry-run")
    code, report = run(commit=args.commit, force_price_as_of=args.force_price_as_of)
    path = Path(args.json_report); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("[budget-ranking] " + json.dumps({k: report.get(k) for k in ("status", "previous_price_as_of", "selected_price_as_of", "snapshot_id", "row_count", "failed_gate", "warnings", "duration_ms")}, default=str))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
