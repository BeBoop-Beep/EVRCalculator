import pandas as pd
import numpy as np
import os

from itertools import combinations_with_replacement
from .initializeCalculations import PackEVInitializer


class PackEVCalculator(PackEVInitializer):
    """Main EV calculation methods"""

    def __init__(self, config):
        super().__init__(config)

    def calculate_god_packs_ev_contributions(self, df):
        return {
            "god_pack_ev": PackEVCalculator._calculate_god_packs_ev_contributions(self.config.GOD_PACK_CONFIG, df, self.config),
            "demi_god_pack_ev": PackEVCalculator._calculate_god_packs_ev_contributions(self.config.DEMI_GOD_PACK_CONFIG, df, self.config),
        }

    @staticmethod
    def _calculate_god_packs_ev_contributions(strategy_config, df, config):
        if not strategy_config.get("enabled", False):
            return 0.0

        pull_rate = strategy_config.get("pull_rate", 0)
        strategy = strategy_config.get("strategy", {})
        strategy_type = strategy.get("type")

        if strategy_type == "fixed":
            cards = strategy.get("cards", [])
            total = df[df["Card Name"].isin(cards)]["Price ($)"].sum()
            return pull_rate * total

        elif strategy_type == "random":
            rules = strategy.get("rules", {})
            count = rules.get("count", 1)
            rarities = rules.get("rarities", [])

            # Grab rarity-to-slot counts from the config
            rarity_multipliers = config.get_rarity_pack_multiplier()
            common_count = rarity_multipliers.get('common', 0)
            uncommon_count = rarity_multipliers.get('uncommon', 0)

            # Compute averages
            avg_common = df[df["Rarity"] == "common"]["Price ($)"].mean()
            avg_uncommon = df[df["Rarity"] == "uncommon"]["Price ($)"].mean()
            avg_high_rarity = df[df["Rarity"].isin(rarities)]["Price ($)"].mean()

            # Expected value of this specific configuration of a demi-god pack
            pack_value = (common_count * avg_common) + (uncommon_count * avg_uncommon) + (count * avg_high_rarity)
            adjusted_ev = pull_rate * pack_value

            print("=== DEMI-GOD PACK LOGIC ===")
            print(f"Common avg: {avg_common:.4f}, Uncommon avg: {avg_uncommon:.4f}, High rarity avg: {avg_high_rarity:.4f}")
            print(f"Pack layout: common({common_count}), uncommon({uncommon_count}), high rarity({count})")
            print(f"Pack value before scaling: {pack_value:.4f}")
            print(f"Pull rate: {pull_rate}, Final EV: {adjusted_ev:.4f}")

            return adjusted_ev

        return 0.0
    
    def calculate_effective_pull_rate(self, rarity_group, base_pull_rate, card_name=None):
        """
        Calculate the true effective pull rate for each card type following the model's methodology.
        Dynamically determines calculation method based on configuration data.
        """
        
        # Special pattern cards (always use exact rates)
        if card_name and ('master ball' in card_name.lower() or 'poke ball' in card_name.lower()):
            return base_pull_rate
        
        # Determine calculation type and execute appropriate method
        calculation_type = self._determine_calculation_type(rarity_group)
        
        # Strategy pattern using dictionary dispatch
        calculation_strategies = {
            'exact': self._calculate_exact_rate,
            'guaranteed_slot': self._calculate_guaranteed_slot_rate,
            'probability_based': self._calculate_probability_based_rate
        }
        
        # Execute strategy or fallback to default
        strategy = calculation_strategies.get(calculation_type, self._calculate_default_rate)
        return strategy(rarity_group, base_pull_rate)

    def _determine_calculation_type(self, rarity_group):
        """
        Dynamically determine the calculation type based on configuration data.
        
        Returns:
            'exact': Use pull rate as-is (default for most cards)
            'guaranteed_slot': Cards with guaranteed slots (common/uncommon)
            'probability_based': Only for 'rare' rarity group cards
        """
        # Check if it's a guaranteed slot type
        if rarity_group in ['common', 'uncommon']:
            return 'guaranteed_slot'
        
        # Only 'rare' rarity group uses probability-based calculation
        if rarity_group == 'rare':
            return 'probability_based'
        
        # Everything else uses exact calculation 
        return 'exact'

    def _calculate_exact_rate(self, rarity_group, base_pull_rate):
        """Calculate exact rate (no modification needed)"""
        return base_pull_rate

    def _calculate_guaranteed_slot_rate(self, rarity_group, base_pull_rate):
        """Calculate effective rate for cards with guaranteed slots (common/uncommon)"""
        if rarity_group == 'common':
            individual_rate = base_pull_rate  # Already 1/total_commons
            slot_multiplier = getattr(self, 'common_multiplier', 4)  # Default 4 common slots
            effective_rate = individual_rate / slot_multiplier
            return effective_rate
        
        elif rarity_group == 'uncommon':
            individual_rate = base_pull_rate  # Already 1/total_uncommons
            slot_multiplier = getattr(self, 'uncommon_multiplier', 3)  # Default 3 uncommon slots
            effective_rate = individual_rate / slot_multiplier
            return effective_rate
        
        # Shouldn't reach here given our logic, but safety fallback
        print(f"Unexpected rarity '{rarity_group}' in guaranteed slot calculation - using base rate")
        return base_pull_rate

    def _calculate_default_rate(self, rarity_group, base_pull_rate):
        """Default fallback calculation"""
        print(f"Unknown rarity group '{rarity_group}' - using base rate: {base_pull_rate}")
        return base_pull_rate

    def _calculate_probability_based_rate(self, rarity_group, base_pull_rate):
        """Calculate effective rate for cards that appear in probability-based slots"""
        
        # Check rare slot first
        rare_slot_prob = getattr(self.config, 'RARE_SLOT_PROBABILITY', {}).get(rarity_group)
        if rare_slot_prob:
            # Regular rare slot calculation
            type_probability = rare_slot_prob
            individual_probability = 1 / base_pull_rate
            effective_probability = type_probability * individual_probability
            effective_rate = 1 / effective_probability
            return effective_rate
    
        return base_pull_rate

    def calculate_base_ev(self, df):
        """Calculate EV using corrected pull rates following the model's methodology"""
        print("\n=== CALCULATING BASE EV WITH EFFECTIVE PULL RATES ===")
        
        # Calculate effective pull rates for each card
        df['Effective_Pull_Rate'] = df.apply(
            lambda row: self.calculate_effective_pull_rate(
                row['rarity_group'], 
                row['Pull Rate (1/X)'],
                row.get('Card Name', '')
            ), 
            axis=1
        )
        
        # Calculate EV using effective pull rates
        df['EV'] = df['Price ($)'] / df['Effective_Pull_Rate']
        print(f"Total cards processed: {len(df)}")
                
        return df
    
    def calculate_reverse_ev_for_slot(self, df, slot_name):
        """Calculate reverse EV contribution from a single reverse slot"""
        ev_slot_total = 0
        
        if 'Reverse Variant Price ($)' not in df.columns:
            return ev_slot_total
        
        # Get slot configuration
        if slot_name not in self.config.REVERSE_SLOT_PROBABILITIES:
            return ev_slot_total
        
        slot_config = self.config.REVERSE_SLOT_PROBABILITIES[slot_name]
        regular_reverse_prob = slot_config.get("regular_reverse", 0)
        
        if regular_reverse_prob == 0:
            return ev_slot_total
        
        # Cards eligible for regular reverse treatment (exclude special cards)
        is_eligible_for_reverse = ~df['Rarity'].isin(['Illustration Rare', 'Special Illustration Rare'])
        
        # Also exclude special pattern cards from reverse calculation
        pattern_mask = df['Card Name'].str.contains('Master Ball|Poke Ball', case=False, na=False)
        is_eligible_for_reverse = is_eligible_for_reverse & ~pattern_mask
        
        eligible_df = df[is_eligible_for_reverse & df['Reverse Variant Price ($)'].notna()].copy()
        
        if not eligible_df.empty:
            total_eligible_cards = len(eligible_df)
            
            # Each card's probability of appearing as reverse in this slot
            individual_prob_this_slot = regular_reverse_prob / total_eligible_cards
            
            # Calculate EV contribution from this slot
            slot_ev_contribution = (
                eligible_df['Reverse Variant Price ($)'].fillna(0) * individual_prob_this_slot
            ).sum()
            
            ev_slot_total = slot_ev_contribution
        
        return ev_slot_total

    def calculate_reverse_ev(self, df):
        """Calculate total EV for reverse holo variants across all reverse slots"""
        print("\n=== CALCULATING REVERSE EV ===")
        total_reverse_ev = 0
        
        # Dynamically iterate through all reverse slots in config
        for slot_name in self.config.REVERSE_SLOT_PROBABILITIES.keys():
            slot_ev = self.calculate_reverse_ev_for_slot(df, slot_name)
            total_reverse_ev += slot_ev
            print(f"Reverse EV from {slot_name}: {slot_ev:.4f}")
        
        print(f"Total Reverse EV: {total_reverse_ev:.4f}")
        return total_reverse_ev
        
    def calculate_rarity_ev_totals(self, df, ev_reverse_total):
        """Calculate EV totals by rarity group - NO ADDITIONAL MULTIPLIERS NEEDED"""
        print("\n=== CALCULATING RARITY EV TOTALS ===")
        
        # Filter out special patterns from rarity calculations
        pattern_mask = df['Card Name'].str.contains('Master Ball|Poke Ball', case=False, na=False)
        
        # Get special cards separately
        master_ball_cards = df[df['Card Name'].str.contains('Master Ball', case=False, na=False)]
        pokeball_cards = df[df['Card Name'].str.contains('Poke Ball', case=False, na=False)]
        
        # Calculate EV totals by rarity - NO MULTIPLIERS because they're already in effective rates
        ev_totals = {
            'common': df[(df['Rarity'] == 'common') & ~pattern_mask]['EV'].sum(),  # REMOVED MULTIPLIER
            'uncommon': df[(df['Rarity'] == 'uncommon') & ~pattern_mask]['EV'].sum(),  # REMOVED MULTIPLIER
            'rare': df[(df['Rarity'] == 'rare') & ~pattern_mask]['EV'].sum(),
            'double_rare': df[(df['Rarity'] == 'double rare') & ~pattern_mask]['EV'].sum(),
            'ace_spec_rare': df[(df['Rarity'] == 'ace spec rare') & ~pattern_mask]['EV'].sum(),
            'hyper_rare': df[(df['Rarity'] == 'hyper rare') & ~pattern_mask]['EV'].sum(),
            'ultra_rare': df[(df['Rarity'] == 'ultra rare') & ~pattern_mask]['EV'].sum(),
            'special_illustration_rare': df[(df['Rarity'] == 'special illustration rare') & ~pattern_mask]['EV'].sum(),
            'illustration_rare': df[(df['Rarity'] == 'illustration rare') & ~pattern_mask]['EV'].sum(),
            'master_ball': master_ball_cards['EV'].sum(),
            'pokeball': pokeball_cards['EV'].sum(),
            'reverse': ev_reverse_total,
            'other': df[df['rarity_group'] == 'other']['EV'].sum(),
        }

        print("EV totals by rarity:")
        for rarity, total in ev_totals.items():
            if total > 0:
                print(f"  {rarity}: {total:.4f}")
        print(f"Sum of all EV totals: {sum(ev_totals.values()):.4f}")
        
        return ev_totals
    
   
    def calculate_total_ev(self, ev_totals, df):
        regular_pack_ev = sum(ev_totals.values())

        special_pack_metrics = self.calculate_god_packs_ev_contributions(df)
        god_pack_ev, demi_god_pack_ev = special_pack_metrics.values()

        total_ev = regular_pack_ev + god_pack_ev + demi_god_pack_ev

        print(f"\nFINAL EV BREAKDOWN:")
        print(f"  Regular pack EV contribution: ${regular_pack_ev:.6f}")
        print(f"  God pack EV contribution: ${god_pack_ev:.6f}")
        print(f"  Demi-god pack EV contribution: ${demi_god_pack_ev:.6f}")
        print(f"  TOTAL EV: ${total_ev:.2f}\n")

        return total_ev, regular_pack_ev, god_pack_ev, demi_god_pack_ev

    