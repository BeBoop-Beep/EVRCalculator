"""
Derive pack-state probabilities from set config slot probability tables.

Architecture overview
---------------------
Rather than manually entering per-state probabilities (which were scaffolding, not
sourced truth), this module computes them algorithmically from the researched slot
probability inputs that already live in each set config.

Core logic (multiply-then-add)
-------------------------------
For each raw slot combination (rare_slot × reverse_1 × reverse_2):

  1. **Multiply** across slots to get the raw combination probability:
         p_combination = p(rare_out) × p(r1_out) × p(r2_out)

  2. **Coerce** the raw combination through the same constraint rules used by the
     live simulation engine (Rules 1–5 from monteCarloSimV2), yielding a legal
     slot-outcome triple.

  3. **Name** the coerced triple via a reverse lookup of the registered state_outcomes
     registry.  If no registered name exists the state is auto-named from the rarity
     slugs so it remains identifiable.

  4. **Add** the raw probability to the running total for the resolved state name:
         p[state] += p_combination
     (multiple raw combinations that coerce to the same state accumulate here)

The resulting p[state] map sums to exactly 1.0 (within float precision) because
every raw combination probability is accounted for in exactly one resulting state.

Coercion rules (mirrored from monteCarloSimV2._coerce_slot_outcomes)
----------------------------------------------------------------------
Rule 1 – Exclusive singleton: if ANY exclusive hit appears, keep only that one
         (priority: reverse_2 > rare > reverse_1).
Rule 2 – IR / exclusive incompatibility: IR and any exclusive cannot coexist.
Rule 3 – At most max_exclusive_hits exclusives.
Rule 4 – At most max_major_hits (primary + exclusive) major hits.
Rule 5 – At most max_non_regular_hits total non-regular hits; demote bonus/primary
         hits in a defined priority order.

Note: this logic is intentionally kept in sync with monteCarloSimV2.  A future
cleanup pass could extract the coercion rules into a shared utility.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Tuple

from .packStateCoercion import (
    canonical_slot_outcome_tuple,
    coerce_slot_outcomes,
    normalize_rarity,
    validate_unique_state_outcome_shapes,
)

# ---------------------------------------------------------------------------
# Slot baseline sentinels
# ---------------------------------------------------------------------------

_BASELINE_RARE = "rare"
_BASELINE_REVERSE = "regular reverse"


# ---------------------------------------------------------------------------
# Internal helpers that mirror monteCarloSimV2 helpers (no circular import)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# State naming helpers
# ---------------------------------------------------------------------------

def _build_reverse_lookup(
    state_outcomes: Dict[str, Dict[str, str]],
) -> Dict[Tuple[str, str, str], str]:
    """Map (rare, r1, r2) tuples → state name from the registered registry."""
    validate_unique_state_outcome_shapes(
        state_outcomes,
        context="state_outcomes registry before derivation",
    )

    lookup: Dict[Tuple[str, str, str], str] = {}
    for name, slots in state_outcomes.items():
        key = canonical_slot_outcome_tuple(slots)
        lookup[key] = name
    return lookup


def _auto_name(rare: str, r1: str, r2: str) -> str:
    """Generate a systematic name for a slot combination not in the registry."""
    parts = []
    if rare != _BASELINE_RARE:
        parts.append(rare.replace(" ", "_"))
    if r1 != _BASELINE_REVERSE:
        parts.append(r1.replace(" ", "_"))
    if r2 != _BASELINE_REVERSE:
        parts.append(r2.replace(" ", "_"))
    return "_".join(parts) if parts else "baseline"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def derive_pack_state_probabilities_from_slots(
    *,
    rare_slot_probabilities: Dict[str, float],
    reverse_slot_probabilities: Dict[str, Dict[str, float]],
    constraints: Dict,
    state_outcomes: Dict[str, Dict[str, str]],
) -> Dict[str, object]:
    """Derive state probabilities by enumerating all raw slot combinations.

    Parameters
    ----------
    rare_slot_probabilities
        ``{rarity: probability}`` for the rare slot.
    reverse_slot_probabilities
        ``{"slot_1": {rarity: prob}, "slot_2": {rarity: prob}}``.
    constraints
        Era/set constraints dict (``exclusive_hits``, ``max_exclusive_hits``, …).
    state_outcomes
        Structural registry mapping state names → slot outcome dicts.  New
        auto-named states may be added to the returned registry; the caller's
        dict is *not* mutated.

    Returns
    -------
    dict with keys:
    ``"state_probabilities"``
        ``{state_name: float}`` – derived probabilities that sum to ~1.0.
    ``"state_outcomes"``
        Updated structural registry (may include newly auto-named states).
    """
    normalized_constraints = {
        **constraints,
        "primary_hits": frozenset(normalize_rarity(r) for r in constraints.get("primary_hits", set())),
        "exclusive_hits": frozenset(normalize_rarity(r) for r in constraints.get("exclusive_hits", set())),
        "bonus_hits": frozenset(normalize_rarity(r) for r in constraints.get("bonus_hits", set())),
        "max_exclusive_hits": int(constraints.get("max_exclusive_hits", 1)),
        "max_major_hits": int(constraints.get("max_major_hits", 2)),
        "max_non_regular_hits": int(constraints.get("max_non_regular_hits", 2)),
    }

    slot_1_probs = reverse_slot_probabilities.get("slot_1", {_BASELINE_REVERSE: 1.0})
    slot_2_probs = reverse_slot_probabilities.get("slot_2", {_BASELINE_REVERSE: 1.0})

    # Work on a copy so we don't mutate the caller's registry
    working_outcomes: Dict[str, Dict[str, str]] = deepcopy(state_outcomes)
    reverse_lookup = _build_reverse_lookup(working_outcomes)

    # Accumulate probabilities per state name
    prob_acc: Dict[str, float] = {}

    for rare_rarity, p_rare in rare_slot_probabilities.items():
        for r1_rarity, p_r1 in slot_1_probs.items():
            for r2_rarity, p_r2 in slot_2_probs.items():
                raw_prob = p_rare * p_r1 * p_r2

                # Coerce to legal slot-outcome triple
                coerced = coerce_slot_outcomes(
                    {
                        "rare": rare_rarity,
                        "reverse_1": r1_rarity,
                        "reverse_2": r2_rarity,
                    },
                    normalized_constraints,
                )
                c_rare = coerced["rare"]
                c_r1 = coerced["reverse_1"]
                c_r2 = coerced["reverse_2"]
                coerced_key = (c_rare, c_r1, c_r2)

                # Resolve state name from registry or auto-generate
                state_name = reverse_lookup.get(coerced_key)
                if state_name is None:
                    candidate = _auto_name(c_rare, c_r1, c_r2)
                    # Ensure uniqueness if two different coerced triples
                    # somehow produce the same auto-name string (unlikely but safe)
                    existing_names = set(reverse_lookup.values())
                    if candidate in existing_names:
                        idx = 2
                        while f"{candidate}_{idx}" in existing_names:
                            idx += 1
                        candidate = f"{candidate}_{idx}"
                    state_name = candidate
                    reverse_lookup[coerced_key] = state_name
                    working_outcomes[state_name] = {
                        "rare":      c_rare,
                        "reverse_1": c_r1,
                        "reverse_2": c_r2,
                    }

                prob_acc[state_name] = prob_acc.get(state_name, 0.0) + raw_prob

    # Prune states whose derived probability is effectively zero
    prob_acc = {k: v for k, v in prob_acc.items() if v > 1e-12}

    # Keep state_outcomes in sync with state_probabilities (validation requires it)
    final_outcomes = {k: v for k, v in working_outcomes.items() if k in prob_acc}

    validate_unique_state_outcome_shapes(
        final_outcomes,
        context="final derived state_outcomes",
    )

    return {
        "state_probabilities": prob_acc,
        "state_outcomes":      final_outcomes,
    }
