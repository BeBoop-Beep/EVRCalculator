from __future__ import annotations

from typing import Dict

# ---------------------------------------------------------------------------
# Set-level structural overrides for Scarlet & Violet era sets.
#
# These functions define only *structural differences* from the era defaults:
#   - new named state outcome shapes (so the derivation can map combinations
#     to human-readable state names)
#   - constraint additions (new legal raritiy categories, limit changes)
#
# State probabilities are NOT provided here.  They are derived algorithmically
# from each set's RARE_SLOT_PROBABILITY and REVERSE_SLOT_PROBABILITIES tables
# by build_scarlet_and_violet_pack_state_model.  Any ``state_probabilities``
# key that appears in an override dict is intentionally ignored by the builder.
# ---------------------------------------------------------------------------


def get_prismatic_evolutions_pack_state_overrides() -> Dict[str, object]:
    """Structural overrides for Prismatic Evolutions.

    PRE's slot_1 carries ace spec rare and poke ball pattern options.
    This means combinations such as (double rare, poke ball pattern, regular reverse)
    are reachable from the slot probability tables.  Registering
    ``pattern_plus_double_rare`` here gives the derivation a canonical name for
    that combination rather than having it auto-named.

    Probability of ``pattern_plus_double_rare`` is derived from:
        p(double rare in rare slot) × p(poke ball pattern in slot_1) × p(regular reverse in slot_2)
    """
    return {
        "state_outcomes": {
            "pattern_plus_double_rare": {
                "rare":      "double rare",
                "reverse_1": "poke ball pattern",
                "reverse_2": "regular reverse",
            },
            "ace_spec_plus_double_rare": {
                "rare":      "double rare",
                "reverse_1": "ace spec rare",
                "reverse_2": "regular reverse",
            },
        },
    }


def get_black_bolt_pack_state_overrides() -> Dict[str, object]:
    """Structural overrides for Black Bolt.

    Includes initial targeted conditional exclusion; pending broader manual validation.
    """
    return {
        "state_outcomes": {
            "black_white_rare_only": {
                "rare":      "black white rare",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            },
        },
        "constraints": {
            "conditional_slot_exclusions": [
                {
                    "if": {"rare": "black white rare"},
                    "forbid": {
                        "reverse_2": ["illustration rare", "special illustration rare"],
                    },
                },
            ],
        },
    }


def get_white_flare_pack_state_overrides() -> Dict[str, object]:
    """Structural overrides for White Flare.

    Includes initial targeted conditional exclusion; pending broader manual validation.
    """
    return {
        "state_outcomes": {
            "black_white_rare_only": {
                "rare":      "black white rare",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            },
        },
        "constraints": {
            "conditional_slot_exclusions": [
                {
                    "if": {"rare": "black white rare"},
                    "forbid": {
                        "reverse_2": ["illustration rare", "special illustration rare"],
                    },
                },
            ],
        },
    }


def get_ascended_heroes_pack_state_overrides() -> Dict[str, object]:
    """Structural overrides for Ascended Heroes.

    Key structural differences from era defaults:
    - ``ultra rare`` can appear in **reverse_1** (reverse_1 placement change).
    - ``mega hyper rare`` appears in **reverse_2** and remains singleton/exclusive.
    - reverse-slot IR/SIR pairings are constrained for normal packs.
    - ``mega attack rare`` cannot pair with ``special illustration rare``.
    - ``mega hyper rare`` is exclusive (added to exclusive_hits).
    """
    return {
        "state_outcomes": {
            "reverse_1_ultra_plus_rare": {
                "rare":      "rare",
                "reverse_1": "ultra rare",
                "reverse_2": "regular reverse",
            },
            "mega_hyper_only": {
                "rare":      "rare",
                "reverse_1": "regular reverse",
                "reverse_2": "mega hyper rare",
            },
        },
        "constraints": {
            "exclusive_hits": {"mega hyper rare"},
            "conditional_slot_exclusions": [
                {
                    "if": {"reverse_2": "special illustration rare"},
                    "forbid": {
                        "rare": ["ultra rare", "hyper rare"],
                        "reverse_1": ["hyper rare"],
                    },
                },
                {
                    "if": {"reverse_2": "illustration rare"},
                    "forbid": {
                        "rare": ["hyper rare"],
                        "reverse_1": ["hyper rare"],
                    },
                },
                {
                    "if": {"reverse_2": "hyper rare"},
                    "forbid": {
                        "rare": ["illustration rare", "special illustration rare"],
                        "reverse_1": ["illustration rare", "special illustration rare"],
                    },
                },
                {
                    "if": {"reverse_1": "illustration rare"},
                    "forbid": {
                        "reverse_2": ["illustration rare", "special illustration rare"],
                    },
                },
                {
                    "if": {"reverse_1": "special illustration rare"},
                    "forbid": {
                        "reverse_2": ["illustration rare", "special illustration rare"],
                    },
                },
                {
                    "if": {"rare": "mega attack rare"},
                    "forbid": {
                        "reverse_1": ["special illustration rare"],
                        "reverse_2": ["special illustration rare"],
                    },
                },
            ],
        },
    }


def get_mega_evolution_pack_state_overrides() -> Dict[str, object]:
    """Structural overrides for Mega Evolution.

    Same structural signature as Ascended Heroes: reverse_1 can carry ultra rare
    or mega hyper rare; mega hyper rare is exclusive.

    Probabilities derived once RARE_SLOT_PROBABILITY / REVERSE_SLOT_PROBABILITIES
    are populated for this set.
    """
    return {
        "state_outcomes": {
            "reverse_1_ultra_plus_rare": {
                "rare":      "rare",
                "reverse_1": "ultra rare",
                "reverse_2": "regular reverse",
            },
            "mega_hyper_only": {
                "rare":      "rare",
                "reverse_1": "mega hyper rare",
                "reverse_2": "regular reverse",
            },
        },
        "constraints": {
            "exclusive_hits": {"mega hyper rare"},
        },
    }

