"""Bounded look-ahead quantity batching for the fused V2 Best-Open search.

Research candidate, isolated from ``best_open_price_v2_fused`` so the proven
streaming control stays reproducible for A/B comparison.

What changes versus the control
-------------------------------
The control constructs each physical quantity independently
(``prepare_quantities([q])``).  This engine keeps the *identical* search order,
comparators, benchmark handling and exactness evidence, but asks the exact
independent-SINGLE-q flat-stream builder
(``build_single_q_parity_distributions``) for a bounded contiguous block of the
quantities the scan is about to consume, so the RNG/gather work is done once
per block (``N*max(q)``) instead of once per quantity (``N*sum(q)``).

What does NOT change
--------------------
* No quantity is skipped.  Bucket 1 proved no theorem permits it.
* No price binary search or branch-and-bound.
* Prices are still scored in globally descending order, one at a time.

Memory discipline
-----------------
* At most one prepared (active) candidate is resident; the previous one is
  released before the next is built.
* Blocks hold *raw* outcome vectors only.  Prepared scorers are built lazily
  when the scan actually reaches a quantity, so speculative waste costs RNG and
  row-sum work but never scorer preparation.
* At most one bounded pending block exists; it is released whole when
  exhausted, abandoned (scan jumped), or the search ends.
* Block width is the minimum of an adaptive ramp and the memory-aware policy
  ``single_q_parity_batch_width`` (outcome count, max q, memory ceiling), with
  headroom for the flat-stream workspace.

Correctness-first fallback
--------------------------
Any block failure (allocation refusal, construction exception, wrong quantity
set, wrong shape/dtype, non-finite values, preparation failure, identity
mismatch) discards the block, disables batching for the remainder of the
product and falls back to the canonical independent SINGLE-q factory.  Nothing
is approximated or fabricated; the fallback is recorded in diagnostics.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from backend.calculations.evr.best_open_price import (
    BestOpenPriceSearchError,
    PreparedCanonicalCandidate,
    quantity_price_interval_cents,
)
from backend.calculations.evr.best_open_price_v2_fused import (
    DualBestOpenPriceSearch as _FusedControlSearch,
)
from backend.calculations.evr.sealed_product_distribution import (
    DEFAULT_SINGLE_Q_BATCH_MEMORY_CEILING_BYTES,
    DEFAULT_SINGLE_Q_FLAT_DRAW_LIMIT,
    single_q_parity_batch_width,
)

PHASE_MARKET = "market"
PHASE_LEADER = "leader"
PHASE_LOW = "low"

DEFAULT_INITIAL_WIDTH = 4
DEFAULT_MAX_WIDTH = 24
_MAX_FALLBACK_REASONS = 8


@dataclass
class BoundedBatchedDualBestOpenPriceSearch(_FusedControlSearch):
    """Fused V2 dual search with bounded exact multi-q look-ahead.

    ``build_block(quantities, memory_ceiling_bytes=..., flat_draw_limit=...)``
    must return the ``build_single_q_parity_distributions`` payload
    (``{"distributions": {q: ndarray}, "meta": {...}}``).
    ``prepare_from_values(quantity, values)`` must return the prepared
    candidate for one raw outcome vector.  Without both callables the class
    degenerates to the control's canonical per-quantity behaviour.
    """

    build_block: Optional[Callable[..., Mapping[str, Any]]] = None
    prepare_from_values: Optional[Callable[[int, np.ndarray], PreparedCanonicalCandidate]] = None
    initial_width: int = DEFAULT_INITIAL_WIDTH
    max_width: int = DEFAULT_MAX_WIDTH
    memory_ceiling_bytes: int = DEFAULT_SINGLE_Q_BATCH_MEMORY_CEILING_BYTES
    flat_draw_limit: int = DEFAULT_SINGLE_Q_FLAT_DRAW_LIMIT

    _phase: str = field(default=PHASE_MARKET, init=False)
    _pending_values: Dict[int, np.ndarray] = field(default_factory=dict, init=False)
    _batching_disabled: bool = field(default=False, init=False)
    _ramp_width: int = field(default=0, init=False)
    _ramp_phase: Optional[str] = field(default=None, init=False)
    _requested_quantities: set = field(default_factory=set, init=False)
    _consumed_count: int = field(default=0, init=False)
    _consumed_from_block: int = field(default=0, init=False)
    _single_construction_count: int = field(default=0, init=False)
    _block_generated_count: int = field(default=0, init=False)
    _max_active_prepared: int = field(default=0, init=False)
    _max_block_bytes: int = field(default=0, init=False)
    _block_width_history: List[int] = field(default_factory=list, init=False)
    _fallback_reasons: List[str] = field(default_factory=list, init=False)
    _build_seconds: float = field(default=0.0, init=False)
    _prepare_seconds: float = field(default=0.0, init=False)
    _single_seconds: float = field(default=0.0, init=False)
    _draws_effective: int = field(default=0, init=False)
    _draws_legacy: int = field(default=0, init=False)
    _last_block_bytes: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.initial_width < 1 or self.max_width < 1:
            raise ValueError("batch widths must be positive")

    # ------------------------------------------------------------------ hooks
    def _score(self, price_cents: int):
        if price_cents == self.current_price_cents:
            self._phase = PHASE_MARKET
        elif price_cents > self.current_price_cents:
            self._phase = PHASE_LEADER
        else:
            self._phase = PHASE_LOW
        return super()._score(price_cents)

    def search(self) -> Dict[str, Any]:
        try:
            return super().search()
        finally:
            self._release_pending()
            self._resident_candidate = None
            self._resident_quantity = None

    # --------------------------------------------------------------- planning
    def _phase_domain(self, phase: str) -> Optional[Tuple[int, int, int]]:
        """(price_low, price_high, max_quantity) still to be scanned in a phase."""
        max_q = min(self.budget_cents, self.max_quantity_to_construct)
        if phase == PHASE_LEADER:
            low, high = self.current_price_cents + 1, self.budget_cents
            if low > high:
                return None
            return low, high, self.budget_cents // low
        if phase == PHASE_LOW:
            minimum_price = self.budget_cents // (max_q + 1) + 1
            low, high = minimum_price, self.current_price_cents - 1
            if low > high:
                return None
            return low, high, max_q
        return None

    def _plan_block(self, quantity: int) -> List[int]:
        domain = self._phase_domain(self._phase)
        if domain is None:
            return [quantity]
        price_low, price_high, max_q = domain
        if self._ramp_phase != self._phase:
            self._ramp_phase = self._phase
            self._ramp_width = self.initial_width
        n = int(self.rng_outcome_count)
        cap = self.max_width
        if n > 0:
            try:
                # Provision the flat-stream workspace as an extra "row" so the
                # builder's flat chunk is never starved by the outputs.
                cap = min(cap, single_q_parity_batch_width(
                    n, requested_width=self.max_width,
                    maximum_quantity=max(max_q, self.flat_draw_limit),
                    memory_ceiling_bytes=self.memory_ceiling_bytes,
                ))
            except (MemoryError, ValueError):
                cap = 1
        width = max(1, min(self._ramp_width, cap))
        planned = [quantity]
        q = quantity
        while len(planned) < width and q < max_q:
            q += 1
            low, high = quantity_price_interval_cents(self.budget_cents, q)
            if max(low, price_low) <= min(high, price_high):
                planned.append(q)
        self._ramp_width = min(max(self._ramp_width * 2, 1), cap if cap >= 1 else 1)
        return planned

    # --------------------------------------------------------------- building
    def _record_fallback(self, reason: str) -> None:
        self._batch_fallback_count += 1
        self._batching_disabled = True
        if len(self._fallback_reasons) < _MAX_FALLBACK_REASONS:
            self._fallback_reasons.append(reason[:200])
        self._release_pending()

    def _release_pending(self) -> None:
        self._pending_values.clear()

    def _build_single(self, quantity: int) -> PreparedCanonicalCandidate:
        """Canonical independent SINGLE-q construction (no batching)."""
        started = time.perf_counter()
        candidate = self.prepare_quantity(quantity)
        self._validate_candidate(quantity, candidate)
        elapsed = time.perf_counter() - started
        self._single_seconds += elapsed
        self._construction_seconds += elapsed
        self._single_construction_count += 1
        self._quantity_construction_count += 1
        n = int(self.rng_outcome_count)
        if quantity > 1:
            self._draws_effective += n * quantity
            self._draws_legacy += n * quantity
        return candidate

    def _validate_values(self, quantity: int, values: Any) -> np.ndarray:
        if not isinstance(values, np.ndarray) or values.ndim != 1:
            raise BestOpenPriceSearchError("quantity block returned a malformed vector")
        n = int(self.rng_outcome_count)
        if n and values.shape[0] != n:
            raise BestOpenPriceSearchError("quantity block returned the wrong outcome count")
        if values.dtype != np.float64:
            raise BestOpenPriceSearchError("quantity block returned a non-float64 vector")
        if not bool(np.isfinite(values).all()):
            raise BestOpenPriceSearchError("quantity block returned non-finite values")
        return values

    def _build_pending_block(self, quantity: int) -> bool:
        quantities = self._plan_block(quantity)
        started = time.perf_counter()
        try:
            built = self.build_block(
                quantities,
                memory_ceiling_bytes=self.memory_ceiling_bytes,
                flat_draw_limit=self.flat_draw_limit,
            )
            distributions = dict(built["distributions"])
            if set(distributions) != set(quantities):
                raise BestOpenPriceSearchError("quantity batch returned the wrong quantity set")
            for q, values in distributions.items():
                self._validate_values(q, values)
            meta = dict(built.get("meta") or {})
        except Exception as exc:  # correctness-first: never approximate
            self._build_seconds += time.perf_counter() - started
            self._construction_seconds += time.perf_counter() - started
            self._record_fallback(f"block build failed: {type(exc).__name__}: {exc}")
            return False
        elapsed = time.perf_counter() - started
        self._build_seconds += elapsed
        self._construction_seconds += elapsed
        self._pending_values = distributions
        self._batch_build_count += 1
        self._batch_quantity_count += len(quantities)
        self._block_generated_count += len(quantities)
        self._quantity_construction_count += len(quantities)
        self._max_pending = max(self._max_pending, len(quantities))
        self._block_width_history.append(len(quantities))
        block_bytes = int(meta.get("estimatedPeakConstructionBytes") or 0)
        self._last_block_bytes = block_bytes
        self._max_block_bytes = max(self._max_block_bytes, block_bytes)
        self._draws_effective += int(meta.get("effectiveRngDraws") or 0)
        self._draws_legacy += int(meta.get("legacyEquivalentRngDraws") or 0)
        return True

    def _candidate_from_block(self, quantity: int) -> Optional[PreparedCanonicalCandidate]:
        if quantity not in self._pending_values:
            # Scan left the planned block (or none exists): release it whole.
            self._release_pending()
            if not self._build_pending_block(quantity):
                return None
        values = self._pending_values.pop(quantity)
        started = time.perf_counter()
        try:
            candidate = self.prepare_from_values(quantity, values)
            self._validate_candidate(quantity, candidate)
        except Exception as exc:
            elapsed = time.perf_counter() - started
            self._prepare_seconds += elapsed
            self._construction_seconds += elapsed
            self._record_fallback(f"prepare from block failed: {type(exc).__name__}: {exc}")
            return None
        finally:
            del values
        elapsed = time.perf_counter() - started
        self._prepare_seconds += elapsed
        self._construction_seconds += elapsed
        self._consumed_from_block += 1
        return candidate

    def _candidate(self, quantity: int) -> PreparedCanonicalCandidate:
        if self._resident_quantity == quantity and self._resident_candidate is not None:
            return self._resident_candidate
        # Release the active prepared quantity before building its successor.
        self._resident_candidate = None
        self._resident_quantity = None
        self._requested_quantities.add(quantity)
        candidate: Optional[PreparedCanonicalCandidate] = None
        if (
            self.build_block is not None
            and self.prepare_from_values is not None
            and not self._batching_disabled
        ):
            candidate = self._candidate_from_block(quantity)
        if candidate is None:
            candidate = self._build_single(quantity)
        self._constructed_quantities.add(quantity)
        self._consumed_count += 1
        self._resident_candidate = candidate
        self._resident_quantity = quantity
        self._max_resident_quantities = 1
        self._max_active_prepared = 1
        return candidate

    # ------------------------------------------------------------ diagnostics
    def _diagnostics(self, rip, financial) -> Dict[str, Any]:
        diagnostics = super()._diagnostics(rip, financial)
        speculative = max(0, self._block_generated_count - self._consumed_from_block)
        diagnostics.update({
            "fusedStreaming": True,
            "boundedBatched": True,
            "uniqueQuantitiesRequested": len(self._requested_quantities),
            "quantityConstructionCount": self._quantity_construction_count,
            "quantitiesConsumed": self._consumed_count,
            "quantitiesConsumedFromBlocks": self._consumed_from_block,
            "singleQuantityConstructions": self._single_construction_count,
            "quantityBatchBuilds": self._batch_build_count,
            "quantityBatchQuantities": self._block_generated_count,
            "quantityBatchFallbacks": self._batch_fallback_count,
            "speculativeQuantitiesGeneratedNotConsumed": speculative,
            "maximumPendingBatchCandidates": self._max_pending,
            "maximumActivePreparedQuantities": self._max_active_prepared,
            "maximumResidentSharedQuantities": self._max_active_prepared,
            "maximumEstimatedBatchBytes": self._max_block_bytes,
            "blockWidths": list(self._block_width_history),
            "physicalQuantityConstructionSeconds": self._build_seconds + self._single_seconds,
            "blockBuildSeconds": self._build_seconds,
            "singleFallbackConstructionSeconds": self._single_seconds,
            "preparedScorerSeconds": self._prepare_seconds,
            "quantityConstructionSeconds": self._construction_seconds,
            "effectiveRngDraws": self._draws_effective,
            "legacyEquivalentRngDraws": self._draws_legacy,
            "fallbackReasons": list(self._fallback_reasons),
            "batchingDisabledAfterFallback": self._batching_disabled,
        })
        return diagnostics
