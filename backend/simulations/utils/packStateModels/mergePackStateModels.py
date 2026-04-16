from __future__ import annotations

from copy import deepcopy
from typing import Dict, Mapping


REQUIRED_SLOTS = {"rare", "reverse_1", "reverse_2"}
SET_LIKE_CONSTRAINT_KEYS = {"primary_hits", "exclusive_hits", "bonus_hits"}


def _normalize_state_probabilities(state_probabilities: Mapping[str, float]) -> Dict[str, float]:
    cleaned = {str(k): float(v) for k, v in state_probabilities.items()}
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("Merged state probabilities must have a positive total.")
    return {k: (v / total) for k, v in cleaned.items()}


def _merge_state_probabilities(
    base_probabilities: Mapping[str, float],
    override_probabilities: Mapping[str, float],
) -> Dict[str, float]:
    merged = {str(k): float(v) for k, v in base_probabilities.items()}
    for key, value in override_probabilities.items():
        merged[str(key)] = float(value)
    return _normalize_state_probabilities(merged)


def _merge_state_outcomes(
    base_state_outcomes: Mapping[str, Mapping[str, str]],
    override_state_outcomes: Mapping[str, Mapping[str, str]],
) -> Dict[str, Dict[str, str]]:
    merged: Dict[str, Dict[str, str]] = {
        str(state_name): dict(slot_outcomes)
        for state_name, slot_outcomes in base_state_outcomes.items()
    }

    for state_name, slot_outcomes in override_state_outcomes.items():
        key = str(state_name)
        existing = dict(merged.get(key, {}))
        existing.update({str(slot): str(rarity) for slot, rarity in slot_outcomes.items()})

        if set(existing.keys()) != REQUIRED_SLOTS:
            raise ValueError(
                f"State '{key}' must define exactly {sorted(REQUIRED_SLOTS)} slots after merge."
            )

        merged[key] = existing

    return merged


def _merge_constraints(base_constraints: Mapping[str, object], override_constraints: Mapping[str, object]) -> Dict[str, object]:
    merged = {k: deepcopy(v) for k, v in base_constraints.items()}

    for key, value in override_constraints.items():
        if key in SET_LIKE_CONSTRAINT_KEYS:
            base_set = set(merged.get(key, set()))
            override_set = set(value)
            merged[key] = base_set.union(override_set)
        else:
            merged[key] = deepcopy(value)

    return merged


def merge_pack_state_models(base_model: Mapping[str, object], overrides: Mapping[str, object]) -> Dict[str, object]:
    """Merge set-level pack-state overrides into an era default model.

    Rules:
    - state_probabilities: key override/add then normalize to sum=1
    - state_outcomes: merge per state; new states allowed, required slots enforced
    - constraints: union set-like hit categories, scalar keys override
    """
    if not overrides:
        return deepcopy(base_model)

    merged = deepcopy(base_model)

    if "state_probabilities" in overrides:
        merged["state_probabilities"] = _merge_state_probabilities(
            merged.get("state_probabilities", {}),
            overrides["state_probabilities"],
        )

    if "state_outcomes" in overrides:
        merged["state_outcomes"] = _merge_state_outcomes(
            merged.get("state_outcomes", {}),
            overrides["state_outcomes"],
        )

    if "constraints" in overrides:
        merged["constraints"] = _merge_constraints(
            merged.get("constraints", {}),
            overrides["constraints"],
        )

    state_prob_keys = set(merged.get("state_probabilities", {}).keys())
    state_outcome_keys = set(merged.get("state_outcomes", {}).keys())
    missing_outcomes = state_prob_keys - state_outcome_keys
    if missing_outcomes:
        raise ValueError(f"Missing slot outcomes for states after merge: {sorted(missing_outcomes)}")

    return merged
