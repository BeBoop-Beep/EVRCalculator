from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Dict

from backend.db.repositories.calculation_runs_repository import (
    build_calculation_config_payload,
    create_simulation_derived_metrics,
    create_simulation_etb_summary,
    create_simulation_input_cards,
    create_simulation_percentiles,
    create_simulation_pull_summary,
    create_simulation_run_summary,
    create_simulation_state_counts,
    create_calculation_price_snapshot,
    create_parent_calculation_run,
    get_or_create_calculation_config,
)
from backend.db.repositories.sets_repository import get_set_by_canonical_key


logger = logging.getLogger(__name__)


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Missing required field: {field_name}")
    return value


def _require_float(value: Any, field_name: str) -> float:
    if value is None or value == "":
        raise ValueError(f"Missing required field: {field_name}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Missing required field: {field_name}") from exc


def _require_int(value: Any, field_name: str) -> int:
    if value is None or value == "":
        raise ValueError(f"Missing required field: {field_name}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Missing required field: {field_name}") from exc


def _require_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"Missing required field: {field_name}")


def _require_records_fields(rows: list[dict[str, Any]], required_fields: list[str], context: str) -> None:
    for index, row in enumerate(rows, start=1):
        missing: list[str] = []
        for field in required_fields:
            value = row.get(field)
            if value is None:
                missing.append(field)
                continue
            if isinstance(value, str) and not value.strip():
                missing.append(field)
        if missing:
            raise ValueError(f"Missing required field(s) in {context} row {index}: {', '.join(missing)}")


def _require_values_list(sim_results: Mapping[str, Any]) -> list[float]:
    values = sim_results.get("values")
    if not isinstance(values, list) or not values:
        raise ValueError("Missing required field: sim_results.values")

    coerced: list[float] = []
    for index, value in enumerate(values, start=1):
        coerced.append(_require_float(value, f"sim_results.values[{index}]"))
    return coerced


def _extract_required_nested_mapping(source: Mapping[str, Any], key: str, context: str) -> Mapping[str, Any]:
    nested = source.get(key)
    if not isinstance(nested, Mapping):
        raise ValueError(f"Missing required field: {context}.{key}")
    return nested


def _map_snapshot_prices(snapshot_key: str, raw_value: Any) -> dict[str, float]:
    if isinstance(raw_value, Mapping):
        return {
            "market_price": _require_float(raw_value.get("market_price"), f"price_inputs.{snapshot_key}.market_price"),
            "low_price": _require_float(raw_value.get("low_price"), f"price_inputs.{snapshot_key}.low_price"),
            "high_price": _require_float(raw_value.get("high_price"), f"price_inputs.{snapshot_key}.high_price"),
        }

    market_price = _require_float(raw_value, f"price_inputs.{snapshot_key}")
    return {
        "market_price": market_price,
        "low_price": market_price,
        "high_price": market_price,
    }


def _coerce_optional_float(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric field: {field_name}") from exc


def _require_score_0_100(value: Any, field_name: str) -> float:
    score = _require_float(value, field_name)
    if score < 0.0 or score > 100.0:
        raise ValueError(f"Invalid score field (expected 0-100): {field_name}")
    return score


def _require_nonempty_str(value: Any, field_name: str) -> str:
    if value is None:
        raise ValueError(f"Missing required field: {field_name}")
    text = str(value).strip()
    if not text:
        raise ValueError(f"Missing required field: {field_name}")
    return text


def _first_present(source: Mapping[str, Any], field_names: tuple[str, ...]) -> Any:
    for field_name in field_names:
        value = source.get(field_name)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _coerce_share_or_zero(value: Any, field_name: str, *, zero_when_empty: bool) -> float:
    if zero_when_empty and (value is None or value == ""):
        return 0.0
    return _require_float(value, field_name)


def _build_comparison_metrics_payload(
    *,
    pack_value_vs_cost_comparison: Mapping[str, Any],
    etb_value_vs_cost_comparison: Mapping[str, Any] | None,
    booster_box_value_vs_cost_comparison: Mapping[str, Any] | None,
) -> dict[str, float | None]:
    def _extract_roi(comparisons: Mapping[str, Any], comparison_key: str, field_name: str) -> float | None:
        payload = comparisons.get(comparison_key)
        if not isinstance(payload, Mapping):
            raise ValueError(f"Missing required field: {field_name}")
        return _coerce_optional_float(payload.get("roi"), field_name)

    def _extract_optional_roi(
        comparisons: Mapping[str, Any] | None,
        comparison_key: str,
        field_name: str,
    ) -> float | None:
        if not isinstance(comparisons, Mapping):
            return None
        payload = comparisons.get(comparison_key)
        if not isinstance(payload, Mapping):
            return None
        return _coerce_optional_float(payload.get("roi"), field_name)

    def _extract_expected_value(comparisons: Mapping[str, Any], comparison_key: str, field_name: str) -> float | None:
        payload = comparisons.get(comparison_key)
        if not isinstance(payload, Mapping):
            raise ValueError(f"Missing required field: {field_name}")
        return _coerce_optional_float(payload.get("expected_value"), field_name)

    return {
        "simulated_mean_pack_value_vs_pack_cost": _extract_roi(
            pack_value_vs_cost_comparison,
            "simulated_mean_pack_value_vs_pack_cost",
            "simulated_mean_pack_value_vs_pack_cost",
        ),
        "simulated_median_pack_value_vs_pack_cost": _extract_roi(
            pack_value_vs_cost_comparison,
            "simulated_median_pack_value_vs_pack_cost",
            "simulated_median_pack_value_vs_pack_cost",
        ),
        "calculated_expected_pack_value_vs_pack_cost": _extract_expected_value(
            pack_value_vs_cost_comparison,
            "calculated_expected_pack_value_vs_pack_cost",
            "calculated_expected_pack_value_vs_pack_cost",
        ),
        "simulated_mean_etb_value_vs_etb_cost": _extract_optional_roi(
            etb_value_vs_cost_comparison,
            "simulated_mean_etb_value_vs_etb_cost",
            "simulated_mean_etb_value_vs_etb_cost",
        ),
        "simulated_median_etb_value_vs_etb_cost": _extract_optional_roi(
            etb_value_vs_cost_comparison,
            "simulated_median_etb_value_vs_etb_cost",
            "simulated_median_etb_value_vs_etb_cost",
        ),
        "calculated_expected_etb_value_vs_etb_cost": _extract_optional_roi(
            etb_value_vs_cost_comparison,
            "calculated_expected_etb_value_vs_etb_cost",
            "calculated_expected_etb_value_vs_etb_cost",
        ),
        "simulated_mean_booster_box_value_vs_booster_box_cost": _extract_roi(
            booster_box_value_vs_cost_comparison,
            "simulated_mean_booster_box_value_vs_booster_box_cost",
            "simulated_mean_booster_box_value_vs_booster_box_cost",
        ),
        "simulated_median_booster_box_value_vs_booster_box_cost": _extract_roi(
            booster_box_value_vs_cost_comparison,
            "simulated_median_booster_box_value_vs_booster_box_cost",
            "simulated_median_booster_box_value_vs_booster_box_cost",
        ),
        "calculated_expected_booster_box_value_vs_booster_box_cost": _extract_roi(
            booster_box_value_vs_cost_comparison,
            "calculated_expected_booster_box_value_vs_booster_box_cost",
            "calculated_expected_booster_box_value_vs_booster_box_cost",
        ),
    }


def _build_simulation_summary_payloads(
    *,
    sim_results: Mapping[str, Any],
    pack_metrics: Mapping[str, Any],
    derived: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    pack_decision = _extract_required_nested_mapping(derived, "pack_decision_metrics", "derived")
    values = _require_values_list(sim_results)

    run_summary_payload = {
        "values": values,
        "mean_value": _require_float(pack_decision.get("mean"), "derived.pack_decision_metrics.mean"),
        "median_value": _require_float(pack_decision.get("median"), "derived.pack_decision_metrics.median"),
        "min_value": float(min(values)),
        "max_value": float(max(values)),
        "std_dev": _require_float(pack_decision.get("std_dev"), "derived.pack_decision_metrics.std_dev"),
        "coefficient_of_variation": _require_float(
            pack_decision.get("coefficient_of_variation"),
            "derived.pack_decision_metrics.coefficient_of_variation",
        ),
        "prob_profit": _require_float(pack_decision.get("prob_profit"), "derived.pack_decision_metrics.prob_profit"),
        "prob_big_hit": _require_float(
            pack_decision.get("prob_big_hit_dynamic"),
            "derived.pack_decision_metrics.prob_big_hit_dynamic",
        ),
        "big_hit_threshold": _require_float(
            pack_decision.get("big_hit_threshold_dynamic"),
            "derived.pack_decision_metrics.big_hit_threshold_dynamic",
        ),
        "expected_loss_when_losing": _require_float(
            pack_decision.get("expected_loss_given_loss"),
            "derived.pack_decision_metrics.expected_loss_given_loss",
        ),
        "median_loss_when_losing": _require_float(
            pack_decision.get("median_loss_given_loss"),
            "derived.pack_decision_metrics.median_loss_given_loss",
        ),
        "tail_value_p05": _require_float(
            pack_decision.get("tail_value_p05"),
            "derived.pack_decision_metrics.tail_value_p05",
        ),
    }

    pack_summary_payload = {
        "pack_cost": _require_float(pack_decision.get("pack_cost"), "derived.pack_decision_metrics.pack_cost"),
        "total_ev": _require_float(pack_metrics.get("total_ev"), "pack_metrics.total_ev"),
        "net_value": _require_float(pack_metrics.get("net_value"), "pack_metrics.net_value"),
        "roi": _require_float(pack_metrics.get("opening_pack_roi"), "pack_metrics.opening_pack_roi"),
        "roi_percent": _require_float(
            pack_metrics.get("opening_pack_roi_percent"),
            "pack_metrics.opening_pack_roi_percent",
        ),
        "expected_loss_per_pack": _require_float(
            pack_decision.get("expected_loss_unconditional"),
            "derived.pack_decision_metrics.expected_loss_unconditional",
        ),
    }

    return run_summary_payload, pack_summary_payload


def _build_flat_derived_metrics_payload(derived: Mapping[str, Any]) -> dict[str, Any]:
    try:
        ev_comp = _extract_required_nested_mapping(derived, "ev_composition_metrics", "derived")
        chase = _extract_required_nested_mapping(derived, "chase_dependency_metrics", "derived")
        pack_score = _extract_required_nested_mapping(derived, "pack_score", "derived")
        total_pack_ev = _require_float(
            _first_present(ev_comp, ("total_pack_ev",))
            if _first_present(ev_comp, ("total_pack_ev",)) is not None
            else _require_float(ev_comp.get("hit_ev"), "derived.ev_composition_metrics.hit_ev")
            + _require_float(ev_comp.get("non_hit_ev"), "derived.ev_composition_metrics.non_hit_ev"),
            "derived.ev_composition_metrics.total_pack_ev",
        )
        cards_tracked = _require_int(
            _first_present(chase, ("cards_tracked", "n_cards")),
            "derived.chase_dependency_metrics.cards_tracked",
        )
        total_card_ev = _require_float(
            _first_present(chase, ("total_card_ev", "total_ev")),
            "derived.chase_dependency_metrics.total_card_ev",
        )
    except ValueError:
        top_level_keys = sorted(derived.keys()) if isinstance(derived, Mapping) else []
        chase_payload = derived.get("chase_dependency_metrics") if isinstance(derived, Mapping) else None
        chase_keys = sorted(chase_payload.keys()) if isinstance(chase_payload, Mapping) else []
        logger.exception(
            "Derived payload normalization failed. top_level_keys=%s chase_keys=%s chase_cards_tracked=%s chase_n_cards=%s",
            top_level_keys,
            chase_keys,
            chase_payload.get("cards_tracked") if isinstance(chase_payload, Mapping) else None,
            chase_payload.get("n_cards") if isinstance(chase_payload, Mapping) else None,
        )
        raise

    pack_score_is_placeholder = _require_bool(
        pack_score.get("pack_score_is_placeholder"),
        "derived.pack_score.pack_score_is_placeholder",
    )
    pack_score_raw_inputs = pack_score.get("raw_inputs")
    pack_score_raw_inputs_map = pack_score_raw_inputs if isinstance(pack_score_raw_inputs, Mapping) else {}

    hhi_ev_concentration = _coerce_optional_float(
        _first_present(chase, ("hhi_ev_concentration",)),
        "derived.chase_dependency_metrics.hhi_ev_concentration",
    )
    if hhi_ev_concentration is None:
        hhi_ev_concentration = _coerce_optional_float(
            _first_present(pack_score_raw_inputs_map, ("hhi_ev_concentration",)),
            "derived.pack_score.raw_inputs.hhi_ev_concentration",
        )

    effective_chase_count = _coerce_optional_float(
        _first_present(chase, ("effective_chase_count",)),
        "derived.chase_dependency_metrics.effective_chase_count",
    )
    if effective_chase_count is None:
        effective_chase_count = _coerce_optional_float(
            _first_present(pack_score_raw_inputs_map, ("effective_chase_count",)),
            "derived.pack_score.raw_inputs.effective_chase_count",
        )

    if pack_score_is_placeholder:
        canonical_pack_score = None
        canonical_profit_score = None
        canonical_safety_score = None
        canonical_stability_score = None
    else:
        canonical_pack_score = _require_score_0_100(
            pack_score.get("pack_score"),
            "derived.pack_score.pack_score",
        )
        canonical_profit_score = _require_score_0_100(
            pack_score.get("profit_score"),
            "derived.pack_score.profit_score",
        )
        canonical_safety_score = _require_score_0_100(
            pack_score.get("safety_score"),
            "derived.pack_score.safety_score",
        )
        canonical_stability_score = _require_score_0_100(
            pack_score.get("stability_score"),
            "derived.pack_score.stability_score",
        )

    return {
        "hit_ev": _require_float(ev_comp.get("hit_ev"), "derived.ev_composition_metrics.hit_ev"),
        "non_hit_ev": _require_float(ev_comp.get("non_hit_ev"), "derived.ev_composition_metrics.non_hit_ev"),
        "hit_ev_share": _coerce_share_or_zero(
            ev_comp.get("hit_ev_share_of_pack_ev"),
            "derived.ev_composition_metrics.hit_ev_share_of_pack_ev",
            zero_when_empty=total_pack_ev <= 0,
        ),
        "hit_cards_tracked": _require_int(
            ev_comp.get("hit_cards_count"),
            "derived.ev_composition_metrics.hit_cards_count",
        ),
        "cards_tracked": cards_tracked,
        "total_card_ev": total_card_ev,
        "top1_ev_share": _coerce_share_or_zero(
            chase.get("top1_ev_share"),
            "derived.chase_dependency_metrics.top1_ev_share",
            zero_when_empty=cards_tracked == 0 or total_card_ev <= 0,
        ),
        "top3_ev_share": _coerce_share_or_zero(
            chase.get("top3_ev_share"),
            "derived.chase_dependency_metrics.top3_ev_share",
            zero_when_empty=cards_tracked == 0 or total_card_ev <= 0,
        ),
        "top5_ev_share": _coerce_share_or_zero(
            chase.get("top5_ev_share"),
            "derived.chase_dependency_metrics.top5_ev_share",
            zero_when_empty=cards_tracked == 0 or total_card_ev <= 0,
        ),
        "hhi_ev_concentration": hhi_ev_concentration,
        "effective_chase_count": effective_chase_count,
        "pack_score": canonical_pack_score,
        "profit_score": canonical_profit_score,
        "safety_score": canonical_safety_score,
        "stability_score": canonical_stability_score,
        "score_version": _require_nonempty_str(
            _first_present(pack_score, ("score_version",)),
            "derived.pack_score.score_version",
        ),
        "normalization_mode": _require_nonempty_str(
            _first_present(pack_score, ("normalization_mode",)),
            "derived.pack_score.normalization_mode",
        ),
        "pack_score_is_placeholder": pack_score_is_placeholder,
    }


def persist_simulation_derived_metrics(*, run_id: Any, derived: Mapping[str, Any]) -> list[dict[str, Any]]:
    payload = _build_flat_derived_metrics_payload(derived)
    logger.debug(
        "Persisting simulation derived metrics payload for run_id=%s with keys=%s",
        run_id,
        sorted(payload.keys()),
    )
    return create_simulation_derived_metrics(run_id, payload)


def persist_parent_run_with_price_snapshots(
    *,
    config: Any,
    canonical_key: str,
    set_name: str,
    input_mode: str,
    price_inputs: Dict[str, Any],
    pack_value_vs_cost_comparison: Dict[str, Any],
    etb_value_vs_cost_comparison: Dict[str, Any] | None,
    booster_box_value_vs_cost_comparison: Dict[str, Any],
) -> Dict[str, Any]:
    """Persist config, one parent run, and run-level price snapshots."""
    set_row = get_set_by_canonical_key(canonical_key)
    if not isinstance(set_row, dict) or not set_row.get("id"):
        raise ValueError(f"Unable to resolve set target_id for canonical_key: {canonical_key}")

    target_type = "set"
    target_id = str(set_row["id"])
    valuation_method = "combined"
    notes = f"canonical_key={canonical_key};set_name={set_name};input_mode={input_mode}"
    engine_version = "monte_carlo_v2" if bool(getattr(config, "USE_MONTE_CARLO_V2", False)) else "monte_carlo_v1"

    config_hash, config_payload = build_calculation_config_payload(
        config=config,
        canonical_key=canonical_key,
        set_name=set_name,
        input_mode=input_mode,
    )

    config_row = get_or_create_calculation_config(config_hash, config_payload)
    comparison_metrics_payload = _build_comparison_metrics_payload(
        pack_value_vs_cost_comparison=_require_mapping(
            pack_value_vs_cost_comparison,
            "pack_value_vs_cost_comparison",
        ),
        etb_value_vs_cost_comparison=etb_value_vs_cost_comparison,
        booster_box_value_vs_cost_comparison=_require_mapping(
            booster_box_value_vs_cost_comparison,
            "booster_box_value_vs_cost_comparison",
        ),
    )

    console_pack_ev = _coerce_optional_float(
        _require_mapping(
            pack_value_vs_cost_comparison.get("calculated_expected_pack_value_vs_pack_cost"),
            "pack_value_vs_cost_comparison.calculated_expected_pack_value_vs_pack_cost",
        ).get("expected_value"),
        "pack_value_vs_cost_comparison.calculated_expected_pack_value_vs_pack_cost.expected_value",
    )
    persisted_pack_ev = comparison_metrics_payload.get("calculated_expected_pack_value_vs_pack_cost")
    values_match = (
        persisted_pack_ev is not None
        and console_pack_ev is not None
        and abs(float(persisted_pack_ev) - float(console_pack_ev)) <= 1e-9
    )
    print(
        "[TEMP_DEBUG_CALC_RUN_PACK_EV] "
        f"value_to_write={persisted_pack_ev} "
        f"console_ev={console_pack_ev} "
        f"equal={values_match}"
    )

    run_row = create_parent_calculation_run(
        config_row["id"],
        target_type,
        target_id,
        valuation_method,
        notes,
        engine_version,
        comparison_metrics_payload,
    )

    snapshot_count = 0
    captured_at = datetime.now(timezone.utc).date().isoformat()
    for snapshot_key in ("pack", "booster_box"):
        raw_price = price_inputs.get(snapshot_key)
        if raw_price is None:
            continue

        price_values = _map_snapshot_prices(snapshot_key, raw_price)
        create_calculation_price_snapshot(
            run_row["id"],
            snapshot_key,
            "run_input",
            "USD",
            price_values["market_price"],
            price_values["low_price"],
            price_values["high_price"],
            captured_at,
        )
        snapshot_count += 1

    return {
        "config_id": config_row["id"],
        "config_hash": config_hash,
        "run_id": run_row["id"],
        "snapshot_count": snapshot_count,
    }


def persist_simulation_outputs(
    *,
    run_id: Any,
    sim_results: Dict[str, Any],
    pack_metrics: Dict[str, Any],
    derived: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Persist simulation outputs for summary, percentiles, pulls, states, and derived metrics."""
    sim_results_map = _require_mapping(sim_results, "sim_results")
    pack_metrics_map = _require_mapping(pack_metrics, "pack_metrics")
    derived_map = _require_mapping(derived, "derived")

    run_summary_payload, pack_summary_payload = _build_simulation_summary_payloads(
        sim_results=sim_results_map,
        pack_metrics=pack_metrics_map,
        derived=derived_map,
    )

    run_summary_row = create_simulation_run_summary(run_id, run_summary_payload, pack_summary_payload)
    percentile_rows = create_simulation_percentiles(run_id, sim_results_map)
    pull_summary_rows = create_simulation_pull_summary(run_id, sim_results_map)
    state_count_rows = create_simulation_state_counts(run_id, sim_results_map)
    chase_payload = derived_map.get("chase_dependency_metrics") if isinstance(derived_map, Mapping) else None
    logger.info(
        "Derived pre-persist shape for run_id=%s: top_level_keys=%s chase_keys=%s chase_cards_tracked=%s chase_n_cards=%s",
        run_id,
        sorted(derived_map.keys()) if isinstance(derived_map, Mapping) else [],
        sorted(chase_payload.keys()) if isinstance(chase_payload, Mapping) else [],
        chase_payload.get("cards_tracked") if isinstance(chase_payload, Mapping) else None,
        chase_payload.get("n_cards") if isinstance(chase_payload, Mapping) else None,
    )

    derived_metric_rows = persist_simulation_derived_metrics(run_id=run_id, derived=derived_map)

    return {
        "run_summary_id": run_summary_row.get("id"),
        "percentile_count": len(percentile_rows),
        "pull_summary_count": len(pull_summary_rows),
        "state_count": len(state_count_rows),
        "derived_metric_count": len(derived_metric_rows),
    }


def persist_simulation_etb_summary(
    *,
    run_id: Any,
    etb_metrics: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Persist ETB summary metrics with strict schema mapping."""
    etb_metrics_map = _require_mapping(etb_metrics, "etb_metrics")

    mapped = {
        "packs_per_etb": _require_int(etb_metrics_map.get("total_packs_per_etb"), "etb_metrics.total_packs_per_etb"),
        "etb_market_price": _require_float(etb_metrics_map.get("etb_market_price"), "etb_metrics.etb_market_price"),
        "promo_price": _require_float(etb_metrics_map.get("etb_promo_price"), "etb_metrics.etb_promo_price"),
        "ev_per_pack": _require_float(etb_metrics_map.get("total_ev_per_pack"), "etb_metrics.total_ev_per_pack"),
        "total_etb_ev": _require_float(etb_metrics_map.get("total_etb_ev"), "etb_metrics.total_etb_ev"),
        "net_value": _require_float(etb_metrics_map.get("etb_net_value"), "etb_metrics.etb_net_value"),
        "roi": _require_float(etb_metrics_map.get("etb_roi"), "etb_metrics.etb_roi"),
        "roi_percent": _require_float(etb_metrics_map.get("etb_roi_percentage"), "etb_metrics.etb_roi_percentage"),
    }

    inserted = create_simulation_etb_summary(run_id, mapped)
    return {
        "persisted": True,
        "etb_summary_id": inserted.get("id") if isinstance(inserted, dict) else None,
    }


def _normalize_simulation_input_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "card_id": _first_present(row, ("card_id", "Card ID", "card_number", "Card Number")),
            "card_variant_id": _first_present(
                row,
                ("card_variant_id", "Card Variant ID", "card_id", "Card ID", "card_number", "Card Number"),
            ),
            "condition_id": _first_present(row, ("condition_id", "Condition ID")),
            "card_name": _first_present(row, ("card_name", "Card Name")),
            "rarity_bucket": _first_present(row, ("rarity_bucket", "rarity_group", "rarity_raw", "Rarity")),
            "price_source": _first_present(row, ("price_source",)),
            "price_used": _first_present(row, ("price_used", "Price ($)")),
            "captured_at": _first_present(row, ("captured_at",)),
            "effective_pull_rate": _first_present(row, ("effective_pull_rate", "Effective_Pull_Rate")),
            "ev_contribution": _first_present(row, ("ev_contribution", "EV")),
        }
        for row in rows
    ]


def _resolve_simulation_input_snapshot(calculation_input: Any, config: Any) -> list[dict[str, Any]]:
    def _missing_ev_fields(mapped_rows: list[dict[str, Any]]) -> bool:
        for row in mapped_rows:
            if row.get("effective_pull_rate") in (None, "") or row.get("ev_contribution") in (None, ""):
                return True
        return False

    if hasattr(calculation_input, "columns") and hasattr(calculation_input, "to_dict"):
        raw_rows = list(calculation_input.to_dict(orient="records"))
        mapped_rows = _normalize_simulation_input_rows(raw_rows)
        if not _missing_ev_fields(mapped_rows):
            return mapped_rows

    from backend.calculations.packCalcsRefractored import PackCalculationOrchestrator

    orchestrator = PackCalculationOrchestrator(config)
    normalized_df, _ = orchestrator.load_and_prepare_data(calculation_input)
    return _normalize_simulation_input_rows(list(normalized_df.to_dict(orient="records")))


def persist_simulation_inputs(
    *,
    run_id: Any,
    calculation_input: Any,
    config: Any,
) -> Dict[str, Any]:
    """Persist normalized input-card rows for the run."""
    input_rows = _resolve_simulation_input_snapshot(calculation_input, config)

    _require_records_fields(
        input_rows,
        [
            "card_id",
            "card_variant_id",
            "condition_id",
            "card_name",
            "rarity_bucket",
            "price_source",
            "price_used",
            "captured_at",
            "effective_pull_rate",
            "ev_contribution",
        ],
        "simulation_input_cards",
    )

    input_cards_inserted = create_simulation_input_cards(run_id, input_rows)

    return {
        "top_hits_count": 0,
        "input_cards_count": len(input_cards_inserted),
    }
