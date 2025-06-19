import pandas as pd
import numpy as np
import os

from itertools import combinations_with_replacement
from .initializeCalculations import PackEVInitializer


class PackEVCalculator(PackEVInitializer):
    """Main EV calculation methods"""

    def __init__(self, config):
        super().__init__(config)

    def calculate_god_pack_ev(self, df):
        """Calculate EV contribution from God Packs - FIXED FOR CONFIG MAPPING"""
        print("\n=== CALCULATING GOD PACK EV ADJUSTMENTS ===")
        
        # God pack configuration - pull from PULL_RATE_MAPPING
        god_pack_rate = self.config.PULL_RATE_MAPPING.get('god pack')
        demi_god_pack_rate = self.config.PULL_RATE_MAPPING.get('demi god pack')
        
        # Only calculate if god pack and demi god pack rates exist in config
        if god_pack_rate is None and demi_god_pack_rate is None:
            print("No god pack or demi god pack rates found in config - skipping calculation")
            return {
                'god_pack_ev': 0,
                'demi_god_pack_ev': 0,
                'total_special_pack_ev': 0,
                'god_pack_probability': 0,
                'demi_god_pack_probability': 0,
                'god_pack_value': 0,
                'demi_god_pack_value': 0
            }
        
        P_god_pack = 1 / god_pack_rate if god_pack_rate else 0
        P_demi_god_pack = 1 / demi_god_pack_rate if demi_god_pack_rate else 0
        
        if god_pack_rate:
            print(f"God pack probability: 1/{god_pack_rate}")
        if demi_god_pack_rate:
            print(f"Demi-god pack probability: 1/{demi_god_pack_rate:.2f}")
        
        # Find SIR cards using the cleaned rarity_raw column
        sir_cards = df[df['rarity_raw'] == 'special illustration rare']
        if not sir_cards.empty:
            average_sir_value = sir_cards['Price ($)'].mean()
            print(f"Found {len(sir_cards)} SIR cards")
            print(f"Average SIR value: ${average_sir_value:.2f}")
        else:
            average_sir_value = 0
            print("No SIR cards found for god pack calculation")
            print(f"Available rarity_raw values: {df['rarity_raw'].unique()}")
        
        # Calculate average reverse value
        reverse_eligible = df[~df['Rarity'].isin(['Illustration Rare', 'Special Illustration Rare'])]
        if 'Reverse Variant Price ($)' in df.columns:
            avg_reverse_value = reverse_eligible['Reverse Variant Price ($)'].fillna(0).mean()
            print(f"Average reverse value: ${avg_reverse_value:.2f}")
        else:
            avg_reverse_value = 0
            print("No reverse variant prices found")
        
        # God pack EV calculation
        if god_pack_rate:
            god_pack_value = (9 * average_sir_value) + avg_reverse_value
            ev_god_pack = P_god_pack * god_pack_value
            print(f"God pack value: 9 × ${average_sir_value:.2f} + ${avg_reverse_value:.2f} = ${god_pack_value:.2f}")
            print(f"God pack EV contribution: {P_god_pack:.8f} × ${god_pack_value:.2f} = ${ev_god_pack:.6f}")
        else:
            god_pack_value = 0
            ev_god_pack = 0
            print("God pack rate not configured - skipping god pack calculation")
        
        # Demi-god pack EV calculation
        if demi_god_pack_rate:
            high_value_cards = df[df['Price ($)'] > df['Price ($)'].quantile(0.9)]
            if not high_value_cards.empty:
                avg_high_value = high_value_cards['Price ($)'].mean()
                demi_god_pack_value = 4 * avg_high_value
                ev_demi_god_pack = P_demi_god_pack * demi_god_pack_value
                print(f"Demi-god pack estimated value: 4 × ${avg_high_value:.2f} = ${demi_god_pack_value:.2f}")
                print(f"Demi-god pack EV contribution: {P_demi_god_pack:.8f} × ${demi_god_pack_value:.2f} = ${ev_demi_god_pack:.6f}")
            else:
                ev_demi_god_pack = 0
                demi_god_pack_value = 0
                print("No high-value cards found for demi-god pack calculation")
        else:
            ev_demi_god_pack = 0
            demi_god_pack_value = 0
            print("Demi-god pack rate not configured - skipping demi-god pack calculation")
        
        total_special_pack_ev = ev_god_pack + ev_demi_god_pack
        print(f"Total special pack EV: ${total_special_pack_ev:.6f}")
        
        return {
            'god_pack_ev': ev_god_pack,
            'demi_god_pack_ev': ev_demi_god_pack,
            'total_special_pack_ev': total_special_pack_ev,
            'god_pack_probability': P_god_pack,
            'demi_god_pack_probability': P_demi_god_pack,
            'god_pack_value': god_pack_value,
            'demi_god_pack_value': demi_god_pack_value
    }
    
    def calculate_effective_pull_rate(self, rarity_group, base_pull_rate, card_name=None):
        """
        Calculate the true effective pull rate for each card type following the model's methodology
        """
        print(f"\n--- Calculating effective pull rate for {rarity_group} ---")
        print(f"Base pull rate: {base_pull_rate}")
        
        # Cards with exact pull rates (use as-is) - One-Step Calculation
        exact_rate_rarities = [
            'double_rare', 'ultra_rare', 'hyper_rare', 'special_illustration_rare',
            'illustration_rare', 'ace_spec_rare'
        ]
        
        # Special pattern cards (also exact rates)
        if card_name and ('master ball' in card_name.lower() or 'poke ball' in card_name.lower()):
            print(f"Special pattern card - using exact rate: {base_pull_rate}")
            return base_pull_rate
        
        if rarity_group in exact_rate_rarities:
            print(f"Exact rate rarity - using base rate: {base_pull_rate}")
            return base_pull_rate
        
        # Guaranteed slot cards - Two-Step Calculation
        elif rarity_group == 'common':
            # P_common_card = (1 / total_commons_in_set) × number_of_common_slots
            individual_rate = base_pull_rate  # This is already 1/total_commons
            slot_multiplier = self.common_multiplier  # Number of common slots
            effective_rate = individual_rate / slot_multiplier
            print(f"Common card: individual_rate={individual_rate}, slot_multiplier={slot_multiplier}")
            print(f"Effective rate: {individual_rate} / {slot_multiplier} = {effective_rate}")
            return effective_rate
        
        elif rarity_group == 'uncommon':
            # P_uncommon_card = (1 / total_uncommons_in_set) × number_of_uncommon_slots
            individual_rate = base_pull_rate  # This is already 1/total_uncommons
            slot_multiplier = self.uncommon_multiplier  # Number of uncommon slots
            effective_rate = individual_rate / slot_multiplier
            print(f"Uncommon card: individual_rate={individual_rate}, slot_multiplier={slot_multiplier}")
            print(f"Effective rate: {individual_rate} / {slot_multiplier} = {effective_rate}")
            return effective_rate
        
        # Regular rares (rare slot only) - Two-Step Calculation
        elif rarity_group == 'rare':
            # P_specific_regular_rare = P_regular_rare_type × (1/number_of_rare_cards)
            type_probability = self.rare_multiplier  # P_regular_rare_type (already calculated)
            individual_probability = 1 / base_pull_rate  # 1/number_of_rare_cards
            effective_probability = type_probability * individual_probability
            effective_rate = 1 / effective_probability
            print(f"Regular rare: type_prob={type_probability}, individual_prob={individual_probability}")
            print(f"Effective probability: {type_probability} × {individual_probability} = {effective_probability}")
            print(f"Effective rate: 1 / {effective_probability} = {effective_rate}")
            return effective_rate
        
        # Regular reverses (both reverse slots) - Two-Step Calculation
        elif rarity_group == 'regular_reverse':
            # P_specific_card_total = Σ(P_type_per_slot_i × (1/number_of_cards_in_type))
            total_type_probability = self.reverse_multiplier  # Sum of both slot probabilities
            individual_probability = 1 / base_pull_rate  # 1/number_of_reverse_cards
            effective_probability = total_type_probability * individual_probability
            effective_rate = 1 / effective_probability
            print(f"Regular reverse: total_type_prob={total_type_probability}, individual_prob={individual_probability}")
            print(f"Effective probability: {total_type_probability} × {individual_probability} = {effective_probability}")
            print(f"Effective rate: 1 / {effective_probability} = {effective_rate}")
            return effective_rate
        
        # Fallback for other rarities
        else:
            print(f"Unknown rarity group '{rarity_group}' - using base rate: {base_pull_rate}")
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
        
        print(f"\n=== BASE EV CALCULATION COMPLETE ===")
        print(f"Total cards processed: {len(df)}")
        print(f"Total base EV: {df['EV'].sum():.4f}")
        
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
    
   
    
    
    def adjust_regular_pack_probabilities(self, regular_pack_ev, special_pack_metrics):
        """Adjust regular pack EV based on special pack probabilities"""
        print("\n=== ADJUSTING REGULAR PACK PROBABILITIES ===")
        
        # Calculate probability of getting a regular pack
        P_god_pack = special_pack_metrics['god_pack_probability']
        P_demi_god_pack = special_pack_metrics['demi_god_pack_probability']
        P_regular_pack = 1 - P_god_pack - P_demi_god_pack
        
        print(f"Regular pack probability: 1 - {P_god_pack:.8f} - {P_demi_god_pack:.8f} = {P_regular_pack:.8f}")
        
        # Adjust regular pack EV
        adjusted_regular_ev = P_regular_pack * regular_pack_ev
        print(f"Adjusted regular pack EV: {P_regular_pack:.8f} × ${regular_pack_ev:.4f} = ${adjusted_regular_ev:.6f}")
        
        return {
            'regular_pack_probability': P_regular_pack,
            'adjusted_regular_ev': adjusted_regular_ev,
            'original_regular_ev': regular_pack_ev
        }
    
    def calculate_total_ev(self, ev_totals, df):
        """Calculate total EV from all sources including special pack adjustments"""
        print(f"\n=== TOTAL EV CALCULATION WITH SPECIAL PACKS ===")
        
        # Calculate base regular pack EV
        regular_pack_ev = sum(ev_totals.values())
        print(f"Regular pack EV (before adjustments): ${regular_pack_ev:.4f}")
        
        # Calculate special pack contributions
        special_pack_metrics = self.calculate_god_pack_ev(df)
        
        # Adjust regular pack probabilities
        regular_pack_adjustments = self.adjust_regular_pack_probabilities(
            regular_pack_ev, special_pack_metrics
        )
        
        # Calculate final total EV
        total_ev = (
            regular_pack_adjustments['adjusted_regular_ev'] + 
            special_pack_metrics['total_special_pack_ev']
        )
        
        print(f"\nFINAL EV BREAKDOWN:")
        print(f"  Adjusted regular pack EV: ${regular_pack_adjustments['adjusted_regular_ev']:.6f}")
        print(f"  God pack EV contribution: ${special_pack_metrics['god_pack_ev']:.6f}")
        print(f"  Demi-god pack EV contribution: ${special_pack_metrics['demi_god_pack_ev']:.6f}")
        print(f"  TOTAL EV: ${total_ev:.4f}")
        
        return total_ev, special_pack_metrics, regular_pack_adjustments
    