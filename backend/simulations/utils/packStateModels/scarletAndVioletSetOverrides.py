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

    Black Bolt includes ``black white rare`` in the rare slot
    (RARE_SLOT_PROBABILITY contains ``black white rare: 1/496``).  Registering
    ``black_white_rare_only`` here gives the derivation a canonical name for
    the (black white rare, regular reverse, regular reverse) combination.

    Probability of ``black_white_rare_only`` is derived directly from:
        RARE_SLOT_PROBABILITY["black white rare"] × p(regular in slot_1) × p(regular in slot_2)
    """
    return {
        "state_outcomes": {
            "black_white_rare_only": {
                "rare":      "black white rare",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            },
        },
    }


def get_white_flare_pack_state_overrides() -> Dict[str, object]:
    """Structural overrides for White Flare.

    Identical structural signature to Black Bolt: ``black white rare`` appears
    in the rare slot.  Probability derived from the White Flare config's own
    RARE_SLOT_PROBABILITY table.
    """
    return {
        "state_outcomes": {
            "black_white_rare_only": {
                "rare":      "black white rare",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            },
        },
    }


def get_ascended_heroes_pack_state_overrides() -> Dict[str, object]:
    """Structural overrides for Ascended Heroes.

    Key structural differences from era defaults:
    - ``mega hyper rare`` can appear in **reverse_1** (not reverse_2).
    - ``ultra rare`` can appear in **reverse_1** (reverse_1 placement change).
    - ``mega hyper rare`` is exclusive (added to exclusive_hits).

    State probabilities will be derived once Ascended Heroes receives
    RARE_SLOT_PROBABILITY and REVERSE_SLOT_PROBABILITIES data.  Until then
    the era-default slot probabilities are used, which means the mega hyper
    and reverse_1 ultra states will carry zero probability (they cannot be
    sampled from era defaults that lack those outcomes) – correctly reflecting
    the absence of sourced data rather than an invented constant.
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

