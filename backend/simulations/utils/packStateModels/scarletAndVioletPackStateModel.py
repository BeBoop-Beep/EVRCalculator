from __future__ import annotations

from copy import deepcopy
from typing import Dict

from .derivePackStateProbabilities import derive_pack_state_probabilities_from_slots
from .packStateCoercion import validate_unique_state_outcome_shapes

# ---------------------------------------------------------------------------
# Structural state outcome registry for the Scarlet & Violet era.
#
# This is the *naming* registry: it defines the canonical slot-outcome shape
# for each named state.  Probabilities are NOT stored here; they are derived
# algorithmically from each set's own RARE_SLOT_PROBABILITY and
# REVERSE_SLOT_PROBABILITIES tables by build_scarlet_and_violet_pack_state_model.
#
# Set overrides may extend this registry with new named states.  A state that
# does not appear in this registry for a given set's slot probabilities will be
# auto-named from its rarity slugs, which is acceptable for uncatalogued
# combinations.
# ---------------------------------------------------------------------------

SV_DEFAULT_STATE_OUTCOMES = {
    "baseline": {
        "rare":      "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "regular reverse",
    },
    "double_rare_only": {
        "rare":      "double rare",
        "reverse_1": "regular reverse",
        "reverse_2": "regular reverse",
    },
    "ultra_rare_only": {
        "rare":      "ultra rare",
        "reverse_1": "regular reverse",
        "reverse_2": "regular reverse",
    },
    "ir_plus_rare": {
        "rare":      "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "illustration rare",
    },
    "ir_plus_double_rare": {
        "rare":      "double rare",
        "reverse_1": "regular reverse",
        "reverse_2": "illustration rare",
    },
    "ir_plus_ultra_rare": {
        "rare":      "ultra rare",
        "reverse_1": "regular reverse",
        "reverse_2": "illustration rare",
    },
    "sir_only": {
        "rare":      "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "special illustration rare",
    },
    "hyper_only": {
        "rare":      "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "hyper rare",
    },
    "ace_spec_plus_rare": {
        "rare":      "rare",
        "reverse_1": "ace spec rare",
        "reverse_2": "regular reverse",
    },
    "pattern_plus_rare": {
        "rare":      "rare",
        "reverse_1": "poke ball pattern",
        "reverse_2": "regular reverse",
    },
    "master_ball_plus_rare": {
        "rare":      "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "master ball pattern",
    },
}

SV_DEFAULT_CONSTRAINTS = {
    "primary_hits":       {"double rare", "ultra rare", "illustration rare"},
    "exclusive_hits":     {"special illustration rare", "hyper rare", "mega hyper rare"},
    "bonus_hits":         {"ace spec rare", "poke ball pattern", "master ball pattern"},
    "max_major_hits":     2,
    "max_non_regular_hits": 2,
    "max_exclusive_hits": 1,
}

# ---------------------------------------------------------------------------
# Era-level default slot probabilities.
#
# Source: Scarlet & Violet Base Set (sv1) pull rate research.
# These are used when a set config does not yet define its own
# RARE_SLOT_PROBABILITY / REVERSE_SLOT_PROBABILITIES (e.g. sets without
# published data).  Set configs always override these once their own data
# is available.
# ---------------------------------------------------------------------------

SV_ERA_DEFAULT_RARE_SLOT_PROBABILITY = {
    "double rare": 1 / 7,
    "ultra rare":  1 / 15,
    "rare":        1 - (1 / 7) - (1 / 15),
}

SV_ERA_DEFAULT_REVERSE_SLOT_PROBABILITIES = {
    "slot_1": {
        "regular reverse": 1.0,
    },
    "slot_2": {
        "illustration rare":          1 / 13,
        "special illustration rare":  1 / 32,
        "hyper rare":                 1 / 54,
        "regular reverse": 1 - (1 / 13) - (1 / 32) - (1 / 54),
    },
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_scarlet_and_violet_pack_state_model(config) -> Dict[str, object]:
    """Build the Scarlet & Violet normal-pack state model.

    State probabilities are *derived* from the set config's slot probability
    tables (RARE_SLOT_PROBABILITY and REVERSE_SLOT_PROBABILITIES).

    Flow
    ----
    1.  Start with the era-default structural registry (SV_DEFAULT_STATE_OUTCOMES)
        and constraint set (SV_DEFAULT_CONSTRAINTS).
    2.  Apply structural overrides from ``config.get_pack_state_overrides()``:
          - new state outcome shapes are registered before derivation
          - constraint additions (hit categories, scalar limits) are merged
          - any ``state_probabilities`` key in the override is ignored; derivation
            always wins because it uses the researched slot probability tables.
    3.  Read the set's slot probability tables, falling back to era defaults when
        the config does not define its own.
    4.  Derive state probabilities via
        ``derive_pack_state_probabilities_from_slots``.
    5.  Return the final model.

    Overrides affect *structure*, not raw probabilities.  If a set introduces a
    genuinely new state, it adds the state outcome shape to the registry; the
    probability is then derived from the set's slot data automatically.
    """

    # --- 1. Start with era defaults ---
    constraints: Dict = {
        key: set(values) if isinstance(values, (set, frozenset)) else values
        for key, values in SV_DEFAULT_CONSTRAINTS.items()
    }
    state_outcomes_registry: Dict[str, Dict[str, str]] = {
        name: dict(slots)
        for name, slots in SV_DEFAULT_STATE_OUTCOMES.items()
    }

    validate_unique_state_outcome_shapes(
        state_outcomes_registry,
        context="Scarlet and Violet era default registry",
    )

    # --- 2. Apply structural overrides (state_outcomes + constraints only) ---
    override_fn = getattr(config, "get_pack_state_overrides", None)
    if callable(override_fn):
        overrides = override_fn() or {}

        for state_name, slot_dict in overrides.get("state_outcomes", {}).items():
            state_outcomes_registry[str(state_name)] = dict(slot_dict)

        for key, value in overrides.get("constraints", {}).items():
            if key in {"primary_hits", "exclusive_hits", "bonus_hits"}:
                constraints[key] = constraints.get(key, set()) | set(value)
            else:
                constraints[key] = value

        validate_unique_state_outcome_shapes(
            state_outcomes_registry,
            context="Scarlet and Violet registry after structural overrides",
        )

        # Explicitly discard any state_probabilities from the override –
        # probabilities are always derived from slot tables.
        # (A future deprecation warning could be added here if needed.)

    # --- 3. Resolve slot probabilities (set-specific or era defaults) ---
    rare_slot_probs = getattr(config, "RARE_SLOT_PROBABILITY", None) or \
        SV_ERA_DEFAULT_RARE_SLOT_PROBABILITY
    reverse_slot_probs = getattr(config, "REVERSE_SLOT_PROBABILITIES", None) or \
        SV_ERA_DEFAULT_REVERSE_SLOT_PROBABILITIES

    # --- 4. Derive state probabilities ---
    derived = derive_pack_state_probabilities_from_slots(
        rare_slot_probabilities=rare_slot_probs,
        reverse_slot_probabilities=reverse_slot_probs,
        constraints=constraints,
        state_outcomes=state_outcomes_registry,
    )

    validate_unique_state_outcome_shapes(
        derived["state_outcomes"],
        context="Scarlet and Violet final derived registry",
    )

    # --- 5. Return complete model ---
    return deepcopy({
        "state_probabilities": derived["state_probabilities"],
        "state_outcomes":      derived["state_outcomes"],
        "constraints":         constraints,
    })
