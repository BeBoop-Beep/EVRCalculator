"""Project 6.8 read-only draft empirical output inspection.

Runs bounded slot-schema simulations for Chilling Reign (swsh6) and
Evolving Skies (swsh7) using test-only runtime subclasses that inject only
draft rare-slot probability tables.

The script is intentionally read-only:
- no runtime enablement is written to production config classes
- no production RARE_SLOT_PROBABILITY is added
- no DB writes are performed
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.simulations.evrSimulator import PackEVRSimulator, _build_slot_schema_card_pool
from backend.simulations.slotSchemaSimulator import simulate_slot_schema_packs
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups


DEFAULT_JSON_PATH = Path("logs/audits/swsh_draft_empirical_output_inspection.json")
DEFAULT_MD_PATH = Path("backend/docs/audits/SWSH_DRAFT_EMPIRICAL_OUTPUT_INSPECTION.md")

DEFAULT_PACK_PRICE = 4.99
AUTO_PACK_COUNT_HIGH = 100000
AUTO_PACK_COUNT_LOW = 50000
AUTO_SLOW_SET_SECONDS = 45.0

SIMULATION_INPUT_REQUIRED_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "name": ("Card Name", "name"),
    "card_number": ("Card Number", "card_number"),
    "rarity": ("Rarity", "rarity", "rarity_raw", "rarity_key"),
    "printing_type": ("printing_type", "Printing Type", "printing_type_key"),
}

PRICE_COLUMN_CANDIDATES: Tuple[str, ...] = (
    "Price ($)",
    "price",
    "market_price",
    "usd_market",
    "near_mint_price",
)


class DraftEmpiricalChillingReignRuntimeConfig(SetChillingReignConfig):
    SLOT_SCHEMA_RUNTIME_ENABLED = True
    RARE_SLOT_PROBABILITY = SetChillingReignConfig.CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT

    @classmethod
    def get_rarity_pack_multiplier(cls):
        return {"common": 5, "uncommon": 3}


class DraftEmpiricalEvolvingSkiesRuntimeConfig(SetEvolvingSkiesConfig):
    SLOT_SCHEMA_RUNTIME_ENABLED = True
    RARE_SLOT_PROBABILITY = SetEvolvingSkiesConfig.EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT

    @classmethod
    def get_rarity_pack_multiplier(cls):
        return {"common": 5, "uncommon": 3}


@dataclass(frozen=True)
class InspectionTarget:
    set_id: str
    canonical_key: str
    set_name: str
    production_config: Any
    runtime_config: Any
    draft_table_attr: str


TARGETS: Tuple[InspectionTarget, ...] = (
    InspectionTarget(
        set_id="swsh6",
        canonical_key="chillingReign",
        set_name="Chilling Reign",
        production_config=SetChillingReignConfig,
        runtime_config=DraftEmpiricalChillingReignRuntimeConfig,
        draft_table_attr="CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT",
    ),
    InspectionTarget(
        set_id="swsh7",
        canonical_key="evolvingSkies",
        set_name="Evolving Skies",
        production_config=SetEvolvingSkiesConfig,
        runtime_config=DraftEmpiricalEvolvingSkiesRuntimeConfig,
        draft_table_attr="EVOLVING_SKIES_RARE_SLOT_PROBABILITY_DRAFT",
    ),
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0:
        return float(min(values))
    if q >= 1:
        return float(max(values))

    ordered = sorted(float(v) for v in values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def _compute_probability_table_status(target: InspectionTarget) -> Dict[str, Any]:
    draft_table = dict(getattr(target.production_config, target.draft_table_attr))
    mapping_keys = set(target.production_config.SLOT_SCHEMA_OUTCOME_POOL_MAPPING.keys())
    table_keys = set(draft_table.keys())

    probability_sum = sum(float(v) for v in draft_table.values())
    sum_is_one = abs(probability_sum - 1.0) <= 1e-9

    return {
        "draft_table_attr": target.draft_table_attr,
        "sum_probability": probability_sum,
        "sum_is_one": sum_is_one,
        "mapping_keys_match": table_keys == mapping_keys,
        "missing_mapping_keys": sorted(mapping_keys - table_keys),
        "unexpected_table_keys": sorted(table_keys - mapping_keys),
        "residual_rare_probability": float(draft_table.get("rare", 0.0)),
        "production_runtime_enabled": bool(getattr(target.production_config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)),
        "production_has_rare_slot_probability": hasattr(target.production_config, "RARE_SLOT_PROBABILITY"),
        "draft_probability_table": {key: float(value) for key, value in draft_table.items()},
    }


def _load_fallback_simulation_input(target: InspectionTarget) -> Tuple[Any, float, str]:
    from backend.tests.unit.simulations.test_slot_schema_simulation_math_validation import (  # noqa: WPS433
        _build_chilling_reign_variant_level_df,
        _build_evolving_skies_variant_level_df,
    )

    if target.set_id == "swsh6":
        return _build_chilling_reign_variant_level_df(), DEFAULT_PACK_PRICE, "fallback_test_builder"
    if target.set_id == "swsh7":
        return _build_evolving_skies_variant_level_df(), DEFAULT_PACK_PRICE, "fallback_test_builder"
    raise ValueError(f"No fallback builder configured for {target.set_id!r}")


def _load_simulation_input(
    target: InspectionTarget,
    prefer_db_input: bool = True,
    allow_fallback: bool = True,
) -> Tuple[Any, float, Dict[str, Any]]:
    diagnostics: Dict[str, Any] = {
        "source": "",
        "db_attempted": bool(prefer_db_input),
        "db_error": None,
        "fallback_used": False,
    }

    if prefer_db_input:
        try:
            from backend.db.services.evr_input_preparation_service import EVRInputPreparationService  # noqa: WPS433

            prepared = EVRInputPreparationService().prepare_for_set(
                target.runtime_config(),
                target.canonical_key,
                target.set_name,
            )
            dataframe = prepared.get("dataframe")
            pack_price = prepared.get("pack_price")
            if dataframe is None or getattr(dataframe, "empty", True):
                raise ValueError("DB input preparation returned an empty dataframe")
            diagnostics["source"] = "db_evr_input_preparation_service"
            return dataframe, _safe_float(pack_price, DEFAULT_PACK_PRICE), diagnostics
        except Exception as exc:  # pragma: no cover - environment dependent
            diagnostics["db_error"] = f"{type(exc).__name__}: {exc}"
            if not allow_fallback:
                raise RuntimeError(
                    "DB input path failed with fallback disabled | "
                    f"set_id={target.set_id} | set_name={target.set_name} | "
                    "attempted_source=db_evr_input_preparation_service | "
                    f"original_exception={type(exc).__name__}: {exc}"
                ) from exc

    if not allow_fallback:
        raise RuntimeError(
            "Fallback is disabled and DB input was not available | "
            f"set_id={target.set_id} | set_name={target.set_name} | "
            f"attempted_source={'db_evr_input_preparation_service' if prefer_db_input else '<none>'}"
        )

    fallback_df, fallback_pack_price, fallback_source = _load_fallback_simulation_input(target)
    diagnostics["source"] = fallback_source
    diagnostics["fallback_used"] = True
    return fallback_df, fallback_pack_price, diagnostics


def _resolve_detected_price_column(df: pd.DataFrame) -> Optional[str]:
    for column in PRICE_COLUMN_CANDIDATES:
        if column not in df.columns:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().any():
            return str(column)
    return None


def _build_simulation_input_metadata(
    dataframe: Any,
    *,
    source: str,
    db_attempted: bool,
    fallback_used: bool,
    strict_db_input: bool,
) -> Dict[str, Any]:
    if not isinstance(dataframe, pd.DataFrame):
        return {
            "source": source,
            "db_attempted": bool(db_attempted),
            "fallback_used": bool(fallback_used),
            "strict_db_input": bool(strict_db_input),
            "row_count": 0,
            "column_names": [],
            "required_columns_present": False,
            "missing_required_columns": list(SIMULATION_INPUT_REQUIRED_COLUMNS.keys()),
            "price_column_detected": None,
            "non_positive_price_rows": 0,
            "missing_price_rows": 0,
            "usable_price_rows": 0,
        }

    row_count = int(len(dataframe))
    column_names = [str(column) for column in dataframe.columns]

    missing_required: List[str] = []
    for canonical_name, aliases in SIMULATION_INPUT_REQUIRED_COLUMNS.items():
        if not any(alias in dataframe.columns for alias in aliases):
            missing_required.append(canonical_name)

    detected_price_column = _resolve_detected_price_column(dataframe)
    if detected_price_column is None:
        missing_price_rows = row_count
        non_positive_price_rows = 0
        usable_price_rows = 0
    else:
        numeric_price = pd.to_numeric(dataframe[detected_price_column], errors="coerce")
        missing_price_rows = int(numeric_price.isna().sum())
        non_positive_price_rows = int((numeric_price.fillna(0.0) <= 0.0).sum())
        usable_price_rows = int((numeric_price.fillna(0.0) > 0.0).sum())

    return {
        "source": source,
        "db_attempted": bool(db_attempted),
        "fallback_used": bool(fallback_used),
        "strict_db_input": bool(strict_db_input),
        "row_count": row_count,
        "column_names": sorted(column_names),
        "required_columns_present": len(missing_required) == 0,
        "missing_required_columns": missing_required,
        "price_column_detected": detected_price_column,
        "non_positive_price_rows": non_positive_price_rows,
        "missing_price_rows": missing_price_rows,
        "usable_price_rows": usable_price_rows,
    }


def _raise_strict_db_input_failure(
    target: InspectionTarget,
    *,
    attempted_source: str,
    reason: str,
    original_exception: Optional[BaseException] = None,
    input_metadata: Optional[Mapping[str, Any]] = None,
) -> None:
    message_parts = [
        "Strict DB-source input validation failed.",
        f"set_id={target.set_id}",
        f"set_name={target.set_name}",
        f"attempted_source={attempted_source}",
        f"reason={reason}",
    ]

    if input_metadata:
        missing_required = list(input_metadata.get("missing_required_columns") or [])
        if missing_required:
            message_parts.append(f"missing_required_columns={missing_required}")
        message_parts.append(f"price_column_detected={input_metadata.get('price_column_detected')}")
        message_parts.append(f"usable_price_rows={input_metadata.get('usable_price_rows')}")

    if original_exception is not None:
        message_parts.append(
            "original_exception="
            f"{type(original_exception).__name__}: {original_exception}"
        )

    raise RuntimeError(" | ".join(message_parts))


def _max_pool_value_card(card_pool: Mapping[str, Sequence[Mapping[str, Any]]]) -> Dict[str, Any]:
    best: Optional[Dict[str, Any]] = None
    for bucket, rows in card_pool.items():
        for row in rows:
            value = _safe_float(row.get("value"), 0.0)
            candidate = {
                "bucket": str(bucket),
                "card_name": str(row.get("Card Name") or row.get("name") or ""),
                "card_number": str(row.get("Card Number") or row.get("card_number") or ""),
                "printing_type": str(row.get("printing_type") or ""),
                "value": value,
            }
            if best is None or candidate["value"] > best["value"]:
                best = candidate
    return best or {"bucket": None, "card_name": None, "card_number": None, "printing_type": None, "value": 0.0}


def _compute_rare_slot_frequency_deltas(
    draft_table: Mapping[str, float],
    rarity_counts: Mapping[str, int],
    pack_count: int,
) -> Tuple[List[Dict[str, Any]], float]:
    deltas: List[Dict[str, Any]] = []
    largest_abs_delta = 0.0

    for bucket, expected_probability in draft_table.items():
        observed_count = int(rarity_counts.get(bucket, 0))
        observed_probability = (observed_count / pack_count) if pack_count > 0 else 0.0
        delta = observed_probability - float(expected_probability)
        abs_delta = abs(delta)
        largest_abs_delta = max(largest_abs_delta, abs_delta)
        deltas.append(
            {
                "bucket": str(bucket),
                "expected_bucket_probability": float(expected_probability),
                "observed_bucket_probability": observed_probability,
                "observed_count": observed_count,
                "delta": delta,
                "abs_delta": abs_delta,
            }
        )

    deltas.sort(key=lambda row: (-row["abs_delta"], row["bucket"]))
    return deltas, largest_abs_delta


def _top_ev_contributions_from_pools(
    card_pool: Mapping[str, Sequence[Mapping[str, Any]]],
    draft_table: Mapping[str, float],
    total_pack_ev: float,
    limit: int = 10,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    per_card_ev: Dict[str, float] = {}

    for bucket, probability in draft_table.items():
        pool = list(card_pool.get(bucket, []))
        if not pool:
            continue

        per_card_probability = _safe_float(probability, 0.0) / float(len(pool))
        if per_card_probability <= 0.0:
            continue

        for row in pool:
            card_name = str(row.get("Card Name") or row.get("name") or "<unknown>")
            value = _safe_float(row.get("value"), 0.0)
            contribution = per_card_probability * value
            per_card_ev[card_name] = per_card_ev.get(card_name, 0.0) + contribution

    ordered = sorted(per_card_ev.items(), key=lambda item: (-_safe_float(item[1]), str(item[0])))
    rare_slot_ev_total = sum(_safe_float(value) for _card, value in ordered)

    top_rows: List[Dict[str, Any]] = []
    for card_name, ev_value in ordered[:limit]:
        numeric_ev = _safe_float(ev_value)
        top_rows.append(
            {
                "card_name": str(card_name),
                "display_label": str(card_name),
                "ev_contribution": numeric_ev,
                "share_of_hit_ev": (numeric_ev / rare_slot_ev_total) if rare_slot_ev_total > 0 else 0.0,
                "share_of_total_pack_ev": (numeric_ev / total_pack_ev) if total_pack_ev > 0 else 0.0,
            }
        )

    top_1_share = top_rows[0]["share_of_hit_ev"] if top_rows else 0.0
    top_5_share = sum(row["share_of_hit_ev"] for row in top_rows[:5])
    concentration = {
        "top_1_share_of_hit_ev": top_1_share,
        "top_5_share_of_hit_ev": top_5_share,
        "hit_ev_total": rare_slot_ev_total,
        "total_pack_ev": total_pack_ev,
    }
    return top_rows, concentration


def _reverse_slot_sanity_check(
    runtime_config: Any,
    card_pool: Mapping[str, Sequence[Mapping[str, Any]]],
    rarity_counts: Mapping[str, int],
    pack_count: int,
) -> Dict[str, Any]:
    reverse_table = getattr(runtime_config, "REVERSE_SLOT_PROBABILITIES", {}) or {}
    expected_regular_reverse = 0.0
    for slot_table in reverse_table.values():
        if isinstance(slot_table, Mapping):
            expected_regular_reverse += _safe_float(slot_table.get("regular reverse"), 0.0)

    expected_regular_reverse_count = int(round(pack_count * expected_regular_reverse))
    observed_regular_reverse_count = int(rarity_counts.get("regular reverse", 0))

    leakage_by_bucket: Dict[str, int] = {}
    for bucket in runtime_config.RARE_SLOT_PROBABILITY.keys():
        bucket_pool = list(card_pool.get(bucket, []))
        leak_count = sum(1 for row in bucket_pool if str(row.get("printing_type") or "").strip().lower() == "reverse-holo")
        if leak_count > 0:
            leakage_by_bucket[str(bucket)] = int(leak_count)

    reverse_pool_count = len(card_pool.get("reverse", []))
    reverse_pool_has_non_reverse = any(
        str(row.get("printing_type") or "").strip().lower() != "reverse-holo"
        for row in card_pool.get("reverse", [])
    )

    return {
        "expected_regular_reverse_probability": expected_regular_reverse,
        "expected_regular_reverse_count": expected_regular_reverse_count,
        "observed_regular_reverse_count": observed_regular_reverse_count,
        "count_delta": observed_regular_reverse_count - expected_regular_reverse_count,
        "reverse_pool_count": reverse_pool_count,
        "reverse_pool_has_non_reverse_entries": reverse_pool_has_non_reverse,
        "rare_slot_reverse_holo_leakage_by_bucket": leakage_by_bucket,
        "has_reverse_holo_leakage": bool(leakage_by_bucket),
    }


def _warning_flags(
    *,
    probability_status: Mapping[str, Any],
    avg_pack_value: float,
    median_pack_value: float,
    pack_price: float,
    largest_rare_slot_delta: float,
    reverse_sanity: Mapping[str, Any],
    card_pool: Mapping[str, Sequence[Mapping[str, Any]]],
    draft_table: Mapping[str, float],
    top_concentration: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    flags: List[Dict[str, Any]] = []

    def emit(code: str, severity: str, triggered: bool, detail: str, value: Any = None, threshold: Any = None) -> None:
        flags.append(
            {
                "code": code,
                "severity": severity,
                "triggered": bool(triggered),
                "detail": detail,
                "value": value,
                "threshold": threshold,
            }
        )

    impossible = (
        avg_pack_value < 0.0
        or median_pack_value < 0.0
        or not bool(probability_status.get("sum_is_one"))
        or not bool(probability_status.get("mapping_keys_match"))
    )
    emit(
        "negative_or_impossible_metric",
        "critical",
        impossible,
        "Negative central metric or invalid probability-table contract detected.",
        value={
            "avg_pack_value": avg_pack_value,
            "median_pack_value": median_pack_value,
            "sum_is_one": bool(probability_status.get("sum_is_one")),
            "mapping_keys_match": bool(probability_status.get("mapping_keys_match")),
        },
    )

    low_floor = max(pack_price * 0.05, 0.10)
    high_ceiling = max(pack_price * 8.0, 60.0)
    implausible = avg_pack_value < low_floor or avg_pack_value > high_ceiling
    emit(
        "average_pack_value_implausible",
        "warning",
        implausible,
        "Average simulated pack value falls outside broad plausibility bounds.",
        value=avg_pack_value,
        threshold={"min": low_floor, "max": high_ceiling},
    )

    emit(
        "rare_slot_frequency_drift_too_large",
        "warning",
        largest_rare_slot_delta > 0.03,
        "Largest bucket-frequency delta exceeds tolerance.",
        value=largest_rare_slot_delta,
        threshold=0.03,
    )

    leakage_by_bucket = reverse_sanity.get("rare_slot_reverse_holo_leakage_by_bucket", {}) or {}
    reverse_leakage = bool(reverse_sanity.get("has_reverse_holo_leakage")) or bool(leakage_by_bucket)
    emit(
        "reverse_holo_leakage",
        "critical",
        reverse_leakage,
        "Reverse-holo leakage detected in rare-slot buckets.",
        value={
            "leakage_by_bucket": leakage_by_bucket,
            "reverse_pool_has_non_reverse_entries": bool(reverse_sanity.get("reverse_pool_has_non_reverse_entries")),
        },
    )

    reverse_pool_representation_uses_base_rows = bool(
        reverse_sanity.get("reverse_pool_has_non_reverse_entries")
    )
    emit(
        "reverse_pool_representation_uses_base_rows",
        "info",
        reverse_pool_representation_uses_base_rows,
        (
            "Reverse pool contains non-reverse printing_type rows, likely because DB legacy input "
            "represents reverse-slot values through Reverse Variant Price ($). This is not rare-slot leakage "
            "when rare_slot_reverse_holo_leakage_by_bucket is empty."
        ),
        value={
            "reverse_pool_has_non_reverse_entries": reverse_pool_representation_uses_base_rows,
            "reverse_pool_count": int(reverse_sanity.get("reverse_pool_count", 0) or 0),
        },
    )

    reverse_slot_count_delta = int(reverse_sanity.get("count_delta", 0) or 0)
    emit(
        "reverse_slot_regular_count_mismatch",
        "warning",
        reverse_slot_count_delta != 0,
        "Observed regular reverse count differs from expected count derived from REVERSE_SLOT_PROBABILITIES.",
        value={
            "expected_regular_reverse_count": int(reverse_sanity.get("expected_regular_reverse_count", 0) or 0),
            "observed_regular_reverse_count": int(reverse_sanity.get("observed_regular_reverse_count", 0) or 0),
            "count_delta": reverse_slot_count_delta,
        },
        threshold=0,
    )

    missing_bucket_pool = [bucket for bucket in draft_table.keys() if not card_pool.get(bucket)]
    emit(
        "missing_bucket_pool",
        "critical",
        bool(missing_bucket_pool),
        "One or more draft buckets resolved to missing/empty pools.",
        value=missing_bucket_pool,
    )

    important_buckets = [bucket for bucket, probability in draft_table.items() if _safe_float(probability) >= 0.05]
    missing_prices = {}
    for bucket in important_buckets:
        pool = list(card_pool.get(bucket, []))
        if not pool:
            continue
        non_positive = sum(1 for row in pool if _safe_float(row.get("value"), 0.0) <= 0.0)
        if non_positive > 0:
            missing_prices[bucket] = {
                "non_positive_price_rows": non_positive,
                "pool_size": len(pool),
            }
    emit(
        "missing_prices_in_important_buckets",
        "warning",
        bool(missing_prices),
        "Important probability buckets include non-positive prices.",
        value=missing_prices,
    )

    top_1_share = _safe_float(top_concentration.get("top_1_share_of_hit_ev"), 0.0)
    top_5_share = _safe_float(top_concentration.get("top_5_share_of_hit_ev"), 0.0)
    concentration_extreme = top_1_share > 0.55 or top_5_share > 0.90
    emit(
        "top_card_ev_concentration_extreme",
        "warning",
        concentration_extreme,
        "Top-card EV concentration is unusually high.",
        value={"top_1_share_of_hit_ev": top_1_share, "top_5_share_of_hit_ev": top_5_share},
        threshold={"top_1": 0.55, "top_5": 0.90},
    )

    return flags


def _run_single_set_inspection(
    target: InspectionTarget,
    *,
    pack_count: int,
    seed: int,
    prefer_db_input: bool,
    strict_db_input: bool,
) -> Dict[str, Any]:
    probability_status = _compute_probability_table_status(target)
    draft_table = dict(probability_status["draft_probability_table"])

    try:
        simulation_df, estimated_pack_price, input_diagnostics = _load_simulation_input(
            target,
            prefer_db_input=prefer_db_input,
            allow_fallback=not strict_db_input,
        )
    except Exception as exc:
        _raise_strict_db_input_failure(
            target,
            attempted_source="db_evr_input_preparation_service",
            reason="db_input_loading_failed",
            original_exception=exc,
        )

    input_metadata = _build_simulation_input_metadata(
        simulation_df,
        source=str(input_diagnostics.get("source") or ""),
        db_attempted=bool(input_diagnostics.get("db_attempted")),
        fallback_used=bool(input_diagnostics.get("fallback_used")),
        strict_db_input=bool(strict_db_input),
    )

    if strict_db_input and input_metadata.get("fallback_used"):
        _raise_strict_db_input_failure(
            target,
            attempted_source=str(input_metadata.get("source") or "<unknown>"),
            reason="fallback_input_forbidden_in_strict_mode",
            input_metadata=input_metadata,
        )

    if strict_db_input and int(input_metadata.get("row_count", 0)) <= 0:
        _raise_strict_db_input_failure(
            target,
            attempted_source=str(input_metadata.get("source") or "<unknown>"),
            reason="empty_dataframe",
            input_metadata=input_metadata,
        )

    if strict_db_input and not bool(input_metadata.get("required_columns_present")):
        _raise_strict_db_input_failure(
            target,
            attempted_source=str(input_metadata.get("source") or "<unknown>"),
            reason="missing_required_columns",
            input_metadata=input_metadata,
        )

    if strict_db_input and not input_metadata.get("price_column_detected"):
        _raise_strict_db_input_failure(
            target,
            attempted_source=str(input_metadata.get("source") or "<unknown>"),
            reason="price_value_field_not_detected",
            input_metadata=input_metadata,
        )

    if strict_db_input and int(input_metadata.get("usable_price_rows", 0)) <= 0:
        _raise_strict_db_input_failure(
            target,
            attempted_source=str(input_metadata.get("source") or "<unknown>"),
            reason="no_usable_price_rows",
            input_metadata=input_metadata,
        )

    runtime_config = target.runtime_config

    card_groups = extract_scarletandviolet_card_groups(runtime_config, simulation_df)
    card_pool = _build_slot_schema_card_pool(runtime_config, card_groups, simulation_df)

    sim_results = simulate_slot_schema_packs(
        runtime_config,
        card_pool,
        num_packs=int(pack_count),
        rng=random.Random(seed),
    )

    pack_values = [float(v) for v in sim_results.get("values", [])]
    pack_count_observed = len(pack_values)
    mean_pack_value = _safe_float(sim_results.get("mean"), sum(pack_values) / pack_count_observed if pack_count_observed else 0.0)
    median_pack_value = float(median(pack_values)) if pack_values else 0.0

    simulator = PackEVRSimulator(runtime_config)
    pack_metrics = simulator.calculate_pack_metrics(sim_results, estimated_pack_price)

    top_cards, concentration = _top_ev_contributions_from_pools(card_pool, draft_table, mean_pack_value)

    big_hit_threshold = max(estimated_pack_price * 3.0, _quantile(pack_values, 0.95)) if pack_values else estimated_pack_price * 3.0
    chance_to_beat_pack_cost = (
        sum(1 for value in pack_values if value > estimated_pack_price) / pack_count_observed
        if pack_count_observed
        else 0.0
    )
    chance_big_hit = (
        sum(1 for value in pack_values if value >= big_hit_threshold) / pack_count_observed
        if pack_count_observed
        else 0.0
    )

    rarity_counts = sim_results.get("rarity_pull_counts", {}) or {}
    rare_slot_deltas, largest_delta = _compute_rare_slot_frequency_deltas(draft_table, rarity_counts, pack_count_observed)
    reverse_sanity = _reverse_slot_sanity_check(runtime_config, card_pool, rarity_counts, pack_count_observed)
    best_pool_card = _max_pool_value_card(card_pool)

    warnings = _warning_flags(
        probability_status=probability_status,
        avg_pack_value=mean_pack_value,
        median_pack_value=median_pack_value,
        pack_price=estimated_pack_price,
        largest_rare_slot_delta=largest_delta,
        reverse_sanity=reverse_sanity,
        card_pool=card_pool,
        draft_table=draft_table,
        top_concentration=concentration,
    )

    return {
        "set_id": target.set_id,
        "set_name": target.set_name,
        "canonical_key": target.canonical_key,
        "simulation_input": input_metadata,
        "pack_count": pack_count_observed,
        "estimated_pack_price": estimated_pack_price,
        "probability_table_status": probability_status,
        "rare_slot_probability_table": draft_table,
        "residual_rare_probability": float(draft_table.get("rare", 0.0)),
        "metrics": {
            "average_pack_value": mean_pack_value,
            "median_pack_value": median_pack_value,
            "roi_at_estimated_pack_price": _safe_float(pack_metrics.get("opening_pack_roi"), 0.0),
            "chance_to_beat_pack_cost": chance_to_beat_pack_cost,
            "chance_at_big_hit": chance_big_hit,
            "big_hit_threshold": big_hit_threshold,
            "p05": _quantile(pack_values, 0.05),
            "p95": _quantile(pack_values, 0.95),
            "p99": _quantile(pack_values, 0.99),
            "best_simulated_pull": {
                "max_pack_value": _safe_float(sim_results.get("max"), max(pack_values) if pack_values else 0.0),
                "best_pool_card_reference": best_pool_card,
            },
        },
        "top_ev_contributing_cards": top_cards,
        "cards_carrying_set": concentration,
        "rare_slot_bucket_frequencies": [
            {
                "bucket": row["bucket"],
                "observed_count": row["observed_count"],
                "observed_probability": row["observed_bucket_probability"],
            }
            for row in rare_slot_deltas
        ],
        "rare_slot_frequency_deltas": {
            "rows": rare_slot_deltas,
            "largest_abs_delta": largest_delta,
        },
        "reverse_slot_sanity_check": reverse_sanity,
        "warning_flags": warnings,
    }


def _render_markdown_report(payload: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# SWSH Draft Empirical Output Inspection")
    lines.append("")
    lines.append(f"Generated: {payload.get('meta', {}).get('generated_at_utc', '')}")
    lines.append("")
    lines.append(
        "Runtime approval input status: "
        f"{payload.get('runtime_approval_input_status', '<unknown>')}"
    )
    lines.append("")
    lines.append("Read-only inspection report for swsh6 and swsh7 draft slot-schema runtime subclasses.")
    lines.append("")

    for row in payload.get("sets", []):
        metrics = row.get("metrics", {})
        warnings = row.get("warning_flags", [])
        triggered = [flag for flag in warnings if flag.get("triggered")]
        probability_status = row.get("probability_table_status", {})
        deltas = row.get("rare_slot_frequency_deltas", {}).get("rows", [])
        reverse_sanity = row.get("reverse_slot_sanity_check", {})

        lines.append(f"## {row.get('set_name')} ({row.get('set_id')})")
        lines.append("")
        lines.append(f"- Pack count: {row.get('pack_count')}")
        lines.append(f"- Input source: {row.get('simulation_input', {}).get('source')}")
        lines.append(f"- Input rows: {row.get('simulation_input', {}).get('row_count')}")
        lines.append(f"- Strict DB input: {row.get('simulation_input', {}).get('strict_db_input')}")
        lines.append(f"- Fallback used: {row.get('simulation_input', {}).get('fallback_used')}")
        lines.append(f"- Price field detected: {row.get('simulation_input', {}).get('price_column_detected')}")
        lines.append(f"- Missing price rows: {row.get('simulation_input', {}).get('missing_price_rows')}")
        lines.append(f"- Non-positive price rows: {row.get('simulation_input', {}).get('non_positive_price_rows')}")
        lines.append(f"- Usable price rows: {row.get('simulation_input', {}).get('usable_price_rows')}")
        lines.append(f"- Estimated pack price: {row.get('estimated_pack_price'):.4f}")
        lines.append(f"- Residual rare probability: {row.get('residual_rare_probability'):.6f}")
        lines.append(f"- Average pack value: {metrics.get('average_pack_value', 0.0):.6f}")
        lines.append(f"- Median pack value: {metrics.get('median_pack_value', 0.0):.6f}")
        lines.append(f"- ROI at estimated pack price: {metrics.get('roi_at_estimated_pack_price', 0.0):.6f}")
        lines.append(f"- Chance to beat pack cost: {metrics.get('chance_to_beat_pack_cost', 0.0):.6%}")
        lines.append(f"- Chance at big hit: {metrics.get('chance_at_big_hit', 0.0):.6%}")
        lines.append(f"- P05/P95/P99: {metrics.get('p05', 0.0):.6f} / {metrics.get('p95', 0.0):.6f} / {metrics.get('p99', 0.0):.6f}")
        lines.append("")

        lines.append("### Probability Table Status")
        lines.append("")
        lines.append(f"- Sum is one: {probability_status.get('sum_is_one')}")
        lines.append(f"- Mapping keys match: {probability_status.get('mapping_keys_match')}")
        lines.append(f"- Production runtime enabled: {probability_status.get('production_runtime_enabled')}")
        lines.append(f"- Production has RARE_SLOT_PROBABILITY: {probability_status.get('production_has_rare_slot_probability')}")
        lines.append("")

        lines.append("### Largest Bucket Deltas")
        lines.append("")
        lines.append("| bucket | expected | observed | delta | abs_delta |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for delta_row in deltas[:10]:
            lines.append(
                "| {bucket} | {expected:.6f} | {observed:.6f} | {delta:.6f} | {abs_delta:.6f} |".format(
                    bucket=delta_row.get("bucket", ""),
                    expected=_safe_float(delta_row.get("expected_bucket_probability"), 0.0),
                    observed=_safe_float(delta_row.get("observed_bucket_probability"), 0.0),
                    delta=_safe_float(delta_row.get("delta"), 0.0),
                    abs_delta=_safe_float(delta_row.get("abs_delta"), 0.0),
                )
            )
        lines.append("")

        lines.append("### Reverse Slot Sanity")
        lines.append("")
        lines.append(
            "- expected regular reverse count: {exp} | observed: {obs} | delta: {delta}".format(
                exp=reverse_sanity.get("expected_regular_reverse_count"),
                obs=reverse_sanity.get("observed_regular_reverse_count"),
                delta=reverse_sanity.get("count_delta"),
            )
        )
        lines.append(f"- reverse-holo leakage present: {reverse_sanity.get('has_reverse_holo_leakage')}")
        lines.append("")

        lines.append("### Top EV-Contributing Cards")
        lines.append("")
        lines.append("| card | ev_contribution | share_of_hit_ev |")
        lines.append("| --- | ---: | ---: |")
        for card_row in row.get("top_ev_contributing_cards", [])[:10]:
            lines.append(
                "| {card} | {ev:.6f} | {share:.6%} |".format(
                    card=str(card_row.get("display_label") or card_row.get("card_name") or ""),
                    ev=_safe_float(card_row.get("ev_contribution"), 0.0),
                    share=_safe_float(card_row.get("share_of_hit_ev"), 0.0),
                )
            )
        lines.append("")

        lines.append("### Warning Flags")
        lines.append("")
        if triggered:
            for flag in triggered:
                lines.append(f"- TRIGGERED [{flag.get('severity')}] {flag.get('code')}: {flag.get('detail')}")
        else:
            lines.append("- No warning flags triggered.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run_draft_output_inspection(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    markdown_output_path: Path = DEFAULT_MD_PATH,
    pack_count: Optional[int] = None,
    auto_slow_set_seconds: float = AUTO_SLOW_SET_SECONDS,
    seed_base: int = 68000,
    prefer_db_input: bool = True,
    strict_db_input: bool = False,
) -> Dict[str, Any]:
    start = time.perf_counter()

    production_guardrail_snapshot = {
        target.set_id: {
            "slot_schema_runtime_enabled": bool(getattr(target.production_config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)),
            "has_rare_slot_probability": hasattr(target.production_config, "RARE_SLOT_PROBABILITY"),
        }
        for target in TARGETS
    }

    if pack_count is not None:
        set_pack_counts = {target.set_id: int(pack_count) for target in TARGETS}
        auto_mode = False
    else:
        set_pack_counts = {TARGETS[0].set_id: AUTO_PACK_COUNT_HIGH, TARGETS[1].set_id: AUTO_PACK_COUNT_HIGH}
        auto_mode = True

    rows: List[Dict[str, Any]] = []
    for index, target in enumerate(TARGETS):
        target_pack_count = int(set_pack_counts[target.set_id])
        target_seed = int(seed_base + index)

        t0 = time.perf_counter()
        try:
            row = _run_single_set_inspection(
                target,
                pack_count=target_pack_count,
                seed=target_seed,
                prefer_db_input=prefer_db_input,
                strict_db_input=strict_db_input,
            )
        except Exception as exc:
            # Retry once with a lower bound if auto mode requested and high count failed.
            if auto_mode and not strict_db_input and target_pack_count > AUTO_PACK_COUNT_LOW:
                row = _run_single_set_inspection(
                    target,
                    pack_count=AUTO_PACK_COUNT_LOW,
                    seed=target_seed,
                    prefer_db_input=prefer_db_input,
                    strict_db_input=strict_db_input,
                )
            else:
                if strict_db_input:
                    failure_guardrail_after = {
                        target_row.set_id: {
                            "slot_schema_runtime_enabled": bool(getattr(target_row.production_config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)),
                            "has_rare_slot_probability": hasattr(target_row.production_config, "RARE_SLOT_PROBABILITY"),
                        }
                        for target_row in TARGETS
                    }
                    failure_payload = {
                        "meta": {
                            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                            "project": "6.8",
                            "read_only": True,
                            "strict_db_input": True,
                            "elapsed_seconds": time.perf_counter() - start,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                        "guardrails": {
                            "before": production_guardrail_snapshot,
                            "after": failure_guardrail_after,
                            "unchanged": production_guardrail_snapshot == failure_guardrail_after,
                        },
                        "runtime_approval_input_status": "strict_db_input_failed",
                        "sets": rows,
                    }
                    json_output_path.parent.mkdir(parents=True, exist_ok=True)
                    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
                    json_output_path.write_text(json.dumps(failure_payload, indent=2, sort_keys=True), encoding="utf-8")
                    markdown_output_path.write_text(_render_markdown_report(failure_payload), encoding="utf-8")
                raise

        elapsed = time.perf_counter() - t0
        row["elapsed_seconds"] = elapsed
        rows.append(row)

        if auto_mode and target.set_id == TARGETS[0].set_id and elapsed > auto_slow_set_seconds:
            set_pack_counts[TARGETS[1].set_id] = AUTO_PACK_COUNT_LOW

    production_guardrail_after = {
        target.set_id: {
            "slot_schema_runtime_enabled": bool(getattr(target.production_config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)),
            "has_rare_slot_probability": hasattr(target.production_config, "RARE_SLOT_PROBABILITY"),
        }
        for target in TARGETS
    }

    any_fallback = any(bool((row.get("simulation_input") or {}).get("fallback_used")) for row in rows)
    runtime_approval_input_status = "strict_db_input_passed" if strict_db_input else "fallback_behavior_only"
    if any_fallback:
        runtime_approval_input_status = "fallback_behavior_only"

    payload = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "6.8",
            "read_only": True,
            "auto_pack_count_mode": auto_mode,
            "default_high_pack_count": AUTO_PACK_COUNT_HIGH,
            "fallback_low_pack_count": AUTO_PACK_COUNT_LOW,
            "elapsed_seconds": time.perf_counter() - start,
        },
        "guardrails": {
            "before": production_guardrail_snapshot,
            "after": production_guardrail_after,
            "unchanged": production_guardrail_snapshot == production_guardrail_after,
        },
        "runtime_approval_input_status": runtime_approval_input_status,
        "sets": rows,
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_output_path.write_text(_render_markdown_report(payload), encoding="utf-8")

    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only SWSH draft empirical output inspection")
    parser.add_argument(
        "--json-output",
        default=str(DEFAULT_JSON_PATH),
        help="JSON output path",
    )
    parser.add_argument(
        "--markdown-output",
        default=str(DEFAULT_MD_PATH),
        help="Markdown output path",
    )
    parser.add_argument(
        "--pack-count",
        type=int,
        default=None,
        help="Fixed pack count for each set (default: auto 100k, fallback/adjust to 50k)",
    )
    parser.add_argument(
        "--seed-base",
        type=int,
        default=68000,
        help="Base random seed for deterministic bounded runs",
    )
    parser.add_argument(
        "--no-db-input",
        action="store_true",
        help="Skip DB input path and force fallback test input builders",
    )
    parser.add_argument(
        "--strict-db-input",
        action="store_true",
        help="Require DB-prepared simulation input and forbid fallback input builders",
    )
    parser.add_argument("--stdout", action="store_true", help="Print summary JSON to stdout")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = run_draft_output_inspection(
        json_output_path=Path(args.json_output),
        markdown_output_path=Path(args.markdown_output),
        pack_count=args.pack_count,
        seed_base=args.seed_base,
        prefer_db_input=not bool(args.no_db_input),
        strict_db_input=bool(args.strict_db_input),
    )

    summary = {
        "sets": [
            {
                "set_id": row.get("set_id"),
                "pack_count": row.get("pack_count"),
                "source": row.get("simulation_input", {}).get("source"),
                "largest_abs_delta": row.get("rare_slot_frequency_deltas", {}).get("largest_abs_delta"),
                "triggered_warnings": [
                    flag.get("code")
                    for flag in (row.get("warning_flags") or [])
                    if flag.get("triggered")
                ],
            }
            for row in payload.get("sets", [])
        ],
        "guardrails_unchanged": payload.get("guardrails", {}).get("unchanged"),
        "runtime_approval_input_status": payload.get("runtime_approval_input_status"),
    }

    print(f"[audit] guardrails_unchanged={summary['guardrails_unchanged']}")
    print(f"[audit] runtime_approval_input_status={summary['runtime_approval_input_status']}")
    for item in summary["sets"]:
        print(
            "[audit] set_id={set_id} pack_count={pack_count} source={source} "
            "largest_abs_delta={largest_abs_delta:.6f}".format(
                set_id=item["set_id"],
                pack_count=item["pack_count"],
                source=item["source"],
                largest_abs_delta=_safe_float(item["largest_abs_delta"]),
            )
        )

    if args.stdout:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())