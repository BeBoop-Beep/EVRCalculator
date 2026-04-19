from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Callable, Dict, List, Mapping, MutableMapping, Optional, Tuple
import warnings

import numpy as np
import pandas as pd

from .utils.packStateModels.packStateModelOrchestrator import resolve_pack_state_model
from .utils.packStateModels.packStateCoercion import (
    coerce_slot_outcomes,
    contains_incompatible_hits,
    count_exclusive_hits,
    count_major_hits,
    count_non_regular_hits,
    normalize_rarity,
    validate_unique_state_outcome_shapes,
)
from backend.configured_special_pack_resolver import resolve_configured_god_pack_rows


PackState = Dict[str, object]


def _to_rng(rng: Optional[np.random.Generator] = None) -> np.random.Generator:
    return rng if rng is not None else np.random.default_rng()


def _normalize_rarity(value: str) -> str:
    return normalize_rarity(value)


def _extract_probs(mapping: Mapping[str, float]) -> Dict[str, float]:
    return {_normalize_rarity(k): float(v) for k, v in mapping.items()}


def _get_pack_constraints(config) -> Dict[str, object]:
    resolved_model = resolve_pack_state_model(config)
    defaults = resolved_model.get(
        "constraints",
        {
            "primary_hits": {"double rare", "ultra rare", "illustration rare"},
            "exclusive_hits": {"special illustration rare", "hyper rare", "mega hyper rare"},
            "bonus_hits": {"ace spec rare", "poke ball pattern", "master ball pattern"},
            "max_major_hits": 2,
            "max_non_regular_hits": 2,
            "max_exclusive_hits": 1,
        },
    )
    defaults = {
        "primary_hits": set(defaults.get("primary_hits", set())),
        "exclusive_hits": set(defaults.get("exclusive_hits", set())),
        "bonus_hits": set(defaults.get("bonus_hits", set())),
        "max_major_hits": 2,
        "max_non_regular_hits": 2,
        "max_exclusive_hits": 1,
        **{
            key: defaults[key]
            for key in ("max_major_hits", "max_non_regular_hits", "max_exclusive_hits")
            if key in defaults
        },
    }
    overrides = getattr(config, "PACK_CONSTRAINTS", None)
    merged = dict(defaults)
    if isinstance(overrides, dict):
        merged.update(overrides)

    for key in ("primary_hits", "exclusive_hits", "bonus_hits"):
        merged[key] = {_normalize_rarity(x) for x in merged.get(key, set())}

    return merged


def _is_major_hit(rarity: str, constraints: Mapping[str, object]) -> bool:
    normalized = _normalize_rarity(rarity)
    return normalized in constraints["primary_hits"] or normalized in constraints["exclusive_hits"]


def _count_major_hits(slot_outcomes: Mapping[str, str], constraints: Mapping[str, object]) -> int:
    return count_major_hits(slot_outcomes, constraints)


def _is_non_regular_hit(rarity: str) -> bool:
    normalized = _normalize_rarity(rarity)
    return normalized not in {"rare", "regular reverse"}


def _count_non_regular_hits(slot_outcomes: Mapping[str, str]) -> int:
    return count_non_regular_hits(slot_outcomes)


def _count_exclusive_hits(slot_outcomes: Mapping[str, str], constraints: Mapping[str, object]) -> int:
    return count_exclusive_hits(slot_outcomes, constraints)


def _set_slot_to_base(outcomes: MutableMapping[str, str], slot_name: str) -> None:
    outcomes[slot_name] = "rare" if slot_name == "rare" else "regular reverse"


def _contains_incompatible_hits(slot_outcomes: Mapping[str, str]) -> bool:
    return contains_incompatible_hits(slot_outcomes)


def _coerce_slot_outcomes(
    slot_outcomes: Mapping[str, str], constraints: Mapping[str, object]
) -> Dict[str, str]:
    return coerce_slot_outcomes(slot_outcomes, constraints)


def _get_pack_state_model(config) -> Dict[str, object]:
    return resolve_pack_state_model(config)


def validate_pack_state_model(config, pools: Mapping[str, pd.DataFrame]) -> Dict[str, object]:
    """Validate state probabilities, slot outcomes, and pool compatibility for V2 simulation."""
    model = _get_pack_state_model(config)
    constraints = _get_pack_constraints(config)

    if "state_probabilities" not in model or "state_outcomes" not in model:
        raise ValueError("Pack state model requires 'state_probabilities' and 'state_outcomes'.")

    probs = model["state_probabilities"]
    outcomes = model["state_outcomes"]
    if not probs:
        raise ValueError("Pack state model has no states.")

    validate_unique_state_outcome_shapes(
        outcomes,
        context="resolved pack state model",
    )

    prob_sum = float(sum(float(v) for v in probs.values()))
    if not np.isclose(prob_sum, 1.0, atol=1e-8):
        raise ValueError(f"State probabilities must sum to 1.0. Found {prob_sum:.12f}")

    missing = set(probs.keys()) - set(outcomes.keys())
    if missing:
        raise ValueError(f"Missing slot outcomes for states: {sorted(missing)}")

    for state_name in outcomes.keys():
        if state_name not in probs:
            raise ValueError(f"State '{state_name}' has slot outcomes but no probability.")

    reverse_pool = pools.get("reverse")
    rare_pool = pools.get("rare")
    hit_pool = pools.get("hit")

    if reverse_pool is None or rare_pool is None or hit_pool is None:
        raise ValueError("Pools must include reverse, rare, and hit dataframes.")

    available_hit_rarities = {
        _normalize_rarity(r)
        for r in hit_pool.get("Rarity", pd.Series(dtype=str)).dropna().tolist()
    }

    if not available_hit_rarities:
        raise ValueError("Hit pool contains no rarity data.")

    for state, slot_outcomes in outcomes.items():
        required_slots = {"rare", "reverse_1", "reverse_2"}
        if set(slot_outcomes.keys()) != required_slots:
            raise ValueError(f"State {state} must define exactly {sorted(required_slots)} slots.")

        raw_outcomes = {
            "rare": _normalize_rarity(slot_outcomes["rare"]),
            "reverse_1": _normalize_rarity(slot_outcomes["reverse_1"]),
            "reverse_2": _normalize_rarity(slot_outcomes["reverse_2"]),
        }

        if _contains_incompatible_hits(raw_outcomes):
            raise ValueError(f"Invalid state {state}: contains incompatible hit pair.")

        raw_exclusive_hits = _count_exclusive_hits(raw_outcomes, constraints)
        if raw_exclusive_hits > int(constraints["max_exclusive_hits"]):
            raise ValueError(f"Invalid state {state}: more than one exclusive hit.")

        if raw_exclusive_hits == 1 and _count_non_regular_hits(raw_outcomes) > 1:
            raise ValueError(f"Invalid state {state}: exclusive hit must be the only hit.")

        raw_major_hits = _count_major_hits(raw_outcomes, constraints)
        if raw_major_hits > int(constraints["max_major_hits"]):
            raise ValueError(f"Invalid state {state}: exceeds max major hits ({raw_major_hits}).")

        if _count_non_regular_hits(raw_outcomes) > int(constraints["max_non_regular_hits"]):
            raise ValueError(f"Invalid state {state}: exceeds max non-regular hit slots.")

        normalized = _coerce_slot_outcomes(raw_outcomes, constraints)

        if normalized["reverse_2"] == "special illustration rare" and normalized["rare"] != "rare":
            raise ValueError(f"Invalid state {state}: SIR state must downgrade rare slot to rare.")

        for slot_name, rarity in normalized.items():
            if rarity == "regular reverse":
                if reverse_pool.empty:
                    raise ValueError(f"State {state} needs reverse pool but reverse pool is empty.")
                continue

            if slot_name == "rare" and rarity == "rare":
                if rare_pool.empty:
                    raise ValueError(f"State {state} needs rare pool but rare pool is empty.")
                continue

            if rarity not in available_hit_rarities:
                raise ValueError(f"State {state} references rarity '{rarity}' not available in hit pool.")

    max_state_probability = max(float(v) for v in probs.values())
    min_non_zero_probability = min(float(v) for v in probs.values() if float(v) > 0)
    if max_state_probability >= 0.95 or min_non_zero_probability <= 0.001:
        warnings.warn(
            "Pack state probabilities are highly skewed; verify this is intentional.",
            RuntimeWarning,
        )

    model["constraints"] = constraints
    return model


def sample_pack_state(config, rng: Optional[np.random.Generator] = None) -> PackState:
    """Sample a named normal-pack state from the model."""
    rng = _to_rng(rng)
    model = _get_pack_state_model(config)
    states = list(model["state_probabilities"].keys())
    probs = np.array([float(model["state_probabilities"][s]) for s in states], dtype=float)
    probs = probs / probs.sum()
    sampled_state = str(rng.choice(states, p=probs))

    return {
        "entry_path": "normal",
        "state": sampled_state,
        "slot_outcomes": deepcopy(model["state_outcomes"][sampled_state]),
    }


def resolve_slot_outcomes_from_state(
    pack_state: PackState, config, rng: Optional[np.random.Generator] = None
) -> Dict[str, str]:
    """Resolve concrete per-slot rarity outcomes from a pack state."""
    _ = _to_rng(rng)
    model = _get_pack_state_model(config)
    constraints = _get_pack_constraints(config)

    state_name = str(pack_state.get("state", ""))
    if state_name in model.get("state_outcomes", {}):
        return _coerce_slot_outcomes(model["state_outcomes"][state_name], constraints)

    if "slot_outcomes" in pack_state:
        return _coerce_slot_outcomes(pack_state["slot_outcomes"], constraints)

    raise ValueError(f"Unknown pack state '{state_name}'.")


def _sample_rows(df: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    if df.empty or n <= 0:
        return df.iloc[0:0]
    indices = rng.integers(0, len(df), size=n)
    return df.iloc[indices]


def _sample_single_value(
    df: pd.DataFrame,
    value_col: str,
    rng: np.random.Generator,
    fallback: float = 0.0,
) -> Tuple[float, Optional[str]]:
    if df.empty or value_col not in df.columns:
        return float(fallback), None
    row = _sample_rows(df, 1, rng)
    if row.empty:
        return float(fallback), None
    value = float(pd.to_numeric(row.iloc[0][value_col], errors="coerce") or 0.0)
    card_name = row.iloc[0]["Card Name"] if "Card Name" in row.columns else None
    return value, None if pd.isna(card_name) else str(card_name)


def _sample_rows_with_rarity(
    df: pd.DataFrame,
    n: int,
    rng: np.random.Generator,
    value_col: str,
    rarity_col: str = "Rarity",
    default_rarity: Optional[str] = None,
) -> Tuple[List[str], List[float]]:
    rows = _sample_rows(df, n, rng)
    if rows.empty or value_col not in rows.columns:
        return [], []

    values = pd.to_numeric(rows[value_col], errors="coerce").fillna(0.0).astype(float).tolist()
    if default_rarity is not None:
        rarities = [_normalize_rarity(default_rarity) for _ in values]
    elif rarity_col in rows.columns:
        rarities = [_normalize_rarity(v) for v in rows[rarity_col].fillna("unknown").astype(str).tolist()]
    else:
        rarities = ["unknown" for _ in values]

    return rarities, values


def _resolved_rows_to_rarities_and_values(
    rows: pd.DataFrame,
    *,
    value_col: str,
    rarity_col: str = "Rarity",
) -> Tuple[List[str], List[float]]:
    if rows.empty or value_col not in rows.columns:
        return [], []

    values = pd.to_numeric(rows[value_col], errors="coerce").fillna(0.0).astype(float).tolist()
    if rarity_col in rows.columns:
        rarities = [_normalize_rarity(v) for v in rows[rarity_col].fillna("unknown").astype(str).tolist()]
    else:
        rarities = ["unknown" for _ in values]
    return rarities, values


def _sample_special_pack_details(
    *,
    entry_path: str,
    config_map: Mapping[str, object],
    df: pd.DataFrame,
    common_cards: pd.DataFrame,
    uncommon_cards: pd.DataFrame,
    rng: np.random.Generator,
) -> Dict[str, object]:
    rarities: List[str] = []
    values: List[float] = []
    strategy = config_map.get("strategy", {}) if isinstance(config_map, dict) else {}
    strategy_type = strategy.get("type", "fixed")

    if entry_path == "god":
        if strategy_type == "fixed":
            cards: List[object] = []
            context_label = "god.fixed_cards"
            if "packs" in strategy and strategy["packs"]:
                packs = strategy["packs"]
                selected_pack = packs[int(rng.integers(0, len(packs)))]
                cards = selected_pack.get("cards", [])
                context_label = f"god.fixed_pack:{selected_pack.get('name', '?')}"
                c_rarities, c_values = _sample_rows_with_rarity(
                    common_cards, 4, rng, "Price ($)", default_rarity="common"
                )
                u_rarities, u_values = _sample_rows_with_rarity(
                    uncommon_cards, 3, rng, "Price ($)", default_rarity="uncommon"
                )
                rarities.extend(c_rarities + u_rarities)
                values.extend(c_values + u_values)
            elif "cards" in strategy:
                cards = strategy.get("cards", [])

            if cards:
                selected_rows = resolve_configured_god_pack_rows(
                    cards,
                    df,
                    context_label=context_label,
                )
                if not selected_rows.empty:
                    hit_rarities, hit_values = _resolved_rows_to_rarities_and_values(
                        selected_rows,
                        value_col="Price ($)",
                    )
                    rarities.extend(hit_rarities)
                    values.extend(hit_values)

        elif strategy_type == "random":
            rules = strategy.get("rules", {})
            count = int(rules.get("count", 1))
            rarity_rules = rules.get("rarities", [])
            if isinstance(rarity_rules, list):
                eligible = df[df.get("Rarity", pd.Series(dtype=str)).isin(rarity_rules)]
                hit_rarities, hit_values = _sample_rows_with_rarity(
                    eligible, count, rng, "Price ($)"
                )
                rarities.extend(hit_rarities)
                values.extend(hit_values)
            elif isinstance(rarity_rules, dict):
                for rarity, qty in rarity_rules.items():
                    eligible = df[
                        df.get("Rarity", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
                        == _normalize_rarity(rarity)
                    ]
                    hit_rarities, hit_values = _sample_rows_with_rarity(
                        eligible, int(qty), rng, "Price ($)"
                    )
                    rarities.extend(hit_rarities)
                    values.extend(hit_values)

    elif entry_path == "demi_god":
        c_rarities, c_values = _sample_rows_with_rarity(
            common_cards, 4, rng, "Price ($)", default_rarity="common"
        )
        u_rarities, u_values = _sample_rows_with_rarity(
            uncommon_cards, 3, rng, "Price ($)", default_rarity="uncommon"
        )
        rarities.extend(c_rarities + u_rarities)
        values.extend(c_values + u_values)

        rules = strategy.get("rules", {})
        rarity_rules = rules.get("rarities", {})
        count = int(rules.get("count", 0))

        if isinstance(rarity_rules, dict) and rarity_rules:
            for rarity, qty in rarity_rules.items():
                normalized_rarity = _normalize_rarity(rarity)
                if normalized_rarity in {"common", "uncommon"}:
                    continue
                eligible = df[
                    df.get("Rarity", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
                    == normalized_rarity
                ]
                hit_rarities, hit_values = _sample_rows_with_rarity(
                    eligible, int(qty), rng, "Price ($)"
                )
                rarities.extend(hit_rarities)
                values.extend(hit_values)
        elif isinstance(rarity_rules, list) and count > 0:
            eligible = df[df.get("Rarity", pd.Series(dtype=str)).isin(rarity_rules)]
            hit_rarities, hit_values = _sample_rows_with_rarity(eligible, count, rng, "Price ($)")
            rarities.extend(hit_rarities)
            values.extend(hit_values)

    return {
        "rarities": rarities,
        "values": values,
        "total_value": float(sum(values)),
    }


def _apply_rarity_tracking(
    *,
    rarities: List[str],
    values: List[float],
    rarity_pull_counts: MutableMapping[str, int],
    rarity_value_totals: MutableMapping[str, float],
) -> None:
    for rarity, value in zip(rarities, values):
        normalized = _normalize_rarity(rarity)
        rarity_pull_counts[normalized] += 1
        rarity_value_totals[normalized] += float(value)


def sample_cards_for_slot_outcomes(
    *,
    common_cards: pd.DataFrame,
    uncommon_cards: pd.DataFrame,
    rare_cards: pd.DataFrame,
    hit_cards: pd.DataFrame,
    reverse_pool: pd.DataFrame,
    slot_outcomes: Mapping[str, str],
    slots_per_rarity: Mapping[str, int],
    rarity_pull_counts: MutableMapping[str, int],
    rarity_value_totals: MutableMapping[str, float],
    rng: Optional[np.random.Generator] = None,
) -> Dict[str, object]:
    """Sample concrete cards for fixed slot outcomes and update rarity trackers.

    All sampled cards — commons, uncommons, and the three variable slots — are
    recorded in rarity_pull_counts and rarity_value_totals so that the pull
    summary reflects every card in the pack, not only slot-resolved hits/reverses.
    """
    rng = _to_rng(rng)
    total_value = 0.0

    sampled_common = _sample_rows(common_cards, int(slots_per_rarity.get("common", 4)), rng)
    common_prices = pd.to_numeric(sampled_common.get("Price ($)"), errors="coerce").fillna(0)
    common_value = float(common_prices.sum())
    total_value += common_value
    rarity_pull_counts["common"] += len(common_prices)
    rarity_value_totals["common"] += common_value

    sampled_uncommon = _sample_rows(uncommon_cards, int(slots_per_rarity.get("uncommon", 3)), rng)
    uncommon_prices = pd.to_numeric(sampled_uncommon.get("Price ($)"), errors="coerce").fillna(0)
    uncommon_value = float(uncommon_prices.sum())
    total_value += uncommon_value
    rarity_pull_counts["uncommon"] += len(uncommon_prices)
    rarity_value_totals["uncommon"] += uncommon_value

    slot_values: Dict[str, float] = {}
    slot_cards: Dict[str, Optional[str]] = {}

    for slot_name in ("rare", "reverse_1", "reverse_2"):
        rarity = _normalize_rarity(slot_outcomes[slot_name])
        if slot_name == "rare" and rarity == "rare":
            value, card_name = _sample_single_value(rare_cards, "Price ($)", rng)
        elif rarity == "regular reverse":
            value, card_name = _sample_single_value(reverse_pool, "Reverse Variant Price ($)", rng)
        else:
            eligible = hit_cards[
                hit_cards.get("Rarity", pd.Series(dtype=str)).astype(str).str.strip().str.lower() == rarity
            ]
            value, card_name = _sample_single_value(eligible, "Price ($)", rng)

        slot_values[slot_name] = value
        slot_cards[slot_name] = card_name
        total_value += value
        rarity_pull_counts[rarity] += 1
        rarity_value_totals[rarity] += value

    return {
        "total_value": total_value,
        "slot_values": slot_values,
        "slot_cards": slot_cards,
        "common_count": len(sampled_common),
        "uncommon_count": len(sampled_uncommon),
        "common_cards": sampled_common.get("Card Name", pd.Series(dtype=str)).dropna().astype(str).tolist(),
        "uncommon_cards": sampled_uncommon.get("Card Name", pd.Series(dtype=str)).dropna().astype(str).tolist(),
    }


def make_simulate_pack_fn_v2(
    *,
    common_cards: pd.DataFrame,
    uncommon_cards: pd.DataFrame,
    rare_cards: pd.DataFrame,
    hit_cards: pd.DataFrame,
    reverse_pool: pd.DataFrame,
    slots_per_rarity: Mapping[str, int],
    config,
    df: pd.DataFrame,
    rarity_pull_counts: MutableMapping[str, int],
    rarity_value_totals: MutableMapping[str, float],
    pack_logs: Optional[list] = None,
    rng: Optional[np.random.Generator] = None,
) -> Callable[..., object]:
    """Create a V2 pack simulator with special-pack bypass and state-first normal packs."""
    rng = _to_rng(rng)

    def simulate_one_pack(*, return_pack_data: bool = False):
        god_cfg = getattr(config, "GOD_PACK_CONFIG", {})
        if god_cfg.get("enabled", False) and rng.random() < float(god_cfg.get("pull_rate", 0.0)):
            special = _sample_special_pack_details(
                entry_path="god",
                config_map=god_cfg,
                df=df,
                common_cards=common_cards,
                uncommon_cards=uncommon_cards,
                rng=rng,
            )
            _apply_rarity_tracking(
                rarities=special["rarities"],
                values=special["values"],
                rarity_pull_counts=rarity_pull_counts,
                rarity_value_totals=rarity_value_totals,
            )
            value = float(special["total_value"])
            record = {
                "entry_path": "god",
                "state": "god_pack",
                "slot_outcomes": {},
                "slot_values": {},
                "special_pack_rarities": special["rarities"],
                "total_value": value,
            }
            if pack_logs is not None:
                pack_logs.append(record)
            return (value, record) if return_pack_data else value

        demi_cfg = getattr(config, "DEMI_GOD_PACK_CONFIG", {})
        if demi_cfg.get("enabled", False) and rng.random() < float(demi_cfg.get("pull_rate", 0.0)):
            special = _sample_special_pack_details(
                entry_path="demi_god",
                config_map=demi_cfg,
                df=df,
                common_cards=common_cards,
                uncommon_cards=uncommon_cards,
                rng=rng,
            )
            _apply_rarity_tracking(
                rarities=special["rarities"],
                values=special["values"],
                rarity_pull_counts=rarity_pull_counts,
                rarity_value_totals=rarity_value_totals,
            )
            value = float(special["total_value"])
            record = {
                "entry_path": "demi_god",
                "state": "demi_god_pack",
                "slot_outcomes": {},
                "slot_values": {},
                "special_pack_rarities": special["rarities"],
                "total_value": value,
            }
            if pack_logs is not None:
                pack_logs.append(record)
            return (value, record) if return_pack_data else value

        pack_state = sample_pack_state(config=config, rng=rng)
        slot_outcomes = resolve_slot_outcomes_from_state(pack_state=pack_state, config=config, rng=rng)

        sampled = sample_cards_for_slot_outcomes(
            common_cards=common_cards,
            uncommon_cards=uncommon_cards,
            rare_cards=rare_cards,
            hit_cards=hit_cards,
            reverse_pool=reverse_pool,
            slot_outcomes=slot_outcomes,
            slots_per_rarity=slots_per_rarity,
            rarity_pull_counts=rarity_pull_counts,
            rarity_value_totals=rarity_value_totals,
            rng=rng,
        )

        record = {
            "entry_path": "normal",
            "state": pack_state["state"],
            "slot_outcomes": slot_outcomes,
            "slot_cards": sampled["slot_cards"],
            "slot_values": sampled["slot_values"],
            "total_value": sampled["total_value"],
        }

        if pack_logs is not None:
            pack_logs.append(record)
        if return_pack_data:
            return sampled["total_value"], record
        return sampled["total_value"]

    return simulate_one_pack


def run_simulation_v2(
    open_pack_fn: Callable[[], object],
    rarity_pull_counts: MutableMapping[str, int],
    rarity_value_totals: MutableMapping[str, float],
    n: int = 100000,
    export_debug_df: bool = False,
) -> Dict[str, object]:
    """Run V2 simulation with a single pass so all outputs come from the same sample set."""
    values = []
    path_counts: MutableMapping[str, int] = defaultdict(int)
    state_counts: MutableMapping[str, int] = defaultdict(int)
    debug_rows = []

    for _ in range(n):
        result = open_pack_fn()
        if isinstance(result, tuple):
            value = float(result[0])
            pack_data = result[1] if len(result) > 1 and isinstance(result[1], dict) else {}
            path = pack_data.get("entry_path")
            state = pack_data.get("state")
            if path:
                path_counts[str(path)] += 1
            if state and str(path) == "normal":
                state_counts[str(state)] += 1
            if export_debug_df:
                debug_rows.append(
                    {
                        "pack_state": state,
                        "entry_path": path,
                        "slot_outcomes": pack_data.get("slot_outcomes", {}),
                        "slot_values": pack_data.get("slot_values", {}),
                        "total_value": value,
                    }
                )
        else:
            value = float(result)
            if export_debug_df:
                debug_rows.append(
                    {
                        "pack_state": None,
                        "entry_path": None,
                        "slot_outcomes": {},
                        "slot_values": {},
                        "total_value": value,
                    }
                )
        values.append(value)

    results_array = np.array(values, dtype=float)
    result = {
        "values": values,
        "rarity_pull_counts": rarity_pull_counts,
        "rarity_value_totals": rarity_value_totals,
        "mean": float(results_array.mean()),
        "std_dev": float(results_array.std()),
        "min": float(results_array.min()),
        "max": float(results_array.max()),
        "percentiles": {
            "5th": float(np.percentile(results_array, 5)),
            "25th": float(np.percentile(results_array, 25)),
            "50th": float(np.percentile(results_array, 50)),
            "75th": float(np.percentile(results_array, 75)),
            "90th": float(np.percentile(results_array, 90)),
            "95th": float(np.percentile(results_array, 95)),
            "99th": float(np.percentile(results_array, 99)),
        },
        "distribution": results_array,
        "pack_path_counts": dict(path_counts),
        "pack_state_counts": dict(state_counts),
    }
    if export_debug_df:
        result["debug_df"] = pd.DataFrame(debug_rows)
    return result


def print_simulation_summary_v2(sim_results: Mapping[str, object], n_simulations: int = 100000) -> None:
    print(f"Monte Carlo Simulation V2 Results ({n_simulations} simulations):")
    print("-" * 50)
    print(f"Mean Value:          ${sim_results['mean']:.2f}")
    print(f"Standard Deviation:  ${sim_results['std_dev']:.2f}")
    print(f"Minimum Value:       ${sim_results['min']:.2f}")
    print(f"Maximum Value:       ${sim_results['max']:.2f}")
    print()

    print("Percentiles:")
    for perc_label, perc_val in sim_results["percentiles"].items():
        display_label = "50th (median)" if perc_label == "50th" else perc_label
        print(f"  {display_label}:       ${perc_val:.2f}")

    print("-" * 50)
    print("\n=== Pull Summary by Rarity (All Slots) ===")
    print("(avg value is derived from exact sampled totals; shown with higher precision for auditability)")
    pull_counts = sim_results["rarity_pull_counts"]
    value_totals = sim_results["rarity_value_totals"]
    for rarity, count in pull_counts.items():
        total_val = value_totals[rarity]
        avg_val = total_val / count if count else 0
        print(
            f"{rarity:30s} | pulled: {count:7d} | avg value: ${avg_val:.6f} | total sampled value: ${total_val:.2f}"
        )

    path_counts = sim_results.get("pack_path_counts", {})
    if path_counts:
        print("\n=== Pack Path Counts ===")
        for path, count in sorted(path_counts.items()):
            print(f"{path:20s} | {count:7d}")

    state_counts = sim_results.get("pack_state_counts", {})
    if state_counts:
        print("\n=== Normal Pack State Counts ===")
        for state, count in sorted(state_counts.items()):
            print(f"{state:30s} | {count:7d}")
