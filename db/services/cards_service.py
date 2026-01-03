import sys
import os
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.cards_repository import insert_card, get_card_by_name_and_set
from db.repositories.card_variant_repository import insert_card_variant, get_card_variant_by_card_and_type
from db.repositories.card_variant_prices_repository import insert_card_variant_price
from db.repositories.conditions_repository import get_all_conditions, get_condition_by_name

class CardsService:
    """
    Service layer for card business logic.
    Orchestrates writes across cards, card_variants, and card_variant_prices tables.
    """
    
    def __init__(self):
        """Initialize service and cache conditions"""
        self._conditions_cache = None
    
    def _get_conditions_map(self):
        """
        Get a map of condition names to condition IDs.
        Caches the result to avoid repeated DB calls.
        
        Returns:
            Dictionary mapping condition names to condition IDs
        """
        if self._conditions_cache is None:
            conditions = get_all_conditions()
            self._conditions_cache = {cond['name']: cond['id'] for cond in conditions}
        return self._conditions_cache
    
    def _get_condition_id_for_price(self, price_data):
        """
        Determine the condition ID from price data.
        Currently defaults to 'Near Mint' if no condition is specified.
        Can be extended to infer condition from source or other metadata.
        
        Args:
            price_data: Dictionary with price information
            
        Returns:
            The condition ID to use
            
        Raises:
            ValueError: If condition cannot be determined or doesn't exist
        """
        conditions_map = self._get_conditions_map()
        
        # Default to Near Mint for now - can be enhanced later
        default_condition = 'Near Mint'
        
        if default_condition not in conditions_map:
            raise ValueError(f"Default condition '{default_condition}' not found in database")
        
        return conditions_map[default_condition]
    
    def _extract_variant_info(self, card):
        """
        Extract variant information from card data.
        
        Args:
            card: Card dictionary from payload
            
        Returns:
            Tuple of (printing_type, special_type, edition)
        """
        variant = card.get('variant')
        rarity = card.get('rarity', '')
        
        # Determine printing type based on rarity
        printing_type = 'non-holo'
        if 'holo' in rarity.lower():
            printing_type = 'holo'
        elif 'reverse' in rarity.lower():
            printing_type = 'reverse-holo'
        
        # Extract special type (ex, v, vmax, etc.) from variant field
        special_type = variant if variant else None
        
        # Edition can be extracted if needed
        edition = None
        
        return printing_type, special_type, edition
    
    def insert_cards_with_variants_and_prices(self, set_id, cards):
        """
        Process and insert multiple cards with their variants and prices into database.
        
        This method orchestrates the complete flow:
        1. Insert card into 'cards' table
        2. For each unique variant of the card, insert into 'card_variants' table
        3. For each variant, insert price data into 'card_variant_prices' table
        
        Args:
            set_id: UUID of the set these cards belong to
            cards: List of card dictionaries from payload
            
        Returns:
            Dictionary with detailed insertion results
        """
        if not cards:
            return {
                'inserted_cards': 0,
                'inserted_variants': 0,
                'inserted_prices': 0,
                'failed': 0,
                'errors': []
            }
        
        results = {
            'inserted_cards': 0,
            'inserted_variants': 0,
            'inserted_prices': 0,
            'failed': 0,
            'errors': []
        }
        
        # Group cards by unique identifier to avoid duplicates
        cards_by_key = {}
        for card in cards:
            key = (card.get('name'), card.get('card_number'))
            if key not in cards_by_key:
                cards_by_key[key] = []
            cards_by_key[key].append(card)
        
        # Process each unique card
        for (name, card_number), card_list in cards_by_key.items():
            try:
                # Check if card already exists
                existing_card = get_card_by_name_and_set(name, set_id)
                
                if existing_card:
                    card_id = existing_card['id']
                    print(f"[INFO]  Card already exists: {name} (ID: {card_id})")
                else:
                    # Insert new card
                    card_data = {
                        'set_id': set_id,
                        'name': name,
                        'rarity': card_list[0].get('rarity'),
                        'card_number': card_number,
                        'copies_in_pack': card_list[0].get('pull_rate'),
                    }
                    
                    card_id = insert_card(card_data)
                    results['inserted_cards'] += 1
                    print(f"[OK] Inserted card: {name} (ID: {card_id})")
                
                # Process each price entry (which may have different variants)
                for card_entry in card_list:
                    try:
                        # Extract variant information
                        printing_type, special_type, edition = self._extract_variant_info(card_entry)
                        
                        # Get or create the variant
                        # Note: Variants are unique per card and printing type - there should only be 1 of each
                        existing_variant = get_card_variant_by_card_and_type(
                            card_id, printing_type, special_type, edition
                        )
                        
                        if existing_variant:
                            card_variant_id = existing_variant['id']
                            print(f"  [INFO]  Variant already exists: {printing_type}/{special_type} (ID: {card_variant_id})")
                        else:
                            # Insert new card variant
                            variant_data = {
                                'card_id': card_id,
                                'printing_type': printing_type,
                                'special_type': special_type,
                                'edition': edition,
                            }
                            
                            card_variant_id = insert_card_variant(variant_data)
                            results['inserted_variants'] += 1
                            print(f"  [OK] Inserted variant: {printing_type}/{special_type} (ID: {card_variant_id})")
                        
                        # ALWAYS insert price data for this scrape
                        # Prices are historical and can fluctuate over time
                        # Each scrape should record the current price with a new timestamp
                        prices = card_entry.get('prices', {})
                        market_price = prices.get('market')
                        
                        if market_price is not None:
                            try:
                                condition_id = self._get_condition_id_for_price(prices)
                                
                                price_data = {
                                    'card_variant_id': card_variant_id,
                                    'condition_id': condition_id,
                                    'market_price': market_price,
                                    'currency': prices.get('currency') or 'USD',
                                    'source': card_entry.get('source') or prices.get('source'),
                                    'captured_at': datetime.utcnow().isoformat(),
                                    'high_price': prices.get('high'),
                                    'low_price': prices.get('low'),
                                }
                                
                                price_id = insert_card_variant_price(price_data)
                                results['inserted_prices'] += 1
                                print(f"    [OK] Inserted price: ${market_price} (Price ID: {price_id})")
                            
                            except Exception as e:
                                error_msg = f"Failed to insert price for {name}: {e}"
                                print(f"    [ERROR] {error_msg}")
                                results['errors'].append(error_msg)
                        else:
                            print(f"    [WARN]  No market price found for {name}")
                    
                    except Exception as e:
                        error_msg = f"Failed to process variant for {name}: {e}"
                        print(f"  [ERROR] {error_msg}")
                        results['errors'].append(error_msg)
            
            except Exception as e:
                error_msg = f"Failed to process card {name}: {e}"
                print(f"[ERROR] {error_msg}")
                results['errors'].append(error_msg)
                results['failed'] += 1
        
        return results
