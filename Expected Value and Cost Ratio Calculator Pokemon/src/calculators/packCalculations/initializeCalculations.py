import pandas as pd
import os

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


    def _load_file(self, file_path):
        try:
            return pd.read_excel(file_path)
        except FileNotFoundError:
            return pd.read_csv(file_path)

    def _validate_required_columns(self, df):
        required_cols = ['Rarity', 'Price ($)', 'Pull Rate (1/X)', 'Pack Price']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: '{col}'")

    def _clean_columns(self, df):
        df['Pull Rate (1/X)'] = (
            df['Pull Rate (1/X)']
            .astype(str)
            .str.replace('[$,]', '', regex=True)
            .replace('', pd.NA)
        )

    def _derive_rarity_columns(self, df):
        df['rarity_raw'] = df['Rarity'].astype(str).str.lower().str.strip()
        df['rarity_group'] = df['rarity_raw'].map(self.config.RARITY_MAPPING)

    def _convert_column_types(self, df):
        df['Price ($)'] = pd.to_numeric(df['Price ($)'], errors='coerce')
        df['Pull Rate (1/X)'] = pd.to_numeric(df['Pull Rate (1/X)'], errors='coerce')
        df.dropna(subset=['Price ($)', 'Pull Rate (1/X)'], inplace=True)

    def _remove_invalid_pull_rates(self, df):
        df = df[df['Pull Rate (1/X)'] != 0]

    def _extract_pack_price(self, df):
        return pd.to_numeric(df["Pack Price"].iloc[0], errors='coerce')

    def _calculate_ev_columns(self, df):
        if "EV_Reverse" not in df.columns:
            if "Reverse Variant Price ($)" in df.columns:
                df["EV_Reverse"] = df["Reverse Variant Price ($)"]
            elif "Price ($)" in df.columns:
                df["EV_Reverse"] = df["Price ($)"]
            else:
                df["EV_Reverse"] = 0.0

        df['Effective_Pull_Rate'] = df.apply(
            lambda row: self.calculate_effective_pull_rate(
                row['rarity_group'], 
                row['Pull Rate (1/X)'],
                row.get('Card Name', '')
            ),
            axis=1
        )

        df['EV'] = df['Price ($)'] / df['Effective_Pull_Rate']
        df['EV_Reverse'] = df.get('Reverse Variant Price ($)', df['Price ($)']) * df['Effective_Pull_Rate']

    def _strip_column_names(self, df):
        df.columns = df.columns.str.strip()

    def _debug_print(self, df):
        print(f"Total cards processed: {len(df)}")
        print(df[['Card Name', 'Rarity', 'Price ($)', 'Effective_Pull_Rate', 'EV']].head(10))

    def load_and_prepare_data(self, file_path):
        df = self._load_file(file_path)
        self._validate_required_columns(df)
        self._clean_columns(df)
        self._derive_rarity_columns(df)
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