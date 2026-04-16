from __future__ import annotations

from typing import Dict, Mapping, MutableMapping, Sequence, Tuple


REQUIRED_SLOTS = ("rare", "reverse_1", "reverse_2")
_BASELINE_RARE = "rare"
_BASELINE_REVERSE = "regular reverse"


def normalize_rarity(value: str) -> str:
    return str(value).strip().lower()


def normalize_slot_outcomes(slot_outcomes: Mapping[str, str]) -> Dict[str, str]:
    return {
        "rare": normalize_rarity(slot_outcomes.get("rare", _BASELINE_RARE)),
        "reverse_1": normalize_rarity(slot_outcomes.get("reverse_1", _BASELINE_REVERSE)),
        "reverse_2": normalize_rarity(slot_outcomes.get("reverse_2", _BASELINE_REVERSE)),
    }


def canonical_slot_outcome_tuple(slot_outcomes: Mapping[str, str]) -> Tuple[str, str, str]:
    normalized = normalize_slot_outcomes(slot_outcomes)
    return (
        normalized["rare"],
        normalized["reverse_1"],
        normalized["reverse_2"],
    )


def validate_unique_state_outcome_shapes(
    state_outcomes: Mapping[str, Mapping[str, str]],
    *,
    context: str,
) -> None:
    """Forbid duplicate structural aliases (same slot triple under different state names)."""
    tuple_to_names: Dict[Tuple[str, str, str], list[str]] = {}

    for state_name, slot_outcomes in state_outcomes.items():
        slots = set(slot_outcomes.keys())
        required = set(REQUIRED_SLOTS)
        if slots != required:
            raise ValueError(
                f"State '{state_name}' in {context} must define exactly {sorted(required)} slots."
            )

        key = canonical_slot_outcome_tuple(slot_outcomes)
        tuple_to_names.setdefault(key, []).append(str(state_name))

    conflicts = [
        (key, names)
        for key, names in tuple_to_names.items()
        if len(set(names)) > 1
    ]
    if conflicts:
        key, names = conflicts[0]
        names_sorted = sorted(set(names))
        raise ValueError(
            "Duplicate state-outcome shape detected "
            f"in {context}: states {names_sorted} share slot outcomes {key}. "
            "Duplicate aliases are forbidden."
        )


def _is_non_regular_hit(rarity: str) -> bool:
    normalized = normalize_rarity(rarity)
    return normalized not in {_BASELINE_RARE, _BASELINE_REVERSE}


def count_non_regular_hits(slot_outcomes: Mapping[str, str]) -> int:
    return sum(1 for rarity in slot_outcomes.values() if _is_non_regular_hit(rarity))


def is_major_hit(rarity: str, constraints: Mapping[str, object]) -> bool:
    normalized = normalize_rarity(rarity)
    return normalized in constraints["primary_hits"] or normalized in constraints["exclusive_hits"]


def count_major_hits(slot_outcomes: Mapping[str, str], constraints: Mapping[str, object]) -> int:
    return sum(1 for rarity in slot_outcomes.values() if is_major_hit(rarity, constraints))


def count_exclusive_hits(slot_outcomes: Mapping[str, str], constraints: Mapping[str, object]) -> int:
    return sum(
        1
        for rarity in slot_outcomes.values()
        if normalize_rarity(rarity) in constraints["exclusive_hits"]
    )


def _set_slot_to_base(outcomes: MutableMapping[str, str], slot_name: str) -> None:
    outcomes[slot_name] = _BASELINE_RARE if slot_name == "rare" else _BASELINE_REVERSE


def contains_incompatible_hits(slot_outcomes: Mapping[str, str]) -> bool:
    hits = {normalize_rarity(r) for r in slot_outcomes.values() if _is_non_regular_hit(r)}
    return (
        {"illustration rare", "special illustration rare"}.issubset(hits)
        or {"special illustration rare", "hyper rare"}.issubset(hits)
        or {"hyper rare", "illustration rare"}.issubset(hits)
    )


def coerce_slot_outcomes(
    slot_outcomes: Mapping[str, str], constraints: Mapping[str, object]
) -> Dict[str, str]:
    """Apply canonical pack-state coercion rules (shared by simulation and derivation)."""
    outcomes = normalize_slot_outcomes(slot_outcomes)

    # Rule 1: Exclusive hits always force a singleton-style hit pack.
    exclusive_slots = [
        slot_name
        for slot_name, rarity in outcomes.items()
        if normalize_rarity(rarity) in constraints["exclusive_hits"]
    ]
    if exclusive_slots:
        if normalize_rarity(outcomes["reverse_2"]) in constraints["exclusive_hits"]:
            keep_slot = "reverse_2"
        elif normalize_rarity(outcomes["rare"]) in constraints["exclusive_hits"]:
            keep_slot = "rare"
        else:
            keep_slot = "reverse_1"

        for slot_name in REQUIRED_SLOTS:
            if slot_name != keep_slot:
                _set_slot_to_base(outcomes, slot_name)

    # Rule 2: Illustration Rare and exclusive hits may not coexist.
    if contains_incompatible_hits(outcomes):
        if normalize_rarity(outcomes["reverse_2"]) in constraints["exclusive_hits"]:
            _set_slot_to_base(outcomes, "rare")
            _set_slot_to_base(outcomes, "reverse_1")
        else:
            if normalize_rarity(outcomes["rare"]) == "illustration rare":
                _set_slot_to_base(outcomes, "rare")
            if normalize_rarity(outcomes["reverse_1"]) == "illustration rare":
                _set_slot_to_base(outcomes, "reverse_1")

    # Rule 3: At most one exclusive hit.
    if count_exclusive_hits(outcomes, constraints) > int(constraints["max_exclusive_hits"]):
        keep = "reverse_2" if normalize_rarity(outcomes["reverse_2"]) in constraints["exclusive_hits"] else "rare"
        for slot_name in REQUIRED_SLOTS:
            if slot_name != keep and normalize_rarity(outcomes[slot_name]) in constraints["exclusive_hits"]:
                _set_slot_to_base(outcomes, slot_name)

    # Rule 4: Max two major hits (primary + exclusive).
    while count_major_hits(outcomes, constraints) > int(constraints["max_major_hits"]):
        if normalize_rarity(outcomes["reverse_1"]) in constraints["primary_hits"]:
            _set_slot_to_base(outcomes, "reverse_1")
            continue
        if normalize_rarity(outcomes["rare"]) in constraints["primary_hits"]:
            _set_slot_to_base(outcomes, "rare")
            continue
        if normalize_rarity(outcomes["reverse_2"]) in constraints["primary_hits"]:
            _set_slot_to_base(outcomes, "reverse_2")
            continue
        break

    # Rule 5: Max two total non-regular hits (primary + exclusive + bonus).
    while count_non_regular_hits(outcomes) > int(constraints["max_non_regular_hits"]):
        if normalize_rarity(outcomes["reverse_1"]) in constraints["bonus_hits"]:
            _set_slot_to_base(outcomes, "reverse_1")
            continue
        if normalize_rarity(outcomes["rare"]) in constraints["bonus_hits"]:
            _set_slot_to_base(outcomes, "rare")
            continue
        if normalize_rarity(outcomes["reverse_2"]) in constraints["bonus_hits"]:
            _set_slot_to_base(outcomes, "reverse_2")
            continue
        if normalize_rarity(outcomes["reverse_1"]) in constraints["primary_hits"]:
            _set_slot_to_base(outcomes, "reverse_1")
            continue
        if normalize_rarity(outcomes["rare"]) in constraints["primary_hits"]:
            _set_slot_to_base(outcomes, "rare")
            continue
        break

    return outcomes
