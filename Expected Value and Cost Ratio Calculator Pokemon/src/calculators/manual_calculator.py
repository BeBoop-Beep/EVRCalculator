"""
Independent Manual Calculator Module
Calculates EVR and related metrics using purely manual calculations (no simulation)
This module is completely independent from the simulation engine.
"""

import sys
import os
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.calculators.packCalculations.evrCalculator import PackEVCalculator
from src.calculators.packCalculations.otherCalculations import PackCalculations


class ManualCalculator:
    """
    Independent calculator for manual EV calculations.
    Does NOT run simulations - purely mathematical calculations.
    """
    
    def __init__(self, config):
        """
        Initialize the manual calculator
        
        Args:
            config: Set configuration (e.g., SET_CONFIG_MAP['Stellar Crown'])
        """
        self.config = config
        self.calculator = PackCalculations(config)
    
    def calculate(self, df: pd.DataFrame, pack_price: float) -> dict:
        """
        Run all manual calculations on the provided card data
        
        Args:
            df: DataFrame with card data (from DatabaseCardLoader)
            pack_price: Price of a single pack
            
        Returns:
            Dictionary with all manual calculation results:
            {
                'total_ev': float,
                'pack_price': float,
                'net_value': float,
                'roi': float,
                'roi_percent': float,
                'hit_probability_percent': float,
                'no_hit_probability_percent': float,
                'ev_breakdown': dict,  # EV by rarity
                'god_pack_ev': float,
                'demi_god_pack_ev': float,
                'reverse_multiplier': float,
                'rare_multiplier': float,
            }
        """
        print("=== STARTING MANUAL EV CALCULATION ===")
        
        # Calculate reverse EV (dynamically handles all slots)
        ev_reverse_total = self.calculator.calculate_reverse_ev(df)
        print(f"Reverse EV Total: ${ev_reverse_total:.4f}")
        
        # Calculate EV totals by rarity
        ev_totals = self.calculator.calculate_rarity_ev_totals(df, ev_reverse_total)
        
        # Calculate hit probability
        hit_prob, no_hit_prob = self.calculator.calculate_hit_probability(df)
        
        # Calculate total EV with special pack adjustments
        total_manual_ev, regular_pack_contribution, god_pack_ev, demi_god_pack_ev = \
            self.calculator.calculate_total_ev(ev_totals, df)
        
        # Calculate pack metrics
        net_value = total_manual_ev - pack_price
        roi = total_manual_ev / pack_price if pack_price > 0 else 0
        roi_percent = (roi - 1) * 100
        
        print(f"Total Manual EV: ${total_manual_ev:.4f}")
        print(f"Pack Price: ${pack_price:.2f}")
        print(f"Net Value: ${net_value:.4f}")
        print(f"ROI: {roi:.4f}x ({roi_percent:.2f}%)")
        print(f"Hit Probability: {hit_prob:.2f}%")
        
        # Build result dictionary
        results = {
            'total_ev': total_manual_ev,
            'pack_price': pack_price,
            'net_value': net_value,
            'roi': roi,
            'roi_percent': roi_percent,
            'hit_probability_percent': hit_prob,
            'no_hit_probability_percent': no_hit_prob,
            'ev_breakdown': {
                'common': ev_totals.get('common', 0),
                'uncommon': ev_totals.get('uncommon', 0),
                'rare': ev_totals.get('rare', 0),
                'reverse': ev_reverse_total,
                'ace_spec_rare': ev_totals.get('ace_spec_rare', 0),
                'pokeball': ev_totals.get('pokeball', 0),
                'master_ball': ev_totals.get('master_ball', 0),
                'illustration_rare': ev_totals.get('illustration_rare', 0),
                'special_illustration_rare': ev_totals.get('special_illustration_rare', 0),
                'double_rare': ev_totals.get('double_rare', 0),
                'hyper_rare': ev_totals.get('hyper_rare', 0),
                'ultra_rare': ev_totals.get('ultra_rare', 0),
            },
            'god_pack_ev': god_pack_ev,
            'demi_god_pack_ev': demi_god_pack_ev,
            'regular_pack_contribution': regular_pack_contribution,
            'reverse_multiplier': self.calculator.reverse_multiplier,
            'rare_multiplier': self.calculator.rare_multiplier,
        }
        
        print("=== MANUAL EV CALCULATION COMPLETE ===\n")
        return results
