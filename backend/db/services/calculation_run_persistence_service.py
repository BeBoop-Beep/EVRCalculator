from __future__ import annotations

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
    create_simulation_top_hits,
    create_calculation_price_snapshot,
    create_parent_calculation_run,
    get_or_create_calculation_config,
)
from backend.db.repositories.sets_repository import get_set_by_canonical_key


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


def persist_simulation_derived_metrics(*, run_id: Any, derived: Mapping[str, Any]) -> list[dict[str, Any]]:
    ev_comp = _extract_required_nested_mapping(derived, "ev_composition_metrics", "derived")
    chase = _extract_required_nested_mapping(derived, "chase_dependency_metrics", "derived")
    index_score = _extract_required_nested_mapping(derived, "index_score", "derived")

    payload = {
        "hit_ev": _require_float(ev_comp.get("hit_ev"), "derived.ev_composition_metrics.hit_ev"),
        "non_hit_ev": _require_float(ev_comp.get("non_hit_ev"), "derived.ev_composition_metrics.non_hit_ev"),
        "hit_ev_share": _require_float(
            ev_comp.get("hit_ev_share_of_pack_ev"),
            "derived.ev_composition_metrics.hit_ev_share_of_pack_ev",
        ),
        "hit_cards_tracked": _require_int(
            ev_comp.get("hit_cards_count"),
            "derived.ev_composition_metrics.hit_cards_count",
        ),
        "cards_tracked": _require_int(chase.get("cards_tracked"), "derived.chase_dependency_metrics.cards_tracked"),
        "total_card_ev": _require_float(chase.get("total_card_ev"), "derived.chase_dependency_metrics.total_card_ev"),
        "top1_ev_share": _require_float(chase.get("top1_ev_share"), "derived.chase_dependency_metrics.top1_ev_share"),
        "top3_ev_share": _require_float(chase.get("top3_ev_share"), "derived.chase_dependency_metrics.top3_ev_share"),
        "top5_ev_share": _require_float(chase.get("top5_ev_share"), "derived.chase_dependency_metrics.top5_ev_share"),
        "index_score": _require_float(index_score.get("ind_ex_score_v1"), "derived.index_score.ind_ex_score_v1"),
        "profit_component": _require_float(
            index_score.get("prob_profit_component"),
            "derived.index_score.prob_profit_component",
        ),
        "stability_component": _require_float(
            index_score.get("stability_component"),
            "derived.index_score.stability_component",
        ),
        "diversification_component": _require_float(
            index_score.get("diversification_component"),
            "derived.index_score.diversification_component",
        ),
    }

    return create_simulation_derived_metrics(run_id, payload)


def persist_parent_run_with_price_snapshots(
    *,
    config: Any,
    canonical_key: str,
    set_name: str,
    input_mode: str,
    price_inputs: Dict[str, Any],
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
    run_row = create_parent_calculation_run(
        config_row["id"],
        target_type,
        target_id,
        valuation_method,
        notes,
        engine_version,
    )

    snapshot_count = 0
    captured_at = datetime.now(timezone.utc).date().isoformat()
    for snapshot_key in ("pack", "etb", "etb_promo", "booster_box"):
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


def _to_records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        try:
            return list(value.to_dict(orient="records"))
        except TypeError as exc:
            raise RuntimeError("Failed to convert tabular value to records") from exc
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _resolve_simulation_input_snapshot(calculation_input: Any, config: Any) -> list[dict[str, Any]]:
    if hasattr(calculation_input, "columns") and hasattr(calculation_input, "to_dict"):
        return list(calculation_input.to_dict(orient="records"))

    from backend.calculations.packCalcsRefractored import PackCalculationOrchestrator

    orchestrator = PackCalculationOrchestrator(config)
    normalized_df, _ = orchestrator.load_and_prepare_data(calculation_input)
    return list(normalized_df.to_dict(orient="records"))


def persist_simulation_inputs(
    *,
    run_id: Any,
    top_10_hits: Any,
    calculation_input: Any,
    config: Any,
) -> Dict[str, Any]:
    """Persist top-hit rows and normalized input-card rows for the run."""
    top_hits_rows = _to_records(top_10_hits)
    input_rows = _resolve_simulation_input_snapshot(calculation_input, config)

    _require_records_fields(
        top_hits_rows,
        [
            "card_id",
            "card_variant_id",
            "rank",
            "card_name",
            "rarity_bucket",
            "market_price_at_run",
            "effective_pull_rate",
            "ev_contribution",
        ],
        "simulation_top_hits",
    )
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

    top_hits_inserted = create_simulation_top_hits(run_id, top_hits_rows)
    input_cards_inserted = create_simulation_input_cards(run_id, input_rows)

    return {
        "top_hits_count": len(top_hits_inserted),
        "input_cards_count": len(input_cards_inserted),
    }
