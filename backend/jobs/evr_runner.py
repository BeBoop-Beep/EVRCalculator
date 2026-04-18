import argparse
import difflib
import logging
import sys
from pathlib import Path
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


def _resolve_excel_path(canonical_key: str, set_name: str) -> str:
    repo_root = Path(__file__).resolve().parent.parent.parent
    base_excel_dir = repo_root / "data" / "excelDocs"
    if not base_excel_dir.exists():
        raise FileNotFoundError(f"Excel base directory not found: {base_excel_dir}")

    existing_dirs = {
        d.name.lower(): d.name
        for d in base_excel_dir.iterdir()
        if d.is_dir()
    }

    candidates = [canonical_key, set_name]
    if set_name.endswith("s"):
        candidates.append(set_name[:-1])
    else:
        candidates.append(f"{set_name}s")

    if "Evolutions" in set_name:
        candidates.append(set_name.replace("Evolutions", "Evolution"))
    if "Evolution" in set_name:
        candidates.append(set_name.replace("Evolution", "Evolutions"))

    seen: set[str] = set()
    ordered_candidates: list[str] = []
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if normalized and normalized not in seen:
            ordered_candidates.append(normalized)
            seen.add(normalized)

    for candidate in ordered_candidates:
        exact = base_excel_dir / candidate / "pokemon_data.xlsx"
        if exact.exists():
            return str(exact)

        resolved_folder = existing_dirs.get(candidate.lower())
        if resolved_folder:
            resolved = base_excel_dir / resolved_folder / "pokemon_data.xlsx"
            if resolved.exists():
                return str(resolved)

    raise FileNotFoundError(
        f"Could not find pokemon_data.xlsx for canonical_key='{canonical_key}' set_name='{set_name}'. "
        f"Tried: {ordered_candidates}"
    )


def _validate_db_etb_inputs(*, etb_price: Any, etb_promo_card_price: Any, canonical_key: str) -> None:
    if etb_price is None or etb_promo_card_price is None:
        raise ValueError(
            f"DB input missing required ETB inputs for set '{canonical_key}': "
            f"etb_price={etb_price}, etb_promo_card_price={etb_promo_card_price}"
        )


def _safe_pack_price(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class EVRRunOrchestrator:
    """Owner of end-to-end EVR run orchestration for manual/scheduled invocations."""

    def run(self, *, target_set_identifier: str, input_source: str, run_metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
        effective_input_mode = str(input_source).strip().lower()
        if effective_input_mode not in {"db", "spreadsheet"}:
            raise ValueError("input_source must be one of: db, spreadsheet")

        metadata = run_metadata or {}
        logger.info(
            "Runner starting EVR orchestration: target_set_identifier=%s input_source=%s metadata=%s",
            target_set_identifier,
            effective_input_mode,
            metadata,
        )

        config_cls, canonical_key = _resolve_set_config(target_set_identifier)
        config = config_cls()
        set_name = str(getattr(config, "SET_NAME", canonical_key))

        if effective_input_mode == "db":
            prepared = EVRInputPreparationService().prepare_for_set(config, canonical_key, set_name)
            calculation_input = prepared["dataframe"]
            etb_price = prepared.get("etb_price")
            etb_promo_card_price = prepared.get("etb_promo_card_price")
            _validate_db_etb_inputs(
                etb_price=etb_price,
                etb_promo_card_price=etb_promo_card_price,
                canonical_key=canonical_key,
            )
        else:
            excel_path = _resolve_excel_path(canonical_key=canonical_key, set_name=set_name)
            calculation_input = excel_path
            etb_price = None
            etb_promo_card_price = None

        results, _summary_data, top_10_hits, pack_price = calculate_pack_stats(calculation_input, config)
        sim_results, pack_metrics = calculate_pack_simulations(calculation_input, config)
        total_ev = pack_metrics.get("total_ev", 0.0)

        results.update(
            {
                "actual_simulated_ev": pack_metrics.get("total_ev"),
                "net_value": pack_metrics.get("net_value"),
                "opening_pack_roi": pack_metrics.get("opening_pack_roi"),
                "opening_pack_roi_percent": pack_metrics.get("opening_pack_roi_percent"),
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

        if effective_input_mode == "db":
            etb_metrics = calculate_etb_metrics(
                None,
                9,
                total_ev,
                etb_price=etb_price,
                etb_promo_card_price=etb_promo_card_price,
            )
        else:
            etb_metrics = calculate_etb_metrics(calculation_input, 9, total_ev)

        persisted_parent = persist_parent_run_with_price_snapshots(
            config=config,
            canonical_key=canonical_key,
            set_name=set_name,
            input_mode=effective_input_mode,
            price_inputs={
                "pack": _safe_pack_price(pack_price),
                "etb": etb_metrics.get("etb_market_price"),
                "etb_promo": etb_metrics.get("etb_promo_price"),
            },
        )
        run_id = persisted_parent["run_id"]

        persisted_outputs = persist_simulation_outputs(
            run_id=run_id,
            sim_results=sim_results,
            pack_metrics=pack_metrics,
            derived=derived,
        )

        persisted_etb = persist_simulation_etb_summary(run_id=run_id, etb_metrics=etb_metrics)

        persisted_inputs = persist_simulation_inputs(
            run_id=run_id,
            top_10_hits=top_10_hits,
            calculation_input=calculation_input,
            config=config,
        )

        result = {
            "canonical_key": canonical_key,
            "set_name": set_name,
            "input_source": effective_input_mode,
            "pack_price": _safe_pack_price(pack_price),
            "total_ev": pack_metrics.get("total_ev"),
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
        choices=("db", "spreadsheet"),
        help="Required EVR input source.",
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

    if args.input_source not in {"db", "spreadsheet"}:
        raise ValueError("input-source must be one of: db, spreadsheet")


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
