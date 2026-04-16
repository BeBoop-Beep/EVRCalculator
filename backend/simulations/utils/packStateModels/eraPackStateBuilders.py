from __future__ import annotations

from typing import Dict

from .scarletAndVioletPackStateModel import build_scarlet_and_violet_pack_state_model


def build_base_pack_state_model(config) -> Dict[str, object]:
    """Provide a minimal era-agnostic fallback model when no era builder resolves."""
    constraints = {
        "primary_hits": {"double rare", "ultra rare", "illustration rare"},
        "exclusive_hits": {"special illustration rare", "hyper rare", "mega hyper rare"},
        "bonus_hits": {"ace spec rare", "poke ball pattern", "master ball pattern"},
        "max_major_hits": 2,
        "max_non_regular_hits": 2,
        "max_exclusive_hits": 1,
    }

    has_minimum_slot_config = bool(getattr(config, "SLOTS_PER_RARITY", None))
    if not has_minimum_slot_config:
        era = getattr(config, "ERA", "<missing>")
        raise ValueError(
            "No era-specific pack state builder resolved and base fallback cannot initialize "
            f"for ERA={era}. Provide get_pack_state_model(), PACK_STATE_MODEL, or a registered era builder."
        )

    return {
        "state_probabilities": {"baseline": 1.0},
        "state_outcomes": {
            "baseline": {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"}
        },
        "constraints": constraints,
    }
