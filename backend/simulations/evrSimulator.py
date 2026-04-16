from collections import defaultdict

from .monteCarloSim import make_simulate_pack_fn, print_simulation_summary, run_simulation
from .monteCarloSimV2 import (
    make_simulate_pack_fn_v2,
    print_simulation_summary_v2,
    run_simulation_v2,
    validate_pack_state_model,
)
from backend.calculations.packCalcsRefractored.otherCalculations import PackCalculations
from .utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups
from .validations.monteCarloValidations import validate_and_debug_slot, validate_full_pack_logic


class PackEVRSimulator(PackCalculations):
    def __init__(self, config):
        super().__init__(config)

    def calculate_evr_simulations(self, df):
        print("=== ❗STARTING PACK EV SIMULATION❗ ===")
        card_groups = extract_scarletandviolet_card_groups(self.config, df)
        use_v2 = bool(getattr(self.config, "USE_MONTE_CARLO_V2", False))

        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)

        slot_logs = []

        if use_v2:
            validate_pack_state_model(self.config, card_groups)
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
                pack_logs=slot_logs,
            )

            sim_results = run_simulation_v2(
                lambda: simulate_one_pack(return_pack_data=True),
                rarity_pull_counts,
                rarity_value_totals,
                n=100000,
            )
            print_simulation_summary_v2(sim_results)

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

        sim_results = run_simulation(simulate_one_pack, rarity_pull_counts, rarity_value_totals, n=100000)

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
