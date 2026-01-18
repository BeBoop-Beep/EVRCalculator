"""
Database Card Loader - Loads card data from database instead of Excel
This serves as the single source of truth for card data used by both
manual calculations and simulation engine.
"""

import sys
import os
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from db.repositories.cards_repository import get_all_cards_for_set
from db.repositories.card_variant_repository import get_card_variants_by_card_id
from db.repositories.card_variant_prices_repository import get_latest_price
from db.repositories.sets_repository import get_set_id_by_name
from db.services.conditions_service import ConditionsService


class DatabaseCardLoader:
    """Loads and prepares card data from the database for calculations"""
    
    def __init__(self):
        self.df = None
        self.set_id = None
        self.pack_price = None
        self.reverse_df = None  # Store reverse variant data separately
    
    def load_cards_for_set(self, set_name: str, pack_price: float = None) -> tuple:
        """
        Load all cards for a set from the database and prepare DataFrame
        
        Args:
            set_name: Name of the set (e.g., "Stellar Crown")
            pack_price: Optional pack price. If not provided, must be set separately.
            
        Returns:
            Tuple of (DataFrame with card data, pack_price)
            
        Raises:
            ValueError: If set not found or no cards exist
        """
        # Get set ID from database
        set_id = get_set_id_by_name(set_name)
        if not set_id:
            raise ValueError(f"Set '{set_name}' not found in database")
        
        self.set_id = set_id
        
        # Get all cards for this set
        cards = get_all_cards_for_set(set_id)
        if not cards:
            raise ValueError(f"No cards found for set '{set_name}'")
        
        print(f"Loaded {len(cards)} cards for set '{set_name}'")
        
        # Convert to DataFrame and enrich with pricing data
        self.df = self._build_card_dataframe(cards, set_id)
        self.pack_price = pack_price
        
        return self.df, self.pack_price
    
    def _build_card_dataframe(self, cards: list, set_id: int) -> pd.DataFrame:
        """
        Build a DataFrame from card records and enrich with pricing data
        
        Args:
            cards: List of card records from database
            set_id: Set ID for fetching prices
            
        Returns:
            DataFrame with card data and prices
        """
        # Get the Near Mint condition ID (cached after first lookup)
        condition_id = ConditionsService.get_near_mint_condition_id()
        
        card_data = []
        reverse_data = []
        
        for card in cards:
            # Get card variants for this card (e.g., holo, reverse-holo, non-holo)
            variants = get_card_variants_by_card_id(card['id'])
            
            if not variants:
                # If no variants exist, skip this card
                print(f"[WARN] No variants found for card '{card['name']}' (ID: {card['id']})")
                continue
            
            # Find holo and reverse-holo variants
            holo_variant = None
            reverse_variant = None
            
            for variant in variants:
                if variant['printing_type'] == 'holo':
                    holo_variant = variant
                elif variant['printing_type'] == 'reverse-holo':
                    reverse_variant = variant
            
            # If no holo, use first available variant
            if not holo_variant:
                holo_variant = variants[0]
            
            # Get price for holo variant
            holo_price_data = get_latest_price(holo_variant['id'], condition_id)
            holo_price = holo_price_data.get('market_price', 0.0) if holo_price_data else 0.0
            
            # Build row data for regular card (holo)
            row = {
                'id': card['id'],
                'variant_id': holo_variant['id'],
                'Card Name': card['name'],
                'Rarity': card['rarity'],
                'card_number': card['card_number'],
                'Price ($)': holo_price,
                'Pull Rate (1/X)': 1.0,  # Placeholder - will be set by config
                'Effective_Pull_Rate': 0.0,  # Will be calculated
                # Add derived columns for compatibility
                'rarity_raw': str(card['rarity']).lower().strip(),
                'rarity_group': str(card['rarity']).lower().strip(),  # Will be mapped by config
                'Reverse Variant Price ($)': None,  # Will be filled if reverse exists
            }
            
            # If reverse-holo variant exists, get its price
            if reverse_variant:
                reverse_price_data = get_latest_price(reverse_variant['id'], condition_id)
                reverse_price = reverse_price_data.get('market_price', 0.0) if reverse_price_data else 0.0
                
                # Create reverse card row
                reverse_row = {
                    'id': card['id'],
                    'variant_id': reverse_variant['id'],
                    'Card Name': card['name'],
                    'Rarity': card['rarity'],
                    'card_number': card['card_number'],
                    'Price ($)': reverse_price,
                    'Pull Rate (1/X)': 1.0,
                    'Effective_Pull_Rate': 0.0,
                    'rarity_raw': str(card['rarity']).lower().strip(),
                    'rarity_group': str(card['rarity']).lower().strip(),
                    'Reverse Variant Price ($)': reverse_price,
                    'printing_type': 'reverse-holo',
                }
                reverse_data.append(reverse_row)
                
                # Also store reverse price in main row for reference
                row['Reverse Variant Price ($)'] = reverse_price
            
            card_data.append(row)
        
        df = pd.DataFrame(card_data)
        
        # Sort by price descending for easier analysis
        df = df.sort_values('Price ($)', ascending=False).reset_index(drop=True)
        
        print(f"Card data prepared: {len(df)} cards")
        print(f"Price range: ${df['Price ($)'].min():.2f} - ${df['Price ($)'].max():.2f}")
        print(f"Average price: ${df['Price ($)'].mean():.2f}")
        
        # Store reverse cards data for later access
        self.reverse_df = pd.DataFrame(reverse_data) if reverse_data else pd.DataFrame()
        if not self.reverse_df.empty:
            print(f"Reverse cards available: {len(self.reverse_df)} cards")
        
        return df
        
        return df
    
    def set_pack_price(self, price: float):
        """
        Set or update the pack price
        
        Args:
            price: Price of a single pack
        """
        self.pack_price = price
        print(f"Pack price set to: ${price:.2f}")
    
    def get_dataframe(self) -> pd.DataFrame:
        """Get the loaded DataFrame"""
        if self.df is None:
            raise RuntimeError("No card data loaded. Call load_cards_for_set() first.")
        return self.df
    
    def get_pack_price(self) -> float:
        """Get the pack price"""
        if self.pack_price is None:
            raise RuntimeError("Pack price not set. Call set_pack_price() or load_cards_for_set() with price parameter.")
        return self.pack_price
    
    def get_set_id(self) -> int:
        """Get the set ID"""
        if self.set_id is None:
            raise RuntimeError("Set ID not available. Call load_cards_for_set() first.")
        return self.set_id
    
    def get_reverse_cards(self) -> pd.DataFrame:
        """Get the reverse variant cards DataFrame"""
        if self.reverse_df is None:
            return pd.DataFrame()  # Return empty DataFrame if no reverse cards
        return self.reverse_df
