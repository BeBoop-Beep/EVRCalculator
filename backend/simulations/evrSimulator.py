from collections import defaultdict
import json
import logging
import os
import time
from typing import MutableMapping

from .monteCarloSim import make_simulate_pack_fn, print_simulation_summary, run_simulation
from .monteCarloSimV2 import (
    make_simulate_pack_fn_v2,
    print_simulation_summary_v2,
    run_simulation_v2,
    validate_pack_state_model,
)
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


def _should_use_monte_carlo_v2(config) -> bool:
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
        card_groups = extract_scarletandviolet_card_groups(self.config, df)
        debug_print(f"[SIM_TIMING] stage_name=pool_extraction elapsed_ms={(time.perf_counter()-_t0)*1000:.1f}")

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

        use_v2 = _should_use_monte_carlo_v2(self.config)
        debug_print(
            "[SIM_ENGINE] selected_engine=%s configured_use_monte_carlo_v2=%r era=%s"
            % (
                "v2" if use_v2 else "v1",
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
