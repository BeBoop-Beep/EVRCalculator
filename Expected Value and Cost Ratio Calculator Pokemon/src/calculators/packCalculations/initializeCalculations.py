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
    
    def load_and_prepare_data(self, file_path):
        """Load data from file and prepare it for calculations - NO RARITY MAPPING VERSION"""
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
        
        # Since you removed RARITY_MAPPING, just use the raw rarity directly
        df['rarity_raw'] = df['Rarity'].astype(str).str.lower().str.strip()
        
        # Create rarity_group directly from rarity_raw without mapping
        df['rarity_group'] = df['rarity_raw'].copy()  # Just use the cleaned rarity as-is
        
        # Convert to numeric
        df['Price ($)'] = pd.to_numeric(df['Price ($)'], errors='coerce')
        df['Pull Rate (1/X)'] = pd.to_numeric(df['Pull Rate (1/X)'], errors='coerce')
        df = df.dropna(subset=['Price ($)', 'Pull Rate (1/X)'])
        
        # Remove zero pull rates
        if (df['Pull Rate (1/X)'] == 0).any():
            df = df[df['Pull Rate (1/X)'] != 0]
        
        # Get pack price
        pack_price = pd.to_numeric(df["Pack Price"].iloc[0], errors='coerce')

        # Ensure EV_Reverse column is set
        if "EV_Reverse" not in df.columns:
            if "Reverse Variant Price ($)" in df.columns:
                df["EV_Reverse"] = df["Reverse Variant Price ($)"]
            elif "Price ($)" in df.columns:
                df["EV_Reverse"] = df["Price ($)"]  # fallback if reverse-specific price not available
            else:
                df["EV_Reverse"] = 0.0  # safest fallback to prevent errors

        
        return df, pack_price