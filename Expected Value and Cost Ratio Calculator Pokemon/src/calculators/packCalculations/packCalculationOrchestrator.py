import os
from .otherCalculations import PackCalculations

class PackCalculationOrchestrator(PackCalculations):
    def __init__(self, config):
        super().__init__(config)
        
    def calculate_pack_ev(self, file_path):
        """Main calculation method that orchestrates all calculations"""
        print("=== STARTING PACK EV CALCULATION ===")
        
        # Load and prepare data
        df, pack_price = self.load_and_prepare_data(file_path)
        print(f"Loaded {len(df)} cards from data file")
        
        # Calculate base EV using the new methodology
        df = self.calculate_base_ev(df)
        
        # Calculate reverse EV (now dynamically handles all slots)
        ev_reverse_total = self.calculate_reverse_ev(df)
        
        # Calculate EV totals by rarity
        ev_totals = self.calculate_rarity_ev_totals(df, ev_reverse_total)
        
        # Calculate hit probability
        hit_probability_percentage, no_hit_probability_percentage = self.calculate_hit_probability(df)
        
        # Calculate total EV with special pack adjustments
        total_ev, special_pack_metrics, regular_pack_adjustments = self.calculate_total_ev(ev_totals, df)
        
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
            "expected_value_check": weighted_pack_metrics['expected_value_check'],
            "variance_breakdown": weighted_pack_metrics['variance_breakdown'],
            # Special pack metrics
            "god_pack_ev": special_pack_metrics['god_pack_ev'],
            "demi_god_pack_ev": special_pack_metrics['demi_god_pack_ev'],
            "regular_pack_probability": regular_pack_adjustments['regular_pack_probability'],
            "adjusted_regular_ev": regular_pack_adjustments['adjusted_regular_ev'],
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
            "total_ev": total_ev,
            "net_value": pack_metrics['net_value'],
            "roi": pack_metrics['roi'],
            "roi_percent": pack_metrics['roi_percent'],
            "no_hit_probability_percentage": no_hit_probability_percentage,
            "hit_probability_percentage": hit_probability_percentage,
            "variance_breakdown": weighted_pack_metrics['variance_components'],
            # Special pack data
            "god_pack_ev": special_pack_metrics['god_pack_ev'],
            "demi_god_pack_ev": special_pack_metrics['demi_god_pack_ev'],
            "god_pack_probability": special_pack_metrics['god_pack_probability'],
            "demi_god_pack_probability": special_pack_metrics['demi_god_pack_probability'],
            "regular_pack_probability": regular_pack_adjustments['regular_pack_probability'],
            "original_regular_ev": regular_pack_adjustments['original_regular_ev'],
            "adjusted_regular_ev": regular_pack_adjustments['adjusted_regular_ev'],
        }
        
        print("=== PACK EV CALCULATION COMPLETE ===")
        print(f"Final Total EV: {total_ev:.4f}")
        return results, summary_data, total_ev