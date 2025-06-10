import pandas as pd
import numpy as np
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import os

class PackEVCalculator:
    def __init__(self, config):
        self.config = config
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
    
    def calculate_reverse_ev(self, df):
        """Calculate EV for reverse holo variants"""
        ev_reverse_total = 0
        
        if 'Reverse Variant Price ($)' in df.columns:
            df['Reverse Variant Price ($)'] = pd.to_numeric(df['Reverse Variant Price ($)'], errors='coerce')
            
            # Exclude IR and SIR since they are treated separately
            is_standard_reverse = ~df['Rarity'].isin(['Illustration Rare', 'Special Illustration Rare'])
            
            # Calculate EV for standard reverse holos only
            df['EV_Reverse'] = 0
            df.loc[is_standard_reverse, 'EV_Reverse'] = (
                df.loc[is_standard_reverse, 'Reverse Variant Price ($)'].fillna(0) / 
                df.loc[is_standard_reverse, 'Pull Rate (1/X)']
            )
            
            ev_reverse_total = df.loc[is_standard_reverse, 'EV_Reverse'].sum()
        
        return ev_reverse_total
    
    def calculate_rarity_ev_totals(self, df):
        """Calculate EV totals by rarity group"""
        # Filter out special patterns
        pattern_mask = df['Card Name'].str.contains('Master Ball|Poke Ball', case=False, na=False)
        
        # Get special cards
        master_ball_cards = df[df['Card Name'].str.contains('Master Ball', case=False, na=False)]
        pokeball_cards = df[df['Card Name'].str.contains('Poke Ball', case=False, na=False)]
        
        # Calculate EV totals by rarity
        ev_totals = {
            'common': df[(df['Rarity'] == 'common') & ~pattern_mask]['EV'].sum(),
            'uncommon': df[(df['Rarity'] == 'uncommon') & ~pattern_mask]['EV'].sum(),
            'rare': df[(df['Rarity'] == 'rare') & ~pattern_mask]['EV'].sum(),
            'double_rare': df.loc[df['Rarity'] == 'double rare', 'EV'].sum(),
            'ace_spec_rare': df.loc[df['Rarity'] == 'ace spec rare', 'EV'].sum(),
            'hyper_rare': df.loc[df['Rarity'] == 'hyper rare', 'EV'].sum(),
            'ultra_rare': df.loc[df['Rarity'] == 'ultra rare', 'EV'].sum(),
            'special_illustration_rare': df.loc[df['Rarity'] == 'special illustration rare', 'EV'].sum(),
            'illustration_rare': df.loc[df['Rarity'] == 'illustration rare', 'EV'].sum(),
            'hits': df.loc[df['rarity_group'] == 'hits', 'EV'].sum(),
            'other': df.loc[df['rarity_group'] == 'other', 'EV'].sum(),
            'master_ball': master_ball_cards['EV'].sum(),
            'pokeball': pokeball_cards['EV'].sum()
        }
        
        return ev_totals
    
    def calculate_hit_probability(self, df):
        """Calculate probability of pulling at least one hit card"""
        hit_df = df[df['rarity_group'] == 'hits']
        hit_probs = 1 / hit_df['Pull Rate (1/X)']
        prob_no_hits = (1 - hit_probs).prod()
        no_hit_probability_percentage = prob_no_hits * 100
        hit_probability_percentage = (1 - prob_no_hits) * 100
        
        return hit_probability_percentage, no_hit_probability_percentage
    
    def calculate_total_ev(self, ev_totals, ev_reverse_total):
        """Calculate total EV with multipliers applied"""
        total_ev = (
            ev_totals['common'] * self.common_multiplier + 
            ev_totals['uncommon'] * self.uncommon_multiplier + 
            ev_totals['rare'] * self.rare_multiplier + 
            ev_totals['double_rare'] + 
            ev_totals['ace_spec_rare'] +
            ev_totals['pokeball'] +
            ev_totals['master_ball'] +
            ev_totals['hyper_rare'] +
            ev_totals['ultra_rare'] +
            ev_totals['special_illustration_rare'] +
            ev_totals['illustration_rare'] +
            ev_totals['other'] + 
            ev_reverse_total * self.reverse_multiplier
        )
        
        return total_ev
    
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

        return average, variance, stddev

    
    def calculate_pack_ev(self, file_path):
        """Main calculation method that orchestrates all calculations"""
        # Load and prepare data
        df, pack_price = self.load_and_prepare_data(file_path)
        
        # Calculate base EV
        df = self.calculate_base_ev(df)
        
        # Calculate reverse EV
        ev_reverse_total = self.calculate_reverse_ev(df)
        
        # Calculate EV totals by rarity
        ev_totals = self.calculate_rarity_ev_totals(df)
        
        # Calculate hit probability
        hit_probability_percentage, no_hit_probability_percentage = self.calculate_hit_probability(df)
        
        # Calculate total EV
        total_ev = self.calculate_total_ev(ev_totals, ev_reverse_total)
        
        # Calculate pack metrics
        pack_metrics = self.calculate_pack_metrics(total_ev, pack_price)

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
        }
        
        summary_data = {
            "ev_common_total": ev_totals['common'] * self.common_multiplier,
            "ev_uncommon_total": ev_totals['uncommon'] * self.uncommon_multiplier,
            "ev_rare_total": ev_totals['rare'] * self.rare_multiplier,
            "ev_reverse_total": ev_reverse_total * self.reverse_multiplier,
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
            "ev_hits_total": ev_totals['hits'],
            "total_ev": total_ev,
            "net_value": pack_metrics['net_value'],
            "roi": pack_metrics['roi'],
            "roi_percent": pack_metrics['roi_percent'],
            "no_hit_probability_percentage": no_hit_probability_percentage,
            "hit_probability_percentage": hit_probability_percentage,
        }
        print("results: ", results)
        print("summary_data: ", summary_data)
        return results, summary_data

# Convenience function to maintain backward compatibility
def calculate_pack_ev(file_path, config):
    """Backward compatible function that uses the new class structure"""
    calculator = PackEVCalculator(config)
    return calculator.calculate_pack_ev(file_path)