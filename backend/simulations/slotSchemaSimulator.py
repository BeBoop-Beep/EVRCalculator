from __future__ import annotations

import random
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

from .slotSchemaContract import get_pack_structure, validate_slot_schema_config


def _coerce_rng(rng: Optional[random.Random]) -> random.Random:
    return rng if isinstance(rng, random.Random) else random.Random()


def _pick_weighted_outcome(outcome_weights: Mapping[str, Any], *, rng: random.Random, slot_path: str) -> str:
    if not isinstance(outcome_weights, Mapping) or not outcome_weights:
        raise ValueError(
            f"{slot_path} outcome table must be a non-empty mapping of outcome->probability."
        )

    normalized: List[tuple[str, float]] = []
    for outcome, raw_weight in outcome_weights.items():
        if not isinstance(outcome, str) or not outcome.strip():
            raise ValueError(f"{slot_path} has an invalid outcome key: {outcome!r}.")
        if not isinstance(raw_weight, (int, float)):
            raise ValueError(
                f"{slot_path} probability for outcome {outcome!r} must be numeric. "
                f"Received type={type(raw_weight).__name__}."
            )
        weight = float(raw_weight)
        if weight < 0:
            raise ValueError(
                f"{slot_path} probability for outcome {outcome!r} must be >= 0. "
                f"Received {weight}."
            )
        if weight > 0:
            normalized.append((outcome, weight))

    if not normalized:
        raise ValueError(f"{slot_path} has no positive-probability outcomes to sample from.")

    total = sum(weight for _, weight in normalized)
    roll = rng.random() * total
    running = 0.0
    for outcome, weight in normalized:
        running += weight
        if roll <= running:
            return outcome

    return normalized[-1][0]


def _resolve_slot_outcome(config: Any, slot: Mapping[str, Any], *, slot_index: int, rng: random.Random) -> str:
    slot_name = str(slot.get("name", f"slot_{slot_index}"))
    slot_path = f"PACK_STRUCTURE.rare_family_slots[{slot_index}] ({slot_name})"

    probability_attr = slot.get("probability_attr")
    probability_key = slot.get("probability_key")

    if probability_attr:
        probability_table = getattr(config, probability_attr, None)
        if probability_table is None:
            raise ValueError(
                f"{slot_path} references probability_attr={probability_attr!r}, "
                "but config is missing that attribute."
            )

        distribution = probability_table
        if probability_key is not None:
            if not isinstance(probability_table, Mapping):
                raise ValueError(
                    f"{slot_path} uses probability_key={probability_key!r}, but {probability_attr!r} "
                    f"is type={type(probability_table).__name__} not a mapping."
                )
            if probability_key not in probability_table:
                raise ValueError(
                    f"{slot_path} references probability_key={probability_key!r} in {probability_attr!r}, "
                    "but that key does not exist."
                )
            distribution = probability_table[probability_key]

        return _pick_weighted_outcome(distribution, rng=rng, slot_path=slot_path)

    default_outcome = slot.get("default_outcome")
    if isinstance(default_outcome, str) and default_outcome.strip():
        return default_outcome

    raise ValueError(
        f"{slot_path} cannot be sampled: provide probability_attr (and optional probability_key) "
        "or define a non-empty default_outcome for deterministic slots."
    )


def _resolve_pool_key(outcome: str, card_pool: Mapping[str, Sequence[Mapping[str, Any]]]) -> str:
    if outcome in card_pool:
        return outcome
    if outcome == "regular reverse" and "reverse" in card_pool:
        return "reverse"
    return outcome


def _sample_card_for_outcome(
    outcome: str,
    card_pool: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    slot_name: str,
    slot_role: str,
    rng: random.Random,
) -> Mapping[str, Any]:
    pool_key = _resolve_pool_key(outcome, card_pool)
    cards = card_pool.get(pool_key)
    if cards is None:
        raise ValueError(
            f"Missing card pool for outcome={outcome!r} (resolved key={pool_key!r}) "
            f"required by slot {slot_name!r} (role={slot_role!r})."
        )
    if len(cards) == 0:
        raise ValueError(
            f"Card pool for outcome={outcome!r} (resolved key={pool_key!r}) is empty; "
            f"cannot sample slot {slot_name!r}."
        )
    return cards[rng.randrange(len(cards))]


def _extract_value(card: Mapping[str, Any]) -> float:
    for key in ("value", "price", "Price ($)", "EV"):
        if key in card:
            raw = card.get(key)
            if isinstance(raw, (int, float)):
                return float(raw)
    return 0.0


def simulate_slot_schema_pack(
    config: Any,
    card_pool: Mapping[str, Sequence[Mapping[str, Any]]],
    rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    validation = validate_slot_schema_config(config)
    pack_structure = get_pack_structure(config)
    randomizer = _coerce_rng(rng)

    cards: List[Dict[str, Any]] = []
    rarity_pull_counts: MutableMapping[str, int] = defaultdict(int)
    rarity_value_totals: MutableMapping[str, float] = defaultdict(float)

    def add_draw(*, slot_group: str, slot_name: str, slot_role: str, outcome: str) -> None:
        sampled_card = _sample_card_for_outcome(
            outcome,
            card_pool,
            slot_name=slot_name,
            slot_role=slot_role,
            rng=randomizer,
        )
        value = _extract_value(sampled_card)
        rarity_pull_counts[outcome] += 1
        rarity_value_totals[outcome] += value
        cards.append(
            {
                "slot_group": slot_group,
                "slot_name": slot_name,
                "slot_role": slot_role,
                "outcome": outcome,
                "value": value,
                "card": sampled_card,
            }
        )

    for index in range(pack_structure["common_slots"]):
        add_draw(
            slot_group="common",
            slot_name=f"common_{index + 1}",
            slot_role="common",
            outcome="common",
        )

    for index in range(pack_structure["uncommon_slots"]):
        add_draw(
            slot_group="uncommon",
            slot_name=f"uncommon_{index + 1}",
            slot_role="uncommon",
            outcome="uncommon",
        )

    for index, slot in enumerate(pack_structure["rare_family_slots"]):
        slot_name = slot["name"]
        slot_role = slot["role"]
        outcome = _resolve_slot_outcome(config, slot, slot_index=index, rng=randomizer)
        add_draw(
            slot_group="rare_family",
            slot_name=slot_name,
            slot_role=slot_role,
            outcome=outcome,
        )

    total_cards = len(cards)
    expected_total = validation["total_modeled_slots"]
    if total_cards != expected_total:
        raise RuntimeError(
            f"Slot-schema simulator sampled {total_cards} cards, expected {expected_total}."
        )

    total_value = float(sum(item["value"] for item in cards))
    return {
        "entry_path": "slot_schema",
        "cards": cards,
        "total_cards": total_cards,
        "total_value": total_value,
        "rarity_pull_counts": dict(rarity_pull_counts),
        "rarity_value_totals": dict(rarity_value_totals),
        "validation": validation,
    }


def simulate_slot_schema_packs(
    config: Any,
    card_pool: Mapping[str, Sequence[Mapping[str, Any]]],
    num_packs: int,
    rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    if not isinstance(num_packs, int) or num_packs <= 0:
        raise ValueError(f"num_packs must be a positive integer. Received {num_packs!r}.")

    randomizer = _coerce_rng(rng)
    packs = [simulate_slot_schema_pack(config, card_pool, rng=randomizer) for _ in range(num_packs)]
    values = [float(pack["total_value"]) for pack in packs]

    rarity_pull_counts: MutableMapping[str, int] = defaultdict(int)
    rarity_value_totals: MutableMapping[str, float] = defaultdict(float)
    for pack in packs:
        for rarity, count in pack["rarity_pull_counts"].items():
            rarity_pull_counts[rarity] += int(count)
        for rarity, value in pack["rarity_value_totals"].items():
            rarity_value_totals[rarity] += float(value)

    mean = float(statistics.fmean(values))
    std_dev = float(statistics.pstdev(values)) if len(values) > 1 else 0.0

    return {
        "packs": packs,
        "values": values,
        "rarity_pull_counts": dict(rarity_pull_counts),
        "rarity_value_totals": dict(rarity_value_totals),
        "mean": mean,
        "std_dev": std_dev,
        "min": float(min(values)),
        "max": float(max(values)),
        "distribution": values,
    }
