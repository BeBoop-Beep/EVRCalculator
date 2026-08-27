from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Callable, Mapping, Sequence

import numpy as np

#: v2 adds the `openingEconomics` block: spend-weighted headline ratios, the
#: P05/P25/P75 extensions to both quantile ladders, and per-era scopes. It is a
#: CONTRACT bump only - the payload grew, so a reader must be able to tell a
#: snapshot that carries those fields from one that predates them.
#:
#: The methodology and weighting versions deliberately do NOT move. The
#: statistics are still the exact empirical mixture over the persisted
#: million-outcome artifacts, and sets are still weighted equally; claiming
#: either changed would assert a difference in how the numbers were computed
#: that did not happen. Every previously published field keeps its meaning and
#: its value.
POKEMON_RIP_STATS_CONTRACT_VERSION = "pokemon-rip-stats-v2"
POKEMON_RIP_STATS_METHODOLOGY_VERSION = "exact_empirical_mixture_v1"
POKEMON_RIP_STATS_WEIGHTING_VERSION = "equal-set-empirical-v1"


class PokemonRipStatsError(ValueError):
    pass


def deterministic_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    normalized = sorted((dict(row) for row in rows), key=lambda row: (str(row.get("set_id") or row.get("setId")), json.dumps(row, sort_keys=True, default=str)))
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


#: The exact-outcome quantile ladder published for BOTH distributions. P50/P95/P99
#: predate the ladder and keep their original field names; P05/P25/P75 extend it.
#: Every one is read straight off the pooled empirical population - none is
#: interpolated from summary statistics and none is inferred from the mean.
RAW_QUANTILES = (0.05, 0.25, 0.50, 0.75, 0.95, 0.99)


def _quantiles(values: np.ndarray, qs=RAW_QUANTILES) -> list[float]:
    """All requested quantiles in ONE pass over the pooled population.

    ``overwrite_input`` lets numpy partition the buffer in place rather than
    copying 176 MB; the caller owns ``values`` and fully rewrites it before any
    later read, so the reordering is unobservable. Asking for the whole ladder
    at once also avoids re-partitioning the population once per percentile.
    """
    result = np.quantile(values, list(qs), method="linear", overwrite_input=True)
    return [float(item) for item in np.atleast_1d(result)]


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
    p05_value, p25_value, typical_value, p75_value, p95_value, p99_value = _quantiles(population)
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
    (p05_retention, p25_retention, typical_retention,
     p75_retention, p95_retention, p99_retention) = _quantiles(population)
    mean_cost = float(np.mean(costs))
    # Aggregate dollars for the spend-weighted headline ratios. These answer a
    # DIFFERENT question from `expectedRetention` below: buying one pack from
    # every set and asking what share of that basket the model returns, rather
    # than averaging each set's own return ratio. Because the sets differ in
    # price the two disagree, and the spend-weighted form is the one that
    # describes the actual basket. `expectedRetention` keeps its original
    # equal-weighted meaning for its existing consumers.
    total_cost = float(sum(costs))
    total_ev = float(sum(per_set_ev))
    modeled_return_on_spend = total_ev / total_cost
    return {"setCount": len(ordered), "outcomeCountPerSet": count, "totalSourceOutcomeCount": size,
        "meanPackCost": mean_cost, "medianPackCost": float(np.median(costs)), "expectedValue": expected_value,
        "expectedRetention": expected_retention, "chanceToBeatCost": wins / size,
        "expectedLossUnconditional": loss_total / size,
        "expectedEntertainmentCost": float(np.mean(np.asarray(costs) - np.asarray(per_set_ev))),
        "expectedEntertainmentCostRatio": 1.0 - expected_retention,
        "modeledReturnOnSpend": modeled_return_on_spend,
        "entertainmentCostShare": 1.0 - modeled_return_on_spend,
        "typicalOpeningValue": typical_value, "p95Value": p95_value, "p99Value": p99_value,
        "p05Value": p05_value, "p25Value": p25_value, "p75Value": p75_value,
        "typicalRetention": typical_retention, "p95Retention": p95_retention, "p99Retention": p99_retention,
        "p05Retention": p05_retention, "p25Retention": p25_retention, "p75Retention": p75_retention,
        "averageRetentionGivenLoss": loss_retention_sum / loss_count if loss_count else 1.0,
        "softLossShareGivenLoss": soft_count / loss_count if loss_count else 1.0,
        "hardLossProbability": hard_count / size, "onePackPerSet": {"setCount": len(ordered),
            "totalPackCost": total_cost, "totalExpectedValue": total_ev,
            "expectedEntertainmentCost": total_cost - total_ev}}


def calculate_pokemon_rip_stats(inputs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metadata = [{**dict(item), "outcome_count": int(np.asarray(item.get("outcomes")).size)} for item in inputs]
    return calculate_pokemon_rip_stats_streaming(metadata, lambda item: np.asarray(item["outcomes"], dtype=np.float64))
