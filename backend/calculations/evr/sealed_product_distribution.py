"""Compose the finished loose-pack outcome vector into sealed-product openings.

THE WHOLE IDEA
--------------
The pack simulator has already produced one empirical outcome vector ``X`` - the
value of one opened booster, sampled ``len(X)`` times. A six-pack Booster Bundle
opening is six of those, a standard Booster Box is thirty-six. So instead of
running a second Pokemon simulator, this module BOOTSTRAPS the finished vector:

    Y_k[i] = X[j_1] + X[j_2] + ... + X[j_k],   j_* drawn uniformly WITH
                                               replacement from X

Nothing here knows about cards, rarities, pull rates, slots or collation, and
nothing here may. ``X`` arrives finished and is never mutated.

THE ASSUMPTION, STATED OUT LOUD
-------------------------------
Packs are modeled as INDEPENDENT draws from the empirical pack model. That is
exactly what ``distribution_model_version = empirical_independent_pack_bootstrap_v1``
declares. Real sealed products may carry per-box guarantees, seeded collation or
anti-duplicate batching; none of those are modeled, none are claimed, and the
disclosure travels with every result so nobody has to infer it.

WHY NOT JUST SCALE THE PACK NUMBERS
-----------------------------------
Only the mean is linear. ``6 * P50(X)`` is not ``P50(Y6)``, ``36 * P95(X)`` is
not ``P95(Y36)``, and a scaled Financial RIP is not a Financial RIP at all: sums
of i.i.d. draws concentrate, so the loss distribution, the recover-cost
probability and both tails all move in ways no per-pack multiplication recovers.
The empirical ``Y`` vector is therefore the only admissible input to scoring.

MEMORY
------
A ``len(X) x 36`` sampled matrix is never allocated. Product runs are generated
in chunks of :data:`DEFAULT_CHUNK_SIZE`; each chunk draws one ``(chunk, 36)``
index block, every requested pack count is summed off that same block (common
random numbers - the bundle's six packs ARE the box's first six), the sums are
written into preallocated outputs and the block is discarded.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

STAGE1_DISTRIBUTION_MODEL_VERSION = "empirical_independent_pack_bootstrap_v1"
PACK_INDEPENDENCE_ASSUMPTION = True

#: Product runs generated per chunk. Deliberately conservative: at 36 packs a
#: chunk holds ~7.2M int64 indices (~58 MB) before being discarded, which is a
#: fixed ceiling regardless of how many product runs are requested.
DEFAULT_CHUNK_SIZE = 25_000


def _stable_seed_material(parts: Iterable[Any]) -> int:
    """A process-stable 64-bit seed from SHA-256.

    Python's built-in ``hash()`` is randomized per process (PYTHONHASHSEED), so
    it cannot back a reproducible simulation seed. SHA-256 can.
    """
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def stage1_distribution_seed(
    *,
    canonical_set_key: Any,
    outcome_count: int,
    run_fingerprint: Optional[str] = None,
) -> int:
    """The local RNG seed for one set's Stage 1 product bootstrap.

    Identity is deliberately limited to what defines the OPENING: the contract
    version, the set, the size of the empirical vector, and any stable run
    fingerprint that is already available.

    WHAT "REPRODUCIBLE" DOES AND DOES NOT MEAN HERE
    -----------------------------------------------
    This seed makes ``Y`` a deterministic function of ``X`` - same ``X``, same
    identity, same ``Y``, forever. It does NOT make ``Y`` recoverable from the
    database: the million-outcome ``X`` is not persisted, so a historical product
    distribution cannot be rebuilt from Postgres alone. Re-deriving it means
    re-running the pack simulation, which reproduces ``X`` bit-for-bit only if
    every simulation input and the simulator itself are unchanged. Closing that
    gap is future outcome-artifact work and is deliberately not done here.

    Deliberately EXCLUDED:
      * product price - price must never change a simulated opening outcome, and
      * ``sealed_product_id`` - two SKUs with the same composition must receive
        the same ``Y``, otherwise "same product, different sticker" would score
        differently for a reason that is pure RNG.
    """
    return _stable_seed_material(
        [
            STAGE1_DISTRIBUTION_MODEL_VERSION,
            str(canonical_set_key or ""),
            int(outcome_count),
            str(run_fingerprint or ""),
        ]
    )


def normalize_pack_outcome_vector(pack_values: Any) -> np.ndarray:
    """Validate and return the empirical pack vector ``X`` as read-only float64.

    Read-only because the whole layer's correctness rests on never touching the
    simulator's finished output; a write barrier is cheaper than trusting every
    future caller.
    """
    if pack_values is None:
        raise ValueError("A pack outcome vector is required to build sealed-product distributions.")

    array = np.asarray(pack_values, dtype=np.float64)
    if array.ndim != 1:
        # squeeze only trailing/leading singleton axes; a genuinely 2-D vector is
        # a contract violation, not something to silently ravel.
        array = np.squeeze(array)
    if array.ndim != 1:
        raise ValueError(f"Pack outcome vector must be one-dimensional; got shape {array.shape}.")
    if array.size == 0:
        raise ValueError("Pack outcome vector must not be empty.")
    if not np.all(np.isfinite(array)):
        raise ValueError("Pack outcome vector contains non-finite values.")

    array = array.copy()
    array.setflags(write=False)
    return array


def extract_pack_outcome_vector(sim_results: Mapping[str, Any]) -> np.ndarray:
    """``X`` from a completed pack simulation result.

    Prefers the in-memory NumPy array the simulator already built. The list form
    is a fallback only - round-tripping a million floats through a Python list
    when the array is right there is pure waste.
    """
    if not isinstance(sim_results, Mapping):
        raise TypeError("sim_results must be a mapping produced by the pack simulation.")

    distribution = sim_results.get("distribution")
    if distribution is not None:
        return normalize_pack_outcome_vector(distribution)

    values = sim_results.get("values")
    if values is None:
        raise ValueError(
            "Pack simulation result exposed neither 'distribution' nor 'values'; "
            "there is no empirical outcome vector to compose."
        )
    return normalize_pack_outcome_vector(values)


def build_stage1_product_distributions(
    pack_values: Any,
    *,
    pack_counts: Sequence[int],
    canonical_set_key: Any,
    run_fingerprint: Optional[str] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Dict[str, Any]:
    """Build one product outcome vector per requested pack count.

    Returns ``{"distributions": {pack_count: ndarray}, "meta": {...}}``.

    ``pack_count == 1`` returns ``X`` itself: a sleeved booster IS one booster
    opening, so resampling it would only add Monte Carlo noise to a distribution
    we already have exactly.

    Each returned vector has exactly ``len(X)`` outcomes, and every count > 1 is
    generated once and shared - the distribution depends on the pack simulation
    and the pack count, never on which SKU consumes it.
    """
    x = normalize_pack_outcome_vector(pack_values)
    n = int(x.size)

    requested = sorted({int(count) for count in pack_counts})
    for count in requested:
        if count < 1:
            raise ValueError(f"pack_count must be >= 1; got {count}.")

    started = time.perf_counter()
    distributions: Dict[int, np.ndarray] = {}
    if 1 in requested:
        distributions[1] = x

    bootstrap_counts = [count for count in requested if count > 1]
    seed = stage1_distribution_seed(
        canonical_set_key=canonical_set_key,
        outcome_count=n,
        run_fingerprint=run_fingerprint,
    )

    if bootstrap_counts:
        rng = np.random.default_rng(seed)
        max_count = max(bootstrap_counts)
        outputs = {count: np.empty(n, dtype=np.float64) for count in bootstrap_counts}
        step = max(1, int(chunk_size))

        for start in range(0, n, step):
            stop = min(start + step, n)
            rows = stop - start
            # ONE index block per chunk backs every requested count: common
            # random numbers, so the bundle's six packs are literally the box's
            # first six. The block is released at the next iteration.
            indices = rng.integers(0, n, size=(rows, max_count), dtype=np.int64)
            sampled = x[indices]
            for count in bootstrap_counts:
                outputs[count][start:stop] = sampled[:, :count].sum(axis=1)
            del indices, sampled

        distributions.update(outputs)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "distributions": distributions,
        "meta": {
            "distributionModel": STAGE1_DISTRIBUTION_MODEL_VERSION,
            "packIndependenceAssumption": PACK_INDEPENDENCE_ASSUMPTION,
            "packOutcomeCount": n,
            "productRunCount": n,
            "packCounts": requested,
            "bootstrapPackCounts": bootstrap_counts,
            "chunkSize": int(chunk_size),
            "seed": int(seed),
            "canonicalSetKey": str(canonical_set_key or ""),
            "runFingerprint": run_fingerprint,
            "elapsedMs": round(elapsed_ms, 3),
        },
    }
