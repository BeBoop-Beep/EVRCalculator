"""Bucket 3 candidate: Bucket 2 bounded batching + lifecycle accounting + consumption-aware ramp.

Built beside ``best_open_price_v2_fused_batched`` (the Bucket 2 control, untouched).

Findings that shaped this module (see docs/research/BEST_OPEN_PRICE_V2_PREPARED_SCORER_OPTIMIZATION.md)
-----------------------------------------------------------------------------------------------
* Bucket 2 already prepares a quantity's canonical distribution lazily, only
  when the scan consumes it: speculative quantities never reach
  ``PreparedFinancialRipDistribution.prepare``.  There is no eager
  speculative preparation to remove.
* Prepared-scorer cost is a property of ``prepare`` itself (sort + partitions),
  addressed by ``PreparedFinancialRipDistribution.prepare_exact_accelerated``
  which the caller supplies through ``prepare_from_values``.
* This subclass adds (a) exact lifecycle accounting of every block (built,
  consumed, discarded unprepared, raw/prepared bytes), (b) an optional
  research trace (per block and per q request; ``None`` means zero overhead),
  (c) an opt-in consumption-aware ramp: a block that is abandoned with
  unconsumed quantities resets (``reset``) or halves (``halve``) the next width.

Nothing here changes search order, price traversal, comparators, exactness or
the candidate values: the widths only choose how many exact single-q vectors are
built per physical block.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from backend.calculations.evr.best_open_price import PreparedCanonicalCandidate
from backend.calculations.evr.best_open_price_v2_fused_batched import (
    BoundedBatchedDualBestOpenPriceSearch as _Bucket2Search,
)


@dataclass
class PreparedLifecycleBatchedDualBestOpenPriceSearch(_Bucket2Search):
    abandon_policy: str = "none"  # "none" | "reset" | "halve"
    trace: Optional[List[Dict[str, Any]]] = None
    measure_speculative_marginal: bool = False

    _block: Optional[Dict[str, Any]] = field(default=None, init=False)
    _blocks_finalized: int = field(default=0, init=False)
    _blocks_abandoned: int = field(default=0, init=False)
    _blocks_fully_consumed: int = field(default=0, init=False)
    _ramp_resets: int = field(default=0, init=False)
    _prepared_built: int = field(default=0, init=False)
    _discarded_unprepared: int = field(default=0, init=False)
    _raw_pending_bytes: int = field(default=0, init=False)
    _max_raw_pending_bytes: int = field(default=0, init=False)
    _max_prepared_bytes: int = field(default=0, init=False)
    _max_pending_plus_prepared_bytes: int = field(default=0, init=False)
    _prepared_active_bytes: int = field(default=0, init=False)
    _consumed_build_seconds_est: float = field(default=0.0, init=False)
    _speculative_build_seconds_est: float = field(default=0.0, init=False)
    _marginal_speculative_seconds: float = field(default=0.0, init=False)
    _marginal_measured_blocks: int = field(default=0, init=False)
    _last_block_width: int = field(default=0, init=False)

    # ---------------------------------------------------------------- blocks
    def _finalize_block(self, *, abandoned: bool) -> None:
        block = self._block
        if block is None:
            return
        self._block = None
        planned = block["planned"]
        consumed = block["consumed"]
        unconsumed = [q for q in planned if q not in consumed]
        self._blocks_finalized += 1
        weight_total = float(sum(planned)) or 1.0
        spec_share = float(sum(unconsumed)) / weight_total
        self._speculative_build_seconds_est += block["seconds"] * spec_share
        self._consumed_build_seconds_est += block["seconds"] * (1.0 - spec_share)
        if unconsumed:
            self._discarded_unprepared += len(unconsumed)
            self._blocks_abandoned += 1
            self._apply_abandon_policy(block)
        else:
            self._blocks_fully_consumed += 1
        marginal = None
        if self.measure_speculative_marginal and unconsumed:
            marginal = self._measure_marginal(block)
        if self.trace is not None:
            self.trace.append({
                "kind": "block", "phase": block["phase"], "planned": list(planned),
                "consumed": sorted(consumed), "seconds": block["seconds"],
                "abandoned": bool(unconsumed), "marginalSpeculativeSeconds": marginal,
            })

    def _measure_marginal(self, block: Dict[str, Any]) -> Optional[float]:
        """Research-only: exact speculative cost = T(full block) - T(consumed-only block)."""
        consumed = sorted(block["consumed"])
        if not consumed:
            self._marginal_speculative_seconds += block["seconds"]
            self._marginal_measured_blocks += 1
            return block["seconds"]
        started = time.perf_counter()
        try:
            self.build_block(
                consumed, memory_ceiling_bytes=self.memory_ceiling_bytes,
                flat_draw_limit=self.flat_draw_limit,
            )
        except Exception:
            return None
        only = time.perf_counter() - started
        marginal = max(0.0, block["seconds"] - only)
        self._marginal_speculative_seconds += marginal
        self._marginal_measured_blocks += 1
        return marginal

    def _apply_abandon_policy(self, block: Dict[str, Any]) -> None:
        if self.abandon_policy == "none":
            return
        width = max(1, int(block["width"]))
        if self.abandon_policy == "reset":
            new_width = self.initial_width
        elif self.abandon_policy == "halve":
            new_width = max(self.initial_width, width // 2)
        else:
            raise ValueError(f"unknown abandon policy {self.abandon_policy!r}")
        # The parent doubles ``_ramp_width`` when planning; seed it so the NEXT
        # plan starts at ``new_width`` in the same phase.
        self._ramp_width = new_width
        self._ramp_phase = self._phase
        self._ramp_resets += 1

    def _release_pending(self) -> None:
        if self._pending_values:
            self._raw_pending_bytes = 0
        self._pending_values.clear()
        self._finalize_block(abandoned=True)

    def _build_pending_block(self, quantity: int) -> bool:
        before_seconds = self._build_seconds
        built = super()._build_pending_block(quantity)
        if not built:
            return False
        planned = sorted(self._pending_values)
        n_bytes = sum(int(v.nbytes) for v in self._pending_values.values())
        self._raw_pending_bytes = n_bytes
        self._max_raw_pending_bytes = max(self._max_raw_pending_bytes, n_bytes)
        self._last_block_width = len(planned)
        self._block = {
            "planned": planned, "consumed": set(), "phase": self._phase,
            "seconds": self._build_seconds - before_seconds, "width": len(planned),
        }
        return True

    def _candidate_from_block(self, quantity: int) -> Optional[PreparedCanonicalCandidate]:
        candidate = super()._candidate_from_block(quantity)
        raw_bytes = int(self.rng_outcome_count) * 8
        if candidate is not None and self._block is not None and quantity in self._block["planned"]:
            self._prepared_built += 1
            self._raw_pending_bytes = max(0, self._raw_pending_bytes - raw_bytes)
            if self._block is not None:
                self._block["consumed"].add(quantity)
            # sorted vector + prefix sums, plus what is still pending raw.
            prepared_bytes = 2 * raw_bytes + 8
            self._prepared_active_bytes = prepared_bytes
            self._max_prepared_bytes = max(self._max_prepared_bytes, prepared_bytes)
            self._max_pending_plus_prepared_bytes = max(
                self._max_pending_plus_prepared_bytes, self._raw_pending_bytes + prepared_bytes)
            if self._block is not None and not self._pending_values:
                self._finalize_block(abandoned=False)
        if self.trace is not None:
            self.trace.append({"kind": "request", "phase": self._phase, "q": quantity})
        return candidate

    def search(self) -> Dict[str, Any]:
        try:
            return super().search()
        finally:
            self._finalize_block(abandoned=True)

    # ------------------------------------------------------------ diagnostics
    def _diagnostics(self, rip, financial) -> Dict[str, Any]:
        self._finalize_block(abandoned=True)
        diagnostics = super()._diagnostics(rip, financial)
        diagnostics.update({
            "preparedLifecycle": True,
            "abandonPolicy": self.abandon_policy,
            "initialWidth": self.initial_width,
            "maxWidth": self.max_width,
            "preparedBuilt": self._prepared_built,
            "speculativePreparationsAvoided": self._discarded_unprepared,
            "discardedUnpreparedQuantities": self._discarded_unprepared,
            "blocksFinalized": self._blocks_finalized,
            "blocksAbandoned": self._blocks_abandoned,
            "blocksFullyConsumed": self._blocks_fully_consumed,
            "rampResets": self._ramp_resets,
            "maxRawPendingBytes": self._max_raw_pending_bytes,
            "maxPreparedBytes": self._max_prepared_bytes,
            "maxPendingPlusPreparedBytes": self._max_pending_plus_prepared_bytes,
            "consumedBuildSecondsEstimate": self._consumed_build_seconds_est,
            "speculativeBuildSecondsEstimate": self._speculative_build_seconds_est,
            "marginalSpeculativeSeconds": self._marginal_speculative_seconds,
            "marginalMeasuredBlocks": self._marginal_measured_blocks,
        })
        return diagnostics
