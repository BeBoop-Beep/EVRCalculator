from .otherCalculations import PackCalculations

class PackCalculationOrchestrator(PackCalculations):
    def __init__(self, config):
        super().__init__(config)

    def calculate_evr_calculations(self, df):
        # Calculate reverse EV (now dynamically handles all slots)
        ev_reverse_total = self.calculate_reverse_ev(df)

        # Calculate EV totals by rarity
        ev_totals = self.calculate_rarity_ev_totals(df, ev_reverse_total)

        # Calculate hit probability
        hit_probability_percentage, no_hit_probability_percentage = self.calculate_hit_probability(df)

        # Calculate total EV with special pack adjustments
        total_manual_ev, regular_pack_contribution, god_pack_ev_contribution, demi_god_pack_ev_contribution = self.calculate_total_ev(ev_totals, df)

        summary_data_for_manual_calcs = {
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
            "regular_pack_ev_contribution": regular_pack_contribution,
            "god_pack_ev_contribution": god_pack_ev_contribution,
            "demi_god_pack_ev_contribution": demi_god_pack_ev_contribution,
            "total_manual_ev": total_manual_ev,
        }

        return {
            "ev_reverse_total": ev_reverse_total,
            "ev_totals": ev_totals,
            "hit_probability_percentage": hit_probability_percentage,
            "no_hit_probability_percentage": no_hit_probability_percentage,
            "total_manual_ev": total_manual_ev,
            "regular_pack_contribution": regular_pack_contribution,
            "god_pack_ev_contribution": god_pack_ev_contribution,
            "demi_god_pack_ev_contribution": demi_god_pack_ev_contribution,
            "summary_data_for_manual_calcs": summary_data_for_manual_calcs,
        }

    def calculate_pack_ev(self, file_path):
        """Main calculation method that orchestrates all calculations"""
        print("=== ⭐STARTING REFRACTORED PACK EV CALCULATION⭐ ===")
        
        # Load and prepare data
        df, pack_price = self.load_and_prepare_data(file_path)
        print(f"Loaded {len(df)} cards from data file")
        
        manual_results = self.calculate_evr_calculations(df)
        
        # # Calculate weighted pack variance using existing calculations
        # weighted_pack_metrics = self.calculate_weighted_pack_variance(df, ev_totals, total_manual_ev)
        
        # # Calculate variance and stddev
        # card_metrics = self.calculate_variance_and_stddev(df)

        # Assuming df is your DataFrame with card data
        top_10_hits = df.sort_values(by="Price ($)", ascending=False)[["Card Name", "Price ($)", "Effective_Pull_Rate"]].head(10)
        print(top_10_hits)

        # Compile results
        results = {
            "total_manual_ev": manual_results["total_manual_ev"],
            "pack_price": pack_price,
            "hit_probability_percentage": manual_results["hit_probability_percentage"],
            "no_hit_probability_percentage": manual_results["no_hit_probability_percentage"],
            # Special pack metrics
        
        }
        
        summary_data_for_manual_calcs = manual_results["summary_data_for_manual_calcs"]
        
        print("=== PACK EV CALCULATION COMPLETE ===")
        return results, summary_data_for_manual_calcs, top_10_hits, pack_price