from collections import defaultdict
import json
import logging
import os
import time
from typing import Mapping, MutableMapping

from .monteCarloSim import make_simulate_pack_fn, print_simulation_summary, run_simulation
from .monteCarloSimV2 import (
    make_simulate_pack_fn_v2,
    print_simulation_summary_v2,
    run_simulation_v2,
    validate_pack_state_model,
)
from .slotSchemaContract import get_pack_structure
from .slotSchemaOutcomeResolver import apply_slot_schema_outcome_pool_mapping
from .slotSchemaSimulator import simulate_slot_schema_packs
from backend.calculations.packCalcsRefractored.otherCalculations import PackCalculations
from backend.utils.debug_output import debug_print
from .utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups
from .utils.packStateModels.packStateModelOrchestrator import resolve_pack_state_model
from .utils.simulationTokenResolver import (
    get_row_match_keys,
    get_simulation_token_mode,
    resolve_hit_pool_rows,
)
from .validations.monteCarloValidations import validate_and_debug_slot, validate_full_pack_logic


logger = logging.getLogger(__name__)


def _coerce_bool_flag(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_simulation_engine(engine) -> str:
    normalized = str(engine).strip().lower()
    if not normalized:
        raise ValueError("SIMULATION_ENGINE cannot be empty.")
    if normalized in {"v1", "legacy", "v2", "slot_schema"}:
        return normalized
    raise ValueError(
        f"Unsupported SIMULATION_ENGINE={engine!r}. Expected 'legacy', 'v1', 'v2', or 'slot_schema'."
    )


def _coerce_float(value) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric if numeric == numeric else 0.0


def _coerce_slot_schema_pool_rows(pool, *, value_column: str):
    if pool is None:
        return []

    if hasattr(pool, "to_dict"):
        records = pool.to_dict(orient="records")
    elif isinstance(pool, list):
        records = pool
    else:
        records = list(pool)

    normalized_rows = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(
                "slot_schema pool rows must be mapping-like dicts. "
                f"Received type={type(record).__name__} at index={index}."
            )

        row = dict(record)
        raw_value = row.get(value_column)
        if raw_value is None and value_column != "Price ($)":
            raw_value = row.get("Price ($)")
        if raw_value is None and value_column != "Reverse Variant Price ($)":
            raw_value = row.get("Reverse Variant Price ($)")
        row["value"] = _coerce_float(raw_value)
        normalized_rows.append(row)

    return normalized_rows


def _build_slot_schema_card_pool(config, card_groups, simulation_input_df):
    card_pool = {
        "common": _coerce_slot_schema_pool_rows(card_groups.get("common"), value_column="Price ($)"),
        "uncommon": _coerce_slot_schema_pool_rows(card_groups.get("uncommon"), value_column="Price ($)"),
        "rare": _coerce_slot_schema_pool_rows(card_groups.get("rare"), value_column="Price ($)"),
        "reverse": _coerce_slot_schema_pool_rows(
            card_groups.get("reverse"),
            value_column="Reverse Variant Price ($)",
        ),
        "hit": _coerce_slot_schema_pool_rows(card_groups.get("hit"), value_column="Price ($)"),
    }

    outcome_mapping = getattr(config, "SLOT_SCHEMA_OUTCOME_POOL_MAPPING", None)
    if isinstance(outcome_mapping, Mapping) and outcome_mapping:
        resolved_outcome_pools = apply_slot_schema_outcome_pool_mapping(
            config,
            simulation_input_df,
            allow_empty_pools=True,
        )

        required_outcomes = set(getattr(config, "RARE_SLOT_PROBABILITY", {}).keys())
        for required_outcome in required_outcomes:
            required_pool = resolved_outcome_pools.get(required_outcome)
            if required_pool is not None and required_pool.empty:
                raise ValueError(
                    "slot_schema runtime pool construction failed: "
                    f"required outcome {required_outcome!r} resolved to an empty mapped pool."
                )

        for outcome, pool_df in resolved_outcome_pools.items():
            if pool_df.empty:
                continue
            card_pool[outcome] = _coerce_slot_schema_pool_rows(pool_df, value_column="Price ($)")

    return card_pool


def _is_slot_schema_runtime_enabled(config) -> bool:
    """Return True only when the config has explicitly opted into slot-schema runtime.

    The config must set SLOT_SCHEMA_RUNTIME_ENABLED = True.  The flag is
    intentionally absent from base configs so that individual set configs must
    make a deliberate opt-in.  Inheriting classes automatically propagate the
    flag, making it straightforward to pilot on one set at a time.
    """
    raw = getattr(config, "SLOT_SCHEMA_RUNTIME_ENABLED", False)
    return _coerce_bool_flag(raw)


def _validate_slot_schema_runtime_readiness(config) -> None:
    """Fail fast when slot-schema runtime is enabled without required probability tables.

    Readiness is derived directly from PACK_STRUCTURE.rare_family_slots so runtime
    enablement cannot drift from the slot contract.
    """
    pack_structure = get_pack_structure(config)
    rare_family_slots = pack_structure.get("rare_family_slots", [])

    for index, slot in enumerate(rare_family_slots):
        slot_name = str(slot.get("name", f"slot_{index}"))
        slot_path = f"PACK_STRUCTURE.rare_family_slots[{index}] ({slot_name})"

        probability_attr = slot.get("probability_attr")
        probability_key = slot.get("probability_key")

        if isinstance(probability_attr, str) and probability_attr.strip():
            attr_name = probability_attr.strip()
            if not hasattr(config, attr_name):
                raise ValueError(
                    "slot_schema runtime readiness failed: "
                    f"{slot_path} references probability_attr={attr_name!r}, "
                    "but config does not define that attribute."
                )

            probability_table = getattr(config, attr_name)
            if probability_key is not None:
                if not isinstance(probability_table, Mapping):
                    raise ValueError(
                        "slot_schema runtime readiness failed: "
                        f"{slot_path} uses probability_key={probability_key!r}, "
                        f"but {attr_name!r} is type={type(probability_table).__name__} "
                        "not a mapping."
                    )
                if probability_key not in probability_table:
                    raise ValueError(
                        "slot_schema runtime readiness failed: "
                        f"{slot_path} references probability_key={probability_key!r} in "
                        f"{attr_name!r}, but that key does not exist."
                    )
            continue

        default_outcome = slot.get("default_outcome")
        if not isinstance(default_outcome, str) or not default_outcome.strip():
            raise ValueError(
                "slot_schema runtime readiness failed: "
                f"{slot_path} has no probability_attr and must define a non-empty "
                "default_outcome."
            )

    rare_slot_probability = getattr(config, "RARE_SLOT_PROBABILITY", None)
    if rare_slot_probability is None:
        return

    if not isinstance(rare_slot_probability, Mapping) or not rare_slot_probability:
        raise ValueError(
            "slot_schema runtime readiness failed: RARE_SLOT_PROBABILITY must be a non-empty mapping "
            "when present on a slot_schema runtime-enabled config."
        )

    outcome_pool_mapping = getattr(config, "SLOT_SCHEMA_OUTCOME_POOL_MAPPING", None)
    if not isinstance(outcome_pool_mapping, Mapping) or not outcome_pool_mapping:
        raise ValueError(
            "slot_schema runtime readiness failed: runtime-enabled slot_schema config with "
            "RARE_SLOT_PROBABILITY must define SLOT_SCHEMA_OUTCOME_POOL_MAPPING."
        )

    missing_mapped_outcomes = [
        outcome
        for outcome in rare_slot_probability
        if outcome not in outcome_pool_mapping
    ]
    if missing_mapped_outcomes:
        raise ValueError(
            "slot_schema runtime readiness failed: SLOT_SCHEMA_OUTCOME_POOL_MAPPING is missing "
            "outcomes required by RARE_SLOT_PROBABILITY: "
            + ", ".join(sorted(str(item) for item in missing_mapped_outcomes))
        )


def _is_celebrations_special_set(config) -> bool:
    era = str(getattr(config, "ERA", "")).strip().lower()
    set_name = str(getattr(config, "SET_NAME", "")).strip().lower()
    set_id = str(getattr(config, "SET_ID", "")).strip().lower()
    return era == "sword and shield" and (set_name == "celebrations" or set_id == "cel25")


def _has_explicit_pack_structure_override(config) -> bool:
    config_dict = getattr(config, "__dict__", {})
    return isinstance(config_dict, dict) and "PACK_STRUCTURE" in config_dict


def get_simulation_engine(config) -> str:
    configured_engine = getattr(config, "SIMULATION_ENGINE", None)
    if configured_engine is not None:
        normalized_engine = _normalize_simulation_engine(configured_engine)
        if (
            normalized_engine == "slot_schema"
            and _is_celebrations_special_set(config)
            and not _has_explicit_pack_structure_override(config)
        ):
            raise ValueError(
                "Set 'Celebrations' cannot use inherited standard SWSH PACK_STRUCTURE with "
                "SIMULATION_ENGINE='slot_schema'. Define an explicit special PACK_STRUCTURE "
                "four-card override before enabling slot-schema routing."
            )
        return normalized_engine

    return "v2" if _should_use_monte_carlo_v2(config) else "v1"


def _should_use_monte_carlo_v2(config) -> bool:
    configured_engine = getattr(config, "SIMULATION_ENGINE", None)
    if configured_engine is not None:
        return _normalize_simulation_engine(configured_engine) == "v2"

    configured = getattr(config, "USE_MONTE_CARLO_V2", False)
    if _coerce_bool_flag(configured):
        return True

    era = str(getattr(config, "ERA", "")).strip().lower()
    return era in {"scarlet and violet", "mega evolution"}


def _is_black_bolt_config(config) -> bool:
    set_name = str(getattr(config, "SET_NAME", "")).strip().lower()
    set_id = str(getattr(config, "SET_ID", "")).strip().lower()
    return set_name == "black bolt" or set_id == "zsv10pt5"


def _is_black_bolt_sim_audit_enabled(config) -> bool:
    if not _is_black_bolt_config(config):
        return False
    raw = os.getenv("DEBUG_BLACK_BOLT_SIM_AUDIT", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _build_black_bolt_calc_bucket_stats(df, config, card_groups):
    if df is None or len(df) == 0:
        return {}

    working = df.copy()
    rarity_keys, _ = get_row_match_keys(working, mode="base_rarity")
    pattern_keys, _ = get_row_match_keys(working, mode="pattern")
    effective_rates = working.get("Effective_Pull_Rate")
    prices = working.get("Price ($)")
    ev_values = working.get("EV")

    if effective_rates is None or prices is None or ev_values is None:
        return {}

    working["_bucket"] = rarity_keys.astype(str)
    working.loc[pattern_keys.eq("pokeball_pattern"), "_bucket"] = "poke ball pattern"
    working.loc[pattern_keys.eq("master_ball_pattern"), "_bucket"] = "master ball pattern"

    bucket_stats = {}
    for bucket_name, group in working.groupby("_bucket"):
        if not bucket_name:
            continue
        rate_values = group["Effective_Pull_Rate"]
        event_probability = float((1.0 / rate_values).replace([float("inf")], 0.0).fillna(0.0).sum())
        bucket_stats[bucket_name] = {
            "calc_event_probability": event_probability,
            "calc_eligible_rows": int(len(group)),
            "calc_avg_eligible_value": float(group["Price ($)"].fillna(0.0).mean()) if len(group) else 0.0,
            "calc_ev_contribution": float(group["EV"].fillna(0.0).sum()),
        }

    reverse_slot_probs = getattr(config, "REVERSE_SLOT_PROBABILITIES", {}) or {}
    regular_reverse_event_probability = 0.0
    for slot_config in reverse_slot_probs.values():
        if isinstance(slot_config, dict):
            regular_reverse_event_probability += float(slot_config.get("regular reverse", 0.0) or 0.0)

    reverse_pool = card_groups.get("reverse")
    reverse_mean = 0.0
    reverse_rows = 0
    if reverse_pool is not None and len(reverse_pool) > 0:
        reverse_rows = int(len(reverse_pool))
        reverse_mean = float(reverse_pool.get("Reverse Variant Price ($)", 0).fillna(0.0).mean())

    bucket_stats["regular reverse"] = {
        "calc_event_probability": float(regular_reverse_event_probability),
        "calc_eligible_rows": reverse_rows,
        "calc_avg_eligible_value": reverse_mean,
        "calc_ev_contribution": float(regular_reverse_event_probability * reverse_mean),
    }

    return bucket_stats


def _resolve_bucket_pool_stats(bucket: str, card_groups):
    if bucket == "common":
        pool = card_groups.get("common")
        if pool is None or len(pool) == 0:
            return 0, 0.0
        return int(len(pool)), float(pool.get("Price ($)", 0).fillna(0.0).mean())
    if bucket == "uncommon":
        pool = card_groups.get("uncommon")
        if pool is None or len(pool) == 0:
            return 0, 0.0
        return int(len(pool)), float(pool.get("Price ($)", 0).fillna(0.0).mean())
    if bucket == "rare":
        pool = card_groups.get("rare")
        if pool is None or len(pool) == 0:
            return 0, 0.0
        return int(len(pool)), float(pool.get("Price ($)", 0).fillna(0.0).mean())
    if bucket == "regular reverse":
        pool = card_groups.get("reverse")
        if pool is None or len(pool) == 0:
            return 0, 0.0
        return int(len(pool)), float(pool.get("Reverse Variant Price ($)", 0).fillna(0.0).mean())

    hit_pool = card_groups.get("hit")
    if hit_pool is None:
        return 0, 0.0

    mode = get_simulation_token_mode(bucket)
    eligible, _resolution = resolve_hit_pool_rows(hit_pool, bucket, mode=mode)
    if eligible.empty:
        return 0, 0.0
    return int(len(eligible)), float(eligible.get("Price ($)", 0).fillna(0.0).mean())


def _emit_black_bolt_sim_audit(*, config, df, card_groups, sim_results):
    model = resolve_pack_state_model(config)
    state_probabilities = model.get("state_probabilities", {})

    pack_count = len(sim_results.get("values", []))
    pack_count = pack_count if pack_count > 0 else 1
    rarity_pull_counts = sim_results.get("rarity_pull_counts", {}) or {}
    rarity_value_totals = sim_results.get("rarity_value_totals", {}) or {}

    calc_bucket_stats = _build_black_bolt_calc_bucket_stats(df, config, card_groups)

    tracked_buckets = [
        "common",
        "uncommon",
        "rare",
        "double rare",
        "illustration rare",
        "special illustration rare",
        "ultra rare",
        "black white rare",
        "poke ball pattern",
        "master ball pattern",
        "regular reverse",
    ]

    rarity_audit_rows = []
    for bucket in tracked_buckets:
        calc_stats = calc_bucket_stats.get(bucket, {})
        pool_rows, sim_pool_mean = _resolve_bucket_pool_stats(bucket, card_groups)
        sim_count = int(rarity_pull_counts.get(bucket, 0))
        sim_total = float(rarity_value_totals.get(bucket, 0.0))
        sim_mean = (sim_total / sim_count) if sim_count > 0 else 0.0
        rarity_audit_rows.append(
            {
                "bucket": bucket,
                "calc_event_probability": float(calc_stats.get("calc_event_probability", 0.0)),
                "calc_eligible_rows": int(calc_stats.get("calc_eligible_rows", pool_rows)),
                "calc_avg_eligible_value": float(calc_stats.get("calc_avg_eligible_value", sim_pool_mean)),
                "calc_ev_contribution": float(calc_stats.get("calc_ev_contribution", 0.0)),
                "sim_pool_rows": int(pool_rows),
                "sim_pool_avg_value": float(sim_pool_mean),
                "sim_realized_frequency_per_pack": float(sim_count / pack_count),
                "sim_realized_mean_sampled_value": float(sim_mean),
                "sim_total_sampled_value": float(sim_total),
            }
        )

    state_counts = sim_results.get("pack_state_counts", {}) or {}
    path_counts = sim_results.get("pack_path_counts", {}) or {}
    normal_pack_count = int(path_counts.get("normal", 0))
    normal_denominator = normal_pack_count if normal_pack_count > 0 else 1

    state_rows = []
    for state_name, expected_probability in sorted(state_probabilities.items()):
        realized_count = int(state_counts.get(state_name, 0))
        state_rows.append(
            {
                "state": state_name,
                "expected_probability": float(expected_probability),
                "realized_frequency_given_normal": float(realized_count / normal_denominator),
                "realized_count": realized_count,
            }
        )

    payload = {
        "set_name": getattr(config, "SET_NAME", "<unknown>"),
        "pack_count": pack_count,
        "normal_pack_count": normal_pack_count,
        "mean_pack_value": float(sim_results.get("mean", 0.0)),
        "pack_path_counts": {k: int(v) for k, v in path_counts.items()},
        "rarity_audit": rarity_audit_rows,
        "state_audit": state_rows,
    }

    debug_print(f"[BLACK_BOLT_SIM_AUDIT] {json.dumps(payload, sort_keys=True)}")


class PackEVRSimulator(PackCalculations):
    def __init__(self, config):
        super().__init__(config)

    def calculate_evr_simulations(self, df):
        print("=== STARTING PACK EV SIMULATION ===")
        _t0 = time.perf_counter()
        simulation_engine = get_simulation_engine(self.config)

        if simulation_engine == "slot_schema" and not _is_slot_schema_runtime_enabled(self.config):
            set_name = str(getattr(self.config, "SET_NAME", "<unknown>"))
            raise ValueError(
                "SIMULATION_ENGINE='slot_schema' requires SLOT_SCHEMA_RUNTIME_ENABLED = True on the config. "
                f"Set '{set_name}' has not opted into slot-schema runtime simulation."
            )

        if simulation_engine == "slot_schema":
            _validate_slot_schema_runtime_readiness(self.config)

        card_groups = extract_scarletandviolet_card_groups(self.config, df)
        debug_print(f"[SIM_TIMING] stage_name=pool_extraction elapsed_ms={(time.perf_counter()-_t0)*1000:.1f}")

        if simulation_engine == "slot_schema":
            slot_schema_card_pool = _build_slot_schema_card_pool(self.config, card_groups, df)
            sim_results = simulate_slot_schema_packs(
                self.config,
                slot_schema_card_pool,
                num_packs=1000000,
            )
            return {
                "sim_results": sim_results,
                "slot_logs": [],
            }

        pattern_keys_source, _ = get_row_match_keys(df, mode="pattern")
        source_pattern_mask = pattern_keys_source.isin({"pokeball_pattern", "master_ball_pattern"})

        base_pool_indices = (
            set(card_groups["common"].index.tolist())
            | set(card_groups["uncommon"].index.tolist())
            | set(card_groups["rare"].index.tolist())
        )
        source_pattern_indices = set(df.index[source_pattern_mask].tolist())
        base_pools_pattern_overlap_count = len(base_pool_indices & source_pattern_indices)

        hit_pattern_keys, _ = get_row_match_keys(card_groups["hit"], mode="pattern")
        patterns_in_hit_pool = int(
            hit_pattern_keys.isin({"pokeball_pattern", "master_ball_pattern"}).sum()
        )

        covered_indices = (
            set(card_groups["common"].index.tolist())
            | set(card_groups["uncommon"].index.tolist())
            | set(card_groups["rare"].index.tolist())
            | set(card_groups["hit"].index.tolist())
        )
        source_indices = set(df.index.tolist())
        all_rows_accounted_for = covered_indices == source_indices

        logger.info("[POOL_CROSS_CHECK] Verifying pool composition for simulation...")
        logger.info(
            "[POOL_CROSS_CHECK] base_pools_pattern_overlap_count=%d (expected >=0 with dual semantic membership)",
            base_pools_pattern_overlap_count,
        )
        logger.info("[POOL_CROSS_CHECK] patterns_in_hit_pool=%d_rows", patterns_in_hit_pool)
        logger.info(
            "[POOL_CROSS_CHECK] all_rows_accounted_for=%s (common+uncommon+rare+hit cover source rows)",
            all_rows_accounted_for,
        )

        use_v2 = simulation_engine == "v2"
        debug_print(
            "[SIM_ENGINE] selected_engine=%s configured_use_monte_carlo_v2=%r era=%s"
            % (
                simulation_engine,
                getattr(self.config, "USE_MONTE_CARLO_V2", None),
                getattr(self.config, "ERA", ""),
            )
        )

        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)

        slot_logs = []

        if use_v2:
            _t0 = time.perf_counter()
            debug_print(
                "[SIM_POOL_DEBUG] [SIM_PATH_TRACE] "
                f"set_name={getattr(self.config, 'SET_NAME', '<unknown>')} phase=pre_validate_pack_state_model"
            )
            validate_pack_state_model(self.config, card_groups)
            debug_print(
                "[SIM_POOL_DEBUG] [SIM_PATH_TRACE] "
                f"set_name={getattr(self.config, 'SET_NAME', '<unknown>')} phase=post_validate_pack_state_model"
            )
            debug_print(f"[SIM_TIMING] stage_name=validation elapsed_ms={(time.perf_counter()-_t0)*1000:.1f}")

            # Dedicated counters populated by the closure directly — no record
            # dicts are built for normal runs, so run_simulation_v2 never needs
            # to inspect a return tuple for path/state tracking.
            _path_counts: MutableMapping[str, int] = defaultdict(int)
            _state_counts: MutableMapping[str, int] = defaultdict(int)

            # token_pool_precomputation timing is printed inside make_simulate_pack_fn_v2
            debug_print(
                "[SIM_POOL_DEBUG] [SIM_PATH_TRACE] "
                f"set_name={getattr(self.config, 'SET_NAME', '<unknown>')} phase=pre_make_simulate_pack_fn_v2"
            )
            simulate_one_pack = make_simulate_pack_fn_v2(
                common_cards=card_groups["common"],
                uncommon_cards=card_groups["uncommon"],
                rare_cards=card_groups["rare"],
                hit_cards=card_groups["hit"],
                reverse_pool=card_groups["reverse"],
                slots_per_rarity=self.config.SLOTS_PER_RARITY,
                config=self.config,
                df=df,
                rarity_pull_counts=rarity_pull_counts,
                rarity_value_totals=rarity_value_totals,
                pack_logs=None,
                path_counts=_path_counts,
                state_counts=_state_counts,
            )
            debug_print(
                "[SIM_POOL_DEBUG] [SIM_PATH_TRACE] "
                f"set_name={getattr(self.config, 'SET_NAME', '<unknown>')} phase=post_make_simulate_pack_fn_v2"
            )

            _t0 = time.perf_counter()
            sim_results = run_simulation_v2(
                simulate_one_pack,
                rarity_pull_counts,
                rarity_value_totals,
                n=1000000,
                pack_path_counts=_path_counts,
                pack_state_counts=_state_counts,
            )
            debug_print(f"[SIM_TIMING] stage_name=simulation_loop elapsed_ms={(time.perf_counter()-_t0)*1000:.1f}")

            _t0 = time.perf_counter()
            print_simulation_summary_v2(sim_results)
            debug_print(f"[SIM_TIMING] stage_name=post_simulation_summary elapsed_ms={(time.perf_counter()-_t0)*1000:.1f}")

            if _is_black_bolt_sim_audit_enabled(self.config):
                _emit_black_bolt_sim_audit(
                    config=self.config,
                    df=df,
                    card_groups=card_groups,
                    sim_results=sim_results,
                )

            return {
                "sim_results": sim_results,
                "slot_logs": slot_logs,
            }

        simulate_one_pack = make_simulate_pack_fn(
            common_cards=card_groups["common"],
            uncommon_cards=card_groups["uncommon"],
            rare_cards=card_groups["rare"],
            hit_cards=card_groups["hit"],
            reverse_pool=card_groups["reverse"],
            rare_slot_config=self.config.RARE_SLOT_PROBABILITY,
            reverse_slot_config=self.config.REVERSE_SLOT_PROBABILITIES,
            slots_per_rarity=self.config.SLOTS_PER_RARITY,
            config=self.config,
            df=df,
            rarity_pull_counts=rarity_pull_counts,
            rarity_value_totals=rarity_value_totals,
            log_choices=slot_logs
        )

        sim_results = run_simulation(simulate_one_pack, rarity_pull_counts, rarity_value_totals, n=1000000)

        print_simulation_summary(sim_results)

        validate_and_debug_slot(
            rare_slot_config=self.config.RARE_SLOT_PROBABILITY,
            reverse_slot_config=self.config.REVERSE_SLOT_PROBABILITIES,
            config=self.config,
            n=500000
        )

        validate_full_pack_logic(
            slot_logs,
            simulate_one_pack=simulate_one_pack,
            rare_slot_config=self.config.RARE_SLOT_PROBABILITY,
            reverse_slot_config=self.config.REVERSE_SLOT_PROBABILITIES,
            n=500000
        )

        return {
            "sim_results": sim_results,
            "slot_logs": slot_logs,
        }

    def simulate_pack_ev(self, file_path):
        df, pack_price = self.load_and_prepare_data(file_path)
        simulation_results = self.calculate_evr_simulations(df)
        pack_metrics = self.calculate_pack_metrics(simulation_results["sim_results"], pack_price)
        return simulation_results["sim_results"], pack_metrics


def calculate_pack_simulations(file_path, config):
    """Convenience function to run only the simulation pipeline."""
    simulator = PackEVRSimulator(config)
    return simulator.simulate_pack_ev(file_path)
