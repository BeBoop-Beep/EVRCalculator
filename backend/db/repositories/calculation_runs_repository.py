from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple

from backend.db.clients.supabase_client import supabase


def _to_jsonable(value: Any) -> Any:
    """Convert config values into deterministic JSON-safe primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_to_jsonable(item) for item in sorted(value, key=lambda item: str(item))]
    return str(value)


def _stable_json(value: Any) -> str:
    return json.dumps(_to_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_calculation_config_payload(
    config: Any,
    canonical_key: str,
    set_name: str,
    input_mode: str,
) -> Tuple[str, Dict[str, Any]]:
    """Build deterministic config payload and SHA-256 hash for de-duplication."""
    config_fields: Dict[str, Any] = {}

    for attr_name in dir(config):
        if not attr_name.isupper() or attr_name.startswith("_"):
            continue
        value = getattr(config, attr_name, None)
        if callable(value):
            continue
        config_fields[attr_name] = _to_jsonable(value)

    payload = {
        "config_class": config.__class__.__name__,
        "canonical_key": canonical_key,
        "set_name": set_name,
        "input_mode": input_mode,
        "config": config_fields,
    }

    serialized = _stable_json(payload)
    config_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return config_hash, payload


def _insert_required_payload(table_name: str, payload: Dict[str, Any], context: str) -> Dict[str, Any]:
    try:
        response = supabase.table(table_name).insert(payload).execute()
    except Exception as exc:
        raise RuntimeError(
            f"{context} failed for table '{table_name}'. payload_keys={sorted(payload.keys())}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    rows = response.data if response and response.data else []
    if rows and isinstance(rows[0], dict):
        return rows[0]
    raise RuntimeError(
        f"{context} failed for table '{table_name}': insert returned no row. payload_keys={sorted(payload.keys())}"
    )


def _require_present(value: Any, field_name: str) -> Any:
    if value is None:
        raise ValueError(f"Missing required field: {field_name}")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"Missing required field: {field_name}")
    return value


def _require_fields(source: Mapping[str, Any], field_names: List[str], context: str) -> None:
    missing: List[str] = []
    for field_name in field_names:
        value = source.get(field_name)
        if value is None:
            missing.append(field_name)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field_name)
    if missing:
        raise ValueError(f"Missing required field(s) in {context}: {', '.join(missing)}")


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


def get_or_create_calculation_config(config_hash: str, config_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create-or-reuse config row keyed by config_hash."""
    existing_response = (
        supabase.table("calculation_configs")
        .select("id,config_hash")
        .eq("config_hash", config_hash)
        .limit(1)
        .execute()
    )
    existing_rows = existing_response.data if existing_response and existing_response.data else []
    if existing_rows and isinstance(existing_rows[0], dict):
        return existing_rows[0]

    _require_present(config_hash, "config_hash")
    _require_present(config_payload, "config")

    inserted = _insert_required_payload(
        "calculation_configs",
        {"config_hash": config_hash, "config": config_payload},
        "Config insert",
    )

    inserted_hash = str(inserted.get("config_hash") or "").strip()
    if inserted_hash and inserted_hash != config_hash:
        raise RuntimeError(
            f"Config hash mismatch after insert: expected={config_hash} actual={inserted_hash}"
        )

    if not inserted.get("id"):
        raise RuntimeError("Config insert succeeded but returned no id")

    return inserted


def create_parent_calculation_run(
    config_id: Any,
    target_type: str,
    target_id: str,
    valuation_method: str,
    notes: str,
    engine_version: str,
) -> Dict[str, Any]:
    """Create one parent run row for a solve."""
    _require_present(config_id, "calculation_config_id")
    _require_present(target_type, "target_type")
    _require_present(target_id, "target_id")
    _require_present(valuation_method, "valuation_method")
    _require_present(notes, "notes")
    _require_present(engine_version, "engine_version")

    inserted = _insert_required_payload(
        "calculation_runs",
        {
            "target_type": str(target_type),
            "target_id": str(target_id),
            "calculation_config_id": config_id,
            "valuation_method": str(valuation_method),
            "notes": str(notes),
            "engine_version": str(engine_version),
        },
        "Parent run insert",
    )
    if not inserted.get("id"):
        raise RuntimeError("Parent run insert succeeded but returned no id")
    return inserted


def create_calculation_price_snapshot(
    run_id: Any,
    price_type: str,
    price_source: str,
    currency: str,
    market_price: Any,
    low_price: Any,
    high_price: Any,
    captured_at: str,
) -> Dict[str, Any]:
    """Persist one run-level price snapshot row."""
    _require_present(run_id, "calculation_run_id")
    _require_present(price_type, "price_type")
    _require_present(price_source, "price_source")
    _require_present(currency, "currency")
    _require_present(captured_at, "captured_at")

    payload = {
        "calculation_run_id": run_id,
        "price_type": str(price_type),
        "price_source": str(price_source),
        "currency": str(currency),
        "market_price": _require_float(market_price, "market_price"),
        "low_price": _require_float(low_price, "low_price"),
        "high_price": _require_float(high_price, "high_price"),
        "captured_at": str(captured_at),
    }

    inserted = _insert_required_payload(
        "calculation_price_snapshots",
        payload,
        f"Price snapshot insert for {price_type}",
    )
    if not inserted.get("id"):
        raise RuntimeError(f"Price snapshot insert for {price_type} succeeded but returned no id")
    return inserted


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_percentile_rank(label: str) -> Optional[float]:
    normalized = (label or "").strip().lower()
    if not normalized:
        return None
    cleaned = normalized.replace("th", "").replace("st", "").replace("nd", "").replace("rd", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def create_simulation_run_summary(
    run_id: Any,
    sim_results: Mapping[str, Any],
    pack_metrics: Mapping[str, Any],
) -> Dict[str, Any]:
    """Persist one simulation summary row for a parent calculation run."""
    if not isinstance(sim_results, Mapping):
        raise ValueError("Missing required field: sim_results")
    if not isinstance(pack_metrics, Mapping):
        raise ValueError("Missing required field: pack_metrics")

    values = sim_results.get("values")
    if not isinstance(values, list):
        raise ValueError("Missing required field: values")

    _require_fields(
        sim_results,
        [
            "mean_value",
            "median_value",
            "min_value",
            "max_value",
            "std_dev",
            "coefficient_of_variation",
            "prob_profit",
            "prob_big_hit",
            "big_hit_threshold",
            "expected_loss_when_losing",
            "median_loss_when_losing",
            "tail_value_p05",
        ],
        "simulation_run_summary.sim_results",
    )
    _require_fields(
        pack_metrics,
        [
            "pack_cost",
            "total_ev",
            "net_value",
            "roi",
            "roi_percent",
            "expected_loss_per_pack",
        ],
        "simulation_run_summary.pack_metrics",
    )

    payload = {
        "calculation_run_id": _require_present(run_id, "calculation_run_id"),
        "simulation_count": len(values),
        "pack_cost": _require_float(pack_metrics.get("pack_cost"), "pack_cost"),
        "mean_value": _require_float(sim_results.get("mean_value"), "mean_value"),
        "median_value": _require_float(sim_results.get("median_value"), "median_value"),
        "min_value": _require_float(sim_results.get("min_value"), "min_value"),
        "max_value": _require_float(sim_results.get("max_value"), "max_value"),
        "std_dev": _require_float(sim_results.get("std_dev"), "std_dev"),
        "coefficient_of_variation": _require_float(
            sim_results.get("coefficient_of_variation"), "coefficient_of_variation"
        ),
        "total_ev": _require_float(pack_metrics.get("total_ev"), "total_ev"),
        "net_value": _require_float(pack_metrics.get("net_value"), "net_value"),
        "roi": _require_float(pack_metrics.get("roi"), "roi"),
        "roi_percent": _require_float(pack_metrics.get("roi_percent"), "roi_percent"),
        "prob_profit": _require_float(sim_results.get("prob_profit"), "prob_profit"),
        "prob_big_hit": _require_float(sim_results.get("prob_big_hit"), "prob_big_hit"),
        "big_hit_threshold": _require_float(sim_results.get("big_hit_threshold"), "big_hit_threshold"),
        "expected_loss_when_losing": _require_float(
            sim_results.get("expected_loss_when_losing"), "expected_loss_when_losing"
        ),
        "median_loss_when_losing": _require_float(
            sim_results.get("median_loss_when_losing"), "median_loss_when_losing"
        ),
        "expected_loss_per_pack": _require_float(pack_metrics.get("expected_loss_per_pack"), "expected_loss_per_pack"),
        "tail_value_p05": _require_float(sim_results.get("tail_value_p05"), "tail_value_p05"),
    }

    inserted = _insert_required_payload(
        "simulation_run_summary",
        payload,
        "Simulation run summary insert",
    )
    if not inserted.get("id"):
        raise RuntimeError("Simulation run summary insert succeeded but returned no id")
    return inserted


def create_simulation_percentiles(run_id: Any, sim_results: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Persist percentile rows from simulation output."""
    if not isinstance(sim_results, Mapping):
        raise ValueError("Missing required field: sim_results")

    percentiles = sim_results.get("percentiles")
    if not isinstance(percentiles, Mapping):
        raise ValueError("Missing required field: percentiles")

    inserted_rows: List[Dict[str, Any]] = []
    for percentile_label, percentile_value in percentiles.items():
        percentile_rank = _parse_percentile_rank(str(percentile_label))
        if percentile_rank is None:
            raise ValueError(f"Invalid percentile label for required percentile field: {percentile_label}")
        percentile_number = _coerce_optional_float(percentile_value)
        if percentile_number is None:
            raise ValueError(f"Missing required percentile value for label: {percentile_label}")

        payload = {
            "calculation_run_id": _require_present(run_id, "calculation_run_id"),
            "percentile": percentile_rank,
            "value": percentile_number,
        }
        inserted = _insert_required_payload(
            "simulation_percentiles",
            payload,
            f"Simulation percentile insert ({percentile_label})",
        )
        inserted_rows.append(inserted)

    return inserted_rows


def create_simulation_pull_summary(run_id: Any, sim_results: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Persist rarity pull summary rows from simulation output."""
    if not isinstance(sim_results, Mapping):
        raise ValueError("Missing required field: sim_results")

    pull_counts = sim_results.get("rarity_pull_counts")
    value_totals = sim_results.get("rarity_value_totals")
    if not isinstance(pull_counts, Mapping):
        raise ValueError("Missing required field: rarity_pull_counts")
    if not isinstance(value_totals, Mapping):
        raise ValueError("Missing required field: rarity_value_totals")

    inserted_rows: List[Dict[str, Any]] = []
    for rarity, raw_count in pull_counts.items():
        pull_count = _require_int(raw_count, "pulled_count")
        total_value = _coerce_optional_float(value_totals.get(rarity))
        if total_value is None:
            raise ValueError(f"Missing required field: total_sampled_value (rarity bucket: {rarity})")
        avg_value = None
        if pull_count > 0:
            avg_value = total_value / pull_count

        payload = {
            "calculation_run_id": _require_present(run_id, "calculation_run_id"),
            "rarity_bucket": str(_require_present(rarity, "rarity_bucket")),
            "pulled_count": pull_count,
            "avg_sampled_value": avg_value,
            "total_sampled_value": total_value,
        }
        inserted = _insert_required_payload(
            "simulation_pull_summary",
            payload,
            f"Simulation pull summary insert ({rarity})",
        )
        inserted_rows.append(inserted)

    return inserted_rows


def create_simulation_state_counts(run_id: Any, sim_results: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Persist V2 pack path/state counts. V1 safely writes zero rows."""
    if not isinstance(sim_results, Mapping):
        raise ValueError("Missing required field: sim_results")

    path_counts = sim_results.get("pack_path_counts")
    state_counts = sim_results.get("pack_state_counts")

    if not isinstance(path_counts, Mapping) and not isinstance(state_counts, Mapping):
        raise ValueError("Missing required field(s): pack_path_counts, pack_state_counts")

    inserted_rows: List[Dict[str, Any]] = []

    if isinstance(path_counts, Mapping):
        for state_name, raw_count in path_counts.items():
            _require_present(state_name, "state_name")
            payload = {
                "calculation_run_id": _require_present(run_id, "calculation_run_id"),
                "state_group": "pack_path",
                "state_name": str(state_name),
                "occurrence_count": _require_int(raw_count, "occurrence_count"),
            }
            inserted = _insert_required_payload(
                "simulation_state_counts",
                payload,
                f"Simulation state count insert (path:{state_name})",
            )
            inserted_rows.append(inserted)

    if isinstance(state_counts, Mapping):
        for state_name, raw_count in state_counts.items():
            _require_present(state_name, "state_name")
            payload = {
                "calculation_run_id": _require_present(run_id, "calculation_run_id"),
                "state_group": "normal_pack_state",
                "state_name": str(state_name),
                "occurrence_count": _require_int(raw_count, "occurrence_count"),
            }
            inserted = _insert_required_payload(
                "simulation_state_counts",
                payload,
                f"Simulation state count insert (state:{state_name})",
            )
            inserted_rows.append(inserted)

    return inserted_rows


def create_simulation_derived_metrics(run_id: Any, derived: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Persist one derived-metrics row per run."""
    if not isinstance(derived, Mapping):
        raise ValueError("Missing required field: derived")

    _require_fields(
        derived,
        [
            "hit_ev",
            "non_hit_ev",
            "hit_ev_share",
            "hit_cards_tracked",
            "cards_tracked",
            "total_card_ev",
            "top1_ev_share",
            "top3_ev_share",
            "top5_ev_share",
            "index_score",
            "profit_component",
            "stability_component",
            "diversification_component",
        ],
        "simulation_derived_metrics",
    )

    payload = {
        "calculation_run_id": _require_present(run_id, "calculation_run_id"),
        "hit_ev": _require_float(derived.get("hit_ev"), "hit_ev"),
        "non_hit_ev": _require_float(derived.get("non_hit_ev"), "non_hit_ev"),
        "hit_ev_share": _require_float(derived.get("hit_ev_share"), "hit_ev_share"),
        "hit_cards_tracked": _require_int(derived.get("hit_cards_tracked"), "hit_cards_tracked"),
        "cards_tracked": _require_int(derived.get("cards_tracked"), "cards_tracked"),
        "total_card_ev": _require_float(derived.get("total_card_ev"), "total_card_ev"),
        "top1_ev_share": _require_float(derived.get("top1_ev_share"), "top1_ev_share"),
        "top3_ev_share": _require_float(derived.get("top3_ev_share"), "top3_ev_share"),
        "top5_ev_share": _require_float(derived.get("top5_ev_share"), "top5_ev_share"),
        "index_score": _require_float(derived.get("index_score"), "index_score"),
        "profit_component": _require_float(derived.get("profit_component"), "profit_component"),
        "stability_component": _require_float(derived.get("stability_component"), "stability_component"),
        "diversification_component": _require_float(
            derived.get("diversification_component"), "diversification_component"
        ),
    }

    inserted = _insert_required_payload(
        "simulation_derived_metrics",
        payload,
        "Simulation derived metrics insert",
    )
    return [inserted]


def _coerce_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def map_simulation_top_hits_rows(run_id: Any, top_hits_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map top-hit rows to strict schema payload shape for persistence."""
    mapped_rows: List[Dict[str, Any]] = []
    for index, row in enumerate(top_hits_rows, start=1):
        _require_fields(
            row,
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
            f"simulation_top_hits row {index}",
        )

        mapped_rows.append(
            {
                "calculation_run_id": _require_present(run_id, "calculation_run_id"),
                "card_id": row.get("card_id"),
                "card_variant_id": row.get("card_variant_id"),
                "rank": _require_int(row.get("rank"), "rank"),
                "card_name": _coerce_optional_str(row.get("card_name")),
                "rarity_bucket": _coerce_optional_str(row.get("rarity_bucket")),
                "market_price_at_run": _require_float(row.get("market_price_at_run"), "market_price_at_run"),
                "effective_pull_rate": _require_float(row.get("effective_pull_rate"), "effective_pull_rate"),
                "ev_contribution": _require_float(row.get("ev_contribution"), "ev_contribution"),
            }
        )
    return mapped_rows


def create_simulation_top_hits(run_id: Any, top_hits_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Persist ordered top-hit rows from pack calculation output."""
    mapped_rows = map_simulation_top_hits_rows(run_id, top_hits_rows)
    inserted_rows: List[Dict[str, Any]] = []

    for mapped in mapped_rows:
        if mapped.get("rank") is None:
            raise ValueError("Missing required field: rank")

        inserted = _insert_required_payload(
            "simulation_top_hits",
            mapped,
            f"Simulation top-hit insert (rank:{mapped.get('rank')})",
        )
        inserted_rows.append(inserted)

    return inserted_rows


def map_simulation_input_cards_rows(run_id: Any, input_cards_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map normalized input-card rows to strict schema payload shape for persistence."""
    mapped_rows: List[Dict[str, Any]] = []
    for index, row in enumerate(input_cards_rows, start=1):
        _require_fields(
            row,
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
            f"simulation_input_cards row {index}",
        )

        mapped_rows.append(
            {
                "calculation_run_id": _require_present(run_id, "calculation_run_id"),
                "card_id": row.get("card_id"),
                "card_variant_id": row.get("card_variant_id"),
                "condition_id": row.get("condition_id"),
                "price_source": _coerce_optional_str(row.get("price_source")),
                "price_used": _require_float(row.get("price_used"), "price_used"),
                "card_name": _coerce_optional_str(row.get("card_name")),
                "rarity_bucket": _coerce_optional_str(row.get("rarity_bucket")),
                "captured_at": _coerce_optional_str(row.get("captured_at")),
                "effective_pull_rate": _require_float(row.get("effective_pull_rate"), "effective_pull_rate"),
                "ev_contribution": _require_float(row.get("ev_contribution"), "ev_contribution"),
            }
        )
    return mapped_rows


def create_simulation_input_cards(run_id: Any, input_cards_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Persist normalized simulation input rows used for the run."""
    mapped_rows = map_simulation_input_cards_rows(run_id, input_cards_rows)
    inserted_rows: List[Dict[str, Any]] = []

    for mapped in mapped_rows:
        inserted = _insert_required_payload(
            "simulation_input_cards",
            mapped,
            f"Simulation input-card insert (card:{mapped.get('card_id')})",
        )
        inserted_rows.append(inserted)

    return inserted_rows


def map_simulation_etb_summary_row(run_id: Any, etb_metrics: Mapping[str, Any]) -> Dict[str, Any]:
    """Map ETB metrics to a canonical payload shape for persistence."""
    if not isinstance(etb_metrics, Mapping):
        raise ValueError("Missing required field: etb_metrics")

    _require_fields(
        etb_metrics,
        [
            "packs_per_etb",
            "etb_market_price",
            "promo_price",
            "ev_per_pack",
            "total_etb_ev",
            "net_value",
            "roi",
            "roi_percent",
        ],
        "simulation_etb_summary",
    )

    return {
        "calculation_run_id": _require_present(run_id, "calculation_run_id"),
        "packs_per_etb": _require_int(etb_metrics.get("packs_per_etb"), "packs_per_etb"),
        "etb_market_price": _require_float(etb_metrics.get("etb_market_price"), "etb_market_price"),
        "promo_price": _require_float(etb_metrics.get("promo_price"), "promo_price"),
        "ev_per_pack": _require_float(etb_metrics.get("ev_per_pack"), "ev_per_pack"),
        "total_etb_ev": _require_float(etb_metrics.get("total_etb_ev"), "total_etb_ev"),
        "net_value": _require_float(etb_metrics.get("net_value"), "net_value"),
        "roi": _require_float(etb_metrics.get("roi"), "roi"),
        "roi_percent": _require_float(etb_metrics.get("roi_percent"), "roi_percent"),
    }


def create_simulation_etb_summary(run_id: Any, etb_metrics: Mapping[str, Any]) -> Dict[str, Any]:
    """Persist ETB summary metrics for a simulation run."""
    mapped = map_simulation_etb_summary_row(run_id, etb_metrics)

    return _insert_required_payload(
        "simulation_etb_summary",
        mapped,
        "Simulation ETB summary insert",
    )
