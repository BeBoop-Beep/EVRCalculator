from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
import time
from typing import Callable, Dict, List, Mapping, MutableMapping, Optional, Tuple
import warnings

import numpy as np
import pandas as pd

from .utils.packStateModels.packStateModelOrchestrator import resolve_pack_state_model
from .utils.simulationTokenResolver import (
    format_token_resolution_error,
    get_row_match_keys,
    get_simulation_token_mode,
    list_available_canonical_tokens,
    normalize_simulation_token,
    resolve_hit_pool_rows,
)
from .utils.packStateModels.packStateCoercion import (
    DEFAULT_PACK_CONSTRAINTS,
    coerce_slot_outcomes,
    contains_incompatible_hits,
    count_exclusive_hits,
    count_major_hits,
    count_non_regular_hits,
    normalize_rarity,
    resolve_singleton_exclusive_hits,
    validate_unique_state_outcome_shapes,
)
from backend.configured_special_pack_resolver import resolve_configured_god_pack_rows
from backend.utils.special_pack_config import (
    iter_rarity_bucket_rules,
    parse_rarity_bucket_spec,
)
from backend.utils.debug_output import debug_print


PackState = Dict[str, object]


@dataclass(frozen=True)
class _ArrayPool:
    prices: np.ndarray
    source_row_indices: Optional[np.ndarray]
    card_names: Optional[np.ndarray]
    rarities: Optional[np.ndarray]


def _emit_sim_pool_debug(prefix: str, pool_name: str, pool_df: pd.DataFrame, price_col: str) -> None:
    row_count = int(len(pool_df))
    if row_count == 0:
        debug_print(f"{prefix} pool={pool_name} rows=0 price_col='{price_col}' min=0.0000 max=0.0000 mean=0.0000")
        return

    prices = pd.to_numeric(pool_df.get(price_col), errors="coerce").dropna()
    min_price = float(prices.min()) if not prices.empty else 0.0
    max_price = float(prices.max()) if not prices.empty else 0.0
    mean_price = float(prices.mean()) if not prices.empty else 0.0
    debug_print(
        f"{prefix} pool={pool_name} rows={row_count} price_col='{price_col}' "
        f"min={min_price:.4f} max={max_price:.4f} mean={mean_price:.4f}"
    )

    for idx, (_, row) in enumerate(pool_df.head(10).iterrows(), start=1):
        card_name = str(row.get("Card Name", "<missing>") or "<missing>")
        rarity = str(row.get("Rarity", row.get("rarity_key", "<missing>")) or "<missing>")
        price = pd.to_numeric(pd.Series([row.get(price_col)]), errors="coerce").fillna(0.0).iloc[0]
        card_number = row.get("Card Number", row.get("card_number", ""))
        variant_marker = row.get("Special Type", row.get("special_type_key", row.get("pattern_key", "")))
        variant_id = row.get("card_variant_id", "")
        debug_print(
            f"{prefix} sample[{idx}] pool={pool_name} name={card_name} rarity={rarity} "
            f"price={float(price):.4f} card_number={card_number or '<none>'} "
            f"variant_marker={variant_marker or '<none>'} "
            f"card_variant_id={variant_id if variant_id not in (None, '') else '<none>'}"
        )


def _to_rng(rng: Optional[np.random.Generator] = None) -> np.random.Generator:
    return rng if rng is not None else np.random.default_rng()


def _normalize_rarity(value: str) -> str:
    return normalize_rarity(value)


def _extract_probs(mapping: Mapping[str, float]) -> Dict[str, float]:
    return {_normalize_rarity(k): float(v) for k, v in mapping.items()}


def _get_pack_constraints(config) -> Dict[str, object]:
    resolved_model = resolve_pack_state_model(config)
    resolved_constraints = deepcopy(resolved_model.get("constraints", DEFAULT_PACK_CONSTRAINTS))
    defaults = {
        "primary_hits": set(resolved_constraints.get("primary_hits", set())),
        "exclusive_hits": set(resolved_constraints.get("exclusive_hits", set())),
        "bonus_hits": set(resolved_constraints.get("bonus_hits", set())),
        "singleton_exclusive_hits": set(resolved_constraints.get("singleton_exclusive_hits", set())),
        "max_major_hits": 2,
        "max_non_regular_hits": 2,
        "max_exclusive_hits": 1,
        **{
            key: resolved_constraints[key]
            for key in ("max_major_hits", "max_non_regular_hits", "max_exclusive_hits")
            if key in resolved_constraints
        },
    }
    if "conditional_slot_exclusions" in resolved_constraints:
        defaults["conditional_slot_exclusions"] = resolved_constraints["conditional_slot_exclusions"]
    overrides = getattr(config, "PACK_CONSTRAINTS", None)
    merged = dict(defaults)
    if isinstance(overrides, dict):
        merged.update(overrides)

    for key in ("primary_hits", "exclusive_hits", "bonus_hits", "singleton_exclusive_hits"):
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

    available_base_tokens = list_available_canonical_tokens(hit_pool, mode="base_rarity")
    available_pattern_tokens = list_available_canonical_tokens(hit_pool, mode="pattern")
    available_aggregation_tokens = list_available_canonical_tokens(hit_pool, mode="aggregation")

    debug_print(
        "[SIM_POOL_DEBUG] [SIM_TOKEN_TRACE] "
        f"set_name={getattr(config, 'SET_NAME', '<unknown>')} "
        f"available_base_tokens={available_base_tokens} "
        f"available_pattern_tokens={available_pattern_tokens} "
        f"available_aggregation_tokens={available_aggregation_tokens}"
    )

    if not available_base_tokens and not available_pattern_tokens:
        debug_print(
            "[SIM_POOL_DEBUG] [SIM_TOKEN_TRACE] "
            "validation_exit reason=no_resolvable_tokens_in_hit_pool"
        )
        raise ValueError("Hit pool contains no resolvable simulation tokens.")

    for state, slot_outcomes in outcomes.items():
        required_slots = {"rare", "reverse_1", "reverse_2"}
        if set(slot_outcomes.keys()) != required_slots:
            raise ValueError(f"State {state} must define exactly {sorted(required_slots)} slots.")

        raw_outcomes = {
            "rare": _normalize_rarity(slot_outcomes["rare"]),
            "reverse_1": _normalize_rarity(slot_outcomes["reverse_1"]),
            "reverse_2": _normalize_rarity(slot_outcomes["reverse_2"]),
        }

        raw_exclusive_hits = _count_exclusive_hits(raw_outcomes, constraints)
        if raw_exclusive_hits > int(constraints["max_exclusive_hits"]):
            raise ValueError(f"Invalid state {state}: more than one exclusive hit.")

        singleton_exclusive_hits = resolve_singleton_exclusive_hits(constraints)
        has_singleton_exclusive = any(
            _normalize_rarity(raw_outcomes[slot]) in singleton_exclusive_hits
            for slot in ("rare", "reverse_1", "reverse_2")
        )
        if has_singleton_exclusive and _count_non_regular_hits(raw_outcomes) > 1:
            raise ValueError(f"Invalid state {state}: exclusive hit must be the only hit.")

        raw_major_hits = _count_major_hits(raw_outcomes, constraints)
        if raw_major_hits > int(constraints["max_major_hits"]):
            raise ValueError(f"Invalid state {state}: exceeds max major hits ({raw_major_hits}).")

        if _count_non_regular_hits(raw_outcomes) > int(constraints["max_non_regular_hits"]):
            raise ValueError(f"Invalid state {state}: exceeds max non-regular hit slots.")

        normalized = _coerce_slot_outcomes(raw_outcomes, constraints)

        for slot_name, rarity in normalized.items():
            if rarity == "regular reverse":
                if reverse_pool.empty:
                    raise ValueError(f"State {state} needs reverse pool but reverse pool is empty.")
                continue

            if slot_name == "rare" and rarity == "rare":
                if rare_pool.empty:
                    raise ValueError(f"State {state} needs rare pool but rare pool is empty.")
                continue

            requested_token = str(slot_outcomes.get(slot_name, rarity))
            resolution_mode = get_simulation_token_mode(requested_token)
            resolved_rows, resolution = resolve_hit_pool_rows(
                hit_pool,
                requested_token,
                mode=resolution_mode,
            )
            if resolved_rows.empty:
                debug_print(
                    "[SIM_POOL_DEBUG] [SIM_TOKEN_TRACE] "
                    f"state={state} slot={slot_name} mode={resolution['mode']} "
                    f"requested_token={resolution['requested_token']} "
                    f"canonical_token={resolution['canonical_token']} "
                    f"match_source={resolution['match_source']} "
                    f"available_tokens={resolution['available_tokens']}"
                )
                details = format_token_resolution_error(
                    mode=resolution["mode"],
                    requested_token=resolution["requested_token"],
                    canonical_token=resolution["canonical_token"],
                    available_tokens=resolution["available_tokens"],
                )
                raise ValueError(f"State {state} slot {slot_name} {details}")

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


def _sample_rows_controlled(
    df: pd.DataFrame,
    n: int,
    rng: np.random.Generator,
    replace: bool = True,
) -> pd.DataFrame:
    """Sample rows with controlled replacement.
    
    Args:
        df: DataFrame to sample from
        n: Number of rows to sample
        rng: Random number generator
        replace: If True, sample with replacement (current behavior).
                 If False, sample without replacement (raises if n > len(df))
    
    Returns:
        Sampled rows DataFrame
    
    Raises:
        ValueError: If replace=False and n > len(df)
    """
    if df.empty or n <= 0:
        return df.iloc[0:0]
    
    if replace:
        # With replacement: use the standard approach
        indices = rng.integers(0, len(df), size=n)
        return df.iloc[indices]
    else:
        # Without replacement: sample unique indices
        pool_size = len(df)
        if n > pool_size:
            raise ValueError(
                f"Cannot sample {n} unique cards from pool of size {pool_size}. "
                f"Requested count exceeds available cards without replacement."
            )
        indices = rng.choice(pool_size, size=n, replace=False)
        return df.iloc[indices]


def _sample_single_value(
    df: pd.DataFrame,
    value_col: str,
    rng: np.random.Generator,
    fallback: float = 0.0,
) -> Tuple[float, Optional[str], Optional[object]]:
    if df.empty or value_col not in df.columns:
        return float(fallback), None, None
    row = _sample_rows(df, 1, rng)
    if row.empty:
        return float(fallback), None, None
    value = float(pd.to_numeric(row.iloc[0][value_col], errors="coerce") or 0.0)
    card_name = row.iloc[0]["Card Name"] if "Card Name" in row.columns else None
    source_row_index = row.iloc[0].get("__source_row_index__") if "__source_row_index__" in row.columns else None
    return value, None if pd.isna(card_name) else str(card_name), source_row_index


def _exclude_selected_source_rows(df: pd.DataFrame, selected_source_rows: set) -> pd.DataFrame:
    if not selected_source_rows or "__source_row_index__" not in df.columns:
        return df

    filtered = df.loc[~df["__source_row_index__"].isin(selected_source_rows)]
    # Preserve continuity when no alternate rows exist.
    return filtered if not filtered.empty else df


def _prefer_non_pattern_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Prefer non-pattern rows for base-slot sampling, fallback to full pool when needed."""
    if df.empty:
        return df
    pattern_keys, _ = get_row_match_keys(df, mode="pattern")
    non_pattern_rows = df.loc[pattern_keys.eq("")]
    return non_pattern_rows if not non_pattern_rows.empty else df


def _get_base_slot_sampling_pool(df: pd.DataFrame) -> pd.DataFrame:
    """Return ordinary base-slot pool: non-pattern rows when present, else fallback to full pool."""
    return _prefer_non_pattern_rows(df)


def _validate_pool_has_no_pattern_rows(pool_df: pd.DataFrame, *, label: str) -> None:
    if pool_df.empty:
        return

    pattern_keys, _ = get_row_match_keys(pool_df, mode="pattern")
    leaked_mask = pattern_keys.ne("")
    if leaked_mask.any():
        sample_cards = (
            pool_df.loc[leaked_mask, "Card Name"].fillna("<unknown>").astype(str).head(5).tolist()
            if "Card Name" in pool_df.columns
            else []
        )
        raise ValueError(
            f"[FAST_PATH_POOL_INTEGRITY] {label} contains pattern-overlay rows. "
            f"sample_cards={sample_cards}"
        )


def _validate_pattern_token_pool(pool_df: pd.DataFrame, *, token: str) -> None:
    if pool_df.empty:
        return

    pattern_keys, _ = get_row_match_keys(pool_df, mode="pattern")
    if pattern_keys.eq("").any():
        sample_cards = (
            pool_df.loc[pattern_keys.eq(""), "Card Name"].fillna("<unknown>").astype(str).head(5).tolist()
            if "Card Name" in pool_df.columns
            else []
        )
        raise ValueError(
            f"[FAST_PATH_POOL_INTEGRITY] pattern token pool '{token}' contains non-pattern rows. "
            f"sample_cards={sample_cards}"
        )
    canonical_token = normalize_simulation_token(token)
    canonical_pool_tokens = {
        token_name for token_name in list_available_canonical_tokens(pool_df, mode="pattern") if token_name
    }
    if canonical_token not in canonical_pool_tokens:
        raise ValueError(
            f"[FAST_PATH_POOL_INTEGRITY] pattern token pool '{token}' resolved to unexpected tokens "
            f"{sorted(canonical_pool_tokens)}"
        )


def _build_array_pool(
    df: pd.DataFrame,
    *,
    value_col: str,
    rarity_col: str = "Rarity",
    default_rarity: Optional[str] = None,
) -> _ArrayPool:
    if df.empty or value_col not in df.columns:
        return _ArrayPool(
            prices=np.empty(0, dtype=np.float64),
            source_row_indices=None,
            card_names=None,
            rarities=None,
        )

    prices = pd.to_numeric(df[value_col], errors="coerce").fillna(0.0).to_numpy(dtype=np.float64, copy=True)

    source_row_indices = None
    if "__source_row_index__" in df.columns:
        source_row_indices = (
            df["__source_row_index__"].where(df["__source_row_index__"].notna(), None).to_numpy(dtype=object, copy=True)
        )

    if "Card Name" in df.columns:
        card_names = df["Card Name"].where(df["Card Name"].notna(), None).to_numpy(dtype=object, copy=True)
    else:
        card_names = None

    if default_rarity is not None:
        normalized = _normalize_rarity(default_rarity)
        rarities = np.full(prices.shape[0], normalized, dtype=object)
    elif rarity_col in df.columns:
        rarities = np.array(
            [_normalize_rarity(v) for v in df[rarity_col].fillna("unknown").astype(str).tolist()],
            dtype=object,
        )
    else:
        rarities = None

    return _ArrayPool(
        prices=prices,
        source_row_indices=source_row_indices,
        card_names=card_names,
        rarities=rarities,
    )


def _sample_pool_total(
    pool: _ArrayPool,
    n: int,
    rng: np.random.Generator,
    *,
    include_card_names: bool,
) -> Tuple[float, int, List[str]]:
    if pool.prices.size == 0 or n <= 0:
        return 0.0, 0, []

    indices = rng.integers(0, pool.prices.size, size=n)
    total = float(pool.prices[indices].sum(dtype=np.float64))

    if not include_card_names or pool.card_names is None:
        return total, int(indices.size), []

    names = [str(name) for name in pool.card_names[indices].tolist() if name is not None]
    return total, int(indices.size), names


def _sample_single_from_array_pool(
    pool: _ArrayPool,
    rng: np.random.Generator,
    selected_source_rows: set,
    fallback: float = 0.0,
    *,
    include_card_name: bool = True,
) -> Tuple[float, Optional[str], Optional[object]]:
    if pool.prices.size == 0:
        return float(fallback), None, None

    source_row_indices = pool.source_row_indices
    if source_row_indices is None or not selected_source_rows:
        chosen_index = int(rng.integers(0, pool.prices.size))
    else:
        chosen_index = -1
        for _ in range(8):
            candidate_index = int(rng.integers(0, pool.prices.size))
            candidate_source = source_row_indices[candidate_index]
            if candidate_source is None or candidate_source not in selected_source_rows:
                chosen_index = candidate_index
                break

        if chosen_index == -1:
            eligible_mask = np.ones(pool.prices.shape[0], dtype=bool)
            for selected_source in selected_source_rows:
                eligible_mask &= source_row_indices != selected_source

            if eligible_mask.any():
                eligible_positions = np.flatnonzero(eligible_mask)
                chosen_index = int(eligible_positions[int(rng.integers(0, eligible_positions.size))])
            else:
                # Preserve existing fallback semantics: when exclusion empties the
                # pool, sample from the full pool rather than failing.
                chosen_index = int(rng.integers(0, pool.prices.size))

    value = float(pool.prices[chosen_index])
    card_name = None
    if include_card_name and pool.card_names is not None:
        raw_name = pool.card_names[chosen_index]
        if raw_name is not None:
            card_name = str(raw_name)

    source_row_index = None
    if source_row_indices is not None:
        source_row_index = source_row_indices[chosen_index]

    return value, card_name, source_row_index


def _sample_rows_with_rarity(
    df: pd.DataFrame,
    n: int,
    rng: np.random.Generator,
    value_col: str,
    rarity_col: str = "Rarity",
    default_rarity: Optional[str] = None,
    replace: bool = True,
) -> Tuple[List[str], List[float]]:
    rows = _sample_rows_controlled(df, n, rng, replace=replace)
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


def _parse_rarity_config(qty_spec: object) -> Tuple[int, bool]:
    """Backward-compatible wrapper for tests/import sites.

    Authoritative parsing lives in special_pack_config.parse_rarity_bucket_spec.
    """
    return parse_rarity_bucket_spec(qty_spec)


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
    common_sampling_pool = _get_base_slot_sampling_pool(common_cards)
    uncommon_sampling_pool = _get_base_slot_sampling_pool(uncommon_cards)
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
                    common_sampling_pool, 4, rng, "Price ($)", default_rarity="common"
                )
                u_rarities, u_values = _sample_rows_with_rarity(
                    uncommon_sampling_pool, 3, rng, "Price ($)", default_rarity="uncommon"
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
                for rarity, sample_count, use_replacement in iter_rarity_bucket_rules(rarity_rules):
                    eligible = df[
                        df.get("Rarity", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
                        == _normalize_rarity(rarity)
                    ]
                    hit_rarities, hit_values = _sample_rows_with_rarity(
                        eligible, sample_count, rng, "Price ($)", replace=use_replacement
                    )
                    rarities.extend(hit_rarities)
                    values.extend(hit_values)

    elif entry_path == "demi_god":
        c_rarities, c_values = _sample_rows_with_rarity(
            common_sampling_pool, 4, rng, "Price ($)", default_rarity="common"
        )
        u_rarities, u_values = _sample_rows_with_rarity(
            uncommon_sampling_pool, 3, rng, "Price ($)", default_rarity="uncommon"
        )
        rarities.extend(c_rarities + u_rarities)
        values.extend(c_values + u_values)

        rules = strategy.get("rules", {})
        rarity_rules = rules.get("rarities", {})
        count = int(rules.get("count", 0))

        if isinstance(rarity_rules, dict) and rarity_rules:
            for rarity, sample_count, use_replacement in iter_rarity_bucket_rules(rarity_rules):
                normalized_rarity = _normalize_rarity(rarity)
                if normalized_rarity in {"common", "uncommon"}:
                    continue
                eligible = df[
                    df.get("Rarity", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
                    == normalized_rarity
                ]
                hit_rarities, hit_values = _sample_rows_with_rarity(
                    eligible, sample_count, rng, "Price ($)", replace=use_replacement
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

    common_sampling_pool = _get_base_slot_sampling_pool(common_cards)
    uncommon_sampling_pool = _get_base_slot_sampling_pool(uncommon_cards)

    sampled_common = _sample_rows(common_sampling_pool, int(slots_per_rarity.get("common", 4)), rng)
    common_prices = pd.to_numeric(sampled_common.get("Price ($)"), errors="coerce").fillna(0)
    common_value = float(common_prices.sum())
    total_value += common_value
    rarity_pull_counts["common"] += len(common_prices)
    rarity_value_totals["common"] += common_value

    sampled_uncommon = _sample_rows(uncommon_sampling_pool, int(slots_per_rarity.get("uncommon", 3)), rng)
    uncommon_prices = pd.to_numeric(sampled_uncommon.get("Price ($)"), errors="coerce").fillna(0)
    uncommon_value = float(uncommon_prices.sum())
    total_value += uncommon_value
    rarity_pull_counts["uncommon"] += len(uncommon_prices)
    rarity_value_totals["uncommon"] += uncommon_value

    slot_values: Dict[str, float] = {}
    slot_cards: Dict[str, Optional[str]] = {}
    selected_source_rows: set = set()

    for slot_name in ("rare", "reverse_1", "reverse_2"):
        requested_token = str(slot_outcomes[slot_name])
        rarity = _normalize_rarity(requested_token)
        if slot_name == "rare" and rarity == "rare":
            eligible_rare = _exclude_selected_source_rows(rare_cards, selected_source_rows)
            eligible_rare = _get_base_slot_sampling_pool(eligible_rare)
            value, card_name, source_row_index = _sample_single_value(eligible_rare, "Price ($)", rng)
        elif rarity == "regular reverse":
            eligible_reverse = _exclude_selected_source_rows(reverse_pool, selected_source_rows)
            value, card_name, source_row_index = _sample_single_value(
                eligible_reverse,
                "Reverse Variant Price ($)",
                rng,
            )
        else:
            resolution_mode = get_simulation_token_mode(requested_token)
            eligible, resolution = resolve_hit_pool_rows(
                hit_cards,
                requested_token,
                mode=resolution_mode,
            )
            if eligible.empty:
                details = format_token_resolution_error(
                    mode=resolution["mode"],
                    requested_token=resolution["requested_token"],
                    canonical_token=resolution["canonical_token"],
                    available_tokens=resolution["available_tokens"],
                )
                raise ValueError(f"Slot {slot_name} {details}")
            eligible = _exclude_selected_source_rows(eligible, selected_source_rows)
            value, card_name, source_row_index = _sample_single_value(eligible, "Price ($)", rng)

        if source_row_index is not None and not pd.isna(source_row_index):
            selected_source_rows.add(source_row_index)

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


def _sample_cards_fast(
    *,
    common_pool: _ArrayPool,
    uncommon_pool: _ArrayPool,
    rare_base_pool: _ArrayPool,
    reverse_pool: _ArrayPool,
    slot_outcomes: Mapping[str, str],
    slot_pool_keys: Mapping[str, tuple],
    token_pool_map: Dict[Tuple[str, str], _ArrayPool],
    n_common: int,
    n_uncommon: int,
    rarity_pull_counts: MutableMapping[str, int],
    rarity_value_totals: MutableMapping[str, float],
    rng: np.random.Generator,
    include_details: bool = False,
) -> Dict[str, object]:
    """Hot-path card sampler using precomputed pools and slot-key lookup table.

    Replaces sample_cards_for_slot_outcomes in the inner simulation loop.
    Semantics and outputs are identical; DataFrame filtering and token
    resolution are bypassed via pre-built structures.
    """
    total_value = 0.0

    common_value, common_count, common_names = _sample_pool_total(
        common_pool,
        n_common,
        rng,
        include_card_names=include_details,
    )
    total_value += common_value
    rarity_pull_counts["common"] += common_count
    rarity_value_totals["common"] += common_value

    uncommon_value, uncommon_count, uncommon_names = _sample_pool_total(
        uncommon_pool,
        n_uncommon,
        rng,
        include_card_names=include_details,
    )
    total_value += uncommon_value
    rarity_pull_counts["uncommon"] += uncommon_count
    rarity_value_totals["uncommon"] += uncommon_value

    slot_values: Dict[str, float] = {}
    slot_cards: Dict[str, Optional[str]] = {}
    selected_source_rows: set = set()

    for slot_name in ("rare", "reverse_1", "reverse_2"):
        key_info = slot_pool_keys[slot_name]
        pool_type = key_info[0]
        rarity = _normalize_rarity(str(slot_outcomes[slot_name]))

        if pool_type == "rare_pool":
            value, card_name, source_row_index = _sample_single_from_array_pool(
                rare_base_pool,
                rng,
                selected_source_rows,
                include_card_name=include_details,
            )
        elif pool_type == "reverse_pool":
            value, card_name, source_row_index = _sample_single_from_array_pool(
                reverse_pool,
                rng,
                selected_source_rows,
                include_card_name=include_details,
            )
        else:
            # hit_pool: key_info = ("hit_pool", mode, canonical_token)
            eligible = token_pool_map[(key_info[1], key_info[2])]
            if eligible.prices.size == 0:
                raise ValueError(
                    f"Slot {slot_name}: empty token pool for '{key_info[2]}' "
                    f"(mode={key_info[1]}). Pool was non-empty at validation time."
                )
            value, card_name, source_row_index = _sample_single_from_array_pool(
                eligible,
                rng,
                selected_source_rows,
                include_card_name=include_details,
            )

        if source_row_index is not None:
            selected_source_rows.add(source_row_index)

        if include_details:
            slot_values[slot_name] = value
            slot_cards[slot_name] = card_name
        total_value += value
        rarity_pull_counts[rarity] += 1
        rarity_value_totals[rarity] += value

    return {
        "total_value": total_value,
        "slot_values": slot_values,
        "slot_cards": slot_cards,
        "common_count": common_count,
        "uncommon_count": uncommon_count,
        "common_cards": common_names if include_details else [],
        "uncommon_cards": uncommon_names if include_details else [],
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
    max_pack_logs: int = 0,
    path_counts: Optional[MutableMapping[str, int]] = None,
    state_counts: Optional[MutableMapping[str, int]] = None,
) -> Callable[..., object]:
    """Create a V2 pack simulator with special-pack bypass and state-first normal packs.

    Parameters
    ----------
    max_pack_logs:
        Controls pack-record logging into *pack_logs*.
        ``0``  — logging disabled (default; avoids 100 k record allocations per run).
        ``-1`` — unlimited (all packs logged; use for debugging only).
        ``N>0`` — log at most N records then stop.
    path_counts:
        Optional external counter updated directly in the hot path.  When
        provided the caller does not need ``return_pack_data=True`` to get
        pack-path statistics.
    state_counts:
        Optional external counter for normal-pack state names, same contract
        as *path_counts*.
    """
    rng = _to_rng(rng)

    # ------------------------------------------------------------------
    # Precompute pack model, constraints, and all per-state structures
    # ONCE so the hot loop performs only O(1) dict/array lookups.
    # ------------------------------------------------------------------
    _t_pre0 = time.perf_counter()

    _model = _get_pack_state_model(config)
    _constraints = _get_pack_constraints(config)

    # State sampling arrays (built once)
    _state_names: List[str] = list(_model["state_probabilities"].keys())
    _state_probs = np.array(
        [float(_model["state_probabilities"][s]) for s in _state_names], dtype=float
    )
    _state_probs = _state_probs / _state_probs.sum()

    _god_cfg = getattr(config, "GOD_PACK_CONFIG", {})
    _demi_cfg = getattr(config, "DEMI_GOD_PACK_CONFIG", {})
    _god_pull_rate = float(_god_cfg.get("pull_rate", 0.0)) if bool(_god_cfg.get("enabled", False)) else 0.0
    _demi_pull_rate = float(_demi_cfg.get("pull_rate", 0.0)) if bool(_demi_cfg.get("enabled", False)) else 0.0
    # Sequential entry logic in simulate_one_pack:
    # P(god) = g, P(demi) = (1-g)*d, P(normal) = (1-g)*(1-d)
    _path_prob_god = _god_pull_rate
    _path_prob_demi = (1.0 - _god_pull_rate) * _demi_pull_rate
    _path_prob_normal = (1.0 - _god_pull_rate) * (1.0 - _demi_pull_rate)
    debug_print(
        "[SIM_POOL_DEBUG] [SIM_PATH_TRACE] "
        f"set_name={getattr(config, 'SET_NAME', '<unknown>')} "
        f"pack_path_probabilities={{'normal': {_path_prob_normal:.12f}, 'god': {_path_prob_god:.12f}, 'demi_god': {_path_prob_demi:.12f}}}"
    )

    # Pre-coerce all slot outcomes so coerce_slot_outcomes is never called per-pack
    _coerced_outcomes: Dict[str, Dict[str, str]] = {
        state: _coerce_slot_outcomes(outcomes, _constraints)
        for state, outcomes in _model["state_outcomes"].items()
    }

    # Precompute base slot sampling pools (non-pattern filter runs once)
    _common_pool_df = _get_base_slot_sampling_pool(common_cards)
    _uncommon_pool_df = _get_base_slot_sampling_pool(uncommon_cards)
    _rare_base_pool_df = _get_base_slot_sampling_pool(rare_cards)
    _validate_pool_has_no_pattern_rows(_common_pool_df, label="common_base_pool")
    _validate_pool_has_no_pattern_rows(_uncommon_pool_df, label="uncommon_base_pool")
    _validate_pool_has_no_pattern_rows(_rare_base_pool_df, label="rare_base_pool")

    debug_print(
        "[SIM_POOL_DEBUG] "
        f"base_common_count={len(_common_pool_df)} "
        f"base_uncommon_count={len(_uncommon_pool_df)} "
        f"base_rare_count={len(_rare_base_pool_df)} "
        f"reverse_pool_size={len(reverse_pool)}"
    )
    _emit_sim_pool_debug("[SIM_POOL_DEBUG]", "base_common_prepared", _common_pool_df, "Price ($)")
    _emit_sim_pool_debug("[SIM_POOL_DEBUG]", "base_uncommon_prepared", _uncommon_pool_df, "Price ($)")
    _emit_sim_pool_debug("[SIM_POOL_DEBUG]", "base_rare_prepared", _rare_base_pool_df, "Price ($)")
    _emit_sim_pool_debug("[SIM_POOL_DEBUG]", "reverse_prepared", reverse_pool, "Reverse Variant Price ($)")

    _common_pool = _build_array_pool(_common_pool_df, value_col="Price ($)", default_rarity="common")
    _uncommon_pool = _build_array_pool(
        _uncommon_pool_df,
        value_col="Price ($)",
        default_rarity="uncommon",
    )
    _rare_base_pool = _build_array_pool(_rare_base_pool_df, value_col="Price ($)")
    _reverse_pool = _build_array_pool(reverse_pool, value_col="Reverse Variant Price ($)")

    # Slot-count constants
    _n_common = int(slots_per_rarity.get("common", 4))
    _n_uncommon = int(slots_per_rarity.get("uncommon", 3))

    # Build token pool map: (mode, canonical_token) -> eligible DataFrame slice.
    # Iterate over every coerced state outcome to cover all tokens used in this run.
    _token_pool_map: Dict[Tuple[str, str], _ArrayPool] = {}
    for _outcomes in _coerced_outcomes.values():
        for _slot_name, _token in _outcomes.items():
            _rarity = _normalize_rarity(_token)
            if _slot_name == "rare" and _rarity == "rare":
                continue  # uses _rare_base_pool
            if _rarity == "regular reverse":
                continue  # uses reverse_pool
            _mode = get_simulation_token_mode(_token)
            _canonical = normalize_simulation_token(_token)
            _key: Tuple[str, str] = (_mode, _canonical)
            if _key not in _token_pool_map:
                _eligible, _ = resolve_hit_pool_rows(hit_cards, _token, mode=_mode)
                if _mode == "pattern":
                    _validate_pattern_token_pool(_eligible, token=_token)
                _token_pool_map[_key] = _build_array_pool(_eligible, value_col="Price ($)")

    # Per-state slot-pool key lookup: avoids get_simulation_token_mode +
    # normalize_simulation_token calls inside the hot loop.
    _state_slot_info: Dict[str, Dict[str, tuple]] = {}
    for _state, _outcomes in _coerced_outcomes.items():
        _slot_keys: Dict[str, tuple] = {}
        for _slot_name in ("rare", "reverse_1", "reverse_2"):
            _token = _outcomes[_slot_name]
            _rarity = _normalize_rarity(_token)
            if _slot_name == "rare" and _rarity == "rare":
                _slot_keys[_slot_name] = ("rare_pool",)
            elif _rarity == "regular reverse":
                _slot_keys[_slot_name] = ("reverse_pool",)
            else:
                _mode = get_simulation_token_mode(_token)
                _canonical = normalize_simulation_token(_token)
                _slot_keys[_slot_name] = ("hit_pool", _mode, _canonical)
        _state_slot_info[_state] = _slot_keys

    _t_pre1 = time.perf_counter()
    debug_print(
        f"[SIM_TIMING] stage_name=token_pool_precomputation "
        f"elapsed_ms={(_t_pre1 - _t_pre0) * 1000:.1f}"
    )

    # ------------------------------------------------------------------
    # Determine log cap once so the closure avoids recomputing it
    # ------------------------------------------------------------------
    _log_cap = max_pack_logs  # 0=disabled, -1=unlimited, N>0=cap at N

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
            if path_counts is not None:
                path_counts["god"] += 1
            _should_log = (
                pack_logs is not None
                and (_log_cap == -1 or (_log_cap > 0 and len(pack_logs) < _log_cap))
            )
            if return_pack_data or _should_log:
                record: Dict[str, object] = {
                    "entry_path": "god",
                    "state": "god_pack",
                    "slot_outcomes": {},
                    "slot_values": {},
                    "special_pack_rarities": special["rarities"],
                    "total_value": value,
                }
                if _should_log:
                    pack_logs.append(record)  # type: ignore[union-attr]
                if return_pack_data:
                    return value, record
            return value

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
            if path_counts is not None:
                path_counts["demi_god"] += 1
            _should_log = (
                pack_logs is not None
                and (_log_cap == -1 or (_log_cap > 0 and len(pack_logs) < _log_cap))
            )
            if return_pack_data or _should_log:
                record = {
                    "entry_path": "demi_god",
                    "state": "demi_god_pack",
                    "slot_outcomes": {},
                    "slot_values": {},
                    "special_pack_rarities": special["rarities"],
                    "total_value": value,
                }
                if _should_log:
                    pack_logs.append(record)  # type: ignore[union-attr]
                if return_pack_data:
                    return value, record
            return value

        # --- Hot path: O(1) state sampling via precomputed arrays ---
        idx = rng.choice(len(_state_names), p=_state_probs)
        sampled_state = _state_names[idx]
        slot_outcomes = _coerced_outcomes[sampled_state]   # already coerced, no deepcopy needed
        slot_pool_keys = _state_slot_info[sampled_state]
        _should_log = (
            pack_logs is not None
            and (_log_cap == -1 or (_log_cap > 0 and len(pack_logs) < _log_cap))
        )
        _collect_details = return_pack_data or _should_log

        sampled = _sample_cards_fast(
            common_pool=_common_pool,
            uncommon_pool=_uncommon_pool,
            rare_base_pool=_rare_base_pool,
            reverse_pool=_reverse_pool,
            slot_outcomes=slot_outcomes,
            slot_pool_keys=slot_pool_keys,
            token_pool_map=_token_pool_map,
            n_common=_n_common,
            n_uncommon=_n_uncommon,
            rarity_pull_counts=rarity_pull_counts,
            rarity_value_totals=rarity_value_totals,
            rng=rng,
            include_details=_collect_details,
        )

        # Cheap direct-counter update — no record dict needed for normal runs.
        if path_counts is not None:
            path_counts["normal"] += 1
        if state_counts is not None:
            state_counts[sampled_state] += 1

        if return_pack_data or _should_log:
            record = {
                "entry_path": "normal",
                "state": sampled_state,
                "slot_outcomes": slot_outcomes,
                "slot_cards": sampled["slot_cards"],
                "slot_values": sampled["slot_values"],
                "total_value": sampled["total_value"],
            }
            if _should_log:
                pack_logs.append(record)  # type: ignore[union-attr]
            if return_pack_data:
                return sampled["total_value"], record

        return sampled["total_value"]

    return simulate_one_pack


def run_simulation_v2(
    open_pack_fn: Callable[[], object],
    rarity_pull_counts: MutableMapping[str, int],
    rarity_value_totals: MutableMapping[str, float],
    n: int = 1000000,
    export_debug_df: bool = False,
    pack_path_counts: Optional[MutableMapping[str, int]] = None,
    pack_state_counts: Optional[MutableMapping[str, int]] = None,
) -> Dict[str, object]:
    """Run V2 simulation with a single pass so all outputs come from the same sample set.

    Parameters
    ----------
    pack_path_counts:
        When provided (pre-populated by the pack closure), these counters are
        used directly in the result dict and internal tuple-based tracking is
        skipped.  Allows ``open_pack_fn`` to return a plain ``float``.
    pack_state_counts:
        Same contract as *pack_path_counts* for normal-pack state names.
    """
    results_array = np.empty(n, dtype=np.float64)
    _internal_path_counts: MutableMapping[str, int] = defaultdict(int)
    _internal_state_counts: MutableMapping[str, int] = defaultdict(int)
    debug_rows = []

    for index in range(n):
        result = open_pack_fn()
        if isinstance(result, tuple):
            value = float(result[0])
            pack_data = result[1] if len(result) > 1 and isinstance(result[1], dict) else {}
            path = pack_data.get("entry_path")
            state = pack_data.get("state")
            # Only count internally when external counters are not supplied.
            if pack_path_counts is None and path:
                _internal_path_counts[str(path)] += 1
            if pack_state_counts is None and state and str(path) == "normal":
                _internal_state_counts[str(state)] += 1
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
        results_array[index] = value

    values = results_array.tolist()
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
        "pack_path_counts": dict(pack_path_counts if pack_path_counts is not None else _internal_path_counts),
        "pack_state_counts": dict(pack_state_counts if pack_state_counts is not None else _internal_state_counts),
    }
    debug_print(
        "[SIM_POOL_DEBUG] [SIM_PATH_TRACE] "
        f"run_complete n={n} "
        f"chosen_pack_path_counts={result['pack_path_counts']}"
    )
    if export_debug_df:
        result["debug_df"] = pd.DataFrame(debug_rows)
    return result


def print_simulation_summary_v2(sim_results: Mapping[str, object], n_simulations: int = 1000000) -> None:
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
