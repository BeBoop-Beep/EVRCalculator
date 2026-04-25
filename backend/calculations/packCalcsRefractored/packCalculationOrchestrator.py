import pandas as pd
from typing import Optional

from .otherCalculations import PackCalculations
from ..utils.rarity_classification import filter_card_ev_by_hits

class PackCalculationOrchestrator(PackCalculations):
    def __init__(self, config):
        super().__init__(config)

    _PATTERN_TOTAL_KEYS = {
        "pokeball_pattern": ("pokeball_pattern", "poke_ball_pattern", "pokeball"),
        "master_ball_pattern": ("master_ball_pattern", "master_ball"),
    }

    @staticmethod
    def _get_ev_total(ev_totals_by_rarity: dict, *rarity_keys: str) -> float:
        for rarity_key in rarity_keys:
            if rarity_key in ev_totals_by_rarity:
                return float(ev_totals_by_rarity.get(rarity_key, 0.0))
        return 0.0

    @staticmethod
    def _derive_total_manual_ev(
        ev_totals_by_rarity: dict,
        god_pack_ev_contribution: float,
        demi_god_pack_ev_contribution: float,
    ) -> float:
        regular_pack_total = sum(float(total) for total in ev_totals_by_rarity.values())
        return float(regular_pack_total + god_pack_ev_contribution + demi_god_pack_ev_contribution)

    def _build_manual_summary_data(
        self,
        ev_totals_by_rarity: dict,
        regular_pack_contribution: float,
        god_pack_ev_contribution: float,
        demi_god_pack_ev_contribution: float,
        total_manual_ev: Optional[float] = None,
    ) -> dict:
        derived_total_manual_ev = self._derive_total_manual_ev(
            ev_totals_by_rarity,
            god_pack_ev_contribution,
            demi_god_pack_ev_contribution,
        )

        return {
            "ev_totals_by_rarity": ev_totals_by_rarity,
            "ev_common_total": self._get_ev_total(ev_totals_by_rarity, 'common'),
            "ev_uncommon_total": self._get_ev_total(ev_totals_by_rarity, 'uncommon'),
            "ev_rare_total": self._get_ev_total(ev_totals_by_rarity, 'rare'),
            "ev_reverse_total": self._get_ev_total(ev_totals_by_rarity, 'reverse'),
            "ev_ace_spec_total": self._get_ev_total(ev_totals_by_rarity, 'ace_spec_rare'),
            "ev_pokeball_total": self._get_ev_total(
                ev_totals_by_rarity,
                *self._PATTERN_TOTAL_KEYS["pokeball_pattern"],
            ),
            "ev_master_ball_total": self._get_ev_total(
                ev_totals_by_rarity,
                *self._PATTERN_TOTAL_KEYS["master_ball_pattern"],
            ),
            "ev_IR_total": self._get_ev_total(ev_totals_by_rarity, 'illustration_rare'),
            "ev_SIR_total": self._get_ev_total(ev_totals_by_rarity, 'special_illustration_rare'),
            "ev_double_rare_total": self._get_ev_total(ev_totals_by_rarity, 'double_rare'),
            "ev_hyper_rare_total": self._get_ev_total(ev_totals_by_rarity, 'hyper_rare'),
            "ev_ultra_rare_total": self._get_ev_total(ev_totals_by_rarity, 'ultra_rare'),
            "reverse_multiplier": self.reverse_multiplier,
            "rare_multiplier": self.rare_multiplier,
            "regular_pack_ev_contribution": regular_pack_contribution,
            "god_pack_ev_contribution": god_pack_ev_contribution,
            "demi_god_pack_ev_contribution": demi_god_pack_ev_contribution,
            "total_manual_ev": derived_total_manual_ev,
        }

    @staticmethod
    def build_card_ev_contributions(df: pd.DataFrame) -> tuple:
        """Build card-level EV contribution map from the existing EV pipeline output.

        Identity key is card_number when the 'Card Number' column is present and
        non-empty, otherwise falls back to card name (legacy/Excel-input path).
        Card name is NEVER the primary identity key when card_number is available.

        Note: Card names are NOT the same as card identity. Multiple distinct cards
        can share a name within a set (e.g., two printings of 'Charizard ex' at
        different rarities). Using card_number as the key prevents these from being
        incorrectly collapsed into a single EV bucket.

        Parameters
        ----------
        df : pd.DataFrame
            Must have columns: {"Card Name", "EV"}.
            May optionally have: {"Card Number", "Rarity"}.

        Returns
        -------
        tuple
            (ev_contributions, card_display_labels) where:
            - ev_contributions: Dict[str, float] keyed by card_number (or card_name
              fallback), values are summed EV > 0.0
            - card_display_labels: Dict[str, dict] mapping the same key to
              {"card_name": str, "rarity": str, "card_number": str}

        Notes
        -----
        - Zero-EV cards are excluded from ev_contributions.
        - This returns ALL cards (both hit and non-hit). Use
          build_hit_and_non_hit_ev_contributions() to split by rarity mapping.
        """
        required_columns = {"Card Name", "EV"}
        if not required_columns.issubset(df.columns):
            return {}, {}

        ev_series = pd.to_numeric(df["EV"], errors="coerce").fillna(0.0)
        has_card_number = (
            "Card Number" in df.columns
            and df["Card Number"].astype(str).str.strip().replace("", pd.NA).notna().any()
        )
        has_rarity = "Rarity" in df.columns

        if has_card_number:
            working = pd.DataFrame(
                {
                    "card_key": df["Card Number"].astype(str).str.strip(),
                    "Card Name": df["Card Name"].astype(str).str.strip(),
                    "Rarity": df["Rarity"].astype(str).str.strip() if has_rarity else "",
                    "EV": ev_series,
                }
            )
        else:
            # Legacy fallback: card_name is the key (ambiguous for same-name cards)
            print(
                "[IDENTITY_WARNING] 'Card Number' column not present in DataFrame. "
                "Falling back to card name as EV contribution key. "
                "Same-named cards with different rarities will be collapsed — "
                "this may cause incorrect hit/non-hit classification."
            )
            working = pd.DataFrame(
                {
                    "card_key": df["Card Name"].astype(str).str.strip(),
                    "Card Name": df["Card Name"].astype(str).str.strip(),
                    "Rarity": df["Rarity"].astype(str).str.strip() if has_rarity else "",
                    "EV": ev_series,
                }
            )

        # Group EV by stable key (card_number or fallback name)
        grouped_ev = working.groupby("card_key", as_index=True)["EV"].sum()
        ev_contributions = {
            str(key): float(ev_value)
            for key, ev_value in grouped_ev.items()
            if float(ev_value) > 0.0
        }

        # Build display label map: key → {card_name, rarity, card_number}
        # Use first row per key for metadata (after groupby on key)
        label_rows = working.drop_duplicates(subset=["card_key"])
        card_display_labels = {}
        for _, row in label_rows.iterrows():
            key = str(row["card_key"])
            card_display_labels[key] = {
                "card_name": str(row["Card Name"]),
                "rarity": str(row["Rarity"]),
                "card_number": str(row["card_key"]) if has_card_number else "",
            }

        return ev_contributions, card_display_labels

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
        all_contributions, card_display_labels = self.build_card_ev_contributions(df)
        
        if not all_contributions:
            return {
                'hit_ev_contributions': {},
                'non_hit_ev_contributions': {},
                'hit_ev': 0.0,
                'non_hit_ev': 0.0,
                'total_card_ev': 0.0,
                'card_display_labels': {},
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
            'card_display_labels': card_display_labels,
        }

    def calculate_evr_calculations(self, df):
        # Calculate reverse EV (now dynamically handles all slots)
        ev_reverse_total = self.calculate_reverse_ev(df)

        # Calculate EV totals by rarity
        ev_totals_by_rarity = self.calculate_rarity_ev_totals(df, ev_reverse_total)
        ev_reverse_total = self._get_ev_total(ev_totals_by_rarity, 'reverse')

        # Calculate hit probability
        hit_probability_percentage, no_hit_probability_percentage = self.calculate_hit_probability(df)

        # Calculate total EV with special pack adjustments
        upstream_total_manual_ev, regular_pack_contribution, god_pack_ev_contribution, demi_god_pack_ev_contribution = self.calculate_total_ev(ev_totals_by_rarity, df)
        total_manual_ev = self._derive_total_manual_ev(
            ev_totals_by_rarity,
            god_pack_ev_contribution,
            demi_god_pack_ev_contribution,
        )
        
        # Build card EV contributions split into hit/non-hit pools
        card_ev_split = self.build_hit_and_non_hit_ev_contributions(df)

        summary_data_for_manual_calcs = self._build_manual_summary_data(
            ev_totals_by_rarity,
            regular_pack_contribution,
            god_pack_ev_contribution,
            demi_god_pack_ev_contribution,
            upstream_total_manual_ev,
        )

        return {
            "ev_reverse_total": ev_reverse_total,
            "ev_totals_by_rarity": ev_totals_by_rarity,
            "ev_totals": ev_totals_by_rarity,
            "card_ev_contributions": card_ev_split['hit_ev_contributions'],  # For backwards compat, use hit pool
            "hit_ev_contributions": card_ev_split['hit_ev_contributions'],
            "non_hit_ev_contributions": card_ev_split['non_hit_ev_contributions'],
            "hit_ev": card_ev_split['hit_ev'],
            "non_hit_ev": card_ev_split['non_hit_ev'],
            "total_card_ev": card_ev_split['total_card_ev'],
            "card_display_labels": card_ev_split.get('card_display_labels', {}),
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

        top_10_hits = df.sort_values(by="Price ($)", ascending=False).head(10).copy()
        top_10_hits["rank"] = range(1, len(top_10_hits) + 1)
        top_10_hits = top_10_hits.reindex(
            columns=[
                "card_id",
                "card_variant_id",
                "rank",
                "Card Name",
                "rarity_group",
                "Price ($)",
                "Effective_Pull_Rate",
                "EV",
            ]
        ).rename(
            columns={
                "Card Name": "card_name",
                "rarity_group": "rarity_bucket",
                "Price ($)": "market_price_at_run",
                "Effective_Pull_Rate": "effective_pull_rate",
                "EV": "ev_contribution",
            }
        )
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
            "card_display_labels": manual_results.get("card_display_labels", {}),
            "hit_probability_percentage": manual_results["hit_probability_percentage"],
            "no_hit_probability_percentage": manual_results["no_hit_probability_percentage"],
        }
        
        summary_data_for_manual_calcs = manual_results["summary_data_for_manual_calcs"]
        
        print("=== PACK EV CALCULATION COMPLETE ===")
        return results, summary_data_for_manual_calcs, top_10_hits, pack_price