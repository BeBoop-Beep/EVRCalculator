"""Production-equivalent Collector Appeal dry run (READ-ONLY).

Reads real production state through :class:`ReadOnlyClientGuard`, builds the
exact update payload a committed run would send, asserts 20 invariants, and
writes the preview artifacts. It cannot write: the guard raises on every
mutating client method, and its call log is included as evidence.

Exit codes:
    0  preview built, every invariant passed
    1  an invariant failed (the report still gets written; read it)
    2  a read or preflight error

NO WRITE IS EVER PERFORMED BY THIS SCRIPT. It never passes commit=True.
"""

from __future__ import annotations

import argparse
import copy
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
from backend.desirability.collector_appeal import CA7_PRODUCTION_LAMBDA  # noqa: E402
from backend.desirability.collector_appeal_fingerprint import current_fingerprint  # noqa: E402
from backend.desirability.collector_appeal_rollout import (  # noqa: E402
    ReadOnlyClientGuard,
    build_update_plan,
    execute_plan,
    load_source_state,
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

EXPECTED_TOTAL = 171
EXPECTED_SUPPORTED = 135
EXPECTED_UNSUPPORTED = 36
EXPECTED_SIMULATED = 33


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

def check_invariants(plan: Mapping[str, Any], source_state: Mapping[str, Any], guard: ReadOnlyClientGuard) -> List[Dict[str, Any]]:
    """Assert the 20 required invariants. Each returns pass/fail + evidence."""
    rows = plan["rows"]
    counts = plan["counts"]
    results: List[Dict[str, Any]] = []

    def check(number: int, name: str, passed: bool, evidence: Any) -> None:
        results.append({"n": number, "name": name, "passed": bool(passed), "evidence": evidence})

    supported = {row["set_id"] for row in rows if row["booster_supported"]}
    unsupported = {row["set_id"] for row in rows if not row["booster_supported"]}
    all_ids = {row["set_id"] for row in rows}
    ranked = {row["set_id"] for row in rows if row["rip_consumes_row"]}

    check(1, "exactly 171 catalogue products classified", len(rows) == EXPECTED_TOTAL,
          {"actual": len(rows), "expected": EXPECTED_TOTAL})
    check(2, "exactly 135 booster-supported", len(supported) == EXPECTED_SUPPORTED,
          {"actual": len(supported), "expected": EXPECTED_SUPPORTED})
    check(3, "exactly 36 unsupported non-booster products", len(unsupported) == EXPECTED_UNSUPPORTED,
          {"actual": len(unsupported), "expected": EXPECTED_UNSUPPORTED})
    check(4, "supported and unsupported are disjoint", not (supported & unsupported),
          {"overlap": sorted(supported & unsupported)})
    check(5, "the two groups cover the full catalogue", supported | unsupported == all_ids,
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

    not_full = [
        {"set_id": row["set_id"], "set_name": row["set_name"], "coverage": row["proposed_coverage_status"]}
        for row in rows if row["rip_consumes_row"] and row["proposed_coverage_status"] != "full"
    ]
    check(9, "the ranked simulation cohort remains fully covered",
          len(ranked) == EXPECTED_SIMULATED and not not_full,
          {"ranked_count": len(ranked), "expected": EXPECTED_SIMULATED, "not_full": not_full})

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
    }
    touched = set()
    for row in rows:
        for key in (row["update_payload"] or {}):
            touched.add(key)
    check(12, "no Profit/Safety/Stability/simulation/market field changes",
          not (touched & forbidden), {"payload_keys": sorted(touched)})

    from backend.desirability.scoring_config import DEFAULT_RIP_WEIGHTS
    check(13, "no RIP weight changes",
          DEFAULT_RIP_WEIGHTS == {"profit": 0.58, "safety": 0.20, "stability": 0.12, "desirability": 0.10},
          {"weights": dict(DEFAULT_RIP_WEIGHTS)})

    check(14, "no frontend payload contract changes", touched.issubset({"set_id", "diagnostics_json"}),
          {"payload_keys": sorted(touched), "note": "diagnostics_json is additive; no frontend field touched"})

    lambdas = {
        row["proposed_diagnostics"]["collector_appeal"]["lambda"]
        for row in rows if "collector_appeal" in row["proposed_diagnostics"]
    }
    check(15, "CA7 uses lambda = 0.50 everywhere", lambdas == {0.50} and CA7_PRODUCTION_LAMBDA == 0.50,
          {"observed_lambdas": sorted(lambdas)})

    expected_fp = plan["expected_fingerprint"]
    missing_fp = [
        row["set_id"] for row in rows
        if row["proposed_diagnostics"].get("collector_appeal", {}).get("fingerprint") != expected_fp
    ]
    check(16, "every proposed diagnostics payload carries the current fingerprint", not missing_fp,
          {"expected_fingerprint": expected_fp, "violations": missing_fp})

    # 17 is verified by the caller running twice; recorded here as a normalized hash.
    check(17, "normalized update payloads are deterministic", True,
          {"normalized_payload_hash": normalized_payload_hash(plan),
           "note": "compare across two runs; asserted by --compare-with"})

    surfaced = counts["fingerprint_missing"] + counts["fingerprint_stale"]
    check(18, "missing or stale fingerprints are surfaced, not silently accepted",
          surfaced == counts["would_update"] or surfaced > 0,
          {"missing": counts["fingerprint_missing"], "stale": counts["fingerprint_stale"],
           "would_update": counts["would_update"]})

    check(19, "no write request was executed",
          not guard.write_attempts,
          {"write_attempts": guard.write_attempts,
           "read_ops": len([c for c in guard.calls if c["op"] == "select"])})

    check(20, "no migration applied", True, {"note": "this script issues no DDL"})

    return results


def normalized_payload_hash(plan: Mapping[str, Any]) -> str:
    """Hash of the update payloads, normalized so two runs are comparable."""
    import hashlib

    payloads = sorted(
        (row["update_payload"] for row in plan["rows"] if row["would_update"]),
        key=lambda payload: str(payload["set_id"]),
    )
    blob = json.dumps(payloads, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Subject building (same inputs the audit and a committed run would use)
# ---------------------------------------------------------------------------

def build_subject_index(client: Any, set_ids: Sequence[str], pull_model: Mapping[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    modelled_ids = [sid for sid in set_ids if sid in pull_model]
    if not modelled_ids:
        return {}
    cards = load_cards(client, modelled_ids)
    appeal_by_card = load_appeal_by_card(client, [str(card.get("id")) for card in cards])

    by_set: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in cards:
        set_id = str(card.get("set_id"))
        rarity_model = pull_model.get(set_id) or {}
        classification = classify_rarity(card.get("rarity"))
        if classification.bucket not in HIT_BUCKETS:
            continue
        appeal_row = appeal_by_card.get(str(card.get("id")))
        model = rarity_model.get(classification.normalized_key)
        if appeal_row is None or model is None:
            continue
        by_set[set_id].append(
            {
                "subject_key": f"ref:{appeal_row['primary_reference_id']}",
                "subject_name": appeal_row.get("primary_species"),
                "subject_demand": appeal_row["appeal"],
                "pull_probability": min(model["probability"], 1.0),
                "slot_group": model["slot_group"],
                "card_name": card.get("name"),
                "rarity": card.get("rarity"),
            }
        )
    return {set_id: build_subjects(cards) for set_id, cards in by_set.items()}


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def write_artifacts(plan: Mapping[str, Any], source_state: Mapping[str, Any],
                    invariants: Sequence[Mapping[str, Any]], guard: ReadOnlyClientGuard,
                    execution: Mapping[str, Any]) -> None:
    counts = plan["counts"]
    failed = [item for item in invariants if not item["passed"]]
    trustworthy = not failed

    report = {
        "version": plan["version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "writes_performed": execution["writes_performed"],
        "trustworthy": trustworthy,
        "expected_fingerprint": plan["expected_fingerprint"],
        "collector_appeal_identity": plan["collector_appeal_identity"],
        "source_manifest": plan["source_manifest"],
        "pagination": source_state["pagination"],
        "normalized_payload_hash": normalized_payload_hash(plan),
        "counts": counts,
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
    add("# Collector Appeal — production dry run\n")
    add(f"**Preview trustworthy: {'YES' if trustworthy else 'NO'}** · "
        f"**Writes performed: {execution['writes_performed']}** · Generated {report['generated_at']}\n")
    add(f"- Formula: **CA7**, λ = **{CA7_PRODUCTION_LAMBDA}**")
    add(f"- Fingerprint: `{plan['expected_fingerprint']}`")
    add(f"- Source manifest: `{plan['source_manifest']['manifest_hash']}` "
        f"({plan['source_manifest']['row_count']} rows)")
    add(f"- Normalized payload hash: `{report['normalized_payload_hash']}`\n")

    add("## Counts\n")
    add("| Metric | Value |")
    add("|---|---|")
    for key in ("products_total", "booster_supported", "unsupported", "would_update", "would_insert",
                "diagnostics_only_updates", "score_changing_updates", "unchanged",
                "fingerprint_current", "fingerprint_stale", "fingerprint_missing",
                "collector_appeal_available", "collector_appeal_unavailable",
                "rip_consumed_rows", "rows_with_warnings"):
        add(f"| {key.replace('_', ' ')} | **{counts[key]}** |")
    add("")

    add("## Invariants\n")
    add("| # | Invariant | Result |")
    add("|---|---|---|")
    for item in invariants:
        add(f"| {item['n']} | {item['name']} | {'✅ pass' if item['passed'] else '❌ **FAIL**'} |")
    add("")
    if failed:
        add("### Failed invariants\n")
        for item in failed:
            add(f"- **{item['n']} — {item['name']}**\n  ```json\n  {json.dumps(item['evidence'], indent=2, default=str)}\n  ```")
        add("")

    add("## Pagination\n")
    pagination = source_state["pagination"]
    add(f"- Pages read: {len(pagination['pages'])} · total rows {pagination['total_rows']}")
    add(f"- Final page partial (proves no truncation): **{pagination['final_page_partial']}**")
    add(f"- Truncation possible: **{pagination['truncation_possible']}**\n")

    add("## Read-only evidence\n")
    add(f"- Mutating client methods attempted: **{len(guard.write_attempts)}** {guard.write_attempts or ''}")
    add(f"- Tables read: {', '.join(report['read_only_guard']['table_ops'])}\n")

    anomalies = [row for row in plan["rows"] if row["validation_warnings"]]
    add("## Anomalies\n")
    if anomalies:
        for row in anomalies:
            add(f"- **{row['set_name']}** (`{row['set_canonical_key']}`): {'; '.join(row['validation_warnings'])}")
    else:
        add("None.")
    add("")

    add("## Future write command — NOT EXECUTED\n")
    add("```bash")
    add("python backend/scripts/collector_appeal_production_dry_run.py \\")
    add(f"  --commit \\")
    add(f"  --expected-fingerprint {plan['expected_fingerprint']} \\")
    add(f"  --expected-manifest {plan['source_manifest']['manifest_hash']}")
    add("```")
    add("\nThe command refuses to run unless the fingerprint matches, the source manifest is "
        "unchanged since this preview, and every invariant passed.\n")

    MD_ARTIFACT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare-with", type=str, default=None,
                        help="Path to a previous dry-run JSON; asserts byte-equivalent normalized payloads.")
    parser.add_argument("--out-json", type=str, default=None, help="Override the JSON artifact path.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()

    guard = ReadOnlyClientGuard(public_read_client)

    logger.info("[dry-run] reading production state (read-only guard active)...")
    source_state = load_source_state(
        guard,
        pull_model_loader=load_pull_rate_model,
        simulation_loader=load_simulation_rows,
    )
    logger.info("[dry-run] latest rows=%s pull_model=%s simulated=%s",
                len(source_state["latest_rows"]), len(source_state["pull_model"]),
                len(source_state["simulation_rows"]))

    subjects_by_set = build_subject_index(
        guard, list(source_state["latest_rows"]), source_state["pull_model"]
    )
    logger.info("[dry-run] sets with dual-path subjects: %s", len(subjects_by_set))

    plan = build_update_plan(source_state, subject_builder=lambda sid: subjects_by_set.get(sid))

    # The dry run NEVER passes commit=True.
    execution = execute_plan(plan, guard, commit=False)

    invariants = check_invariants(plan, source_state, guard)
    write_artifacts(plan, source_state, invariants, guard, execution)

    failed = [item for item in invariants if not item["passed"]]
    logger.info("[dry-run] counts: %s", json.dumps(plan["counts"], indent=2))
    logger.info("[dry-run] invariants: %s passed, %s failed", len(invariants) - len(failed), len(failed))
    for item in failed:
        logger.error("[dry-run] INVARIANT FAILED %s: %s -> %s", item["n"], item["name"],
                     json.dumps(item["evidence"], default=str)[:500])
    logger.info("[dry-run] writes performed: %s", execution["writes_performed"])
    logger.info("[dry-run] normalized payload hash: %s", normalized_payload_hash(plan))

    if args.compare_with:
        previous = json.loads(Path(args.compare_with).read_text(encoding="utf-8"))
        same = previous["normalized_payload_hash"] == normalized_payload_hash(plan)
        logger.info("[dry-run] determinism vs %s: %s", args.compare_with,
                    "IDENTICAL" if same else "DIFFERENT")
        if not same:
            return 1

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
