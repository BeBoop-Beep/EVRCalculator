import pandas as pd
import numpy as np
import os

from .evrCalculator import PackEVCalculator
from backend.calculations.utils.rarity_classification import normalize_rarity_key, normalize_rarity_string
from backend.calculations.utils.reverse_pool import (
    build_reverse_eligible_pool,
    get_normalized_base_rarity_key_series,
    get_normalized_classification_key_series,
    get_regular_reverse_probability,
    normalize_reverse_classification_key,
)
from backend.calculations.utils.special_type_normalization import RECOGNIZED_PATTERN_BUCKETS

class PackCalculations(PackEVCalculator):
    """Complete pack EV calculator with all metrics"""
    def __init__(self, config):
        super().__init__(config)

    def calculate_pack_metrics(self, sim_results, pack_price):
        """Calculate pack-level metrics"""
        total_ev = sim_results['mean']
        net_value = total_ev - pack_price
        roi = total_ev / pack_price
        roi_percent = (roi - 1) * 100

        print('\nExpected Value Per Pack: ', total_ev)
        print('Cost Per Pack: ', pack_price)
        print("Net Value Upon Opening: ", net_value)
        print("ROI Upon Opening: ", roi)
        print(f"ROI Percent Upon Opening: {roi_percent:.2f}\n")
        return {
            'total_ev': total_ev,
            'net_value': net_value,
            'opening_pack_roi': roi,
            'opening_pack_roi_percent': roi_percent
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
        
        rarity_source = df['rarity_raw'] if 'rarity_raw' in df.columns else df['Rarity']
        rarity_normalized = rarity_source.astype(str).str.strip().str.lower()
        rarity_keys = get_normalized_base_rarity_key_series(df)
        classification_keys = get_normalized_classification_key_series(df)
        rarity_groups = (
            df['rarity_group']
            if 'rarity_group' in df.columns
            else rarity_normalized.map(self.config.RARITY_MAPPING)
        )
        variance_df = df.assign(
            _rarity_normalized=rarity_normalized,
            _rarity_key=rarity_keys,
            _classification_key=classification_keys,
            _rarity_group=rarity_groups,
        )

        def filter_cards_by_rarity_semantics(cards_df, rarity_value):
            classification_key = normalize_reverse_classification_key(rarity_value)
            rarity_key = normalize_rarity_key(rarity_value)
            accepted_classification_keys = {classification_key}
            accepted_rarity_keys = {rarity_key}

            if classification_key in {'ace_spec', 'ace_spec_rare'} or rarity_key in {'ace_spec', 'ace_spec_rare'}:
                accepted_classification_keys.update({'ace_spec', 'ace_spec_rare'})
                accepted_rarity_keys.update({'ace_spec', 'ace_spec_rare'})

            if classification_key in RECOGNIZED_PATTERN_BUCKETS:
                return cards_df[cards_df['_classification_key'].isin(accepted_classification_keys)]

            return cards_df[
                cards_df['_classification_key'].isin(accepted_classification_keys)
                | cards_df['_rarity_key'].isin(accepted_rarity_keys)
            ]

        def get_rarity_mask(cards_df, rarity_value):
            rarity_key = normalize_rarity_key(rarity_value)
            accepted_keys = {rarity_key}

            if rarity_key == 'ace_spec':
                accepted_keys.add('ace_spec_rare')

            return (
                cards_df['_rarity_key'].isin(accepted_keys)
                & ~cards_df['_classification_key'].isin(RECOGNIZED_PATTERN_BUCKETS)
            )

        def is_supported_reverse_special_outcome(outcome_type):
            outcome_key = normalize_reverse_classification_key(outcome_type)
            supported_outcome_keys = {
                'illustration_rare',
                'special_illustration_rare',
                'ace_spec',
                'ace_spec_rare',
                'pokeball_pattern',
                'master_ball_pattern',
            }
            return outcome_key in supported_outcome_keys

        # Get card pools for each rarity using prepared rarity semantics.
        common_cards = variance_df[get_rarity_mask(variance_df, 'common')]
        uncommon_cards = variance_df[get_rarity_mask(variance_df, 'uncommon')]
        rare_cards = variance_df[get_rarity_mask(variance_df, 'rare')]
        
        # Get hit cards and special cards
        hit_cards = variance_df[variance_df['_rarity_group'] == 'hits']
    
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
                    
                hit_subset = filter_cards_by_rarity_semantics(hit_cards, rarity)

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
            if not reverse_config:
                return 0.0

            reverse_cards = build_reverse_eligible_pool(self.config, variance_df)
            
            total_variance = 0.0
            
            for slot_name, slot_outcomes in reverse_config.items():
                regular_reverse_probability = get_regular_reverse_probability(slot_name, slot_outcomes)
                
                slot_variance = 0.0
                slot_outcomes_list = []
                
                for outcome_type, probability in slot_outcomes.items():
                    if outcome_type == "regular reverse":
                        if regular_reverse_probability > 0 and reverse_cards.empty:
                            raise ValueError(
                                f"Reverse slot '{slot_name}' has regular reverse probability {regular_reverse_probability} "
                                "but the eligible reverse pool is empty."
                            )
                        if not reverse_cards.empty:
                            num_reverse = len(reverse_cards)
                            for _, card in reverse_cards.iterrows():
                                card_prob = probability / num_reverse
                                slot_outcomes_list.append((card_prob, card['Reverse Variant Price ($)']))
                    
                    # Keep reverse-slot specials explicitly enumerated to preserve pack math.
                    elif is_supported_reverse_special_outcome(outcome_type):
                        special_cards = filter_cards_by_rarity_semantics(variance_df, outcome_type)
                        
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
        
        print(f"Rare cards count: {len(rare_cards)}")
        # 2. Rare slot with hit replacements - ALREADY CORRECT
        rare_variance = calculate_rare_slot_variance(
            rare_cards, 
            hit_cards, 
            getattr(self.config, 'RARE_SLOT_PROBABILITY', {})
        )
        reverse_cards = build_reverse_eligible_pool(self.config, variance_df)
        print(f"Reverse cards count: {len(reverse_cards)}")

        # 3. Reverse slots with special replacements - ALREADY CORRECT
        reverse_variance = calculate_reverse_slot_variance(
            df, 
            getattr(self.config, 'REVERSE_SLOT_PROBABILITIES', {})
        )
        print(f"Hit cards count: {len(hit_cards)}")
        
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
    
    def calculate_hit_probability(self, df):
        """Calculate probability of pulling at least one hit card"""
        hit_df = df[df['rarity_group'] == 'hits']
        
        if hit_df.empty:
            return 0.0, 100.0
        
        # Use effective pull rates for hit probability calculation
        hit_probs = 1 / hit_df['Effective_Pull_Rate']
        prob_no_hits = (1 - hit_probs).prod()
        no_hit_probability_percentage = prob_no_hits * 100
        hit_probability_percentage = (1 - prob_no_hits) * 100
        
        return hit_probability_percentage, no_hit_probability_percentage
    