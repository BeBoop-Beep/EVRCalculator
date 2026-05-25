"""Project 6.10 production-runtime smoke validation for swsh6/swsh7.

Runs bounded slot-schema simulations for Chilling Reign (swsh6) and
Evolving Skies (swsh7) using real production config classes.

The script is intentionally read-only:
- no runtime enablement is written to production config classes
- no probability tables or mappings are mutated
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

from backend.constants.tcg.pokemon.megaEvolutionEra.ascendedHeroes import SetAscendedHeroesConfig
from backend.constants.tcg.pokemon.megaEvolutionEra.megaEvolution import SetMegaEvolutionConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeaEvolved import SetPaldeaEvolvedConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeanFates import SetPaldeanFatesConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.chillingReign import SetChillingReignConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.evolvingSkies import SetEvolvingSkiesConfig
from backend.constants.tcg.pokemon.swordAndShieldEra.setMap import SET_CONFIG_MAP
from backend.simulations.evrSimulator import (
    _build_slot_schema_card_pool,
    _should_use_monte_carlo_v2,
    get_simulation_engine,
)
from backend.simulations.slotSchemaSimulator import simulate_slot_schema_packs
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups


DEFAULT_JSON_PATH = Path("logs/audits/swsh_production_runtime_smoke.json")
DEFAULT_MD_PATH = Path("backend/docs/audits/SWSH_PRODUCTION_RUNTIME_SMOKE.md")

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

SWSH_TARGET_SET_IDS = {"swsh6", "swsh7"}
SWSH_MAINLINE_SET_IDS = {
    "swsh1",
    "swsh2",
    "swsh3",
    "swsh4",
    "swsh5",
    "swsh6",
    "swsh7",
    "swsh8",
    "swsh9",
    "swsh10",
    "swsh11",
    "swsh12",
}

SV_MEGA_V2_GUARDRAIL_CONFIGS: Tuple[Any, ...] = (
    SetPaldeaEvolvedConfig,
    SetPaldeanFatesConfig,
    SetAscendedHeroesConfig,
    SetMegaEvolutionConfig,
)


@dataclass(frozen=True)
class ProductionSmokeTarget:
    set_id: str
    canonical_key: str
    set_name: str
    production_config: Any
    draft_table_attr: str


TARGETS: Tuple[ProductionSmokeTarget, ...] = (
    ProductionSmokeTarget(
        set_id="swsh6",
        canonical_key="chillingReign",
        set_name="Chilling Reign",
        production_config=SetChillingReignConfig,
        draft_table_attr="CHILLING_REIGN_RARE_SLOT_PROBABILITY_DRAFT",
    ),
    ProductionSmokeTarget(
        set_id="swsh7",
        canonical_key="evolvingSkies",
        set_name="Evolving Skies",
        production_config=SetEvolvingSkiesConfig,
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


def _resolve_detected_price_column(df: pd.DataFrame) -> Optional[str]:
    for column in PRICE_COLUMN_CANDIDATES:
        if column not in df.columns:
            continue
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().any():
            return str(column)
    return None


def _load_fallback_simulation_input(target: ProductionSmokeTarget) -> Tuple[Any, float, str]:
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
    target: ProductionSmokeTarget,
    *,
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
                target.production_config(),
                target.canonical_key,
                target.set_name,
            )
            dataframe = prepared.get("dataframe")
            pack_price = prepared.get("pack_price")
            prepared_diagnostics = prepared.get("diagnostics") if isinstance(prepared, Mapping) else None
            if isinstance(prepared_diagnostics, Mapping):
                diagnostics["pack_price_source"] = prepared_diagnostics.get("pack_price_source")
                diagnostics["pack_price_resolution_status"] = prepared_diagnostics.get("pack_price_resolution_status")
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
    target: ProductionSmokeTarget,
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


def _compute_probability_table_status(target: ProductionSmokeTarget) -> Dict[str, Any]:
    production_table_raw = getattr(target.production_config, "RARE_SLOT_PROBABILITY", None)
    has_production_table = isinstance(production_table_raw, Mapping)
    production_table = {
        str(k): _safe_float(v)
        for k, v in (dict(production_table_raw).items() if has_production_table else [])
    }

    draft_table_raw = getattr(target.production_config, target.draft_table_attr, None)
    has_draft_table = isinstance(draft_table_raw, Mapping)
    draft_table = {
        str(k): _safe_float(v)
        for k, v in (dict(draft_table_raw).items() if has_draft_table else [])
    }

    mapping_keys = set(getattr(target.production_config, "SLOT_SCHEMA_OUTCOME_POOL_MAPPING", {}).keys())
    table_keys = set(production_table.keys())

    probability_sum = sum(float(v) for v in production_table.values())
    sum_is_one = abs(probability_sum - 1.0) <= 1e-9
    residual_rare_probability = _safe_float(production_table.get("rare"), 0.0)

    simulation_engine = get_simulation_engine(target.production_config)
    should_use_v2 = _should_use_monte_carlo_v2(target.production_config)
    runtime_enabled = bool(getattr(target.production_config, "SLOT_SCHEMA_RUNTIME_ENABLED", False))

    return {
        "draft_table_attr": target.draft_table_attr,
        "production_has_rare_slot_probability": has_production_table,
        "draft_table_present": has_draft_table,
        "production_equals_draft": has_production_table and has_draft_table and production_table == draft_table,
        "sum_probability": probability_sum,
        "sum_is_one": sum_is_one,
        "mapping_keys_match": table_keys == mapping_keys,
        "missing_mapping_keys": sorted(mapping_keys - table_keys),
        "unexpected_table_keys": sorted(table_keys - mapping_keys),
        "residual_rare_probability": residual_rare_probability,
        "residual_rare_non_negative": residual_rare_probability >= 0.0,
        "runtime_enabled": runtime_enabled,
        "simulation_engine": simulation_engine,
        "routes_slot_schema": simulation_engine == "slot_schema",
        "monte_carlo_v2_disabled": not should_use_v2,
        "production_probability_table": production_table,
        "draft_probability_table": draft_table,
    }


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
    probability_table: Mapping[str, float],
    rarity_counts: Mapping[str, int],
    pack_count: int,
) -> Tuple[List[Dict[str, Any]], float]:
    deltas: List[Dict[str, Any]] = []
    largest_abs_delta = 0.0

    for bucket, expected_probability in probability_table.items():
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
    probability_table: Mapping[str, float],
    total_pack_ev: float,
    limit: int = 10,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    per_card_ev: Dict[str, float] = {}

    for bucket, probability in probability_table.items():
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
    rare_table = getattr(runtime_config, "RARE_SLOT_PROBABILITY", {}) or {}
    for bucket in rare_table.keys():
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


def _capture_other_swsh_runtime_enabled_state() -> Dict[str, bool]:
    state: Dict[str, bool] = {}
    for _key, config_cls in sorted(SET_CONFIG_MAP.items(), key=lambda item: str(item[0])):
        set_id = str(getattr(config_cls, "SET_ID", "") or "")
        if set_id not in SWSH_MAINLINE_SET_IDS or set_id in SWSH_TARGET_SET_IDS:
            continue
        state[set_id] = bool(getattr(config_cls, "SLOT_SCHEMA_RUNTIME_ENABLED", False))
    return state


def _capture_sv_mega_routing_state() -> Dict[str, Dict[str, Any]]:
    snapshot: Dict[str, Dict[str, Any]] = {}
    for cfg in SV_MEGA_V2_GUARDRAIL_CONFIGS:
        key = str(getattr(cfg, "SET_ID", cfg.__name__))
        snapshot[key] = {
            "config": cfg.__name__,
            "set_id": str(getattr(cfg, "SET_ID", "") or ""),
            "simulation_engine": get_simulation_engine(cfg),
            "should_use_monte_carlo_v2": _should_use_monte_carlo_v2(cfg),
        }
    return snapshot


def _compute_sv_mega_routing_status(before: Mapping[str, Any], after: Mapping[str, Any]) -> Dict[str, Any]:
    changed_entries: Dict[str, Dict[str, Any]] = {}
    for key in sorted(set(before.keys()) | set(after.keys())):
        previous = before.get(key)
        current = after.get(key)
        if previous != current:
            changed_entries[str(key)] = {
                "before": previous,
                "after": current,
            }

    v2_violations = []
    for key, row in after.items():
        if row.get("simulation_engine") != "v2" or row.get("should_use_monte_carlo_v2") is not True:
            v2_violations.append(
                {
                    "key": key,
                    "config": row.get("config"),
                    "simulation_engine": row.get("simulation_engine"),
                    "should_use_monte_carlo_v2": row.get("should_use_monte_carlo_v2"),
                }
            )

    return {
        "changed": bool(changed_entries),
        "changed_entries": changed_entries,
        "v2_violations": v2_violations,
        "all_expected_v2": len(v2_violations) == 0,
    }


def _warning_flags(
    *,
    probability_status: Mapping[str, Any],
    simulation_input: Mapping[str, Any],
    largest_rare_slot_delta: float,
    reverse_sanity: Mapping[str, Any],
    card_pool: Mapping[str, Sequence[Mapping[str, Any]]],
    sv_mega_routing_status: Mapping[str, Any],
    roi_consistency_check: Mapping[str, Any],
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

    emit(
        "production_table_missing",
        "critical",
        not bool(probability_status.get("production_has_rare_slot_probability")),
        "Production RARE_SLOT_PROBABILITY is missing.",
    )

    emit(
        "production_table_differs_from_draft",
        "critical",
        not bool(probability_status.get("production_equals_draft")),
        "Production RARE_SLOT_PROBABILITY differs from draft empirical table.",
        value={
            "production_equals_draft": bool(probability_status.get("production_equals_draft")),
            "draft_table_attr": probability_status.get("draft_table_attr"),
        },
    )

    emit(
        "probability_sum_invalid",
        "critical",
        not bool(probability_status.get("sum_is_one")),
        "Production probability sum is invalid.",
        value=probability_status.get("sum_probability"),
        threshold=1.0,
    )

    emit(
        "mapping_keys_mismatch",
        "critical",
        not bool(probability_status.get("mapping_keys_match")),
        "Production probability keys do not match SLOT_SCHEMA_OUTCOME_POOL_MAPPING keys.",
        value={
            "missing_mapping_keys": probability_status.get("missing_mapping_keys"),
            "unexpected_table_keys": probability_status.get("unexpected_table_keys"),
        },
    )

    emit(
        "residual_rare_negative",
        "critical",
        not bool(probability_status.get("residual_rare_non_negative")),
        "Residual rare probability is negative.",
        value=probability_status.get("residual_rare_probability"),
        threshold=0.0,
    )

    source = str(simulation_input.get("source") or "")
    row_count = int(simulation_input.get("row_count", 0) or 0)
    emit(
        "db_input_unavailable",
        "critical",
        source != "db_evr_input_preparation_service" or row_count <= 0,
        "DB-prepared simulation input is unavailable.",
        value={"source": source, "row_count": row_count},
    )

    emit(
        "fallback_used",
        "critical",
        bool(simulation_input.get("fallback_used")),
        "Fallback input source was used.",
        value={"source": source, "fallback_used": bool(simulation_input.get("fallback_used"))},
    )

    leakage_by_bucket = reverse_sanity.get("rare_slot_reverse_holo_leakage_by_bucket", {}) or {}
    reverse_leakage = bool(reverse_sanity.get("has_reverse_holo_leakage")) or bool(leakage_by_bucket)
    emit(
        "reverse_holo_leakage",
        "critical",
        reverse_leakage,
        "Reverse-holo leakage detected in rare-slot pools.",
        value={
            "leakage_by_bucket": leakage_by_bucket,
            "reverse_pool_has_non_reverse_entries": bool(reverse_sanity.get("reverse_pool_has_non_reverse_entries")),
        },
    )

    table = probability_status.get("production_probability_table", {}) or {}
    missing_bucket_pool = [bucket for bucket in table.keys() if not card_pool.get(bucket)]
    emit(
        "missing_bucket_pool",
        "critical",
        bool(missing_bucket_pool),
        "One or more rare-slot probability buckets resolved to empty pools.",
        value=missing_bucket_pool,
    )

    emit(
        "rare_slot_bucket_drift_too_large",
        "warning",
        largest_rare_slot_delta > 0.03,
        "Largest rare-slot bucket-frequency delta exceeds tolerance.",
        value=largest_rare_slot_delta,
        threshold=0.03,
    )

    emit(
        "sv_mega_routing_changed",
        "critical",
        bool(sv_mega_routing_status.get("changed")) or not bool(sv_mega_routing_status.get("all_expected_v2")),
        "SV/Mega routing changed or no longer routes to v2.",
        value={
            "changed_entries": sv_mega_routing_status.get("changed_entries"),
            "v2_violations": sv_mega_routing_status.get("v2_violations"),
        },
    )

    emit(
        "roi_consistency_mismatch",
        "critical",
        not bool(roi_consistency_check.get("passed")),
        "Reported ROI does not match average pack value and estimated pack price.",
        value={
            "expected_roi_from_mean_and_pack_price": roi_consistency_check.get("expected_roi_from_mean_and_pack_price"),
            "reported_roi": roi_consistency_check.get("reported_roi"),
            "absolute_delta": roi_consistency_check.get("absolute_delta"),
        },
        threshold=1e-9,
    )

    return flags


def _run_single_set_production_smoke(
    target: ProductionSmokeTarget,
    *,
    pack_count: int,
    seed: int,
    prefer_db_input: bool,
    strict_db_input: bool,
    sv_mega_routing_status: Mapping[str, Any],
) -> Dict[str, Any]:
    probability_status = _compute_probability_table_status(target)

    if not probability_status.get("routes_slot_schema"):
        raise AssertionError(f"{target.set_id} must route to slot_schema")
    if not probability_status.get("runtime_enabled"):
        raise AssertionError(f"{target.set_id} SLOT_SCHEMA_RUNTIME_ENABLED must be True")
    if not probability_status.get("monte_carlo_v2_disabled"):
        raise AssertionError(f"{target.set_id} must not route to monte-carlo v2")

    production_table = dict(probability_status["production_probability_table"])

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

    if strict_db_input and str(input_metadata.get("source") or "") != "db_evr_input_preparation_service":
        _raise_strict_db_input_failure(
            target,
            attempted_source=str(input_metadata.get("source") or "<unknown>"),
            reason="non_db_input_source",
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

    runtime_config = target.production_config

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

    roi_at_estimated_pack_price = (
        ((mean_pack_value - estimated_pack_price) / estimated_pack_price)
        if estimated_pack_price > 0
        else 0.0
    )

    estimated_pack_price_source = str(
        input_diagnostics.get("pack_price_source")
        or "EVRInputPreparationService.prepare_for_set.pack_price"
    )
    estimated_pack_price_resolution_status = str(
        input_diagnostics.get("pack_price_resolution_status")
        or ("resolved" if estimated_pack_price > 0 else "fallback_or_missing")
    )

    expected_roi_from_mean = (
        ((mean_pack_value - estimated_pack_price) / estimated_pack_price)
        if estimated_pack_price > 0
        else 0.0
    )
    roi_absolute_delta = abs(expected_roi_from_mean - roi_at_estimated_pack_price)
    roi_consistency_check = {
        "expected_roi_from_mean_and_pack_price": expected_roi_from_mean,
        "reported_roi": roi_at_estimated_pack_price,
        "absolute_delta": roi_absolute_delta,
        "passed": roi_absolute_delta <= 1e-9,
    }

    top_cards, concentration = _top_ev_contributions_from_pools(card_pool, production_table, mean_pack_value)

    chance_to_beat_pack_cost = (
        sum(1 for value in pack_values if value > estimated_pack_price) / pack_count_observed
        if pack_count_observed
        else 0.0
    )

    rarity_counts = sim_results.get("rarity_pull_counts", {}) or {}
    rare_slot_deltas, largest_delta = _compute_rare_slot_frequency_deltas(production_table, rarity_counts, pack_count_observed)
    reverse_sanity = _reverse_slot_sanity_check(runtime_config, card_pool, rarity_counts, pack_count_observed)
    best_pool_card = _max_pool_value_card(card_pool)

    warnings = _warning_flags(
        probability_status=probability_status,
        simulation_input=input_metadata,
        largest_rare_slot_delta=largest_delta,
        reverse_sanity=reverse_sanity,
        card_pool=card_pool,
        sv_mega_routing_status=sv_mega_routing_status,
        roi_consistency_check=roi_consistency_check,
    )

    return {
        "set_id": target.set_id,
        "set_name": target.set_name,
        "canonical_key": target.canonical_key,
        "simulation_input": input_metadata,
        "pack_count": pack_count_observed,
        "estimated_pack_price": estimated_pack_price,
        "estimated_pack_price_source": estimated_pack_price_source,
        "estimated_pack_price_resolution_status": estimated_pack_price_resolution_status,
        "roi_formula": "(average_pack_value - estimated_pack_price) / estimated_pack_price",
        "simulation_engine": probability_status.get("simulation_engine"),
        "slot_schema_runtime_enabled": probability_status.get("runtime_enabled"),
        "probability_table_status": probability_status,
        "rare_slot_probability_table": production_table,
        "production_probability_table_sum": probability_status.get("sum_probability"),
        "residual_rare_probability": probability_status.get("residual_rare_probability"),
        "metrics": {
            "average_pack_value": mean_pack_value,
            "median_pack_value": median_pack_value,
            "roi_at_estimated_pack_price": roi_at_estimated_pack_price,
            "chance_to_beat_pack_cost": chance_to_beat_pack_cost,
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
        "largest_bucket_frequency_delta": largest_delta,
        "roi_consistency_check": roi_consistency_check,
        "reverse_slot_sanity_check": reverse_sanity,
        "warning_flags": warnings,
    }


def _render_markdown_report(payload: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# SWSH Production Runtime Smoke")
    lines.append("")
    lines.append(f"Generated: {payload.get('meta', {}).get('generated_at_utc', '')}")
    lines.append("")
    lines.append("Read-only production-runtime smoke report for swsh6 and swsh7.")
    lines.append("")
    lines.append(
        "Runtime approval input status: "
        f"{payload.get('runtime_approval_input_status', '<unknown>')}"
    )
    lines.append("")

    for row in payload.get("sets", []):
        metrics = row.get("metrics", {})
        warnings = row.get("warning_flags", [])
        triggered = [flag for flag in warnings if flag.get("triggered")]
        deltas = row.get("rare_slot_frequency_deltas", {}).get("rows", [])
        reverse_sanity = row.get("reverse_slot_sanity_check", {})

        lines.append(f"## {row.get('set_name')} ({row.get('set_id')})")
        lines.append("")
        lines.append(f"- Input source: {row.get('simulation_input', {}).get('source')}")
        lines.append(f"- Input rows: {row.get('simulation_input', {}).get('row_count')}")
        lines.append(f"- Usable price rows: {row.get('simulation_input', {}).get('usable_price_rows')}")
        lines.append(f"- Simulation engine: {row.get('simulation_engine')}")
        lines.append(f"- Runtime enabled: {row.get('slot_schema_runtime_enabled')}")
        lines.append(f"- Production probability sum: {row.get('production_probability_table_sum'):.6f}")
        lines.append(f"- Residual rare probability: {row.get('residual_rare_probability'):.6f}")
        lines.append(f"- Estimated pack price used: ${row.get('estimated_pack_price', 0.0):.6f}")
        lines.append(f"- Estimated pack price source: {row.get('estimated_pack_price_source')}")
        lines.append(f"- Estimated pack price resolution status: {row.get('estimated_pack_price_resolution_status')}")
        lines.append(f"- Average pack value: ${metrics.get('average_pack_value', 0.0):.6f}")
        lines.append(f"- Median pack value: {metrics.get('median_pack_value', 0.0):.6f}")
        lines.append(f"- ROI at estimated pack price: {metrics.get('roi_at_estimated_pack_price', 0.0):.6%}")
        lines.append(f"- ROI formula: {row.get('roi_formula')}")
        roi_check = row.get("roi_consistency_check", {})
        lines.append(
            "- ROI consistency check: {status} (abs_delta={delta:.12f})".format(
                status="passed" if roi_check.get("passed") else "failed",
                delta=_safe_float(roi_check.get("absolute_delta"), 0.0),
            )
        )
        lines.append(f"- Chance to beat pack cost: {metrics.get('chance_to_beat_pack_cost', 0.0):.6%}")
        lines.append(f"- P05/P95/P99: {metrics.get('p05', 0.0):.6f} / {metrics.get('p95', 0.0):.6f} / {metrics.get('p99', 0.0):.6f}")
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

        lines.append("### Warning Flags")
        lines.append("")
        if triggered:
            for flag in triggered:
                lines.append(f"- TRIGGERED [{flag.get('severity')}] {flag.get('code')}: {flag.get('detail')}")
        else:
            lines.append("- No warning flags triggered.")
        lines.append("")

    sv_mega = payload.get("sv_mega_routing_guardrail", {})
    lines.append("## SV/Mega Guardrail")
    lines.append("")
    lines.append(f"- Changed: {sv_mega.get('changed')}")
    lines.append(f"- All expected v2: {sv_mega.get('all_expected_v2')}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run_production_runtime_smoke(
    *,
    json_output_path: Path = DEFAULT_JSON_PATH,
    markdown_output_path: Path = DEFAULT_MD_PATH,
    pack_count: Optional[int] = None,
    auto_slow_set_seconds: float = AUTO_SLOW_SET_SECONDS,
    seed_base: int = 69000,
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
    other_swsh_before = _capture_other_swsh_runtime_enabled_state()
    sv_mega_before = _capture_sv_mega_routing_state()

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
            row = _run_single_set_production_smoke(
                target,
                pack_count=target_pack_count,
                seed=target_seed,
                prefer_db_input=prefer_db_input,
                strict_db_input=strict_db_input,
                sv_mega_routing_status=_compute_sv_mega_routing_status(sv_mega_before, _capture_sv_mega_routing_state()),
            )
        except Exception as exc:
            if auto_mode and not strict_db_input and target_pack_count > AUTO_PACK_COUNT_LOW:
                row = _run_single_set_production_smoke(
                    target,
                    pack_count=AUTO_PACK_COUNT_LOW,
                    seed=target_seed,
                    prefer_db_input=prefer_db_input,
                    strict_db_input=strict_db_input,
                    sv_mega_routing_status=_compute_sv_mega_routing_status(sv_mega_before, _capture_sv_mega_routing_state()),
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
                            "project": "6.10",
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
                        "other_swsh_runtime_guardrail": {
                            "before": other_swsh_before,
                            "after": _capture_other_swsh_runtime_enabled_state(),
                            "unchanged": other_swsh_before == _capture_other_swsh_runtime_enabled_state(),
                        },
                        "sv_mega_routing_guardrail": _compute_sv_mega_routing_status(sv_mega_before, _capture_sv_mega_routing_state()),
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

    other_swsh_after = _capture_other_swsh_runtime_enabled_state()
    sv_mega_after = _capture_sv_mega_routing_state()
    sv_mega_routing_status = _compute_sv_mega_routing_status(sv_mega_before, sv_mega_after)

    any_fallback = any(bool((row.get("simulation_input") or {}).get("fallback_used")) for row in rows)
    runtime_approval_input_status = "strict_db_input_passed" if strict_db_input else "fallback_behavior_only"
    if any_fallback:
        runtime_approval_input_status = "fallback_behavior_only"

    payload = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "6.10",
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
        "other_swsh_runtime_guardrail": {
            "before": other_swsh_before,
            "after": other_swsh_after,
            "unchanged": other_swsh_before == other_swsh_after,
            "unexpected_enabled_ids": [set_id for set_id, enabled in sorted(other_swsh_after.items()) if enabled],
        },
        "sv_mega_routing_guardrail": sv_mega_routing_status,
        "runtime_approval_input_status": runtime_approval_input_status,
        "sets": rows,
    }

    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    json_output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_output_path.write_text(_render_markdown_report(payload), encoding="utf-8")

    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only SWSH production runtime smoke audit")
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
        default=69000,
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
    payload = run_production_runtime_smoke(
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
        "other_swsh_runtime_unchanged": payload.get("other_swsh_runtime_guardrail", {}).get("unchanged"),
        "sv_mega_routing_changed": payload.get("sv_mega_routing_guardrail", {}).get("changed"),
        "runtime_approval_input_status": payload.get("runtime_approval_input_status"),
    }

    print(f"[audit] guardrails_unchanged={summary['guardrails_unchanged']}")
    print(f"[audit] other_swsh_runtime_unchanged={summary['other_swsh_runtime_unchanged']}")
    print(f"[audit] sv_mega_routing_changed={summary['sv_mega_routing_changed']}")
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
