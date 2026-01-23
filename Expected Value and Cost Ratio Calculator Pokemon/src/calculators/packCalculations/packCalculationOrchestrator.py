import os
from collections import defaultdict

from .monteCarloSim import make_simulate_pack_fn, print_simulation_summary, run_simulation
from .otherCalculations import PackCalculations
from src.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups
from ...validations.monteCarloValidations import validate_and_debug_slot, validate_full_pack_logic

class PackCalculationOrchestrator(PackCalculations):
    def __init__(self, config):
        super().__init__(config)
        self._cached_df = None
        self._cached_pack_price = None
    
    def calculate_manual_ev(self, file_path):
        """
        Calculate manual EV using mathematical formulas.
        Returns: (results, summary_data, total_manual_ev, top_10_hits, df, pack_price)
        """
        print("=== STARTING MANUAL EV CALCULATION ===")
        
        # Load and prepare data
        df, pack_price = self.load_and_prepare_data(file_path)
        print(f"Loaded {len(df)} cards from data file")
        
        # Cache for potential simulation use
        self._cached_df = df
        self._cached_pack_price = pack_price
        
        # Calculate reverse EV (now dynamically handles all slots)
        ev_reverse_total = self.calculate_reverse_ev(df)
        
        # Calculate EV totals by rarity
        ev_totals = self.calculate_rarity_ev_totals(df, ev_reverse_total)
        
        # Calculate hit probability
        hit_probability_percentage, no_hit_probability_percentage = self.calculate_hit_probability(df)
        
        # Calculate total EV with special pack adjustments
        total_manual_ev, regular_pack_contribution, god_pack_ev_contribution, demi_god_pack_ev_contribution = self.calculate_total_ev(ev_totals, df)
        
        # Get top 10 hits
        top_10_hits = df.sort_values(by="Price ($)", ascending=False)[["Card Name", "Price ($)", "Effective_Pull_Rate"]].head(10)
        print(top_10_hits)
        
        # Compile summary data
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
            "regular_pack_ev_contribution": regular_pack_contribution,
            "god_pack_ev_contribution": god_pack_ev_contribution,
            "demi_god_pack_ev_contribution": demi_god_pack_ev_contribution,
            "total_manual_ev": total_manual_ev,
        }
        
        print("=== MANUAL EV CALCULATION COMPLETE ===")
        print(f"Final Total Manual EV: {total_manual_ev:.4f}\n")
        return summary_data, total_manual_ev, top_10_hits, df, pack_price
    
    def run_monte_carlo_simulation(self, df=None, pack_price=None, n=100000, run_validations=True):
        """
        Run Monte Carlo simulation for pack opening.
        Can use cached data from calculate_manual_ev() or accept explicit df and pack_price.
        Returns: (sim_results, pack_metrics)
        """
        print("=== STARTING MONTE CARLO SIMULATION ===")
        
        # Use provided data or cached data
        if df is None:
            df = self._cached_df
        if pack_price is None:
            pack_price = self._cached_pack_price
            
        if df is None or pack_price is None:
            raise ValueError("DataFrame and pack_price must be provided or calculated via calculate_manual_ev() first")
        
        # Extract card groups for simulation
        card_groups = extract_scarletandviolet_card_groups(self.config, df)
        
        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)
        slot_logs = []
        
        # Create simulation function
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
        
        # Run simulation
        sim_results = run_simulation(simulate_one_pack, rarity_pull_counts, rarity_value_totals, n=n)
        
        print_simulation_summary(sim_results)
        
        # Run validation checks if requested
        if run_validations:
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
        
        print("=== MONTE CARLO SIMULATION COMPLETE ===\n")
        return sim_results, pack_metrics
    
    def calculate_pack_ev(self, file_path):
        """
        Legacy method that maintains backward compatibility by orchestrating both calculation and simulation.
        Calls calculate_manual_ev() and run_monte_carlo_simulation() sequentially.
        """
        print("=== STARTING FULL PACK EV CALCULATION ===\n")
        
        # Step 1: Calculate manual EV
        summary_data, total_manual_ev, top_10_hits, df, pack_price = self.calculate_manual_ev(file_path)
        
        # Step 2: Run simulation
        sim_results, pack_metrics = self.run_monte_carlo_simulation(df, pack_price)
        
        # Compile results for backward compatibility
        results = {
            "total_manual_ev": total_manual_ev,
            "acutal_simulated_ev": pack_metrics['total_ev'],
            "pack_price": pack_price,
            "hit_probability_percentage": summary_data.get("hit_probability_percentage", 0),
            "no_hit_probability_percentage": summary_data.get("no_hit_probability_percentage", 0),
            "net_value": pack_metrics['net_value'],
            "opening_pack_roi": pack_metrics['opening_pack_roi'],
            "opening_pack_roi_percent": pack_metrics['opening_pack_roi_percent'],
        }
        
        print("=== FULL PACK EV CALCULATION COMPLETE ===")
        return results, summary_data, pack_metrics['total_ev'], sim_results, top_10_hits