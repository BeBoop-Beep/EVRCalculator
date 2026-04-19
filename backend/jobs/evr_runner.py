import argparse
import difflib
import logging
import statistics
import sys
from copy import deepcopy
from typing import Any, Dict

from backend.calculations.evr import compute_all_derived_metrics, print_derived_metrics_summary
from backend.calculations.evrEtb import calculate_etb_metrics
from backend.calculations.packCalcsRefractored import calculate_pack_stats
from backend.constants.tcg.pokemon.scarletAndVioletEra.setMap import SET_ALIAS_MAP, SET_CONFIG_MAP
from backend.db.services.calculation_run_persistence_service import (
    persist_parent_run_with_price_snapshots,
    persist_simulation_etb_summary,
    persist_simulation_inputs,
    persist_simulation_outputs,
)
from backend.db.services.evr_input_preparation_service import EVRInputPreparationService
from backend.simulations import calculate_pack_simulations

logger = logging.getLogger(__name__)

ENABLE_ETB_IN_ACTIVE_EVR_FLOW = False

DEFAULT_PRODUCT_VARIANT_RULES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "etb": {
        "standard": {"packs_per_product": 9},
    },
    "booster_box": {
        "standard": {"packs_per_product": 36},
    },
}


def _build_constants_config_map() -> Dict[str, Any]:
    if not SET_CONFIG_MAP:
        raise RuntimeError("No Pokemon set configuration map entries were loaded.")
    return SET_CONFIG_MAP


def _build_constants_alias_map() -> Dict[str, str]:
    return SET_ALIAS_MAP


def _resolve_set_config(target_set_identifier: str) -> tuple[Any, str]:
    config_map = _build_constants_config_map()
    alias_map = _build_constants_alias_map()

    raw = str(target_set_identifier or "").strip()
    key = raw.lower()
    if not key:
        raise ValueError("target_set_identifier is required and cannot be empty.")

    canonical_key_by_lower = {str(k).lower(): str(k) for k in config_map.keys()}

    if key in alias_map:
        canonical_key = alias_map[key]
        return config_map[canonical_key], canonical_key

    if key in canonical_key_by_lower:
        canonical_key = canonical_key_by_lower[key]
        return config_map[canonical_key], canonical_key

    possible_inputs = list(alias_map.keys()) + list(canonical_key_by_lower.keys())
    matches = difflib.get_close_matches(key, possible_inputs, n=1, cutoff=0.6)
    if matches:
        matched_key = matches[0]
        canonical_key = alias_map.get(matched_key) or canonical_key_by_lower.get(matched_key)
        if canonical_key and canonical_key in config_map:
            logger.info("Resolved set identifier '%s' to '%s' via fuzzy match.", raw, canonical_key)
            return config_map[canonical_key], canonical_key

    raise ValueError(f"Set '{target_set_identifier}' not found. Please check the set name and try again.")


def _validate_db_etb_inputs(
    *,
    etb_price: Any,
    etb_promo_card_price: Any,
    canonical_key: str,
    etb_variants: Dict[str, Dict[str, Any]] | None = None,
) -> None:
    standard_variant = (etb_variants or {}).get("standard") if isinstance(etb_variants, dict) else None
    standard_variant_price = standard_variant.get("etb_price") if isinstance(standard_variant, dict) else None
    standard_variant_promo = standard_variant.get("etb_promo_card_price") if isinstance(standard_variant, dict) else None

    has_standard_etb_inputs = (
        (etb_price is not None and etb_promo_card_price is not None)
        or (standard_variant_price is not None and standard_variant_promo is not None)
    )

    if not has_standard_etb_inputs:
        raise ValueError(
            f"DB input missing required ETB inputs for set '{canonical_key}': "
            f"etb_price={etb_price}, etb_promo_card_price={etb_promo_card_price}, "
            f"standard_variant={standard_variant}"
        )


def _is_etb_enabled(config: Any) -> bool:
    configured = getattr(config, "ENABLE_ETB_IN_ACTIVE_EVR_FLOW", ENABLE_ETB_IN_ACTIVE_EVR_FLOW)
    return bool(configured)


def _build_inactive_etb_comparison_placeholders() -> Dict[str, Dict[str, Any]]:
    return {
        "simulated_mean_etb_value_vs_etb_cost": {"roi": None},
        "simulated_median_etb_value_vs_etb_cost": {"roi": None},
        "calculated_expected_etb_value_vs_etb_cost": {"roi": None},
    }


def _safe_pack_price(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compute_cost_comparison(*, expected_value: float, cost: float | None) -> Dict[str, Any]:
    if cost is None or cost <= 0:
        return {
            "expected_value": float(expected_value),
            "cost": cost,
            "profit_loss": None,
            "roi": None,
            "roi_percent": None,
        }

    profit_loss = float(expected_value) - float(cost)
    roi = float(expected_value) / float(cost)
    return {
        "expected_value": float(expected_value),
        "cost": float(cost),
        "profit_loss": profit_loss,
        "roi": roi,
        "roi_percent": (roi - 1.0) * 100.0,
    }


def _compute_etb_expected_value(*, packs_per_etb: int, per_pack_value: float, promo_price: float) -> float:
    return (float(packs_per_etb) * float(per_pack_value)) + float(promo_price)


def _compute_etb_comparison(
    *,
    packs_per_etb: int,
    per_pack_value: float,
    promo_price: float,
    etb_cost: float | None,
) -> Dict[str, Any]:
    expected_total_etb_value = _compute_etb_expected_value(
        packs_per_etb=packs_per_etb,
        per_pack_value=per_pack_value,
        promo_price=promo_price,
    )
    comparison = _compute_cost_comparison(expected_value=expected_total_etb_value, cost=etb_cost)
    comparison.update(
        {
            "packs_per_etb": int(packs_per_etb),
            "per_pack_value": float(per_pack_value),
            "promo_price": float(promo_price),
            "expected_total_etb_value": expected_total_etb_value,
            "formula": "expected_total_etb_value = (packs_per_etb * per_pack_value) + promo_price",
        }
    )
    return comparison


def _compute_booster_box_comparison(
    *,
    packs_per_booster_box: int,
    per_pack_value: float,
    booster_box_cost: float | None,
    booster_box_promo_price: float = 0.0,
) -> Dict[str, Any]:
    expected_total_booster_box_value = (float(packs_per_booster_box) * float(per_pack_value)) + float(booster_box_promo_price)
    comparison = _compute_cost_comparison(expected_value=expected_total_booster_box_value, cost=booster_box_cost)
    formula = "expected_total_booster_box_value = packs_per_booster_box * per_pack_value"
    if booster_box_promo_price:
        formula = "expected_total_booster_box_value = (packs_per_booster_box * per_pack_value) + booster_box_promo_price"

    comparison.update(
        {
            "packs_per_booster_box": int(packs_per_booster_box),
            "per_pack_value": float(per_pack_value),
            "booster_box_promo_price": float(booster_box_promo_price),
            "expected_total_booster_box_value": expected_total_booster_box_value,
            "formula": formula,
        }
    )
    return comparison


def _resolve_product_variant_rules(config: Any) -> Dict[str, Dict[str, Dict[str, Any]]]:
    merged = deepcopy(DEFAULT_PRODUCT_VARIANT_RULES)
    configured = getattr(config, "PRODUCT_VARIANT_RULES", None)
    if not isinstance(configured, dict):
        return merged

    for product_key, variants in configured.items():
        if not isinstance(variants, dict):
            continue
        merged.setdefault(str(product_key), {})
        for variant_key, payload in variants.items():
            if not isinstance(payload, dict):
                continue
            merged[str(product_key)][str(variant_key)] = dict(payload)

    return merged


def _packs_per_product_for_variant(
    *,
    config: Any,
    product_key: str,
    variant_key: str,
    fallback: int,
) -> int:
    rules = _resolve_product_variant_rules(config)
    product_rules = rules.get(product_key, {})
    variant_rules = product_rules.get(variant_key, {})
    packs = variant_rules.get("packs_per_product", fallback)
    return int(_safe_float(packs, fallback))


def _build_etb_variant_pricing_inputs(
    *,
    prepared_payload: Dict[str, Any],
    etb_metrics: Dict[str, Any],
) -> Dict[str, Dict[str, float | None]]:
    raw_variants = prepared_payload.get("etb_variants") or {}
    variant_payload: Dict[str, Dict[str, float | None]] = {}

    if isinstance(raw_variants, dict):
        for raw_key, raw_value in raw_variants.items():
            if not isinstance(raw_value, dict):
                continue
            variant_key = str(raw_key)
            etb_price = raw_value.get("etb_price")
            promo_price = raw_value.get("etb_promo_card_price")
            variant_payload[variant_key] = {
                "etb_price": _safe_float(etb_price) if etb_price is not None else None,
                "etb_promo_card_price": _safe_float(promo_price) if promo_price is not None else None,
            }

    standard_price = etb_metrics.get("etb_market_price")
    standard_promo = etb_metrics.get("etb_promo_price")
    variant_payload["standard"] = {
        "etb_price": _safe_float(standard_price) if standard_price is not None else None,
        "etb_promo_card_price": _safe_float(standard_promo) if standard_promo is not None else None,
    }

    return variant_payload


def _build_booster_box_variant_pricing_inputs(*, prepared_payload: Dict[str, Any]) -> Dict[str, Dict[str, float | None]]:
    raw_variants = prepared_payload.get("booster_box_variants") or {}
    variant_payload: Dict[str, Dict[str, float | None]] = {}

    if isinstance(raw_variants, dict):
        for raw_key, raw_value in raw_variants.items():
            if not isinstance(raw_value, dict):
                continue
            variant_key = str(raw_key)
            booster_box_price = raw_value.get("booster_box_price")
            booster_box_promo_price = raw_value.get("booster_box_promo_card_price")
            variant_payload[variant_key] = {
                "booster_box_price": _safe_float(booster_box_price) if booster_box_price is not None else None,
                "booster_box_promo_card_price": _safe_float(booster_box_promo_price, 0.0)
                if booster_box_promo_price is not None
                else 0.0,
            }

    if "standard" not in variant_payload:
        standard_price = prepared_payload.get("booster_box_price")
        variant_payload["standard"] = {
            "booster_box_price": _safe_float(standard_price) if standard_price is not None else None,
            "booster_box_promo_card_price": 0.0,
        }

    return variant_payload


def _compute_etb_variant_comparisons(
    *,
    config: Any,
    variant_inputs: Dict[str, Dict[str, float | None]],
    simulated_mean_value_per_pack: float,
    simulated_median_value_per_pack: float,
    calculated_expected_value_per_pack: float,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    comparisons_by_variant: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for variant_key, payload in variant_inputs.items():
        packs_per_etb = _packs_per_product_for_variant(
            config=config,
            product_key="etb",
            variant_key=variant_key,
            fallback=9,
        )
        etb_cost = payload.get("etb_price")
        promo_price = payload.get("etb_promo_card_price") or 0.0

        comparisons_by_variant[variant_key] = {
            "simulated_mean_etb_value_vs_etb_cost": _compute_etb_comparison(
                packs_per_etb=packs_per_etb,
                per_pack_value=simulated_mean_value_per_pack,
                promo_price=promo_price,
                etb_cost=etb_cost,
            ),
            "simulated_median_etb_value_vs_etb_cost": _compute_etb_comparison(
                packs_per_etb=packs_per_etb,
                per_pack_value=simulated_median_value_per_pack,
                promo_price=promo_price,
                etb_cost=etb_cost,
            ),
            "calculated_expected_etb_value_vs_etb_cost": _compute_etb_comparison(
                packs_per_etb=packs_per_etb,
                per_pack_value=calculated_expected_value_per_pack,
                promo_price=promo_price,
                etb_cost=etb_cost,
            ),
        }

    return comparisons_by_variant


def _compute_booster_box_variant_comparisons(
    *,
    config: Any,
    variant_inputs: Dict[str, Dict[str, float | None]],
    simulated_mean_value_per_pack: float,
    simulated_median_value_per_pack: float,
    calculated_expected_value_per_pack: float,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    comparisons_by_variant: Dict[str, Dict[str, Dict[str, Any]]] = {}
    default_packs = int(_safe_float(getattr(config, "BOOSTER_BOX_PACK_COUNT", 36), 36))

    for variant_key, payload in variant_inputs.items():
        packs_per_booster_box = _packs_per_product_for_variant(
            config=config,
            product_key="booster_box",
            variant_key=variant_key,
            fallback=default_packs,
        )
        booster_box_cost = payload.get("booster_box_price")
        booster_box_promo_price = payload.get("booster_box_promo_card_price") or 0.0

        comparisons_by_variant[variant_key] = {
            "simulated_mean_booster_box_value_vs_booster_box_cost": _compute_booster_box_comparison(
                packs_per_booster_box=packs_per_booster_box,
                per_pack_value=simulated_mean_value_per_pack,
                booster_box_cost=booster_box_cost,
                booster_box_promo_price=booster_box_promo_price,
            ),
            "simulated_median_booster_box_value_vs_booster_box_cost": _compute_booster_box_comparison(
                packs_per_booster_box=packs_per_booster_box,
                per_pack_value=simulated_median_value_per_pack,
                booster_box_cost=booster_box_cost,
                booster_box_promo_price=booster_box_promo_price,
            ),
            "calculated_expected_booster_box_value_vs_booster_box_cost": _compute_booster_box_comparison(
                packs_per_booster_box=packs_per_booster_box,
                per_pack_value=calculated_expected_value_per_pack,
                booster_box_cost=booster_box_cost,
                booster_box_promo_price=booster_box_promo_price,
            ),
        }

    return comparisons_by_variant


def _print_value_vs_cost_summary(
    *,
    pack_comparisons: Dict[str, Dict[str, Any]],
    etb_comparisons: Dict[str, Dict[str, Any]],
    booster_box_comparisons: Dict[str, Dict[str, Any]],
) -> None:
    def _fmt_money(value: Any) -> str:
        if value is None:
            return "n/a"
        return f"${float(value):.2f}"

    def _fmt_roi(value: Any) -> str:
        if value is None:
            return "n/a"
        return f"{float(value):.4f}"

    print("\n=== Value vs Cost Summary ===")
    print("Pack comparisons:")
    for label, payload in pack_comparisons.items():
        print(
            "- "
            f"{label}: expected={_fmt_money(payload.get('expected_value'))}, "
            f"cost={_fmt_money(payload.get('cost'))}, "
            f"profit/loss={_fmt_money(payload.get('profit_loss'))}, "
            f"roi={_fmt_roi(payload.get('roi'))}"
        )

    if etb_comparisons:
        print("ETB comparisons:")
        for label, payload in etb_comparisons.items():
            print(
                "- "
                f"{label}: expected={_fmt_money(payload.get('expected_total_etb_value'))}, "
                f"cost={_fmt_money(payload.get('cost'))}, "
                f"profit/loss={_fmt_money(payload.get('profit_loss'))}, "
                f"roi={_fmt_roi(payload.get('roi'))}, "
                f"formula={payload.get('formula')}"
            )

    print("Booster-box comparisons:")
    for label, payload in booster_box_comparisons.items():
        print(
            "- "
            f"{label}: expected={_fmt_money(payload.get('expected_total_booster_box_value'))}, "
            f"cost={_fmt_money(payload.get('cost'))}, "
            f"profit/loss={_fmt_money(payload.get('profit_loss'))}, "
            f"roi={_fmt_roi(payload.get('roi'))}, "
            f"formula={payload.get('formula')}"
        )


class EVRRunOrchestrator:
    """Owner of end-to-end EVR run orchestration for manual/scheduled invocations."""

    def run(self, *, target_set_identifier: str, input_source: str, run_metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
        effective_input_mode = str(input_source).strip().lower()
        if effective_input_mode != "db":
            raise ValueError("input_source must be 'db' for the active backend runtime")

        metadata = run_metadata or {}
        logger.info(
            "Runner starting EVR orchestration: target_set_identifier=%s input_source=%s metadata=%s",
            target_set_identifier,
            effective_input_mode,
            metadata,
        )

        config_cls, canonical_key = _resolve_set_config(target_set_identifier)
        config = config_cls()
        etb_enabled = _is_etb_enabled(config)
        set_name = str(getattr(config, "SET_NAME", canonical_key))

        prepared = EVRInputPreparationService().prepare_for_set(config, canonical_key, set_name)
        calculation_input = prepared["dataframe"]
        etb_price = prepared.get("etb_price")
        etb_promo_card_price = prepared.get("etb_promo_card_price")
        etb_variants = prepared.get("etb_variants")
        if etb_enabled:
            _validate_db_etb_inputs(
                etb_price=etb_price,
                etb_promo_card_price=etb_promo_card_price,
                canonical_key=canonical_key,
                etb_variants=etb_variants,
            )

        results, _summary_data, top_10_hits, pack_price = calculate_pack_stats(calculation_input, config)
        sim_results, pack_metrics = calculate_pack_simulations(calculation_input, config)
        total_ev = pack_metrics.get("total_ev", 0.0)
        calculated_expected_value_per_pack = _safe_float(results.get("total_manual_ev"), 0.0)
        simulated_mean_value_per_pack = _safe_float(sim_results.get("mean"), 0.0)
        percentile_map = sim_results.get("percentiles", {})
        simulated_median_value_per_pack = _safe_float(
            percentile_map.get("50th", percentile_map.get("50th (median)")),
            statistics.median(sim_results.get("values", [0.0])),
        )
        pack_price_value = _safe_pack_price(pack_price)

        results.update(
            {
                "actual_simulated_ev": pack_metrics.get("total_ev"),
                "net_value": pack_metrics.get("net_value"),
                "opening_pack_roi": pack_metrics.get("opening_pack_roi"),
                "opening_pack_roi_percent": pack_metrics.get("opening_pack_roi_percent"),
                "calculated_expected_value_per_pack": calculated_expected_value_per_pack,
            }
        )

        derived = compute_all_derived_metrics(
            sim_results.get("values", []),
            pack_price,
            card_ev_contributions=results.get("hit_ev_contributions"),
            total_pack_ev=pack_metrics.get("total_ev"),
            hit_ev=results.get("hit_ev"),
            hit_cards_count=len(results.get("hit_ev_contributions", {})) if results.get("hit_ev_contributions") else None,
        )
        print_derived_metrics_summary(derived)

        booster_box_variant_inputs = _build_booster_box_variant_pricing_inputs(prepared_payload=prepared)
        standard_booster_box_variant = booster_box_variant_inputs.get("standard", {})

        booster_box_price_float = standard_booster_box_variant.get("booster_box_price")

        pack_value_vs_cost_comparison = {
            "simulated_mean_pack_value_vs_pack_cost": _compute_cost_comparison(
                expected_value=simulated_mean_value_per_pack,
                cost=pack_price_value,
            ),
            "simulated_median_pack_value_vs_pack_cost": _compute_cost_comparison(
                expected_value=simulated_median_value_per_pack,
                cost=pack_price_value,
            ),
            "calculated_expected_pack_value_vs_pack_cost": _compute_cost_comparison(
                expected_value=calculated_expected_value_per_pack,
                cost=pack_price_value,
            ),
        }

        if etb_enabled:
            etb_metrics = calculate_etb_metrics(
                None,
                9,
                total_ev,
                etb_price=etb_price,
                etb_promo_card_price=etb_promo_card_price,
            )
            etb_variant_inputs = _build_etb_variant_pricing_inputs(prepared_payload=prepared, etb_metrics=etb_metrics)
            standard_etb_variant = etb_variant_inputs.get("standard", {})
            etb_value_vs_cost_comparison_by_variant = _compute_etb_variant_comparisons(
                config=config,
                variant_inputs=etb_variant_inputs,
                simulated_mean_value_per_pack=simulated_mean_value_per_pack,
                simulated_median_value_per_pack=simulated_median_value_per_pack,
                calculated_expected_value_per_pack=calculated_expected_value_per_pack,
            )
            etb_value_vs_cost_comparison = etb_value_vs_cost_comparison_by_variant.get("standard") or {}
            etb_value_vs_cost_comparison_for_persistence = etb_value_vs_cost_comparison
        else:
            etb_metrics = None
            standard_etb_variant = {}
            etb_value_vs_cost_comparison_by_variant = {}
            etb_value_vs_cost_comparison = {}
            etb_value_vs_cost_comparison_for_persistence = None

        booster_box_value_vs_cost_comparison_by_variant = _compute_booster_box_variant_comparisons(
            config=config,
            variant_inputs=booster_box_variant_inputs,
            simulated_mean_value_per_pack=simulated_mean_value_per_pack,
            simulated_median_value_per_pack=simulated_median_value_per_pack,
            calculated_expected_value_per_pack=calculated_expected_value_per_pack,
        )
        booster_box_value_vs_cost_comparison = booster_box_value_vs_cost_comparison_by_variant.get("standard") or {}

        _print_value_vs_cost_summary(
            pack_comparisons=pack_value_vs_cost_comparison,
            etb_comparisons=etb_value_vs_cost_comparison,
            booster_box_comparisons=booster_box_value_vs_cost_comparison,
        )

        persisted_parent = persist_parent_run_with_price_snapshots(
            config=config,
            canonical_key=canonical_key,
            set_name=set_name,
            input_mode=effective_input_mode,
            price_inputs={
                "pack": _safe_pack_price(pack_price),
                "booster_box": booster_box_price_float,
            },
            pack_value_vs_cost_comparison=pack_value_vs_cost_comparison,
            etb_value_vs_cost_comparison=etb_value_vs_cost_comparison_for_persistence,
            booster_box_value_vs_cost_comparison=booster_box_value_vs_cost_comparison,
        )
        run_id = persisted_parent["run_id"]

        persisted_inputs = persist_simulation_inputs(
            run_id=run_id,
            top_10_hits=top_10_hits,
            calculation_input=calculation_input,
            config=config,
        )

        persisted_outputs = persist_simulation_outputs(
            run_id=run_id,
            sim_results=sim_results,
            pack_metrics=pack_metrics,
            derived=derived,
        )

        persisted_etb = None
        if etb_enabled:
            persisted_etb = persist_simulation_etb_summary(run_id=run_id, etb_metrics=etb_metrics)

        result = {
            "canonical_key": canonical_key,
            "set_name": set_name,
            "input_source": effective_input_mode,
            "pack_price": pack_price_value,
            "total_ev": pack_metrics.get("total_ev"),
            "calculated_expected_value_per_pack": calculated_expected_value_per_pack,
            "pack_value_vs_cost_comparison": pack_value_vs_cost_comparison,
            "etb_value_vs_cost_comparison": etb_value_vs_cost_comparison,
            "etb_value_vs_cost_comparison_by_variant": etb_value_vs_cost_comparison_by_variant,
            "booster_box_value_vs_cost_comparison": booster_box_value_vs_cost_comparison,
            "booster_box_value_vs_cost_comparison_by_variant": booster_box_value_vs_cost_comparison_by_variant,
            "etb_metrics": etb_metrics,
            "run_metadata": metadata,
            "persisted": {
                "parent": persisted_parent,
                "outputs": persisted_outputs,
                "inputs": persisted_inputs,
                "etb_summary": persisted_etb,
            },
            "derived": derived,
        }

        logger.info(
            "Runner completed EVR orchestration: canonical_key=%s input_source=%s total_ev=%s",
            result.get("canonical_key"),
            result.get("input_source"),
            result.get("total_ev"),
        )
        return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run EVR calculations for a target Pokemon set (manual or scheduled)."
    )
    parser.add_argument(
        "target_set_identifier",
        help="Required set identifier (alias, canonical key, or set name recognized by set map).",
    )
    parser.add_argument(
        "--input-source",
        required=True,
        choices=("db",),
        help="Required EVR input source. Only 'db' is supported by the active backend runtime.",
    )
    parser.add_argument(
        "--trigger",
        default="manual",
        choices=("manual", "scheduled"),
        help="Optional run trigger metadata for audit/logging.",
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="Optional run label for traceability.",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if not args.target_set_identifier or not args.target_set_identifier.strip():
        raise ValueError("target_set_identifier is required and cannot be empty.")

    if args.input_source != "db":
        raise ValueError("input-source must be 'db' for the active backend runtime")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    parser = _build_parser()
    args = parser.parse_args()

    try:
        _validate_args(args)
        orchestrator = EVRRunOrchestrator()
        orchestrator.run(
            target_set_identifier=args.target_set_identifier,
            input_source=args.input_source,
            run_metadata={
                "trigger": args.trigger,
                "run_label": args.run_label,
            },
        )
        return 0
    except Exception as exc:
        logger.exception("EVR runner failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
