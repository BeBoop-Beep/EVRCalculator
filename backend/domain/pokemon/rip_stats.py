from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

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
    return float(np.quantile(values, q, method="linear"))


def calculate_pokemon_rip_stats(inputs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not inputs:
        raise PokemonRipStatsError("at least one eligible set is required")
    seen: set[str] = set()
    count: int | None = None
    costs: list[float] = []
    vectors: list[np.ndarray] = []
    for item in inputs:
        set_id = str(item.get("set_id") or item.get("setId") or "").strip()
        if not set_id or set_id in seen:
            raise PokemonRipStatsError("set membership must be unique and non-empty")
        seen.add(set_id)
        cost = float(item.get("pack_cost") if item.get("pack_cost") is not None else item.get("packCost"))
        vector = np.asarray(item.get("outcomes"), dtype=np.float64)
        if not math.isfinite(cost) or cost <= 0:
            raise PokemonRipStatsError(f"invalid pack cost for {set_id}")
        if vector.ndim != 1 or vector.size == 0 or not np.isfinite(vector).all() or (vector < 0).any():
            raise PokemonRipStatsError(f"invalid exact outcome vector for {set_id}")
        if count is None:
            count = int(vector.size)
        elif vector.size != count:
            raise PokemonRipStatsError("equal-set empirical v1 requires equal outcome counts")
        costs.append(cost)
        vectors.append(vector)
    absolute = np.empty(len(vectors) * int(count or 0), dtype=np.float64)
    offset = 0
    for vector in vectors:
        absolute[offset:offset + vector.size] = vector
        offset += vector.size
    expected_value = float(absolute.mean())
    typical_value, p95_value, p99_value = (_quantile(absolute, q) for q in (.50, .95, .99))
    wins = 0
    loss_total = 0.0
    offset = 0
    for cost, vector in zip(costs, vectors):
        end = offset + vector.size
        wins += int(np.count_nonzero(vector >= cost))
        loss_total += float(np.maximum(cost - vector, 0.0).sum())
        # Reuse the aggregate dollar buffer after its metrics/quantiles have
        # been calculated; this avoids a second population-sized allocation.
        absolute[offset:end] = vector / cost
        offset = end
    retention = absolute
    losses = retention < 1.0
    hard_losses = retention < 0.50
    soft_losses = (retention >= 0.50) & losses
    expected_retention = float(retention.mean())
    expected_loss = loss_total / retention.size
    mean_cost = float(np.mean(costs))
    per_set_ev = [float(vector.mean()) for vector in vectors]
    entertainment_cost = float(np.mean(np.asarray(costs) - np.asarray(per_set_ev)))
    return {
        "setCount": len(inputs), "outcomeCountPerSet": count,
        "totalSourceOutcomeCount": int(absolute.size), "meanPackCost": mean_cost,
        "medianPackCost": float(np.median(costs)), "expectedValue": expected_value,
        "expectedRetention": expected_retention, "chanceToBeatCost": wins / retention.size,
        "expectedLossUnconditional": expected_loss, "expectedEntertainmentCost": entertainment_cost,
        "expectedEntertainmentCostRatio": 1.0 - expected_retention,
        "typicalOpeningValue": typical_value, "p95Value": p95_value,
        "p99Value": p99_value, "typicalRetention": _quantile(retention, 0.50),
        "p95Retention": _quantile(retention, 0.95), "p99Retention": _quantile(retention, 0.99),
        "averageRetentionGivenLoss": float(retention[losses].mean()) if losses.any() else 0.0,
        "softLossShareGivenLoss": float(soft_losses.sum() / losses.sum()) if losses.any() else 0.0,
        "hardLossProbability": float(hard_losses.mean()), "onePackPerSet": {
            "setCount": len(inputs), "totalPackCost": float(sum(costs)),
            "totalExpectedValue": float(sum(per_set_ev)), "expectedEntertainmentCost": float(sum(costs) - sum(per_set_ev)),
        },
    }
