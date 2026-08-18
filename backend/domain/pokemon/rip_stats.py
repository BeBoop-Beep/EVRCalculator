from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Callable, Mapping, Sequence

import numpy as np

POKEMON_RIP_STATS_CONTRACT_VERSION = "pokemon-rip-stats-v1"
POKEMON_RIP_STATS_METHODOLOGY_VERSION = "exact_empirical_mixture_v1"
POKEMON_RIP_STATS_WEIGHTING_VERSION = "equal-set-empirical-v1"


class PokemonRipStatsError(ValueError):
    pass


def deterministic_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    normalized = sorted((dict(row) for row in rows), key=lambda row: (str(row.get("set_id") or row.get("setId")), json.dumps(row, sort_keys=True, default=str)))
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _quantile(values: np.ndarray, q: float) -> float:
    return float(np.quantile(values, q, method="linear", overwrite_input=True))


def calculate_pokemon_rip_stats_streaming(
    inputs: Sequence[Mapping[str, Any]], load_outcomes: Callable[[Mapping[str, Any]], np.ndarray]
) -> dict[str, Any]:
    """Calculate with one reusable population buffer and one loaded set at a time."""
    if not inputs:
        raise PokemonRipStatsError("at least one eligible set is required")
    ordered = sorted(inputs, key=lambda item: str(item.get("set_id") or item.get("setId") or ""))
    seen: set[str] = set()
    costs: list[float] = []
    count: int | None = None
    for item in ordered:
        set_id = str(item.get("set_id") or item.get("setId") or "").strip()
        cost = float(item.get("pack_cost") if item.get("pack_cost") is not None else item.get("packCost"))
        item_count = int(item.get("outcome_count") or item.get("outcomeCount") or 0)
        if not set_id or set_id in seen:
            raise PokemonRipStatsError("set membership must be unique and non-empty")
        if not math.isfinite(cost) or cost <= 0 or item_count <= 0:
            raise PokemonRipStatsError(f"invalid metadata for {set_id}")
        if count is None:
            count = item_count
        elif item_count != count:
            raise PokemonRipStatsError("equal-set empirical v1 requires equal outcome counts")
        seen.add(set_id); costs.append(cost)
    population = np.empty(len(ordered) * int(count or 0), dtype=np.float64)
    wins = 0; loss_total = 0.0; per_set_ev: list[float] = []
    for index, (item, cost) in enumerate(zip(ordered, costs)):
        vector = np.asarray(load_outcomes(item), dtype=np.float64)
        if vector.ndim != 1 or vector.size != count or not np.isfinite(vector).all() or (vector < 0).any():
            raise PokemonRipStatsError(f"invalid exact outcome vector for {item.get('set_id')}")
        start, end = index * int(count), (index + 1) * int(count)
        population[start:end] = vector
        wins += int(np.count_nonzero(vector >= cost))
        loss_total += float(np.maximum(cost - vector, 0.0).sum())
        per_set_ev.append(float(vector.mean()))
        del vector
    expected_value = float(population.mean())
    typical_value, p95_value, p99_value = (_quantile(population, q) for q in (.50, .95, .99))
    retention_sum = 0.0; loss_retention_sum = 0.0; loss_count = 0; soft_count = 0; hard_count = 0
    for index, (item, cost) in enumerate(zip(ordered, costs)):
        vector = np.asarray(load_outcomes(item), dtype=np.float64)
        if vector.ndim != 1 or vector.size != count or not np.isfinite(vector).all() or (vector < 0).any():
            raise PokemonRipStatsError(f"invalid exact outcome vector for {item.get('set_id')}")
        start, end = index * int(count), (index + 1) * int(count)
        np.divide(vector, cost, out=population[start:end])
        chunk = population[start:end]
        retention_sum += float(chunk.sum())
        losing = chunk < 1.0
        chunk_loss_count = int(np.count_nonzero(losing))
        loss_count += chunk_loss_count
        if chunk_loss_count:
            loss_retention_sum += float(chunk[losing].sum())
        hard_count += int(np.count_nonzero(chunk < 0.50))
        soft_count += int(np.count_nonzero((chunk >= 0.50) & losing))
        del losing, chunk, vector
    size = population.size
    expected_retention = retention_sum / size
    typical_retention, p95_retention, p99_retention = (_quantile(population, q) for q in (.50, .95, .99))
    mean_cost = float(np.mean(costs))
    return {"setCount": len(ordered), "outcomeCountPerSet": count, "totalSourceOutcomeCount": size,
        "meanPackCost": mean_cost, "medianPackCost": float(np.median(costs)), "expectedValue": expected_value,
        "expectedRetention": expected_retention, "chanceToBeatCost": wins / size,
        "expectedLossUnconditional": loss_total / size,
        "expectedEntertainmentCost": float(np.mean(np.asarray(costs) - np.asarray(per_set_ev))),
        "expectedEntertainmentCostRatio": 1.0 - expected_retention,
        "typicalOpeningValue": typical_value, "p95Value": p95_value, "p99Value": p99_value,
        "typicalRetention": typical_retention, "p95Retention": p95_retention, "p99Retention": p99_retention,
        "averageRetentionGivenLoss": loss_retention_sum / loss_count if loss_count else 1.0,
        "softLossShareGivenLoss": soft_count / loss_count if loss_count else 1.0,
        "hardLossProbability": hard_count / size, "onePackPerSet": {"setCount": len(ordered),
            "totalPackCost": float(sum(costs)), "totalExpectedValue": float(sum(per_set_ev)),
            "expectedEntertainmentCost": float(sum(costs) - sum(per_set_ev))}}


def calculate_pokemon_rip_stats(inputs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metadata = [{**dict(item), "outcome_count": int(np.asarray(item.get("outcomes")).size)} for item in inputs]
    return calculate_pokemon_rip_stats_streaming(metadata, lambda item: np.asarray(item["outcomes"], dtype=np.float64))
