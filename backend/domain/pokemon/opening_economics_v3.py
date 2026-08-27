from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

CONTRACT_VERSION = "pokemon-rip-stats-v3"
METHODOLOGY_VERSION = "hierarchical_product_per_pack_empirical_v1"
WEIGHTING_VERSION = "equal-set_equal-family_equal-sku-v1"
QUANTILES = tuple(i / 100 for i in range(1, 100)) + (0.995, 0.999)


class OpeningEconomicsV3Error(ValueError):
    pass


def _positive(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise OpeningEconomicsV3Error(f"{field} must be positive") from exc
    if not math.isfinite(result) or result <= 0:
        raise OpeningEconomicsV3Error(f"{field} must be positive")
    return result


def normalize_product(row: Mapping[str, Any]) -> dict[str, Any]:
    product_id = str(row.get("sealed_product_id") or "").strip()
    family = str(row.get("product_family") or "").strip()
    set_id = str(row.get("set_id") or "").strip()
    if not product_id or not family or not set_id:
        raise OpeningEconomicsV3Error("product id, family, and set id are required")
    pack_count = _positive(row.get("pack_count"), "pack_count")
    random_count = row.get("random_pack_count")
    if random_count is not None and _positive(random_count, "random_pack_count") != pack_count:
        raise OpeningEconomicsV3Error(f"pack-count mismatch for {product_id}")
    price = _positive(row.get("product_market_cost"), "product_market_cost")
    expected = _positive(row.get("expected_value"), "expected_value")
    return {
        **dict(row), "sealed_product_id": product_id, "product_family": family,
        "set_id": set_id, "normalization_pack_count": int(pack_count),
        "cost_per_pack": price / pack_count, "expected_value_per_pack": expected / pack_count,
        "entertainment_cost_per_pack": (price - expected) / pack_count,
        "modeled_return_ratio": expected / price,
        "entertainment_cost_share": (price - expected) / price,
    }


def assign_hierarchical_weights(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_product(row) for row in rows]
    sets = sorted({row["set_id"] for row in normalized})
    if not sets:
        raise OpeningEconomicsV3Error("at least one product is required")
    families = {(set_id, row["product_family"]) for set_id in sets for row in normalized if row["set_id"] == set_id}
    family_counts = {set_id: sum(1 for key in families if key[0] == set_id) for set_id in sets}
    sku_counts = {(set_id, family): sum(1 for row in normalized if row["set_id"] == set_id and row["product_family"] == family) for set_id, family in families}
    result = []
    for row in normalized:
        weight = 1.0 / len(sets) / family_counts[row["set_id"]] / sku_counts[(row["set_id"], row["product_family"])]
        result.append({**row, "weight": weight})
    if not math.isclose(sum(row["weight"] for row in result), 1.0, abs_tol=1e-12):
        raise OpeningEconomicsV3Error("hierarchical weights do not sum to one")
    return result


@dataclass
class _Component:
    path: Path
    count: int
    weight: float
    cost_per_pack: float
    owns_file: bool = True


class WeightedEmpiricalMixture:
    """Disk-backed weighted mixture; only one product vector is resident at a time."""

    def __init__(self, directory: str | os.PathLike[str] | None = None):
        self._owned = directory is None
        self.directory = Path(directory or tempfile.mkdtemp(prefix="pokemon-opening-v3-"))
        self.directory.mkdir(parents=True, exist_ok=True)
        self.components: list[_Component] = []

    def add(self, values: Any, *, weight: float, cost_per_pack: float) -> None:
        vector = np.asarray(values, dtype=np.float64)
        if vector.ndim != 1 or not vector.size or not np.isfinite(vector).all() or (vector < 0).any():
            raise OpeningEconomicsV3Error("invalid product outcome vector")
        if not math.isfinite(weight) or weight <= 0 or not math.isfinite(cost_per_pack) or cost_per_pack <= 0:
            raise OpeningEconomicsV3Error("invalid mixture component metadata")
        path = self.directory / f"component-{len(self.components):04d}.npy"
        sorted_values = np.sort(vector)
        np.save(path, sorted_values, allow_pickle=False)
        self.components.append(_Component(path, vector.size, float(weight), float(cost_per_pack), True))

    def add_path(self, path: str | os.PathLike[str], *, count: int, weight: float, cost_per_pack: float) -> None:
        """Reference an already sorted vector owned by another mixture."""
        self.components.append(_Component(Path(path), int(count), float(weight), float(cost_per_pack), False))

    def _cdf(self, value: float, *, normalized: bool, side: str = "right") -> float:
        total = 0.0
        for component in self.components:
            vector = np.load(component.path, mmap_mode="r", allow_pickle=False)
            threshold = value * component.cost_per_pack if normalized else value
            total += component.weight * int(np.searchsorted(vector, threshold, side=side)) / component.count
        return total

    def quantile(self, q: float, *, normalized: bool = False) -> float:
        if not self.components or not 0 <= q <= 1:
            raise OpeningEconomicsV3Error("invalid quantile request")
        candidates: list[float] = []
        # The inverse ECDF must return an observed boundary. A heap merge would
        # be expensive for 138M outcomes; binary search locates the boundary,
        # then predecessor/successor searches refine it to an observed value.
        lows, highs = [], []
        for component in self.components:
            vector = np.load(component.path, mmap_mode="r", allow_pickle=False)
            scale = component.cost_per_pack if normalized else 1.0
            lows.append(float(vector[0]) / scale); highs.append(float(vector[-1]) / scale)
        lo, hi = min(lows), max(highs)
        for _ in range(64):
            mid = (lo + hi) / 2
            if self._cdf(mid, normalized=normalized) >= q: hi = mid
            else: lo = mid
        for component in self.components:
            vector = np.load(component.path, mmap_mode="r", allow_pickle=False)
            threshold = hi * component.cost_per_pack if normalized else hi
            index = min(int(np.searchsorted(vector, threshold, side="left")), component.count - 1)
            candidates.append(float(vector[index]) / (component.cost_per_pack if normalized else 1.0))
        valid = sorted(value for value in candidates if self._cdf(value, normalized=normalized) >= q)
        if not valid:
            raise OpeningEconomicsV3Error("quantile boundary could not be refined")
        return valid[0]

    def quantiles(self, qs: Iterable[float] = QUANTILES, *, normalized: bool = False) -> dict[str, float]:
        requested = np.asarray(list(qs), dtype=np.float64)
        if not self.components or requested.size == 0 or (requested < 0).any() or (requested > 1).any():
            raise OpeningEconomicsV3Error("invalid quantile request")
        lows, highs = [], []
        for component in self.components:
            vector = np.load(component.path, mmap_mode="r", allow_pickle=False)
            scale = component.cost_per_pack if normalized else 1.0
            lows.append(float(vector[0]) / scale); highs.append(float(vector[-1]) / scale)
        lo = np.full(requested.shape, min(lows)); hi = np.full(requested.shape, max(highs))
        # All percentiles share each component scan. This is ~100x cheaper than
        # locating P01..P99 independently while preserving the same ECDF.
        for _ in range(56):
            mid = (lo + hi) / 2; cdf = np.zeros(requested.shape)
            for component in self.components:
                vector = np.load(component.path, mmap_mode="r", allow_pickle=False)
                thresholds = mid * component.cost_per_pack if normalized else mid
                cdf += component.weight * np.searchsorted(vector, thresholds, side="right") / component.count
            crossed = cdf >= requested
            hi = np.where(crossed, mid, hi); lo = np.where(crossed, lo, mid)
        results = []
        for index, q in enumerate(requested):
            candidates = []
            for component in self.components:
                vector = np.load(component.path, mmap_mode="r", allow_pickle=False)
                threshold = hi[index] * component.cost_per_pack if normalized else hi[index]
                position = min(int(np.searchsorted(vector, threshold, side="left")), component.count - 1)
                candidates.append(float(vector[position]) / (component.cost_per_pack if normalized else 1.0))
            valid = sorted(value for value in candidates if self._cdf(value, normalized=normalized) >= q)
            if not valid: raise OpeningEconomicsV3Error("quantile boundary could not be refined")
            results.append(valid[0])
        return {percentile_key(float(q)): value for q, value in zip(requested, results)}

    def recovery_probability(self) -> float:
        # >= boundary: subtract strict-less-than CDF.
        return 1.0 - self._cdf(1.0, normalized=True, side="left")

    def cleanup(self) -> None:
        for component in self.components:
            if component.owns_file:
                component.path.unlink(missing_ok=True)
        self.components.clear()
        if self._owned:
            try: self.directory.rmdir()
            except OSError: pass

    def __enter__(self): return self
    def __exit__(self, *_): self.cleanup()


def percentile_key(q: float) -> str:
    value = q * 100
    return "p" + (str(int(value)).zfill(2) if value.is_integer() else str(value).replace(".", "_"))


def aggregate_scalars(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    weighted = assign_hierarchical_weights(rows)
    avg_cost = sum(row["weight"] * row["cost_per_pack"] for row in weighted)
    avg_ev = sum(row["weight"] * row["expected_value_per_pack"] for row in weighted)
    avg_entertainment = sum(row["weight"] * row["entertainment_cost_per_pack"] for row in weighted)
    return_on_spend = avg_ev / avg_cost
    mean_retention = sum(row["weight"] * row["modeled_return_ratio"] for row in weighted)
    probabilities = []
    for row in weighted:
        try: probability = float(row.get("chance_to_recover_cost"))
        except (TypeError, ValueError) as exc: raise OpeningEconomicsV3Error("invalid chance_to_recover_cost") from exc
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise OpeningEconomicsV3Error("invalid chance_to_recover_cost")
        probabilities.append((row["weight"], probability))
    recovery = sum(weight * probability for weight, probability in probabilities)
    if not math.isclose(avg_entertainment, avg_cost - avg_ev, abs_tol=1e-9):
        raise OpeningEconomicsV3Error("entertainment-cost invariant failed")
    if not math.isclose(avg_entertainment / avg_cost, 1 - return_on_spend, abs_tol=1e-9):
        raise OpeningEconomicsV3Error("entertainment-share invariant failed")
    return {"averageCostPerPack": avg_cost, "averageModelBreakEvenPerPack": avg_ev,
            "averageEntertainmentCostPerPack": avg_entertainment,
            "modeledReturnOnSpend": return_on_spend, "entertainmentCostShare": 1 - return_on_spend,
            "meanOutcomeRetention": mean_retention, "chanceToRecoverCost": recovery}


def build_scope(rows: Sequence[Mapping[str, Any]], component_paths: Mapping[str, tuple[str | os.PathLike[str], int]], *, qs: Iterable[float] = QUANTILES) -> dict[str, Any]:
    weighted = assign_hierarchical_weights(rows)
    scalars = aggregate_scalars(rows)
    mixture = WeightedEmpiricalMixture(directory=Path(next(iter(component_paths.values()))[0]).parent)
    try:
        for row in weighted:
            path, count = component_paths[row["sealed_product_id"]]
            mixture.add_path(path, count=count, weight=row["weight"], cost_per_pack=row["cost_per_pack"])
        raw = mixture.quantiles(qs)
        returns = mixture.quantiles(qs, normalized=True)
        empirical_recovery = mixture.recovery_probability()
        if not math.isclose(empirical_recovery, scalars["chanceToRecoverCost"], abs_tol=1e-9):
            raise OpeningEconomicsV3Error("recovery distribution invariant failed")
        return {**scalars, "typicalOpeningPerPack": raw["p50"], "typicalRetention": returns["p50"],
                "valuePerPackPercentiles": raw, "normalizedReturnPercentiles": returns}
    finally:
        mixture.cleanup()
