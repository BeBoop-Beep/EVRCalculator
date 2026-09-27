"""Server-side registry for the customer-facing RIP Benchmark contract.

The database RPC deliberately keeps explicit benchmark/calibration arguments.
Browser callers do not: the active Overall authority must map to an explicitly
registered contract, and an unknown future model must fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.desirability.scoring_config import OVERALL_RIP_V12_VERSION


BENCHMARK_KEY = "pokemon_equal_weight_eligible_sets_v1"
V12_CALIBRATION_VERSION = "rip_benchmark_v1_fin5_chase10_collector10_overall5"
ACTIVE_OVERALL_VIEW = "pokemon_overall_rip_active_v"


class BenchmarkContractUnavailable(RuntimeError):
    """The active model family has no customer benchmark calibration."""


@dataclass(frozen=True)
class BenchmarkContract:
    benchmark_key: str
    calibration_version: str
    overall_model_version: str


_REGISTRY = {
    OVERALL_RIP_V12_VERSION: BenchmarkContract(
        benchmark_key=BENCHMARK_KEY,
        calibration_version=V12_CALIBRATION_VERSION,
        overall_model_version=OVERALL_RIP_V12_VERSION,
    ),
}


def contract_for_overall_model(model_version: str) -> BenchmarkContract:
    """Resolve only exact registered identities; never family-prefix fallback."""
    contract = _REGISTRY.get(str(model_version))
    if contract is None:
        raise BenchmarkContractUnavailable(
            f"no canonical RIP Benchmark calibration is registered for active model {model_version!r}"
        )
    return contract


def resolve_active_contract(client: Any) -> BenchmarkContract:
    rows = list(
        client.table(ACTIVE_OVERALL_VIEW)
        .select("model_version")
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows or not rows[0].get("model_version"):
        raise BenchmarkContractUnavailable("active Overall RIP authority is unavailable")
    return contract_for_overall_model(str(rows[0]["model_version"]))
