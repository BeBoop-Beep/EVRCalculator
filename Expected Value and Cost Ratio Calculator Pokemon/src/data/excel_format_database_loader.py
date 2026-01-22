"""
Database loader that produces Excel-compatible DataFrame format
Converts database records into the structure expected by the calculation engine
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


class ExcelFormatDatabaseLoader:
    """
    Loads card data from database and formats it exactly like the Excel loader.
    Each row represents one card (not one variant), with columns for:
    - Base card info (name, rarity, card number, EV)
    - Regular holo price
    - Reverse holo price (in separate column)
    - Pull rates from config
    """
    
    def __init__(self, config=None):
        self.df = None
        self.set_id = None
        self.pack_price = None
        self.config = config
    
    def load_and_prepare_set_data(self, set_name: str, pack_price: float = None, config=None) -> tuple:
        """
        Load all cards for a set from database and format like Excel output
        
        Args:
            set_name: Name of the set (e.g., "Prismatic Evolution")
            pack_price: Optional pack price. If not provided, fetches from database.
            config: Optional config for pull rate mappings
            
        Returns:
            Tuple of (DataFrame with card data, pack_price)
        """
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
        
        # Convert to DataFrame in Excel format
        self.df = self._build_excel_format_dataframe(cards, set_id)
        self.pack_price = pack_price
        
        return self.df, self.pack_price
    
    def _get_booster_pack_price(self, set_id: int) -> float:
        """Get the booster pack price from database"""
        try:
            sealed_products = get_sealed_products_by_set(set_id)
            
            # Find booster pack (shortest name with "booster pack")
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
                print(f"[WARN] No price data found for booster pack, using default $0.00")
                return 0.00
                
        except Exception as e:
            print(f"[WARN] Error fetching booster pack price: {e}, using default $0.00")
            return 0.00
    
    def _build_excel_format_dataframe(self, cards: list, set_id: int) -> pd.DataFrame:
        """
        Build DataFrame with one row per card VARIANT (not per card).
        This matches the structure of the old DatabaseCardLoader.
        """
        condition_id = ConditionsService.get_near_mint_condition_id()
        card_data = []
        
        for card in cards:
            # Get all variants for this card
            variants = get_card_variants_by_card_id(card['id'])
            
            if not variants:
                print(f"[WARN] No variants found for card '{card['name']}'")
                continue
            
            rarity_raw = str(card['rarity']).lower().strip()
            rarity_mapping = getattr(self.config, 'RARITY_MAPPING', {}) if self.config else {}
            rarity_group = rarity_mapping.get(rarity_raw, rarity_raw)
            pull_rate_mapping = getattr(self.config, 'PULL_RATE_MAPPING', {}) if self.config else {}
            pull_rate = pull_rate_mapping.get(rarity_raw, 1.0)
            if pull_rate == 0:
                pull_rate = 1.0
            
            # First pass: find reverse-holo price for this card
            reverse_price = 0.0
            for variant in variants:
                if variant.get('printing_type') == 'reverse-holo':
                    reverse_price_data = get_latest_price(variant['id'], condition_id)
                    reverse_price = reverse_price_data.get('market_price', 0.0) if reverse_price_data else 0.0
                    break
            
            # Process all variants - one row per variant
            for variant in variants:
                printing_type = variant.get('printing_type', 'holo')
                special_type = variant.get('special_type')
                
                # Get price for this variant
                price_data = get_latest_price(variant['id'], condition_id)
                price = price_data.get('market_price', 0.0) if price_data else 0.0
                
                # Determine variant label for display
                if printing_type == 'reverse-holo':
                    variant_label = 'regular reverse'
                elif special_type:
                    variant_label = special_type.lower()
                else:
                    variant_label = printing_type
                
                # Create card name with variant suffix if it's a special variant
                if special_type:
                    card_name = f"{card['name']} ({special_type})"
                else:
                    card_name = card['name']
                
                # Determine pull rate: use special_type if present, otherwise use card rarity
                # Special types in database (master ball, pokeball, ace spec, etc.) may need " pattern" suffix
                # to match config keys (master ball pattern, poke ball pattern, ace spec rare, etc.)
                variant_pull_rate = pull_rate
                if special_type:
                    special_type_lower = special_type.lower()
                    # Try with " pattern" suffix first (for all special pattern variants)
                    pattern_key = f"{special_type_lower} pattern"
                    variant_pull_rate = pull_rate_mapping.get(pattern_key, None)
                    # Fall back to exact match without pattern suffix
                    if variant_pull_rate is None:
                        variant_pull_rate = pull_rate_mapping.get(special_type_lower, pull_rate)
                
                # Only populate reverse price for holo and special variant cards (not reverse-holo itself)
                card_reverse_price = reverse_price if printing_type != 'reverse-holo' else 0.0
                
                row = {
                    'id': card['id'],
                    'variant_id': variant['id'],
                    'Card Name': card_name,
                    'Rarity': card['rarity'],
                    'card_number': card.get('card_number', ''),
                    'Price ($)': price,
                    'Pull Rate (1/X)': variant_pull_rate,
                    'Effective_Pull_Rate': 0.0,
                    'rarity_raw': rarity_raw,
                    'rarity_group': rarity_group,
                    'printing_type': printing_type,
                    'special_type': special_type,
                    'variant_label': variant_label,
                    'Reverse Variant Price ($)': card_reverse_price,
                }
                card_data.append(row)
        
        df = pd.DataFrame(card_data)
        
        # Sort by price descending
        df = df.sort_values('Price ($)', ascending=False).reset_index(drop=True)
        
        print(f"Card data prepared: {len(df)} card variants")
        print(f"Price range: ${df['Price ($)'].min():.2f} - ${df['Price ($)'].max():.2f}")
        print(f"Average price: ${df['Price ($)'].mean():.2f}")
        
        return df
    
    def get_dataframe(self) -> pd.DataFrame:
        """Get the loaded DataFrame"""
        if self.df is None:
            raise RuntimeError("No card data loaded. Call load_and_prepare_set_data() first.")
        return self.df
    
    def get_pack_price(self) -> float:
        """Get the pack price"""
        if self.pack_price is None:
            raise RuntimeError("Pack price not set.")
        return self.pack_price
    
    def get_set_id(self) -> int:
        """Get the set ID"""
        if self.set_id is None:
            raise RuntimeError("Set ID not available.")
        return self.set_id
