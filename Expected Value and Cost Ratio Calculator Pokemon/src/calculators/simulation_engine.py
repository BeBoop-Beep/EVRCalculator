"""
Independent Simulation Engine Module
Runs Monte Carlo pack simulations completely independently from manual calculations.
This module receives card data and produces simulation results without dependencies.
"""

import sys
import os
import pandas as pd
from collections import defaultdict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.calculators.packCalculations.monteCarloSim import make_simulate_pack_fn, run_simulation, print_simulation_summary
from src.calculators.packCalculations.otherCalculations import PackCalculations
from src.utils.card_grouping import group_cards_by_rarity


class SimulationEngine:
    """
    Independent Monte Carlo simulation engine.
    Takes card data and config, produces simulation statistics.
    Does NOT depend on manual calculations.
    """
    
    def __init__(self, config):
        """
        Initialize the simulation engine
        
        Args:
            config: Set configuration (e.g., SET_CONFIG_MAP['Stellar Crown'])
        """
        self.config = config
        self.calculator = PackCalculations(config)
    
    def run_simulation(self, df: pd.DataFrame, pack_price: float, reverse_df: pd.DataFrame = None, num_simulations: int = 100000) -> dict:
        """
        Run Monte Carlo pack simulation
        
        Args:
            df: DataFrame with card data (from DatabaseCardLoader)
            pack_price: Price of a single pack
            reverse_df: DataFrame with reverse-holo variant cards (optional)
            num_simulations: Number of pack simulations to run (default 100000)
            
        Returns:
            Dictionary with simulation results:
            {
                'simulated_ev': float,
                'net_value': float,
                'roi': float,
                'roi_percent': float,
                'mean': float,
                'std_dev': float,
                'min': float,
                'max': float,
                'percentiles': dict,  # 5th, 25th, 50th, 75th, 90th, 95th, 99th
                'distribution': array,  # All individual simulation results
                'rarity_pull_counts': dict,  # Count of pulls by rarity
                'rarity_value_totals': dict,  # Total value pulled by rarity
                'top_hits': DataFrame,  # Top 10 most valuable cards pulled
            }
        """
        print(f"=== STARTING MONTE CARLO SIMULATION ({num_simulations:,} packs) ===")
        
        # Prepare DataFrame: calculate EV columns based on config
        df = self._prepare_dataframe_for_simulation(df)
        
        # Prepare reverse DataFrame if provided
        if reverse_df is not None and not reverse_df.empty:
            reverse_df = self._prepare_dataframe_for_simulation(reverse_df)
        else:
            reverse_df = pd.DataFrame()
        
        # Extract card groups from data
        card_groups = group_cards_by_rarity(self.config, df, reverse_df)
        
        # Initialize tracking dictionaries
        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)
        slot_logs = []
        
        # Create the pack simulation function
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
        
        # Run the simulation
        sim_results = run_simulation(
            simulate_one_pack,
            rarity_pull_counts,
            rarity_value_totals,
            n=num_simulations
        )
        
        # Print summary
        print_simulation_summary(sim_results)
        
        # Get top 10 cards by price
        top_10_hits = df.sort_values(by="Price ($)", ascending=False)[
            ["Card Name", "Price ($)", "Effective_Pull_Rate"]
        ].head(10)
        
        # Calculate pack metrics
        simulated_ev = sim_results['mean']
        net_value = simulated_ev - pack_price
        roi = simulated_ev / pack_price if pack_price > 0 else 0
        roi_percent = (roi - 1) * 100
        
        print(f"Simulated EV Per Pack: ${simulated_ev:.4f}")
        print(f"Pack Price: ${pack_price:.2f}")
        print(f"Net Value: ${net_value:.4f}")
        print(f"ROI: {roi:.4f}x ({roi_percent:.2f}%)\n")
        
        # Build results dictionary
        results = {
            'simulated_ev': simulated_ev,
            'net_value': net_value,
            'roi': roi,
            'roi_percent': roi_percent,
            'mean': sim_results['mean'],
            'std_dev': sim_results['std_dev'],
            'min': sim_results['min'],
            'max': sim_results['max'],
            'percentiles': sim_results['percentiles'],
            'distribution': sim_results['distribution'],
            'rarity_pull_counts': dict(rarity_pull_counts),
            'rarity_value_totals': dict(rarity_value_totals),
            'top_hits': top_10_hits,
        }
        
        print("=== SIMULATION COMPLETE ===\n")
        return results    
    def _prepare_dataframe_for_simulation(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare DataFrame using the initializer's exact EV column calculation
        This preserves the original calculation logic exactly
        
        Args:
            df: DataFrame with card data
            
        Returns:
            DataFrame with EV columns calculated using original logic
        """
        # Make a copy to avoid modifying original
        df = df.copy()
        
        # Use the initializer's _calculate_ev_columns method which has the exact logic
        self.calculator._calculate_ev_columns(df)
        
        return df