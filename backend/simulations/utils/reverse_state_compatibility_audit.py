from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping

import pandas as pd

from backend.calculations.utils.reverse_pool import (
    REVERSE_PRICE_COLUMN,
    build_reverse_eligible_pool,
    get_normalized_base_rarity_key_series,
    get_normalized_classification_key_series,
    get_normalized_reverse_eligible_rarity_keys,
)
from backend.calculations.utils.special_type_normalization import RECOGNIZED_PATTERN_BUCKETS
from backend.simulations.monteCarloSimV2 import (
    resolve_slot_outcomes_from_state,
    validate_pack_state_model,
)
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups
from backend.simulations.utils.packStateModels.packStateCoercion import (
    DEFAULT_PACK_CONSTRAINTS,
    coerce_slot_outcomes,
    normalize_rarity,
)
from backend.simulations.utils.packStateModels.packStateModelOrchestrator import resolve_pack_state_model
from backend.simulations.utils.simulationTokenResolver import (
    get_simulation_token_mode,
    list_available_canonical_tokens,
    resolve_hit_pool_rows,
)


def _build_merged_constraints(config, model: Mapping[str, Any]) -> Dict[str, Any]:
    resolved_constraints = deepcopy(model.get("constraints", DEFAULT_PACK_CONSTRAINTS))
    defaults: Dict[str, Any] = {
        "primary_hits": set(resolved_constraints.get("primary_hits", set())),
        "exclusive_hits": set(resolved_constraints.get("exclusive_hits", set())),
        "bonus_hits": set(resolved_constraints.get("bonus_hits", set())),
        "max_major_hits": int(resolved_constraints.get("max_major_hits", 2)),
        "max_non_regular_hits": int(resolved_constraints.get("max_non_regular_hits", 2)),
        "max_exclusive_hits": int(resolved_constraints.get("max_exclusive_hits", 1)),
    }
    if "conditional_slot_exclusions" in resolved_constraints:
        defaults["conditional_slot_exclusions"] = resolved_constraints["conditional_slot_exclusions"]

    overrides = getattr(config, "PACK_CONSTRAINTS", None)
    if isinstance(overrides, dict):
        defaults.update(overrides)

    for key in ("primary_hits", "exclusive_hits", "bonus_hits"):
        defaults[key] = {normalize_rarity(x) for x in defaults.get(key, set())}

    return defaults


def audit_reverse_pool_composition(config, df: pd.DataFrame) -> Dict[str, Any]:
    """Audit reverse-pool composition under corrected base-pool semantics."""
    issues: List[str] = []

    reverse_pool = build_reverse_eligible_pool(config, df)
    if REVERSE_PRICE_COLUMN not in df.columns:
        issues.append(f"Source dataframe is missing '{REVERSE_PRICE_COLUMN}'.")

    rarity_keys = get_normalized_base_rarity_key_series(df)
    classification_keys = get_normalized_classification_key_series(df)
    reverse_prices = pd.to_numeric(df.get(REVERSE_PRICE_COLUMN, pd.Series(index=df.index)), errors="coerce")

    reverse_eligible_keys = get_normalized_reverse_eligible_rarity_keys(config)
    explicit_pattern_keys = reverse_eligible_keys & RECOGNIZED_PATTERN_BUCKETS
    base_rarity_keys = reverse_eligible_keys - RECOGNIZED_PATTERN_BUCKETS

    source_pattern_mask = classification_keys.isin(RECOGNIZED_PATTERN_BUCKETS)
    source_price_mask = reverse_prices.notna()

    expected_non_pattern_mask = rarity_keys.isin(base_rarity_keys) & ~source_pattern_mask & source_price_mask
    expected_pattern_mask = classification_keys.isin(explicit_pattern_keys) & source_price_mask

    missing_non_pattern = expected_non_pattern_mask[expected_non_pattern_mask].index.difference(reverse_pool.index)
    missing_pattern = expected_pattern_mask[expected_pattern_mask].index.difference(reverse_pool.index)

    if len(missing_non_pattern) > 0:
        issues.append(
            f"Reverse pool is missing {len(missing_non_pattern)} expected non-pattern reverse rows with prices."
        )

    if explicit_pattern_keys and len(missing_pattern) > 0:
        issues.append(
            f"Reverse pool is missing {len(missing_pattern)} pattern-overlay rows eligible for reverse outcomes."
        )

    reverse_pool_classification = get_normalized_classification_key_series(reverse_pool)
    reverse_pool_pattern_mask = reverse_pool_classification.isin(RECOGNIZED_PATTERN_BUCKETS)

    if explicit_pattern_keys and int(reverse_pool_pattern_mask.sum()) == 0:
        issues.append("Pattern keys are explicitly reverse-eligible, but reverse pool has no pattern rows.")

    if not explicit_pattern_keys and int(reverse_pool_pattern_mask.sum()) > 0:
        issues.append("Reverse pool contains pattern rows although config has no pattern reverse eligibility.")

    reverse_pool_prices = pd.to_numeric(reverse_pool.get(REVERSE_PRICE_COLUMN), errors="coerce")
    if reverse_pool_prices.isna().any():
        issues.append("Reverse pool contains rows with null/non-numeric reverse prices.")

    composition = {
        "source_total_rows": int(len(df)),
        "reverse_pool_total_rows": int(len(reverse_pool)),
        "source_rows_with_reverse_price": int(source_price_mask.sum()),
        "source_pattern_rows_with_reverse_price": int((source_pattern_mask & source_price_mask).sum()),
        "source_non_pattern_rows_with_reverse_price": int((~source_pattern_mask & source_price_mask).sum()),
        "expected_pattern_rows": int(expected_pattern_mask.sum()),
        "expected_non_pattern_rows": int(expected_non_pattern_mask.sum()),
        "actual_pattern_rows": int(reverse_pool_pattern_mask.sum()),
        "actual_non_pattern_rows": int((~reverse_pool_pattern_mask).sum()),
        "explicit_pattern_reverse_keys": sorted(explicit_pattern_keys),
        "missing_expected_pattern_rows": int(len(missing_pattern)),
        "missing_expected_non_pattern_rows": int(len(missing_non_pattern)),
    }

    return {
        "is_valid": len(issues) == 0,
        "composition": composition,
        "issues": issues,
    }


def audit_pattern_state_resolution(config, pools: Mapping[str, pd.DataFrame]) -> Dict[str, Any]:
    """Audit pattern token resolution from state outcomes against hit-pool data and constraints."""
    issues: List[str] = []
    resolvable: List[Dict[str, Any]] = []

    hit_pool = pools.get("hit", pd.DataFrame())
    if hit_pool.empty:
        issues.append("Hit pool is empty; cannot resolve pattern state outcomes.")

    try:
        validated_model = validate_pack_state_model(config, pools)
    except Exception as exc:  # pragma: no cover - defensive branch
        validated_model = resolve_pack_state_model(config)
        issues.append(f"validate_pack_state_model failed: {exc}")

    constraints = _build_merged_constraints(config, validated_model)
    state_outcomes = validated_model.get("state_outcomes", {})

    for state_name, slot_outcomes in state_outcomes.items():
        coerced = coerce_slot_outcomes(slot_outcomes, constraints)
        for slot_name, token in slot_outcomes.items():
            mode = get_simulation_token_mode(str(token))
            if mode != "pattern":
                continue

            eligible_rows, info = resolve_hit_pool_rows(hit_pool, str(token), mode="pattern")
            resolvable.append(
                {
                    "state": str(state_name),
                    "slot": str(slot_name),
                    "token": str(token),
                    "canonical_token": info.get("canonical_token"),
                    "resolved_rows": int(len(eligible_rows)),
                    "coerced_value": coerced.get(slot_name),
                }
            )

            if eligible_rows.empty:
                issues.append(
                    f"State '{state_name}' slot '{slot_name}' token '{token}' is not resolvable from hit pool."
                )

            if normalize_rarity(coerced.get(slot_name, "")) != normalize_rarity(str(token)):
                issues.append(
                    f"State '{state_name}' slot '{slot_name}' pattern token '{token}' is coerced to "
                    f"'{coerced.get(slot_name)}' by constraints."
                )

    if not resolvable:
        issues.append("No pattern outcomes found in resolved state model.")

    return {
        "is_valid": len(issues) == 0,
        "pattern_outcomes_resolvable": resolvable,
        "issues": issues,
    }


def audit_non_pattern_sets_compatibility(config, df: pd.DataFrame) -> Dict[str, Any]:
    """Audit that non-pattern sets keep reverse/state behavior unchanged and pattern-free."""
    issues: List[str] = []

    pools = extract_scarletandviolet_card_groups(config, df)
    reverse_pool = pools.get("reverse", pd.DataFrame())
    hit_pool = pools.get("hit", pd.DataFrame())

    source_classification = get_normalized_classification_key_series(df)
    source_pattern_count = int(source_classification.isin(RECOGNIZED_PATTERN_BUCKETS).sum())

    reverse_classification = get_normalized_classification_key_series(reverse_pool)
    reverse_pattern_count = int(reverse_classification.isin(RECOGNIZED_PATTERN_BUCKETS).sum())

    if source_pattern_count > 0:
        issues.append("Input dataframe contains pattern rows; this audit expects a non-pattern set dataset.")

    if reverse_pattern_count > 0:
        issues.append("Reverse pool contains pattern rows for a non-pattern set dataset.")

    pattern_tokens_in_hit = list_available_canonical_tokens(hit_pool, mode="pattern")
    if pattern_tokens_in_hit:
        issues.append(f"False-positive pattern tokens detected in hit pool: {pattern_tokens_in_hit}")

    try:
        validated_model = validate_pack_state_model(config, pools)
    except Exception as exc:
        validated_model = resolve_pack_state_model(config)
        issues.append(f"validate_pack_state_model failed for non-pattern set: {exc}")

    state_outcomes = validated_model.get("state_outcomes", {})
    for state_name, slot_outcomes in state_outcomes.items():
        try:
            resolved = resolve_slot_outcomes_from_state({"state": state_name}, config)
        except Exception as exc:  # pragma: no cover - defensive branch
            issues.append(f"State resolution failed for state '{state_name}': {exc}")
            continue

        for slot_name, token in resolved.items():
            if get_simulation_token_mode(str(token)) == "pattern":
                issues.append(
                    f"Non-pattern set state '{state_name}' resolved slot '{slot_name}' to pattern token '{token}'."
                )

            if slot_name.startswith("reverse") and normalize_rarity(token) == "regular reverse" and reverse_pool.empty:
                issues.append(
                    f"State '{state_name}' requires regular reverse, but reverse pool is empty."
                )

    tested_sets = [
        {
            "set": getattr(config, "SET_NAME", getattr(config, "__name__", str(config))),
            "state_count": int(len(state_outcomes)),
            "source_pattern_rows": source_pattern_count,
            "reverse_pattern_rows": reverse_pattern_count,
            "hit_pattern_tokens": pattern_tokens_in_hit,
        }
    ]

    return {
        "is_valid": len(issues) == 0,
        "tested_sets": tested_sets,
        "issues": issues,
    }
