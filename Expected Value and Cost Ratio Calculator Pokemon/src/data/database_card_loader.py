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
from db.repositories.sealed_repository import get_sealed_products_by_set
from db.repositories.sealed_product_prices_repository import get_latest_price as get_latest_sealed_price
from db.services.conditions_service import ConditionsService


class DatabaseCardLoader:
    """Loads and prepares card data from the database for calculations"""
    
    def __init__(self, config=None):
        self.df = None
        self.set_id = None
        self.pack_price = None
        self.reverse_df = None  # Store reverse variant data separately
        self.config = config  # Store config for pull rate mapping
    
    def load_and_prepare_set_data(self, set_name: str, pack_price: float = None, config=None) -> tuple:
        """
        Load all cards for a set from database, prepare DataFrame, and fetch pack pricing
        
        Args:
            set_name: Name of the set (e.g., "Stellar Crown")
            pack_price: Optional pack price. If not provided, fetches from database.
            config: Optional config for pull rate mappings
            
        Returns:
            Tuple of (DataFrame with card data, pack_price)
            
        Raises:
            ValueError: If set not found or no cards exist
        """
        # Update config if provided
        if config:
            self.config = config
        # Get set ID from database
        set_id = get_set_id_by_name(set_name)
        if not set_id:
            raise ValueError(f"Set '{set_name}' not found in database")
        
        self.set_id = set_id
        
        # If pack_price not provided, fetch from database
        if pack_price is None:
            pack_price = self._get_booster_pack_price(set_id)
        
        # Get all cards for this set
        cards = get_all_cards_for_set(set_id)
        if not cards:
            raise ValueError(f"No cards found for set '{set_name}'")
        
        print(f"Loaded {len(cards)} cards for set '{set_name}'")
        
        # Convert to DataFrame and enrich with pricing data
        self.df = self._build_card_dataframe(cards, set_id)
        self.pack_price = pack_price
        
        return self.df, self.pack_price
    
    def _get_pull_rate_for_rarity(self, rarity: str) -> float:
        """
        Get the pull rate X value for a given rarity from config.
        Returns X where the actual probability is 1/X.
        
        Args:
            rarity: The rarity value
            
        Returns:
            The pull rate X value (e.g., 66 for common, meaning 1/66 probability)
        """
        if not self.config:
            return 1.0
        
        # Get rarity raw value
        rarity_raw = str(rarity).lower().strip()
        
        # Get pull rate X value from mapping
        # Try rarity_raw first (specific rarity like 'double rare')
        # This matches how Excel files stored pull rates
        pull_rate_mapping = getattr(self.config, 'PULL_RATE_MAPPING', {})
        x_value = pull_rate_mapping.get(rarity_raw, None)
        
        # If not found, try the rarity group (like 'hits')
        if x_value is None:
            rarity_mapping = getattr(self.config, 'RARITY_MAPPING', {})
            rarity_group = rarity_mapping.get(rarity_raw, rarity_raw)
            x_value = pull_rate_mapping.get(rarity_group, 1.0)
        
        # Return X directly (not 1/X)
        if x_value == 0:
            return 1.0
        return x_value
    
    def _get_booster_pack_price(self, set_id: int) -> float:
        """
        Get the booster pack price from the database for this set.
        Looks for a sealed product with 'booster pack' in the name.
        
        Args:
            set_id: The set ID
            
        Returns:
            The latest booster pack price, or 4.00 as fallback
        """
        try:
            # Get all sealed products for this set
            sealed_products = get_sealed_products_by_set(set_id)
            
            # Find booster pack (case-insensitive search)
            # Pick the shortest product name containing "booster pack" to filter out bundles/art sets
            booster_packs = [
                p for p in sealed_products 
                if 'booster pack' in p.get('name', '').lower()
            ]
            booster_pack = min(booster_packs, key=lambda p: len(p.get('name', ''))) if booster_packs else None
            
            if not booster_pack:
                print(f"[WARN] No booster pack found for set ID {set_id}, using default $0.00")
                return 0.00
            
            # Get latest price for this booster pack
            price_data = get_latest_sealed_price(booster_pack['id'])
            if price_data:
                price = price_data.get('market_price', 0.00)
                print(f"[INFO] Booster pack price from DB: ${price:.2f}")
                return price
            else:
                print(f"[WARN] No price data found for booster pack, using default $4.00")
                return 0.00
                
        except Exception as e:
            print(f"[WARN] Error fetching booster pack price: {e}, using default $4.00")
            return 0.00
    
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
            rarity_raw = str(card['rarity']).lower().strip()
            rarity_group = self.config.RARITY_MAPPING.get(rarity_raw, rarity_raw) if self.config else rarity_raw
            
            row = {
                'id': card['id'],
                'variant_id': holo_variant['id'],
                'Card Name': card['name'],
                'Rarity': card['rarity'],
                'card_number': card['card_number'],
                'Price ($)': holo_price,
                'Pull Rate (1/X)': self._get_pull_rate_for_rarity(card['rarity']),
                'Effective_Pull_Rate': 0.0,  # Will be calculated
                # Add derived columns for compatibility
                'rarity_raw': rarity_raw,
                'rarity_group': rarity_group,
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
                    'Pull Rate (1/X)': self._get_pull_rate_for_rarity(card['rarity']),
                    'Effective_Pull_Rate': 0.0,
                    'rarity_raw': rarity_raw,
                    'rarity_group': rarity_group,
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
            raise RuntimeError("No card data loaded. Call load_and_prepare_set_data() first.")
        return self.df
    
    def get_pack_price(self) -> float:
        """Get the pack price"""
        if self.pack_price is None:
            raise RuntimeError("Pack price not set. Call set_pack_price() or load_and_prepare_set_data() with price parameter.")
        return self.pack_price
    
    def get_set_id(self) -> int:
        """Get the set ID"""
        if self.set_id is None:
            raise RuntimeError("Set ID not available. Call load_and_prepare_set_data() first.")
        return self.set_id
    
    def get_reverse_cards(self) -> pd.DataFrame:
        """Get the reverse variant cards DataFrame"""
        if self.reverse_df is None:
            return pd.DataFrame()  # Return empty DataFrame if no reverse cards
        return self.reverse_df
