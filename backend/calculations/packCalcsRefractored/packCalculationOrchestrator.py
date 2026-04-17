import pandas as pd

from .otherCalculations import PackCalculations
from ..utils.rarity_classification import filter_card_ev_by_hits

class PackCalculationOrchestrator(PackCalculations):
    def __init__(self, config):
        super().__init__(config)

    @staticmethod
    def build_card_ev_contributions(df: pd.DataFrame) -> dict:
        """Build card-level EV contribution map from the existing EV pipeline output.

        This uses the already-computed per-card EV values and does not invent
        new contribution logic. Duplicate card names are summed.
        
        Note: This returns ALL cards (both hit and non-hit). Use
        build_hit_and_non_hit_ev_contributions() to split by rarity mapping.
        """
        required_columns = {"Card Name", "EV"}
        if not required_columns.issubset(df.columns):
            return {}

        ev_series = pd.to_numeric(df["EV"], errors="coerce").fillna(0.0)
        working = pd.DataFrame(
            {
                "Card Name": df["Card Name"].astype(str).str.strip(),
                "EV": ev_series,
            }
        )
        grouped = working.groupby("Card Name", as_index=True)["EV"].sum()
        return {
            str(card_name): float(ev_value)
            for card_name, ev_value in grouped.items()
            if float(ev_value) > 0.0
        }

    def build_hit_and_non_hit_ev_contributions(self, df: pd.DataFrame) -> dict:
        """Build hit-only and non-hit-only EV contribution pools using config rarity mapping.
        
        Classifies cards based on whether their rarity maps to 'hits' according
        to the active era's base-config RARITY_MAPPING. This is the source of
        truth, not a hardcoded rarity allowlist.
        
        Returns
        -------
        dict with keys:
            'hit_ev_contributions': {card_name: ev_value} for hit rarities only
            'non_hit_ev_contributions': {card_name: ev_value} for non-hit rarities
            'hit_ev': float, sum of hit EV contributions
            'non_hit_ev': float, sum of non-hit EV contributions
            'total_card_ev': float, sum of all card contributions
        
        Notes
        -----
        - Cards with EV <= 0 are excluded from both pools.
        - Cards not found in dataframe are conservatively classified as non-hit.
        - 'total_card_ev' includes both hit and non-hit, but may differ from
          total simulated pack EV due to special pack adjustments.
        """
        all_contributions = self.build_card_ev_contributions(df)
        
        if not all_contributions:
            return {
                'hit_ev_contributions': {},
                'non_hit_ev_contributions': {},
                'hit_ev': 0.0,
                'non_hit_ev': 0.0,
                'total_card_ev': 0.0,
            }
        
        hit_contribs, non_hit_contribs = filter_card_ev_by_hits(
            all_contributions, df, self.config
        )
        
        hit_ev = sum(float(v) for v in hit_contribs.values())
        non_hit_ev = sum(float(v) for v in non_hit_contribs.values())
        total_card_ev = hit_ev + non_hit_ev
        
        return {
            'hit_ev_contributions': hit_contribs,
            'non_hit_ev_contributions': non_hit_contribs,
            'hit_ev': float(hit_ev),
            'non_hit_ev': float(non_hit_ev),
            'total_card_ev': float(total_card_ev),
        }

    def calculate_evr_calculations(self, df):
        # Calculate reverse EV (now dynamically handles all slots)
        ev_reverse_total = self.calculate_reverse_ev(df)

        # Calculate EV totals by rarity
        ev_totals = self.calculate_rarity_ev_totals(df, ev_reverse_total)

        # Calculate hit probability
        hit_probability_percentage, no_hit_probability_percentage = self.calculate_hit_probability(df)

        # Calculate total EV with special pack adjustments
        total_manual_ev, regular_pack_contribution, god_pack_ev_contribution, demi_god_pack_ev_contribution = self.calculate_total_ev(ev_totals, df)
        
        # Build card EV contributions split into hit/non-hit pools
        card_ev_split = self.build_hit_and_non_hit_ev_contributions(df)

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
            "total_manual_ev": total_manual_ev,
        }

        return {
            "ev_reverse_total": ev_reverse_total,
            "ev_totals": ev_totals,
            "card_ev_contributions": card_ev_split['hit_ev_contributions'],  # For backwards compat, use hit pool
            "hit_ev_contributions": card_ev_split['hit_ev_contributions'],
            "non_hit_ev_contributions": card_ev_split['non_hit_ev_contributions'],
            "hit_ev": card_ev_split['hit_ev'],
            "non_hit_ev": card_ev_split['non_hit_ev'],
            "total_card_ev": card_ev_split['total_card_ev'],
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
        print("=== ❗STARTING PACK EV CALCULATION❗ ===")
        
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
            "card_ev_contributions": manual_results["card_ev_contributions"],  # Hit pool only (backwards compat)
            "hit_ev_contributions": manual_results["hit_ev_contributions"],
            "non_hit_ev_contributions": manual_results["non_hit_ev_contributions"],
            "hit_ev": manual_results["hit_ev"],
            "non_hit_ev": manual_results["non_hit_ev"],
            "total_card_ev": manual_results["total_card_ev"],
            "hit_probability_percentage": manual_results["hit_probability_percentage"],
            "no_hit_probability_percentage": manual_results["no_hit_probability_percentage"],
        }
        
        summary_data_for_manual_calcs = manual_results["summary_data_for_manual_calcs"]
        
        print("=== PACK EV CALCULATION COMPLETE ===")
        return results, summary_data_for_manual_calcs, top_10_hits, pack_price