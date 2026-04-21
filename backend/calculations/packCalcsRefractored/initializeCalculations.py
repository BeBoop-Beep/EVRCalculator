import pandas as pd

from ..utils.reverse_pool import normalize_reverse_classification_key
from ..utils.rarity_classification import normalize_rarity_key
from ..utils.special_type_normalization import (
    RECOGNIZED_PATTERN_BUCKETS,
    derive_aggregation_key,
    derive_pattern_key,
    is_recognized_pattern_special_type,
    normalize_special_type_key,
)


CARD_NAME_WITH_NUMBER_PATTERN = r'^(?P<name>.+?)\s*-\s*(?P<number>[A-Za-z0-9.-]+/[A-Za-z0-9.-]+)\s*$'

class PackEVInitializer:
    """Handles initialization and data loading for pack EV calculations"""
    
    def __init__(self, config):
        """Initialize the calculator with configuration"""
        self.config = config
        self.PULL_RATE_MAPPING = config.PULL_RATE_MAPPING
        self.pack_multipliers = config.get_rarity_pack_multiplier()
        self.common_multiplier = self.pack_multipliers.get('common', 1)
        self.uncommon_multiplier = self.pack_multipliers.get('uncommon', 1)
        self.rare_multiplier = config.RARE_SLOT_PROBABILITY['rare']
        
        slot1_rr = config.REVERSE_SLOT_PROBABILITIES["slot_1"]["regular reverse"]
        slot2_rr = config.REVERSE_SLOT_PROBABILITIES["slot_2"]["regular reverse"]
        self.reverse_multiplier = slot1_rr + slot2_rr


    def _load_dataframe(self, calculation_input):
        if not isinstance(calculation_input, pd.DataFrame):
            raise TypeError(
                "Active backend EV calculations only support pandas DataFrame input. "
                "Spreadsheet and file-path inputs are not supported."
            )

        return calculation_input.copy(deep=True)

    def _validate_required_columns(self, df):
        required_cols = ['Rarity', 'Price ($)', 'Pull Rate (1/X)', 'Pack Price']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: '{col}'")

    def _ensure_optional_columns(self, df):
        if 'Special Type' not in df.columns:
            df['Special Type'] = ''
        else:
            df['Special Type'] = df['Special Type'].fillna('').astype(str)

    def _clean_columns(self, df):
        df['Pull Rate (1/X)'] = (
            df['Pull Rate (1/X)']
            .astype(str)
            .str.replace('[$,]', '', regex=True)
            .replace('', pd.NA)
        )

    def _normalize_card_identity_columns(self, df):
        if 'Card Name' not in df.columns:
            return

        card_names = df['Card Name'].fillna('').astype(str).str.strip()
        extracted = card_names.str.extract(CARD_NAME_WITH_NUMBER_PATTERN)
        combined_mask = extracted['number'].notna()

        if not combined_mask.any():
            return

        if 'Card Number' not in df.columns:
            df['Card Number'] = ''

        current_numbers = df['Card Number'].fillna('').astype(str).str.strip()
        missing_number_mask = combined_mask & current_numbers.eq('')

        # Always clean combined identity from Card Name to preserve plain-name semantics.
        df.loc[combined_mask, 'Card Name'] = extracted.loc[combined_mask, 'name'].str.strip()

        # Populate Card Number only where it is currently blank.
        df.loc[missing_number_mask, 'Card Number'] = extracted.loc[missing_number_mask, 'number'].str.strip()

        cleaned_count = int(combined_mask.sum())
        filled_count = int(missing_number_mask.sum())
        print(
            f"[IDENTITY_NORMALIZATION] cleaned_combined_names={cleaned_count} "
            f"filled_missing_card_numbers={filled_count}"
        )

    def _derive_rarity_columns(self, df):
        df['rarity_raw'] = df['Rarity'].astype(str).str.lower().str.strip()
        df['rarity_group'] = df['rarity_raw'].map(self.config.RARITY_MAPPING)
        df['rarity_key'] = df['Rarity'].apply(normalize_rarity_key)
        self._warn_on_unmapped_rarities(df)

    def _derive_special_type_columns(self, df):
        df['special_type_raw'] = df['Special Type'].astype(str).str.lower().str.strip()
        df['special_type_key'] = df['Special Type'].apply(normalize_special_type_key)
        self._warn_on_non_pattern_special_types(df)

    def _derive_aggregation_columns(self, df):
        df['pattern_key'] = df['special_type_key'].apply(derive_pattern_key)
        # Preserve base rarity semantics explicitly for downstream slot logic.
        df['base_rarity_key'] = df['rarity_key']
        df['aggregation_key'] = df.apply(
            lambda row: derive_aggregation_key(row['rarity_key'], row['special_type_key']),
            axis=1,
        )
        # classification_key remains base-rarity oriented; aggregation_key carries overlay/reporting buckets.
        df['classification_key'] = df['base_rarity_key']

    def _warn_on_unmapped_rarities(self, df):
        has_raw_rarity = df['Rarity'].notna() & df['Rarity'].astype(str).str.strip().ne('')
        unmapped_mask = has_raw_rarity & df['rarity_group'].isna()

        if not unmapped_mask.any():
            return

        unmapped_rarities = sorted(df.loc[unmapped_mask, 'rarity_raw'].dropna().unique().tolist())
        print(
            f"[RARITY_WARNING] Unmapped rarities detected for {int(unmapped_mask.sum())} row(s): "
            f"{unmapped_rarities}. Update config.RARITY_MAPPING; no fallback rarity_group was applied."
        )

    def _warn_on_non_pattern_special_types(self, df):
        has_special_type = df['special_type_raw'].ne('')
        non_pattern_mask = has_special_type & ~df['special_type_key'].apply(is_recognized_pattern_special_type)

        if not non_pattern_mask.any():
            return

        distinct_pairs = sorted(
            {
                (row.special_type_raw, row.special_type_key)
                for row in df.loc[non_pattern_mask, ['special_type_raw', 'special_type_key']].itertuples(index=False)
            }
        )
        print(
            f"[SPECIAL_TYPE_WARNING] Non-pattern special types detected for {int(non_pattern_mask.sum())} row(s): "
            f"{distinct_pairs}. pattern_key remains empty and aggregation_key "
            "will fall back to rarity_key for these rows."
        )

    def _convert_column_types(self, df):
        df['Price ($)'] = pd.to_numeric(df['Price ($)'], errors='coerce')
        df['Pull Rate (1/X)'] = pd.to_numeric(df['Pull Rate (1/X)'], errors='coerce')
        df.dropna(subset=['Price ($)', 'Pull Rate (1/X)'], inplace=True)

    def _remove_invalid_pull_rates(self, df):
        df = df[df['Pull Rate (1/X)'] != 0]

    def _extract_pack_price(self, df):
        return pd.to_numeric(df["Pack Price"].iloc[0], errors='coerce')

    def _get_pattern_event_probabilities(self):
        reverse_slot_probabilities = getattr(self.config, 'REVERSE_SLOT_PROBABILITIES', {})
        pattern_event_probabilities = {pattern_key: 0.0 for pattern_key in RECOGNIZED_PATTERN_BUCKETS}

        if not isinstance(reverse_slot_probabilities, dict):
            return pattern_event_probabilities

        for slot_config in reverse_slot_probabilities.values():
            if not isinstance(slot_config, dict):
                continue
            for raw_key, raw_probability in slot_config.items():
                classification_key = normalize_reverse_classification_key(str(raw_key))
                if classification_key not in RECOGNIZED_PATTERN_BUCKETS:
                    continue
                probability = float(pd.to_numeric(raw_probability, errors='coerce') or 0.0)
                if probability > 0:
                    pattern_event_probabilities[classification_key] += probability

        return pattern_event_probabilities

    def _apply_pattern_overlay_pull_rate_overrides(self, df):
        if 'pattern_key' not in df.columns:
            return

        pattern_keys = df['pattern_key'].fillna('').astype(str).str.strip()
        if not pattern_keys.isin(RECOGNIZED_PATTERN_BUCKETS).any():
            return

        pattern_event_probabilities = self._get_pattern_event_probabilities()
        for pattern_key in RECOGNIZED_PATTERN_BUCKETS:
            pattern_mask = pattern_keys.eq(pattern_key)
            pattern_count = int(pattern_mask.sum())
            if pattern_count == 0:
                continue

            event_probability = float(pattern_event_probabilities.get(pattern_key, 0.0))
            if event_probability <= 0.0:
                print(
                    f"[PATTERN_EV_WARNING] pattern_key={pattern_key} has {pattern_count} row(s) "
                    "but no positive event probability in REVERSE_SLOT_PROBABILITIES; "
                    "retaining row-level pull rates."
                )
                continue

            # Pattern overlays are a single event bucket sampled over a finite pool.
            # Per-card probability = P(any pattern event) / pattern_pool_size.
            effective_pull_rate = pattern_count / event_probability
            df.loc[pattern_mask, 'Effective_Pull_Rate'] = float(effective_pull_rate)

            print(
                f"[PATTERN_EV_MODEL] pattern_key={pattern_key} rows={pattern_count} "
                f"event_probability={event_probability:.12f} "
                f"effective_pull_rate_per_card={effective_pull_rate:.6f}"
            )

    def _calculate_ev_columns(self, df):
        df['Effective_Pull_Rate'] = df.apply(
            lambda row: self.calculate_effective_pull_rate(
                row['rarity_group'], 
                row['Pull Rate (1/X)'],
                row.get('pattern_key', '')
            ),
            axis=1
        )

        self._apply_pattern_overlay_pull_rate_overrides(df)

        df['EV'] = df['Price ($)'] / df['Effective_Pull_Rate']

    def _strip_column_names(self, df):
        df.columns = df.columns.str.strip()

    def _debug_print(self, df):
        print(f"Total cards processed: {len(df)}")
        print(df[['Card Name', 'Rarity', 'Price ($)', 'Effective_Pull_Rate', 'EV']].head(10))

    def load_and_prepare_data(self, calculation_input):
        df = self._load_dataframe(calculation_input)
        self._strip_column_names(df)
        self._validate_required_columns(df)
        self._ensure_optional_columns(df)
        self._normalize_card_identity_columns(df)
        self._clean_columns(df)
        self._derive_rarity_columns(df)
        self._derive_special_type_columns(df)
        self._derive_aggregation_columns(df)
        self._convert_column_types(df)
        self._remove_invalid_pull_rates(df)
        pack_price = self._extract_pack_price(df)
        self._calculate_ev_columns(df)
        self._strip_column_names(df)
        self._debug_print(df)

        return df, pack_price

    
    # def load_and_prepare_data(self, file_path):
    #     """Load data from file and prepare it for calculations - NO RARITY MAPPING VERSION"""
    #     # Load data
    #     try:
    #         df = pd.read_excel(file_path)
    #     except FileNotFoundError:
    #         df = pd.read_csv(file_path)
        
    #     # Validate required columns
    #     required_cols = ['Rarity', 'Price ($)', 'Pull Rate (1/X)', 'Pack Price']
    #     for col in required_cols:
    #         if col not in df.columns:
    #             raise ValueError(f"Input data must contain a '{col}' column.")
        
    #     # Clean and process data
    #     df['Pull Rate (1/X)'] = (
    #         df['Pull Rate (1/X)']
    #         .astype(str)
    #         .str.replace('[$,]', '', regex=True)
    #         .replace('', pd.NA)
    #     )
        
    #     # Since you removed RARITY_MAPPING, just use the raw rarity directly
    #     df['rarity_raw'] = df['Rarity'].astype(str).str.lower().str.strip()
        
    #     # Create rarity_group directly from rarity_raw without mapping
    #     df['rarity_group'] = df['rarity_raw'].copy().str.lower().map(self.config.RARITY_MAPPING)  # Just use the cleaned rarity as-is
        
    #     # Convert to numeric
    #     df['Price ($)'] = pd.to_numeric(df['Price ($)'], errors='coerce')
    #     df['Pull Rate (1/X)'] = pd.to_numeric(df['Pull Rate (1/X)'], errors='coerce')
    #     df = df.dropna(subset=['Price ($)', 'Pull Rate (1/X)'])
        
    #     # Remove zero pull rates
    #     if (df['Pull Rate (1/X)'] == 0).any():
    #         df = df[df['Pull Rate (1/X)'] != 0]
        
    #     # Get pack price
    #     pack_price = pd.to_numeric(df["Pack Price"].iloc[0], errors='coerce')


    #     # Ensure EV_Reverse column is set
    #     if "EV_Reverse" not in df.columns:
    #         if "Reverse Variant Price ($)" in df.columns:
    #             df["EV_Reverse"] = df["Reverse Variant Price ($)"]
    #         elif "Price ($)" in df.columns:
    #             df["EV_Reverse"] = df["Price ($)"]  # fallback if reverse-specific price not available
    #         else:
    #             df["EV_Reverse"] = 0.0  # safest fallback to prevent errors

    #      # Calculate effective pull rates for each card
    #     df['Effective_Pull_Rate'] = df.apply(
    #         lambda row: self.calculate_effective_pull_rate(
    #             row['rarity_group'], 
    #             row['Pull Rate (1/X)'],
    #             row.get('Card Name', '')
    #         ), 
    #         axis=1
    #     )
        
    #     # Calculate EV using effective pull rates
    #     df['EV'] = df['Price ($)'] / df['Effective_Pull_Rate']
    #     print(f"Total cards processed: {len(df)}")

    #     df['EV_Reverse'] = df.get('Reverse Variant Price ($)', df['Price ($)']) * df['Effective_Pull_Rate']

    #     df.columns = df.columns.str.strip()

    #     print(df[['Card Name', 'Rarity', 'Price ($)', 'Effective_Pull_Rate', 'EV']].head(10))

        
    #     return df, pack_price