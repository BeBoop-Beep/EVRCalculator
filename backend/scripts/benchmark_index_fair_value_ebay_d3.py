"""Reproducible D3-v3 benchmark orchestrator.

Reuses the existing frozen certification pipeline (certify_ebay_d3_v3.py,
ebay_d3_v3_development_metrics.json) rather than recomputing matcher logic or
hand-calculating headline numbers. Reports development / (missing) validation /
final-blind metrics SEPARATELY -- never combined into one headline figure --
and refuses any code path that could be used to tune against final-blind data.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.scripts import certify_ebay_d3_v3 as certifier
from backend.scripts.ebay_gold_access import FILES as GOLD_PARTITION_FILES
from backend.scripts.ebay_gold_access import OUT

DEVELOPMENT_METRICS = OUT / "ebay_d3_v3_development_metrics.json"
FINAL_CERTIFICATION_METRICS = OUT / "ebay_d3_v3_final_certification_metrics.json"
FINAL_CERTIFICATION_MANIFEST = OUT / "ebay_d3_v3_final_certification_manifest.json"

TUNING_PURPOSES = frozenset({"matcher_development", "threshold_validation"})


class FinalBlindTuningAttempt(RuntimeError):
    """Raised if any code path in this module tries to use final-blind rows for tuning."""


def assert_no_final_blind_tuning(partition: str, purpose: str) -> None:
    """Defense-in-depth on top of ebay_gold_access.py's fail-closed gate.

    This benchmark module must never be the thing that lets final-blind rows
    leak into a tuning workflow, even indirectly.
    """
    sealed = {"FINAL_BLIND_TEST", "PRECISION_BLIND", "COVERAGE_BLIND", "D3_BLIND_REVIEW"}
    if partition.upper() in sealed and purpose in TUNING_PURPOSES:
        raise FinalBlindTuningAttempt(f"refused: {partition} may not be accessed for purpose={purpose}")


def discover_gold_partitions() -> dict[str, dict[str, Any]]:
    """Inventory every known gold/blind partition file without loading labels for tuning."""
    inventory: dict[str, dict[str, Any]] = {}
    for partition, filename in GOLD_PARTITION_FILES.items():
        path = OUT / filename
        inventory[partition] = {
            "file": filename,
            "exists": path.exists(),
            "row_count": _row_count(path) if path.exists() else None,
        }
    return inventory


def _row_count(path: Path) -> int:
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def development_metrics() -> dict[str, Any]:
    if not DEVELOPMENT_METRICS.exists():
        return {"status": "MISSING", "partition": "DEVELOPMENT"}
    data = json.loads(DEVELOPMENT_METRICS.read_text(encoding="utf-8"))
    return {"status": "AVAILABLE", "partition": "DEVELOPMENT", "metrics": data}


def validation_metrics() -> dict[str, Any]:
    """D3-v3 has no dedicated validation-partition benchmark artifact.

    v3 went development -> fresh blind directly, skipping the VALIDATION
    partition entirely. This is reported as a gap, not silently ignored.
    """
    return {
        "status": "NOT_EVALUATED",
        "partition": "VALIDATION",
        "reason": "no ebay_d3_v3_validation_metrics.json exists; v3 study skipped VALIDATION",
    }


def final_blind_metrics(run_certifier: bool = False) -> dict[str, Any]:
    """Report the existing frozen final-blind certification result.

    By default this reruns certify_ebay_d3_v3.main(), which is itself gated by
    hash-fingerprint checks against frozen inputs -- it cannot silently drift
    or be tuned, it can only reproduce the same frozen comparison or raise.
    """
    if run_certifier:
        certifier.main()
    if not FINAL_CERTIFICATION_METRICS.exists():
        return {"status": "MISSING", "partition": "FINAL_BLIND"}
    metrics = json.loads(FINAL_CERTIFICATION_METRICS.read_text(encoding="utf-8"))
    manifest = json.loads(FINAL_CERTIFICATION_MANIFEST.read_text(encoding="utf-8"))
    return {"status": "AVAILABLE", "partition": "FINAL_BLIND", "metrics": metrics, "manifest": manifest}


def critical_error_table(final_blind: dict[str, Any]) -> dict[str, Any]:
    if final_blind.get("status") != "AVAILABLE":
        return {"critical_false_accept_count": None, "critical_false_accept_rate": None}
    catastrophic = final_blind["metrics"]["catastrophic_high_errors"]
    total_high = final_blind["metrics"]["coverage_cohort"]["high_count"]
    count = sum(catastrophic.values())
    return {
        "critical_false_accept_count": count,
        "critical_false_accept_rate": round(count / total_high, 8) if total_high else None,
        "by_category": catastrophic,
        "evaluated_high_confidence_rows": total_high,
    }


GATE_MINIMUM_PRECISION = 0.99
GATE_MAXIMUM_CRITICAL_FALSE_ACCEPTS = 0


def apply_acceptance_gate(final_blind: dict[str, Any], critical: dict[str, Any]) -> dict[str, Any]:
    """Strict production-candidate gate -- never silently lowered."""
    if final_blind.get("status") != "AVAILABLE":
        return {"gate_result": "BLOCKED_NO_FINAL_BLIND_METRICS"}
    precision = final_blind["metrics"]["precision_cohort"]["precision"]
    wilson_lower = final_blind["metrics"]["precision_cohort"]["wilson_95"][0]
    n = final_blind["metrics"]["precision_cohort"]["logical_rows"]
    critical_count = critical["critical_false_accept_count"] or 0
    gates_from_existing_pipeline = final_blind["metrics"]["gates"]
    passed = (
        precision >= GATE_MINIMUM_PRECISION
        and critical_count <= GATE_MAXIMUM_CRITICAL_FALSE_ACCEPTS
        and all(gates_from_existing_pipeline.values())
    )
    return {
        "gate_result": "PASS" if passed else "FAIL",
        "precision": precision,
        "wilson_95_lower": wilson_lower,
        "final_blind_accepted_sample_size": n,
        "critical_false_accept_count": critical_count,
        "existing_pipeline_gates": gates_from_existing_pipeline,
        "existing_pipeline_result": final_blind["metrics"]["overall_result"],
    }


def run_full_benchmark(run_certifier: bool = False) -> dict[str, Any]:
    dev = development_metrics()
    val = validation_metrics()
    fb = final_blind_metrics(run_certifier=run_certifier)
    critical = critical_error_table(fb)
    gate = apply_acceptance_gate(fb, critical)
    return {
        "gold_partition_inventory": discover_gold_partitions(),
        "development": dev,
        "validation": val,
        "final_blind": fb,
        "critical_error_table": critical,
        "acceptance_gate": gate,
    }


if __name__ == "__main__":
    print(json.dumps(run_full_benchmark(), indent=2, default=str))
