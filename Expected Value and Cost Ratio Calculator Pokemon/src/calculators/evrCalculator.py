import pandas as pd
import numpy as np
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from itertools import combinations_with_replacement
import os

class PackEVCalculator:
    def __init__(self, config):
        self.config = config
        self.PULL_RATE_MAPPING = config.PULL_RATE_MAPPING
        self.pack_multipliers = config.get_rarity_pack_multiplier()
        self.common_multiplier = self.pack_multipliers.get('common', 1)
        self.uncommon_multiplier = self.pack_multipliers.get('uncommon', 1)
        self.rare_multiplier = config.RARE_SLOT_PROBABILITY['rare']
        
        slot1_rr = config.REVERSE_SLOT_PROBABILITIES["slot_1"]["regular_reverse"]
        slot2_rr = config.REVERSE_SLOT_PROBABILITIES["slot_2"]["regular_reverse"]
        self.reverse_multiplier = slot1_rr + slot2_rr
    
    def load_and_prepare_data(self, file_path):
        """Load data from file and prepare it for calculations"""
        # Load data
        try:
            df = pd.read_excel(file_path)
        except FileNotFoundError:
            df = pd.read_csv(file_path)
        
        # Validate required columns
        required_cols = ['Rarity', 'Price ($)', 'Pull Rate (1/X)', 'Pack Price']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Input data must contain a '{col}' column.")
        
        # Clean and process data
        df['Pull Rate (1/X)'] = (
            df['Pull Rate (1/X)']
            .astype(str)
            .str.replace('[$,]', '', regex=True)
            .replace('', pd.NA)
        )
        
        df['rarity_raw'] = df['Rarity'].astype(str).str.lower().str.strip()
        df['rarity_group'] = df['rarity_raw'].map(self.config.RARITY_MAPPING).fillna('other')
        
        # Convert to numeric
        df['Price ($)'] = pd.to_numeric(df['Price ($)'], errors='coerce')
        df['Pull Rate (1/X)'] = pd.to_numeric(df['Pull Rate (1/X)'], errors='coerce')
        df = df.dropna(subset=['Price ($)', 'Pull Rate (1/X)'])
        
        # Remove zero pull rates
        if (df['Pull Rate (1/X)'] == 0).any():
            df = df[df['Pull Rate (1/X)'] != 0]
        
        # Get pack price
        pack_price = pd.to_numeric(df["Pack Price"].iloc[0], errors='coerce')
        
        return df, pack_price
    
    def calculate_base_ev(self, df):
        """Calculate base EV for each card"""
        df['EV'] = df['Price ($)'] / df['Pull Rate (1/X)']
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
        total_reverse_ev = 0
        
        # Dynamically iterate through all reverse slots in config
        for slot_name in self.config.REVERSE_SLOT_PROBABILITIES.keys():
            slot_ev = self.calculate_reverse_ev_for_slot(df, slot_name)
            total_reverse_ev += slot_ev
            print(f"Reverse EV from {slot_name}: {slot_ev:.4f}")
        
        print(f"Total Reverse EV: {total_reverse_ev:.4f}")

        # reverse_price_sum = df['Reverse Variant Price ($)'].sum()
        # eligible_count = len(df)
        # excel_style_reverse_ev = reverse_price_sum * (1.88541666666666 / eligible_count)
        # print("TEST-- eligible_count: ", eligible_count)

        return total_reverse_ev
        
    def calculate_rarity_ev_totals(self, df, ev_reverse_total):
        """Calculate EV totals by rarity group"""
        # Filter out special patterns from rarity calculations
        pattern_mask = df['Card Name'].str.contains('Master Ball|Poke Ball', case=False, na=False)
        
        # Get special cards separately
        master_ball_cards = df[df['Card Name'].str.contains('Master Ball', case=False, na=False)]
        pokeball_cards = df[df['Card Name'].str.contains('Poke Ball', case=False, na=False)]
        
        # Calculate EV totals by rarity - exclude special patterns
        ev_totals = {
            'common': df[(df['Rarity'] == 'common') & ~pattern_mask]['EV'].sum() * self.common_multiplier,
            'uncommon': df[(df['Rarity'] == 'uncommon') & ~pattern_mask]['EV'].sum() * self.uncommon_multiplier,
            'rare': df[(df['Rarity'] == 'rare') & ~pattern_mask]['EV'].sum() * self.rare_multiplier,
            'double_rare': df[(df['Rarity'] == 'double rare') & ~pattern_mask]['EV'].sum(),
            'ace_spec_rare': df[(df['Rarity'] == 'ace spec rare') & ~pattern_mask]['EV'].sum(),
            'hyper_rare': df[(df['Rarity'] == 'hyper rare') & ~pattern_mask]['EV'].sum(),
            'ultra_rare': df[(df['Rarity'] == 'ultra rare') & ~pattern_mask]['EV'].sum(),
            'special_illustration_rare': df[(df['Rarity'] == 'special illustration rare') & ~pattern_mask]['EV'].sum(),
            'illustration_rare': df[(df['Rarity'] == 'illustration rare') & ~pattern_mask]['EV'].sum(),
            'master_ball': master_ball_cards['EV'].sum(),
            'pokeball': pokeball_cards['EV'].sum(),
            'reverse': ev_reverse_total,  # Already calculated correctly across all slots
            'other': df[df['rarity_group'] == 'other']['EV'].sum(),
        }

        print("ev_totals: ", ev_totals)
        print("sum(ev_totals.values()): ", sum(ev_totals.values()))
        
        return ev_totals
    
    def calculate_hit_probability(self, df):
        """Calculate probability of pulling at least one hit card"""
        hit_df = df[df['rarity_group'] == 'hits']
        hit_probs = 1 / hit_df['Pull Rate (1/X)']
        prob_no_hits = (1 - hit_probs).prod()
        no_hit_probability_percentage = prob_no_hits * 100
        hit_probability_percentage = (1 - prob_no_hits) * 100
        
        return hit_probability_percentage, no_hit_probability_percentage
    
    def calculate_total_ev(self, ev_totals):
        return sum(ev_totals.values())

    
    def calculate_pack_metrics(self, total_ev, pack_price):
        """Calculate pack-level metrics"""
        net_value = total_ev - pack_price
        roi = total_ev / pack_price
        roi_percent = (roi - 1) * 100
        
        return {
            'net_value': net_value,
            'roi': roi,
            'roi_percent': roi_percent
        }


    def calculate_variance_and_stddev(self, df):
        """Calculate total variance and standard deviation of EV values"""
        ev_values = df['EV'].dropna().values  # Drop NaNs just in case
        if len(ev_values) == 0:
            return 0.0, 0.0

        average = np.mean(ev_values)   
        variance = np.var(ev_values, ddof=0)  # Population variance
        stddev = np.sqrt(variance)

        return {
        'average': average,
        'variance': variance, 
        'stddev': stddev
        }

    def calculate_weighted_pack_variance(self, df, ev_totals, total_ev):
        """
        Calculate the weighted variance for a pack opening by modeling the actual pack structure.
        This properly handles slot-based probability distributions and replacement mechanics.
        
        Args:
            df: DataFrame with card data
            ev_totals: Dictionary with EV totals by rarity (from calculate_rarity_ev_totals)
            total_ev: The already calculated total expected value from calculate_total_ev()
        """
        
        # Filter out special patterns for standard rarity calculations
        pattern_mask = df['Card Name'].str.contains('Master Ball|Poke Ball', case=False, na=False)
        
        # Get card pools for each rarity
        common_cards = df[(df['Rarity'] == 'common') & ~pattern_mask]
        uncommon_cards = df[(df['Rarity'] == 'uncommon') & ~pattern_mask]
        rare_cards = df[(df['Rarity'] == 'rare') & ~pattern_mask]
        
        # Get hit cards and special cards
        hit_cards = df[df['rarity_group'] == 'hits']
        
        def calculate_guaranteed_slot_variance(cards_df, num_slots, total_cards_in_rarity):
            """
            Calculate variance for guaranteed slots (commons/uncommons) with proper count distribution.
            
            Mathematical model:
            - Each card can appear 0, 1, 2, 3, or 4 times in guaranteed slots
            - Sampling with replacement: each draw has probability 1/total_cards_in_rarity
            - Number of times each card appears ~ Binomial(num_slots, 1/total_cards_in_rarity)
            """
            if cards_df.empty:
                return 0.0
            
            total_variance = 0.0
            
            for _, card in cards_df.iterrows():
                price = card['Price ($)']
                
                # Probability of selecting this specific card in one draw
                p = 1 / total_cards_in_rarity
                
                # For num_slots independent draws with replacement:
                # Variance in count = num_slots * p * (1-p)
                variance_count = num_slots * p * (1 - p)
                
                # Variance in dollar value = price² * variance_in_count
                card_variance = (price ** 2) * variance_count
                total_variance += card_variance
            
            return total_variance
        
        def calculate_rare_slot_variance(rare_cards, hit_cards, rare_slot_config):
            """
            Calculate variance for the rare slot considering hit replacements.
            This models a single multinomial draw from all possible outcomes.
            """
            if rare_cards.empty:
                return 0.0
            
            # Verify config probabilities sum to 1
            config_prob_sum = sum(rare_slot_config.values())
            if not np.isclose(config_prob_sum, 1.0, rtol=1e-6):
                print(f"Warning: Rare slot probabilities sum to {config_prob_sum:.6f}, not 1.0")
            
            # Collect all possible outcomes for the rare slot
            outcomes = []  # List of (probability, value) tuples
            
            # Add regular rare cards (scaled by their slot probability)
            rare_slot_prob = rare_slot_config.get('rare', 0)
            if rare_slot_prob > 0 and not rare_cards.empty:
                num_rares = len(rare_cards)
                for _, card in rare_cards.iterrows():
                    # Each rare has equal probability within the rare category
                    card_prob = rare_slot_prob / num_rares
                    outcomes.append((card_prob, card['Price ($)']))
            
            # Add hit cards that can appear in rare slot
            for rarity, slot_prob in rare_slot_config.items():
                if rarity == 'rare':
                    continue
                    
                hit_subset = hit_cards[hit_cards['Rarity'] == rarity]
                if not hit_subset.empty:
                    num_hits = len(hit_subset)
                    for _, card in hit_subset.iterrows():
                        card_prob = slot_prob / num_hits
                        outcomes.append((card_prob, card['Price ($)']))
            
            if not outcomes:
                return 0.0
            
            # Calculate expected value and variance for this multinomial distribution
            probs = np.array([outcome[0] for outcome in outcomes])
            values = np.array([outcome[1] for outcome in outcomes])
            
            expected_value = (probs * values).sum()
            variance = (probs * (values - expected_value)**2).sum()
            
            return variance
        
        def calculate_reverse_slot_variance(df, reverse_config):
            """
            Calculate variance for reverse slots with proper replacement modeling.
            Each slot is independent, within each slot we have a multinomial draw.
            """
            if 'EV_Reverse' not in df.columns or not reverse_config:
                return 0.0
            
            total_variance = 0.0
            
            for slot_name, slot_outcomes in reverse_config.items():
                # Verify slot probabilities sum to 1
                slot_prob_sum = sum(slot_outcomes.values())
                if not np.isclose(slot_prob_sum, 1.0, rtol=1e-6):
                    print(f"Warning: {slot_name} probabilities sum to {slot_prob_sum:.6f}, not 1.0")
                
                slot_variance = 0.0
                slot_outcomes_list = []
                
                for outcome_type, probability in slot_outcomes.items():
                    if outcome_type == "regular_reverse":
                        # Regular reverse cards
                        reverse_cards = df[df['EV_Reverse'] > 0]
                        if not reverse_cards.empty:
                            num_reverse = len(reverse_cards)
                            for _, card in reverse_cards.iterrows():
                                card_prob = probability / num_reverse
                                reverse_price = card['Reverse Variant Price ($)'] if 'Reverse Variant Price ($)' in card else card['Price ($)']
                                slot_outcomes_list.append((card_prob, reverse_price))
                    
                    elif outcome_type in ["illustration_rare", "special_illustration_rare", "ace_spec", "pokeball_pattern", "masterball_pattern"]:
                        # Special cards that can appear in reverse slot
                        # Map outcome types to actual rarity names in your data
                        rarity_mapping = {
                            "illustration_rare": "illustration rare",
                            "special_illustration_rare": "special illustration rare", 
                            "ace_spec": "ace spec",
                            "pokeball_pattern": "poke ball pattern",
                            "masterball_pattern": "master ball pattern"
                        }
                        
                        mapped_rarity = rarity_mapping.get(outcome_type, outcome_type.replace('_', ' '))
                        special_cards = df[df['Rarity'] == mapped_rarity]
                        
                        if not special_cards.empty:
                            num_special = len(special_cards)
                            for _, card in special_cards.iterrows():
                                card_prob = probability / num_special
                                slot_outcomes_list.append((card_prob, card['Price ($)']))
                
                # Calculate variance for this slot
                if slot_outcomes_list:
                    probs = np.array([outcome[0] for outcome in slot_outcomes_list])
                    values = np.array([outcome[1] for outcome in slot_outcomes_list])
                    
                    expected_value = (probs * values).sum()
                    slot_variance = (probs * (values - expected_value)**2).sum()
                
                total_variance += slot_variance
            
            return total_variance
        
        # Calculate variance for each component using corrected methods
        
        # 1. Guaranteed slots (commons and uncommons) - CORRECTED
        common_variance = calculate_guaranteed_slot_variance(
            common_cards, 
            self.common_multiplier,
            self.PULL_RATE_MAPPING.get('common', 46)  # Use config value, default 46
        )
        uncommon_variance = calculate_guaranteed_slot_variance(
            uncommon_cards, 
            self.uncommon_multiplier,
            self.PULL_RATE_MAPPING.get('uncommon', 33)  # Use config value, default 33
        )
        
        # 2. Rare slot with hit replacements - ALREADY CORRECT
        rare_variance = calculate_rare_slot_variance(
            rare_cards, 
            hit_cards, 
            getattr(self, 'RARE_SLOT_PROBABILITY', {})
        )
        
        # 3. Reverse slots with special replacements - ALREADY CORRECT
        reverse_variance = calculate_reverse_slot_variance(
            df, 
            getattr(self, 'REVERSE_SLOT_PROBABILITIES', {})
        )
        
        # 4. No independent hit cards - all hits are handled by rare/reverse slots
        hit_variance = 0.0
        
        # 5. No independent special pattern cards - all are handled by reverse slots
        special_variance = 0.0
        
        # 6. Total pack variance (sum of independent components)
        total_variance = (
            common_variance + 
            uncommon_variance + 
            rare_variance + 
            reverse_variance + 
            hit_variance + 
            special_variance
        )
        
        total_stddev = np.sqrt(total_variance)
        expected_value = total_ev
        
        print(f"Debug: Pack variance breakdown:")
        print(f"  Common variance ({self.common_multiplier} slots): {common_variance:.3f}")
        print(f"  Uncommon variance ({self.uncommon_multiplier} slots): {uncommon_variance:.3f}")
        print(f"  Rare slot variance: {rare_variance:.3f}")
        print(f"  Reverse slots variance: {reverse_variance:.3f}")
        print(f"  Independent hits variance: {hit_variance:.3f} (all hits in rare/reverse slots)")
        print(f"  Special cards variance: {special_variance:.3f} (all in reverse slots)")
        print(f"  Total variance: {total_variance:.3f}")
        print(f"  Standard deviation: {total_stddev:.3f}")
        print(f"  Expected value check: {expected_value:.3f}")
        
        # Verify configuration probabilities (optional debugging)
        if hasattr(self, 'RARE_SLOT_PROBABILITY'):
            rare_prob_sum = sum(self.RARE_SLOT_PROBABILITY.values())
            if not np.isclose(rare_prob_sum, 1.0, rtol=1e-6):
                print(f"Configuration Check: Rare slot probabilities sum to {rare_prob_sum:.6f}")
        
        if hasattr(self, 'REVERSE_SLOT_PROBABILITIES'):
            for slot_name, slot_config in self.REVERSE_SLOT_PROBABILITIES.items():
                slot_sum = sum(slot_config.values())
                if not np.isclose(slot_sum, 1.0, rtol=1e-6):
                    print(f"Configuration Check: {slot_name} probabilities sum to {slot_sum:.6f}")
        
        return {
            'weighted_variance': total_variance,
            'weighted_stddev': total_stddev,
            'expected_value_check': expected_value,
            'variance_breakdown': {
                'common': common_variance,
                'uncommon': uncommon_variance,
                'rare': rare_variance,
                'reverse': reverse_variance,
                'hits': hit_variance,
                'special': special_variance
            },
            # Keep the same key name for compatibility
            'variance_components': {
                'common': common_variance,
                'uncommon': uncommon_variance,
                'rare': rare_variance,
                'reverse': reverse_variance,
                'hits': hit_variance,
                'special': special_variance
            }
        }
    
    def calculate_pack_ev(self, file_path):
        """Main calculation method that orchestrates all calculations"""
        # Load and prepare data
        df, pack_price = self.load_and_prepare_data(file_path)
        
        # Calculate base EV
        df = self.calculate_base_ev(df)
        
        # Calculate reverse EV (now dynamically handles all slots)
        ev_reverse_total = self.calculate_reverse_ev(df)
        
        # Calculate EV totals by rarity
        ev_totals = self.calculate_rarity_ev_totals(df, ev_reverse_total)
        
        # Calculate hit probability
        hit_probability_percentage, no_hit_probability_percentage = self.calculate_hit_probability(df)
        
        # Calculate total EV
        total_ev = self.calculate_total_ev(ev_totals)
        
        # Calculate pack metrics
        pack_metrics = self.calculate_pack_metrics(total_ev, pack_price)

        # Calculate weighted pack variance using existing calculations
        weighted_pack_metrics = self.calculate_weighted_pack_variance(df, ev_totals, total_ev)

        # Calculate variance and stddev
        card_metrics = self.calculate_variance_and_stddev(df)
        
        # Compile results
        results = {
            "total_ev": total_ev,
            "net_value": pack_metrics['net_value'],
            "roi": pack_metrics['roi'],
            "hit_probability_percentage": hit_probability_percentage,
            "average": card_metrics['average'],
            "variance": card_metrics['variance'],
            "stddev": card_metrics['stddev'],
            "weighted_pack_variance": weighted_pack_metrics['weighted_variance'],
            "weighted_pack_stddev": weighted_pack_metrics['weighted_stddev'],
            "expected_value_check" : weighted_pack_metrics['expected_value_check'],
            "variance_breakdown" : weighted_pack_metrics['variance_breakdown'],
        }
        
        summary_data = {
            "ev_common_total": ev_totals['common'],  # Already multiplied in ev_totals
            "ev_uncommon_total": ev_totals['uncommon'],  # Already multiplied in ev_totals
            "ev_rare_total": ev_totals['rare'],  # Already multiplied in ev_totals
            "ev_reverse_total": ev_reverse_total,  # FIXED: Don't multiply again
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
            "total_ev": total_ev,
            "net_value": pack_metrics['net_value'],
            "roi": pack_metrics['roi'],
            "roi_percent": pack_metrics['roi_percent'],
            "no_hit_probability_percentage": no_hit_probability_percentage,
            "hit_probability_percentage": hit_probability_percentage,
            "variance_breakdown": weighted_pack_metrics['variance_components'],
        }
        print("results: ", results)
        print("summary_data: ", summary_data)
        return results, summary_data, total_ev

# Convenience function to maintain backward compatibility
def calculate_pack_ev(file_path, config):
    """Backward compatible function that uses the new class structure"""
    calculator = PackEVCalculator(config)
    return calculator.calculate_pack_ev(file_path)