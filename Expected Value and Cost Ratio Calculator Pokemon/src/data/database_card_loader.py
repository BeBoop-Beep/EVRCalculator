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
from db.repositories.card_variant_prices_repository import get_latest_price
from db.repositories.sets_repository import get_set_id_by_name


class DatabaseCardLoader:
    """Loads and prepares card data from the database for calculations"""
    
    def __init__(self):
        self.df = None
        self.set_id = None
        self.pack_price = None
    
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
        card_data = []
        
        for card in cards:
            # Get latest price for this card
            price_data = get_latest_price(card['id'])
            price = price_data.get('market_price', 0.0) if price_data else 0.0
            
            # Build row data
            row = {
                'id': card['id'],
                'Card Name': card['name'],
                'Rarity': card['rarity'],
                'card_number': card['card_number'],
                'Price ($)': price,
                'Effective_Pull_Rate': 0.0,  # Will be calculated by EV calculator
                # Add derived columns for compatibility
                'rarity_raw': str(card['rarity']).lower().strip(),
                'rarity_group': str(card['rarity']).lower().strip(),  # Will be mapped by config
                'Reverse Variant Price ($)': None,  # Database doesn't have reverse pricing yet
            }
            card_data.append(row)
        
        df = pd.DataFrame(card_data)
        
        # Sort by price descending for easier analysis
        df = df.sort_values('Price ($)', ascending=False).reset_index(drop=True)
        
        print(f"Card data prepared: {len(df)} cards")
        print(f"Price range: ${df['Price ($)'].min():.2f} - ${df['Price ($)'].max():.2f}")
        print(f"Average price: ${df['Price ($)'].mean():.2f}")
        
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
