import os
from collections import defaultdict

from .monteCarloSim import make_simulate_pack_fn, print_simulation_summary, run_simulation
from .otherCalculations import PackCalculations
from src.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups
from ...validations.monteCarloValidations import validate_and_debug_slot, validate_full_pack_logic

class PackCalculationOrchestrator(PackCalculations):
    def __init__(self, config):
        super().__init__(config)
        
    def calculate_pack_ev(self, file_path):
        """Main calculation method that orchestrates all calculations"""
        print("=== STARTING PACK EV CALCULATION ===")
        
        # Load and prepare data
        df, pack_price = self.load_and_prepare_data(file_path)
        print(f"Loaded {len(df)} cards from data file")
        
        # Calculate reverse EV (now dynamically handles all slots)
        ev_reverse_total = self.calculate_reverse_ev(df)
        
        # Calculate EV totals by rarity
        ev_totals = self.calculate_rarity_ev_totals(df, ev_reverse_total)
        
        # Calculate hit probability
        hit_probability_percentage, no_hit_probability_percentage = self.calculate_hit_probability(df)
        
        # Calculate total EV with special pack adjustments
        total_manual_ev, regular_pack_contribution, god_pack_ev_contribution, demi_god_pack_ev_contribution = self.calculate_total_ev(ev_totals, df)
        
        # # Calculate weighted pack variance using existing calculations
        # weighted_pack_metrics = self.calculate_weighted_pack_variance(df, ev_totals, total_manual_ev)
        
        # # Calculate variance and stddev
        # card_metrics = self.calculate_variance_and_stddev(df)

        card_groups = extract_scarletandviolet_card_groups(self.config, df)

        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)    

        slot_logs = []

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
        # Calculate pack metrics
        pack_metrics = self.calculate_pack_metrics(sim_results, pack_price)
        
        print(df.sort_values(by="Price ($)", ascending=False)[["Card Name", "Price ($)", "Effective_Pull_Rate"]].head(10))


        # Compile results
        results = {
            "total_manual_ev": total_manual_ev,
            # "net_value": pack_metrics['net_value'],
            # "opening_pack_roi": pack_metrics['opening_pack_roi'],
            "hit_probability_percentage": hit_probability_percentage,
            # Special pack metrics
            "regular_pack_ev_contribution": regular_pack_contribution,
            "god_pack_ev_contribution": god_pack_ev_contribution,
            "demi_god_pack_ev_contribution": demi_god_pack_ev_contribution,
        }
        
        summary_data = {
            "ev_common_total": ev_totals['common'],
            "ev_uncommon_total": ev_totals['uncommon'],
            "ev_rare_total": ev_totals['rare'],
            "ev_reverse_total": ev_reverse_total,
            "ev_ace_spec_total": ev_totals['ace_spec_rare'],
            "ev_pokeball_total": ev_totals['pokeball'],
            "ev_master_ball_total": ev_totals['master_ball'],
            "ev_IR_total": ev_totals['illustration_rare'],
            "ev_SIR_total": ev_totals['special_illustration_rare'],
            "ev_double_rare_total": ev_totals['double_rare'],
            "ev_hyper_rare_total": ev_totals['hyper_rare'],
            "ev_ultra_rare_total": ev_totals['ultra_rare'],
            "reverse_multiplier": self.reverse_multiplier,
            "rare_multiplier": self.rare_multiplier,
            "total_manual_ev": total_manual_ev,
            "regular_pack_ev_contribution": regular_pack_contribution,
            "god_pack_ev_contribution": god_pack_ev_contribution,
            "demi_god_pack_ev_contribution": demi_god_pack_ev_contribution,
            "net_value": pack_metrics['net_value'],
            "opening_pack_roi": pack_metrics['opening_pack_roi'],
            "opening_pack_roi_percent": pack_metrics['opening_pack_roi_percent'],
            "no_hit_probability_percentage": no_hit_probability_percentage,
            "hit_probability_percentage": hit_probability_percentage,
        }
        
        print("=== PACK EV CALCULATION COMPLETE ===")
        print(f"Final Total EV: {pack_metrics['total_ev']:.4f}")
        return results, summary_data, pack_metrics['total_ev']