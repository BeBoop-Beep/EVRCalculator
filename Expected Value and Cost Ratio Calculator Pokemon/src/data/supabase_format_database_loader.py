"""
Supabase Database Loader - Loads card data from Supabase and caches it.

Similar to ExcelFormatDatabaseLoader but pulls from Supabase instead of Excel.
Loads all data at startup and caches in memory for fast access during calculations.
"""

import sys
import os
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from db.repositories.sets_repository import get_set_id_by_name
from db.repositories.cards_repository import get_all_cards_for_set
from db.repositories.card_variant_repository import get_card_variants_by_card_id
from db.repositories.conditions_repository import get_condition_by_name
from db.clients.supabase_client import supabase


class SupabaseFormatDatabaseLoader:
    """
    Loads card data from Supabase and formats it like ExcelFormatDatabaseLoader.
    
    Caches data in memory for fast access during calculations.
    Each row represents one card variant with:
    - Card name, rarity, card number
    - Holo price, reverse holo price
    - Pull rates from config
    """
    
    def __init__(self, config=None):
        self.df = None
        self.set_id = None
        self.pack_price = None
        self.config = config
        self.condition_id = None
    
    def load_and_prepare_set_data(self, set_name: str, pack_price: float = None, config=None) -> tuple:
        """
        Load all cards for a set from Supabase and format like Excel output.
        
        Args:
            set_name: Name of the set (e.g., "Stellar Crown")
            pack_price: Optional pack price. If not provided, fetches from database.
            config: Optional config for pull rate mappings
            
        Returns:
            Tuple of (DataFrame with card data, pack_price)
        """
        if config:
            self.config = config
        
        print(f"[LOAD] Loading data from Supabase for set: {set_name}")
        
        # Step 1: Get set ID
        set_id = get_set_id_by_name(set_name)
        if not set_id:
            raise ValueError(f"Set '{set_name}' not found in Supabase")
        
        self.set_id = set_id
        print(f"[LOAD] ✓ Set ID: {set_id}")
        
        # Step 2: Get Near Mint condition ID
        near_mint = get_condition_by_name("Near Mint")
        if not near_mint:
            print(f"[WARN] 'Near Mint' condition not found, prices may not filter correctly")
            self.condition_id = None
        else:
            self.condition_id = near_mint.get("id")
            print(f"[LOAD] ✓ Condition ID: {self.condition_id}")
        
        # Step 3: Get all cards for this set
        cards = get_all_cards_for_set(set_id)
        if not cards:
            raise ValueError(f"No cards found for set '{set_name}'")
        
        print(f"[LOAD] ✓ Loaded {len(cards)} cards")
        
        # Step 4: Convert to DataFrame (with variants and prices)
        self.df = self._build_dataframe(cards, set_id)
        
        # Step 5: Get pack price from sealed products
        if pack_price is None:
            pack_price = self._get_booster_pack_price(set_id)
        
        self.pack_price = pack_price
        
        print(f"[LOAD] ✓ DataFrame ready: {len(self.df)} rows")
        print(f"[LOAD] ✓ Pack price: ${pack_price:.2f}")
        
        return self.df, self.pack_price
    
    def _build_dataframe(self, cards: list, set_id: str) -> pd.DataFrame:
        """
        Build DataFrame with one row per card variant.
        
        Columns:
        - Card Name
        - Rarity
        - Card #
        - Price (Holo)
        - Price (Reverse)
        - Pull Rate
        """
        rows = []
        pull_rate_mapping = getattr(self.config, 'PULL_RATE_MAPPING', {}) if self.config else {}
        rarity_mapping = getattr(self.config, 'RARITY_MAPPING', {}) if self.config else {}
        
        for card in cards:
            card_name = card.get('name', '')
            card_number = card.get('card_number', '')
            rarity_raw = str(card.get('rarity', '')).lower().strip()
            
            # Map rarity to group
            rarity_group = rarity_mapping.get(rarity_raw, rarity_raw)
            
            # Get pull rate (1/X format)
            pull_rate = pull_rate_mapping.get(rarity_raw, 1.0)
            if pull_rate <= 0:
                pull_rate = 1.0
            
            # Get variants for this card
            variants = get_card_variants_by_card_id(card.get('id'))
            if not variants:
                continue
            
            # Extract prices from variants
            holo_price = 0.0
            reverse_price = 0.0
            
            for variant in variants:
                # Query price observations directly from Supabase
                query = supabase.table("card_variant_price_observations").select("*").eq(
                    "card_variant_id", variant.get('id')
                )
                
                # Filter by condition if available
                if self.condition_id:
                    query = query.eq("condition_id", self.condition_id)
                
                # Get latest price
                query = query.order("captured_at", desc=True).limit(1)
                result = query.execute()
                
                if result.data:
                    price = float(result.data[0].get('market_price', 0.0))
                    
                    if variant.get('printing_type') == 'reverse-holo':
                        reverse_price = max(reverse_price, price)
                    else:
                        holo_price = max(holo_price, price)
            
            # Create row
            row = {
                'Card Name': card_name,
                'Rarity': rarity_group,
                'Card #': card_number,
                'Price (Holo)': holo_price,
                'Price (Reverse)': reverse_price,
                'Pull Rate': pull_rate,
            }
            rows.append(row)
        
        return pd.DataFrame(rows)
    
    def _get_booster_pack_price(self, set_id: str) -> float:
        """Get booster pack price from sealed products."""
        try:
            # Query sealed products for this set
            result = supabase.table("sealed_products").select("*").eq("set_id", set_id).execute()
            
            if not result.data:
                print(f"[WARN] No sealed products found, using default $0.00")
                return 0.0
            
            sealed_products = result.data
            
            # Find booster pack (look for "booster pack" in name)
            booster_packs = [
                p for p in sealed_products
                if 'booster pack' in p.get('name', '').lower()
            ]
            
            if not booster_packs:
                print(f"[WARN] No booster pack found, using default $0.00")
                return 0.0
            
            # Get shortest name (most likely single booster pack)
            booster_pack = min(booster_packs, key=lambda p: len(p.get('name', '')))
            
            # Get latest price
            price_result = supabase.table("sealed_product_price_observations").select("*").eq(
                "sealed_product_id", booster_pack.get('id')
            ).order("captured_at", desc=True).limit(1).execute()
            
            if price_result.data:
                price = float(price_result.data[0].get('market_price', 0.0))
                print(f"[LOAD] ✓ Booster pack price: ${price:.2f}")
                return price
            else:
                print(f"[WARN] No price data for booster pack, using default $0.00")
                return 0.0
        
        except Exception as e:
            print(f"[WARN] Error fetching booster pack price: {e}, using default $0.00")
            return 0.0
