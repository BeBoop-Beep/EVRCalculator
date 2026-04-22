import pandas as pd
import numpy as np
import os
import logging

from itertools import combinations_with_replacement
from .initializeCalculations import PackEVInitializer
from backend.calculations.utils.reverse_pool import (
    build_reverse_eligible_pool,
    get_regular_reverse_probability,
)
from backend.calculations.utils.special_type_normalization import (
    RECOGNIZED_PATTERN_BUCKETS,
    derive_pattern_key,
    normalize_special_type_key,
)
from backend.configured_special_pack_resolver import resolve_configured_god_pack_rows
from backend.utils.special_pack_config import (
    iter_rarity_bucket_rules,
)


logger = logging.getLogger(__name__)


def _emit_pool_debug_snapshot(prefix: str, pool_name: str, pool_df: pd.DataFrame, price_col: str) -> None:
    row_count = int(len(pool_df))
    if row_count == 0:
        print(
            f"{prefix} pool={pool_name} rows=0 price_col='{price_col}' min=0.0000 max=0.0000 mean=0.0000"
        )
        return

    prices = pd.to_numeric(pool_df.get(price_col), errors="coerce").dropna()
    min_price = float(prices.min()) if not prices.empty else 0.0
    max_price = float(prices.max()) if not prices.empty else 0.0
    mean_price = float(prices.mean()) if not prices.empty else 0.0

    print(
        f"{prefix} pool={pool_name} rows={row_count} price_col='{price_col}' "
        f"min={min_price:.4f} max={max_price:.4f} mean={mean_price:.4f}"
    )

    sample_df = pool_df.head(10)
    for idx, (_, row) in enumerate(sample_df.iterrows(), start=1):
        card_name = str(row.get("Card Name", "<missing>") or "<missing>")
        rarity = str(row.get("Rarity", row.get("_rarity_key", "<missing>")) or "<missing>")
        price = pd.to_numeric(pd.Series([row.get(price_col)]), errors="coerce").fillna(0.0).iloc[0]
        card_number = (
            row.get("Card Number")
            or row.get("card_number")
            or row.get("Card_Number")
            or ""
        )
        variant_marker = (
            row.get("Special Type")
            or row.get("special_type_key")
            or row.get("pattern_key")
            or row.get("aggregation_key")
            or ""
        )
        variant_id = row.get("card_variant_id", "")
        print(
            f"{prefix} sample[{idx}] name={card_name} rarity={rarity} price={float(price):.4f} "
            f"card_number={card_number or '<none>'} variant_marker={variant_marker or '<none>'} "
            f"card_variant_id={variant_id if variant_id not in (None, '') else '<none>'}"
        )


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
            def _resolved_total(card_specs, context_label):
                resolved_rows = resolve_configured_god_pack_rows(
                    card_specs,
                    df,
                    context_label=context_label,
                )
                if resolved_rows.empty or "Price ($)" not in resolved_rows.columns:
                    return 0.0
                return float(pd.to_numeric(resolved_rows["Price ($)"], errors="coerce").fillna(0.0).sum())

            if "packs" in strategy:
                # Handle fixed packs (e.g., 151 — each pack is a named trio)
                pack_values = []
                for pack in strategy["packs"]:
                    trio_value = _resolved_total(
                        pack.get("cards", []),
                        context_label=f"god.fixed_pack:{pack.get('name', '?')}",
                    )
                    avg_common = df[df["Rarity"] == "common"]["Price ($)"].mean()
                    avg_uncommon = df[df["Rarity"] == "uncommon"]["Price ($)"].mean()
                    pack_value = trio_value + 4 * avg_common + 3 * avg_uncommon
                    pack_values.append(pack_value)
                    print(
                        f"  God Pack '{pack.get('name', '?')}': trio=${trio_value:.2f}, "
                        f"common_fill=${4*avg_common:.2f}, uncommon_fill=${3*avg_uncommon:.2f}, "
                        f"total=${pack_value:.2f}"
                    )
                avg_pack_value = np.mean(pack_values)
                adjusted_ev = pull_rate * avg_pack_value
                print(f"God Pack Fixed Value With Multiple Options: ${avg_pack_value:.2f}, Pull Rate: {pull_rate}, EV Contribution: ${adjusted_ev:.4f}")
                return adjusted_ev
            elif "cards" in strategy:
                # Handle single fixed card list
                cards = strategy.get("cards", [])
                total = _resolved_total(cards, context_label="god.fixed_cards")
                adjusted_ev = pull_rate * total
                print(f"God Pack Fixed Value 1 Option: ${total:.2f}, Pull Rate: {pull_rate}, EV Contribution: ${adjusted_ev:.4f}")
                return adjusted_ev

        elif strategy_type == "random":
            rules = strategy.get("rules", {})
            if isinstance(rules.get("rarities"), dict):
                rarities = rules.get("rarities", {})
                pack_value = 0.0
                print("=== GOD PACK (RANDOM by slot count) ===")
                for rarity, sample_count, use_replacement in iter_rarity_bucket_rules(rarities):
                    rarity_normalized = rarity.strip().lower()
                    pool = df[df["Rarity"].str.lower().str.strip() == rarity_normalized]
                    pool_size = len(pool)
                    if not use_replacement and sample_count > pool_size:
                        raise ValueError(
                            f"Cannot sample {sample_count} unique cards from '{rarity_normalized}' pool of size {pool_size}. "
                            f"Requested count exceeds available cards without replacement."
                        )

                    avg_price = pool["Price ($)"].mean()
                    # EV note: For a single rarity bucket, E[sum of n draws] = n * mean(pool)
                    # for both with-replacement and without-replacement sampling (when n <= pool size).
                    # So this subtotal is exact for expected value. It is still an approximation for
                    # higher moments/distribution shape because it does not model per-pack covariance.
                    subtotal = sample_count * avg_price
                    pack_value += subtotal
                    replacement_label = "(no replacement)" if not use_replacement else ""
                    print(f"  {rarity_normalized} × {sample_count} → avg ${avg_price:.2f} → subtotal ${subtotal:.2f} {replacement_label}")
                adjusted_ev = pull_rate * pack_value
                print(f"God Pack Value: ${pack_value:.2f}, Pull Rate: {pull_rate}, EV Contribution: ${adjusted_ev:.4f}")
                return adjusted_ev

        return 0.0

    def calculate_effective_pull_rate(self, rarity_group, base_pull_rate, pattern_key=None):
        """
        Calculate the true effective pull rate for each card type following the model's methodology.
        Dynamically determines calculation method based on configuration data.
        
        For pattern-overlay cards (pattern_key in {'pokeball_pattern', 'master_ball_pattern'}),
        returns the exact base_pull_rate because these cards have database-configured exact 
        pull rates. Non-pattern cards use rarity-based calculations (guaranteed slots or 
        probability-based adjustments).
        
        Args:
            rarity_group: Rarity classification key ('common', 'uncommon', 'rare', etc.)
            base_pull_rate: Base pull rate (1/X) from configuration or database
            pattern_key: Structured pattern key from special_type_key normalization.
                        Recognized values: 'pokeball_pattern', 'master_ball_pattern', or empty string.
        
        Returns:
            float: Effective pull rate for EV calculation
        """
        
        # Special pattern cards (always use exact rates)
        # Pattern overlay cards are DB-configured with exact rates, not derived from rarity
        if pattern_key and pattern_key in {'pokeball_pattern', 'master_ball_pattern'}:
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
    
    def calculate_reverse_ev_for_slot(self, df, slot_name):
        """Calculate reverse EV contribution from a single reverse slot"""
        # Get slot configuration
        reverse_slot_probabilities = getattr(self.config, 'REVERSE_SLOT_PROBABILITIES', {})
        if slot_name not in reverse_slot_probabilities:
            return 0.0

        slot_config = reverse_slot_probabilities.get(slot_name, {})
        regular_reverse_prob = get_regular_reverse_probability(slot_name, slot_config)

        if regular_reverse_prob == 0:
            return 0.0

        reverse_pool = build_reverse_eligible_pool(self.config, df)
        if reverse_pool.empty:
            raise ValueError(
                f"Reverse slot '{slot_name}' has regular reverse probability {regular_reverse_prob} "
                "but the eligible reverse pool is empty."
            )

        mean_reverse_price = float(reverse_pool['Reverse Variant Price ($)'].mean())
        return regular_reverse_prob * mean_reverse_price

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
        """Calculate EV totals by aggregation_key with rarity_key fallback and reverse EV handled separately."""
        print("\n=== CALCULATING RARITY EV TOTALS ===")

        if 'EV' not in df.columns:
            raise ValueError("Prepared dataframe must include an 'EV' column for EV aggregation.")
        if 'aggregation_key' not in df.columns and 'rarity_key' not in df.columns:
            raise ValueError(
                "Prepared dataframe must include an 'aggregation_key' or 'rarity_key' column for EV aggregation."
            )

        aggregation_keys = (
            df['aggregation_key'].fillna('').astype(str).str.strip()
            if 'aggregation_key' in df.columns
            else pd.Series('', index=df.index, dtype='object')
        )
        rarity_keys = (
            df['rarity_key'].fillna('').astype(str).str.strip()
            if 'rarity_key' in df.columns
            else pd.Series('', index=df.index, dtype='object')
        )
        pattern_keys = pd.Series('', index=df.index, dtype='object')
        if 'pattern_key' in df.columns:
            pattern_keys = df['pattern_key'].fillna('').astype(str).map(normalize_special_type_key).map(derive_pattern_key)

        if 'aggregation_key' in df.columns:
            pattern_from_aggregation = df['aggregation_key'].fillna('').astype(str).map(normalize_special_type_key).map(derive_pattern_key)
            missing_pattern_mask = pattern_keys.eq('')
            pattern_keys = pattern_keys.where(~missing_pattern_mask, pattern_from_aggregation)

        for special_type_column in ('special_type_key', 'Special Type'):
            if special_type_column in df.columns:
                pattern_from_special_type = df[special_type_column].fillna('').astype(str).map(normalize_special_type_key).map(derive_pattern_key)
                missing_pattern_mask = pattern_keys.eq('')
                pattern_keys = pattern_keys.where(~missing_pattern_mask, pattern_from_special_type)

        # Stable semantic aggregation axis:
        # - pattern rows must aggregate to pattern buckets only
        # - non-pattern base rows (common/uncommon/rare) must aggregate to base rarity buckets
        # - all other rows use aggregation_key with rarity_key fallback
        bucket_keys = aggregation_keys.where(aggregation_keys.ne(''), rarity_keys)
        all_pattern_mask = pattern_keys.isin(RECOGNIZED_PATTERN_BUCKETS)
        bucket_keys = bucket_keys.where(~all_pattern_mask, pattern_keys)

        # Name-variant rows (Card Name contains parentheses, e.g. "(Friend Ball)") are
        # cosmetic/reverse variants and must NOT be bucketed into base rarity EV totals.
        # Their reverse price is already captured by the external reverse EV calculation.
        name_variant_mask = pd.Series(False, index=df.index)
        if 'Card Name' in df.columns:
            name_variant_mask = df['Card Name'].fillna('').astype(str).str.contains('(', regex=False)

        non_pattern_base_mask = (
            (~all_pattern_mask)
            & (~name_variant_mask)
            & rarity_keys.isin({'common', 'uncommon', 'rare'})
        )
        bucket_keys = bucket_keys.where(~non_pattern_base_mask, rarity_keys)

        name_variant_excluded_count = int(
            (name_variant_mask & rarity_keys.isin({'common', 'uncommon', 'rare'})).sum()
        )
        if name_variant_excluded_count:
            print(
                f"[RARITY_EV_AUDIT] name_variant_rows_excluded_from_base_buckets={name_variant_excluded_count} "
                "(parenthetical-name variants routed out of common/uncommon/rare EV totals)"
            )

        ev_values = pd.to_numeric(df['EV'], errors='coerce').fillna(0.0)
        rows_with_totals = df.assign(
            _bucket_key=bucket_keys,
            _ev_value=ev_values,
            _aggregation_key=aggregation_keys,
            _rarity_key=rarity_keys,
            _pattern_key=pattern_keys,
            _card_name=df['Card Name'].fillna('').astype(str).str.strip()
            if 'Card Name' in df.columns
            else '',
        )

        calc_common_pool = rows_with_totals[
            rows_with_totals['_pattern_key'].eq('') & rows_with_totals['_rarity_key'].eq('common')
        ]
        calc_uncommon_pool = rows_with_totals[
            rows_with_totals['_pattern_key'].eq('') & rows_with_totals['_rarity_key'].eq('uncommon')
        ]
        calc_rare_pool = rows_with_totals[
            rows_with_totals['_pattern_key'].eq('') & rows_with_totals['_rarity_key'].eq('rare')
        ]
        calc_reverse_pool = build_reverse_eligible_pool(self.config, rows_with_totals)

        _emit_pool_debug_snapshot("[CALC_POOL_DEBUG]", "common", calc_common_pool, "Price ($)")
        _emit_pool_debug_snapshot("[CALC_POOL_DEBUG]", "uncommon", calc_uncommon_pool, "Price ($)")
        _emit_pool_debug_snapshot("[CALC_POOL_DEBUG]", "rare", calc_rare_pool, "Price ($)")
        _emit_pool_debug_snapshot("[CALC_POOL_DEBUG]", "reverse", calc_reverse_pool, "Reverse Variant Price ($)")

        print("[RARITY_EV_AUDIT] row_counts_by_rarity_key:")
        rarity_counts = rows_with_totals['_rarity_key'].value_counts(dropna=False)
        for key, count in rarity_counts.items():
            label = key if str(key).strip() else '<blank>'
            print(f"  {label}: rows={int(count)}")

        print("[RARITY_EV_AUDIT] row_counts_by_pattern_key:")
        pattern_counts = rows_with_totals['_pattern_key'].value_counts(dropna=False)
        for key, count in pattern_counts.items():
            label = key if str(key).strip() else '<blank>'
            print(f"  {label}: rows={int(count)}")

        print("[RARITY_EV_AUDIT] row_counts_by_aggregation_key:")
        aggregation_counts = rows_with_totals['_aggregation_key'].value_counts(dropna=False)
        for key, count in aggregation_counts.items():
            label = key if str(key).strip() else '<blank>'
            print(f"  {label}: rows={int(count)}")

        missing_bucket_mask = rows_with_totals['_bucket_key'].eq('')
        missing_bucket_count = int(missing_bucket_mask.sum())
        if missing_bucket_count:
            excluded_ev_total = float(rows_with_totals.loc[missing_bucket_mask, '_ev_value'].sum())
            print(
                "[RARITY_EV_BUCKETS] skipped_rows_without_aggregation_key_or_rarity_key="
                f"{missing_bucket_count} "
                "because they cannot be assigned to a stable rarity bucket."
            )
            print(
                f"[RARITY_EV_BUCKETS] excluded_unbucketed_ev_total={excluded_ev_total:.4f} "
                "bucket_source=aggregation_key->rarity_key"
            )

            skipped_rows = rows_with_totals.loc[
                missing_bucket_mask,
                ['_card_name', '_aggregation_key', '_rarity_key', '_ev_value'],
            ].head(5)
            for card_name, aggregation_key, rarity_key, ev_value in skipped_rows.itertuples(index=False, name=None):
                print(
                    "  unbucketed_row: "
                    f"card_name={card_name or '<missing>'} "
                    f"aggregation_key={aggregation_key or '<missing>'} "
                    f"rarity_key={rarity_key or '<missing>'} "
                    f"ev={float(ev_value):.4f}"
                )

        grouped_totals = (
            rows_with_totals.loc[rows_with_totals['_bucket_key'].ne('')]
            .groupby('_bucket_key', sort=True)['_ev_value']
            .agg(['sum', 'size'])
        )

        ev_totals_by_rarity = {
            str(bucket_key): float(row['sum'])
            for bucket_key, row in grouped_totals.iterrows()
        }
        ev_totals_by_rarity['reverse'] = float(ev_reverse_total)

        if 'aggregation_key' in df.columns:
            print("[RARITY_EV_BUCKETS] row-derived totals by aggregation_key (fallback rarity_key when blank):")
        else:
            print("[RARITY_EV_BUCKETS] row-derived totals by rarity_key:")
        if grouped_totals.empty:
            print("  (none)")
        else:
            for bucket_key, row in grouped_totals.iterrows():
                print(
                    f"  {bucket_key}: rows={int(row['size'])} "
                    f"ev_total={float(row['sum']):.4f}"
                )
        print(f"  reverse: rows=external ev_total={float(ev_reverse_total):.4f}")

        # Targeted integrity printouts for baseline pools and pattern overlays.
        for base_rarity in ('common', 'uncommon', 'rare'):
            base_mask = rows_with_totals['_pattern_key'].eq('') & rows_with_totals['_rarity_key'].eq(base_rarity)
            ev_from_rows = float(rows_with_totals.loc[base_mask, '_ev_value'].sum())
            ev_in_bucket = float(ev_totals_by_rarity.get(base_rarity, 0.0))
            print(
                f"[RARITY_EV_AUDIT] non_pattern_{base_rarity}: "
                f"rows={int(base_mask.sum())} ev_from_rows={ev_from_rows:.6f} ev_in_bucket={ev_in_bucket:.6f}"
            )

        for pattern_key in sorted(RECOGNIZED_PATTERN_BUCKETS):
            pattern_row_mask = rows_with_totals['_pattern_key'].eq(pattern_key)
            ev_from_rows = float(rows_with_totals.loc[pattern_row_mask, '_ev_value'].sum())
            ev_in_bucket = float(ev_totals_by_rarity.get(pattern_key, 0.0))
            print(
                f"[RARITY_EV_AUDIT] pattern_{pattern_key}: "
                f"rows={int(pattern_row_mask.sum())} ev_from_rows={ev_from_rows:.6f} ev_in_bucket={ev_in_bucket:.6f}"
            )

        print(f"\nSum of all EV totals: {sum(ev_totals_by_rarity.values()):.4f}\n")

        pokeball_pattern_ev = float(
            ev_totals_by_rarity.get('pokeball_pattern', 0.0)
            + ev_totals_by_rarity.get('poke_ball_pattern', 0.0)
        )
        master_ball_pattern_ev = float(ev_totals_by_rarity.get('master_ball_pattern', 0.0))
        pattern_ev_total = pokeball_pattern_ev + master_ball_pattern_ev
        base_rarity_ev_total = float(
            ev_totals_by_rarity.get('common', 0.0)
            + ev_totals_by_rarity.get('uncommon', 0.0)
            + ev_totals_by_rarity.get('rare', 0.0)
            + ev_totals_by_rarity.get('reverse', 0.0)
        )
        total_ev_across_all_buckets = float(sum(ev_totals_by_rarity.values()))
        other_special_ev_total = total_ev_across_all_buckets - base_rarity_ev_total - pattern_ev_total
        if abs(other_special_ev_total) < 1e-12:
            other_special_ev_total = 0.0

        logger.info(
            "[MANUAL_EV_COMPOSITION] total_ev_across_all_buckets=%.2f",
            total_ev_across_all_buckets,
        )
        logger.info(
            "[MANUAL_EV_COMPOSITION] base_rarity_ev_total=%.2f (sum of common, uncommon, rare, reverse)",
            base_rarity_ev_total,
        )
        logger.info(
            "[MANUAL_EV_COMPOSITION] pattern_ev_total=%.2f (sum of pokeball_pattern, master_ball_pattern)",
            pattern_ev_total,
        )
        logger.info(
            "[MANUAL_EV_COMPOSITION] other_special_ev_total=%.2f (ace_spec, illustration_rare, etc)",
            other_special_ev_total,
        )
        logger.info("[MANUAL_EV_COMPOSITION] pokeball_pattern_ev=%.3f", pokeball_pattern_ev)
        logger.info("[MANUAL_EV_COMPOSITION] master_ball_pattern_ev=%.3f", master_ball_pattern_ev)

        return ev_totals_by_rarity

    def audit_ev_aggregation_integrity(self, df, ev_totals_by_rarity):
        """
        Audit and verify manual EV aggregation integrity.
        
        Ensures:
        1. Pattern rows aggregate to intended buckets (master_ball_pattern, pokeball_pattern)
        2. Pattern rows do NOT also contribute to base-rarity buckets
        3. No double-counting occurs
        4. Aggregation axis is correct and stable
        
        Args:
            df: Prepared dataframe with 'aggregation_key', 'rarity_key', 'EV', and 'pattern_key'
            ev_totals_by_rarity: Dictionary mapping rarity/pattern keys to EV totals
            
        Returns:
            dict with:
            - is_valid (bool): True if no issues found
            - issues (list): List of issue strings (empty if valid)
            - row_sum (float): Sum of all row EVs grouped by aggregation_key
            - bucket_sum (float): Sum of all bucket totals (excluding reverse)
            - spot_checks (dict): Results of specific verification checks
        """
        issues = []
        
        # ===== AUDIT 1: Total EV Sum Consistency =====
        # Sum all row EVs by aggregation_key (should equal bucket totals)
        if 'aggregation_key' not in df.columns or 'EV' not in df.columns:
            return {
                'is_valid': False,
                'issues': ["DataFrame missing 'aggregation_key' or 'EV' columns"],
                'row_sum': 0.0,
                'bucket_sum': 0.0,
                'spot_checks': {},
            }
        
        aggregation_keys = df['aggregation_key'].fillna('').astype(str).str.strip()
        rarity_keys = df['rarity_key'].fillna('').astype(str).str.strip() if 'rarity_key' in df.columns else pd.Series('', index=df.index)
        pattern_keys = pd.Series('', index=df.index, dtype='object')
        if 'pattern_key' in df.columns:
            pattern_keys = df['pattern_key'].fillna('').astype(str).map(normalize_special_type_key).map(derive_pattern_key)

        if 'aggregation_key' in df.columns:
            pattern_from_aggregation = df['aggregation_key'].fillna('').astype(str).map(normalize_special_type_key).map(derive_pattern_key)
            missing_pattern_mask = pattern_keys.eq('')
            pattern_keys = pattern_keys.where(~missing_pattern_mask, pattern_from_aggregation)

        for special_type_column in ('special_type_key', 'Special Type'):
            if special_type_column in df.columns:
                pattern_from_special_type = df[special_type_column].fillna('').astype(str).map(normalize_special_type_key).map(derive_pattern_key)
                missing_pattern_mask = pattern_keys.eq('')
                pattern_keys = pattern_keys.where(~missing_pattern_mask, pattern_from_special_type)

        bucket_keys = aggregation_keys.where(aggregation_keys.ne(''), rarity_keys)
        all_pattern_mask = pattern_keys.isin(RECOGNIZED_PATTERN_BUCKETS)
        bucket_keys = bucket_keys.where(~all_pattern_mask, pattern_keys)

        name_variant_mask = pd.Series(False, index=df.index)
        if 'Card Name' in df.columns:
            name_variant_mask = df['Card Name'].fillna('').astype(str).str.contains('(', regex=False)

        non_pattern_base_mask = (
            (~all_pattern_mask)
            & (~name_variant_mask)
            & rarity_keys.isin({'common', 'uncommon', 'rare'})
        )
        bucket_keys = bucket_keys.where(~non_pattern_base_mask, rarity_keys)

        ev_values = pd.to_numeric(df['EV'], errors='coerce').fillna(0.0)
        
        # Sum row EVs by bucket
        row_level_sum = float(ev_values[bucket_keys.ne('')].sum())
        
        # Sum bucket totals (excluding reverse which is external)
        bucket_sum = float(sum(
            v for k, v in ev_totals_by_rarity.items()
            if k != 'reverse'
        ))
        
        # Check for consistency (with floating point tolerance)
        tolerance = 1e-6
        if abs(row_level_sum - bucket_sum) > tolerance:
            issues.append(
                f"Row-level EV sum ({row_level_sum:.6f}) != bucket total ({bucket_sum:.6f}). "
                f"Difference: {abs(row_level_sum - bucket_sum):.6f} (tolerance: {tolerance})"
            )
        
        # ===== AUDIT 2: Spot-Check Pattern Rows =====
        spot_checks = {
            'pattern_rows': {},
            'non_pattern_rows': {},
        }
        
        # Find all pattern rows
        for pattern_val in ['master_ball_pattern', 'pokeball_pattern']:
            pattern_row_mask = pattern_keys.eq(pattern_val)
            pattern_rows = df[pattern_row_mask]
            
            if len(pattern_rows) > 0:
                pattern_ev_from_rows = float(pattern_rows['EV'].sum())
                pattern_ev_from_buckets = float(ev_totals_by_rarity.get(pattern_val, 0.0))
                
                check_result = {
                    'row_count': len(pattern_rows),
                    'ev_from_rows': pattern_ev_from_rows,
                    'ev_in_bucket': pattern_ev_from_buckets,
                    'match': abs(pattern_ev_from_rows - pattern_ev_from_buckets) < tolerance,
                    'rows': [],
                }
                
                # Check each pattern row is counted only in pattern bucket, not base rarity bucket
                for idx, row in pattern_rows.iterrows():
                    card_name = row.get('Card Name', '<unknown>')
                    base_rarity = row.get('rarity_key', '')
                    ev = float(row['EV'])
                    
                    # Verify row is in pattern bucket
                    agg_key = bucket_keys.loc[idx]
                    is_in_pattern_bucket = agg_key == pattern_val
                    
                    row_check = {
                        'card_name': card_name,
                        'aggregation_key': agg_key,
                        'base_rarity': base_rarity,
                        'ev': ev,
                        'in_pattern_bucket': is_in_pattern_bucket,
                    }
                    check_result['rows'].append(row_check)
                    
                    # Flag issues only if row is NOT in its intended pattern bucket
                    if not is_in_pattern_bucket:
                        issues.append(
                            f"Pattern row '{card_name}' has pattern_key={pattern_val} "
                            f"but aggregation_key={agg_key} (should be {pattern_val})"
                        )
                
                # Check if pattern bucket EV matches row-level EV
                if not check_result['match']:
                    issues.append(
                        f"Pattern rows for {pattern_val}: EV from dataframe ({pattern_ev_from_rows:.6f}) "
                        f"!= EV in bucket ({pattern_ev_from_buckets:.6f})"
                    )
                
                spot_checks['pattern_rows'][pattern_val] = check_result
        
        # ===== AUDIT 3: Spot-Check Non-Pattern Rows =====
        non_pattern_mask = ~all_pattern_mask
        non_pattern_rows = df[non_pattern_mask]
        
        if len(non_pattern_rows) > 0:
            for base_rarity in ['common', 'uncommon', 'rare']:
                rarity_mask = non_pattern_mask & rarity_keys.eq(base_rarity)
                rarity_rows = df[rarity_mask]
                
                if len(rarity_rows) > 0:
                    rarity_ev_from_rows = float(rarity_rows['EV'].sum())
                    rarity_ev_from_buckets = float(ev_totals_by_rarity.get(base_rarity, 0.0))
                    
                    check_result = {
                        'row_count': len(rarity_rows),
                        'ev_from_rows': rarity_ev_from_rows,
                        'ev_in_bucket': rarity_ev_from_buckets,
                        'match': abs(rarity_ev_from_rows - rarity_ev_from_buckets) < tolerance,
                        'rows': [],
                    }
                    
                    for idx, row in rarity_rows.iterrows():
                        card_name = row.get('Card Name', '<unknown>')
                        ev = float(row['EV'])
                        agg_key = bucket_keys.loc[idx]
                        
                        row_check = {
                            'card_name': card_name,
                            'aggregation_key': agg_key,
                            'base_rarity': base_rarity,
                            'ev': ev,
                            'in_base_bucket': agg_key == base_rarity,
                        }
                        check_result['rows'].append(row_check)
                        
                        if agg_key != base_rarity:
                            issues.append(
                                f"Non-pattern row '{card_name}' has rarity_key={base_rarity} "
                                f"but aggregation_key={agg_key} (should be {base_rarity})"
                            )

                    if not check_result['match']:
                        issues.append(
                            f"Non-pattern rows for {base_rarity}: EV from dataframe ({rarity_ev_from_rows:.6f}) "
                            f"!= EV in bucket ({rarity_ev_from_buckets:.6f})"
                        )

                    spot_checks['non_pattern_rows'][base_rarity] = check_result

        # Structural failure checks.
        pattern_in_base_mask = all_pattern_mask & bucket_keys.isin({'common', 'uncommon', 'rare'})
        if pattern_in_base_mask.any():
            offenders = df.loc[pattern_in_base_mask, 'Card Name'].fillna('<unknown>').astype(str).head(5).tolist()
            issues.append(
                "Pattern rows routed to base rarity buckets. "
                f"sample_cards={offenders}"
            )

        base_non_pattern_mismatch_mask = (~all_pattern_mask) & rarity_keys.isin({'common', 'uncommon', 'rare'}) & bucket_keys.ne(rarity_keys)
        if base_non_pattern_mismatch_mask.any():
            offenders = df.loc[base_non_pattern_mismatch_mask, 'Card Name'].fillna('<unknown>').astype(str).head(5).tolist()
            issues.append(
                "Non-pattern common/uncommon/rare rows routed outside their base rarity bucket. "
                f"sample_cards={offenders}"
            )
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'row_sum': row_level_sum,
            'bucket_sum': bucket_sum,
            'spot_checks': spot_checks,
        }
    
    
   
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

