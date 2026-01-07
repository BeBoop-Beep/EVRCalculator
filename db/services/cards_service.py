import sys
import os
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.cards_repository import insert_card, get_card_by_name_and_set, get_card_by_name_number_rarity_and_set, get_all_cards_for_set
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
    
    def _get_condition_id_for_price(self, condition_name):
        """
        Determine the condition ID from condition name.
        
        Args:
            condition_name: The condition name from the card entry (e.g., 'Near Mint', 'Lightly Played')
            
        Returns:
            The condition ID to use
            
        Raises:
            ValueError: If condition cannot be found in database
        """
        conditions_map = self._get_conditions_map()
        
        if condition_name not in conditions_map:
            raise ValueError(f"Condition '{condition_name}' not found in database. Available: {list(conditions_map.keys())}")
        
        return conditions_map[condition_name]
    
    def _extract_variant_info(self, card):
        """
        Extract variant information from card data.
        
        Args:
            card: Card dictionary from payload
            
        Returns:
            Tuple of (printing_type, special_type, edition)
        """
        variant = card.get('variant')
        printing = card.get('printing', 'Normal')
        
        # Determine printing type based on the 'printing' field from payload
        printing_type = 'non-holo'
        if 'holofoil' in printing.lower():
            if 'reverse' in printing.lower():
                printing_type = 'reverse-holo'
            else:
                printing_type = 'holo'
        
        # Extract special type (ex, v, vmax, etc.) from variant field
        special_type = variant if variant else None
        
        # Edition can be extracted if needed
        edition = None
        
        return printing_type, special_type, edition
    
    def insert_cards_with_variants_and_prices(self, set_id, cards):
        print(cards)
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
        # Include rarity in the key because different rarities of the same card are different cards
        cards_by_key = {}
        for card in cards:
            key = (card.get('name'), card.get('card_number'), card.get('rarity'))
            if key not in cards_by_key:
                cards_by_key[key] = []
            cards_by_key[key].append(card)
        
        # Fetch all existing cards for this set once to avoid repeated DB calls
        existing_cards = get_all_cards_for_set(set_id)
        existing_cards_set = {(card['name'], card['card_number'], card['rarity']): card['id'] for card in existing_cards}
        
        # Build a list of new cards to insert (checking against both DB and incoming payload)
        new_cards_to_insert = []
        new_cards_set = set()  # Track what we've already added to new_cards_to_insert
        card_key_to_id = {}  # Will store (name, card_number, rarity) -> card_id for new cards
        
        for (name, card_number, rarity), card_list in cards_by_key.items():
            card_key = (name, card_number, rarity)
            
            # Skip if it already exists in DB
            if card_key in existing_cards_set:
                card_key_to_id[card_key] = existing_cards_set[card_key]
                print(f"[INFO]  Card already exists: {name} (ID: {existing_cards_set[card_key]})")
                continue
            
            # Skip if we've already added this to the new_cards_to_insert list
            if card_key in new_cards_set:
                continue
            
            # Add to new cards list
            card_data = {
                'set_id': set_id,
                'name': name,
                'rarity': rarity,
                'card_number': card_number,
                'copies_in_pack': card_list[0].get('pull_rate'),
            }
            new_cards_to_insert.append(card_data)
            new_cards_set.add(card_key)
        
        # Insert all new cards at once
        for card_data in new_cards_to_insert:
            try:
                card_id = insert_card(card_data)
                results['inserted_cards'] += 1
                card_key = (card_data['name'], card_data['card_number'], card_data['rarity'])
                card_key_to_id[card_key] = card_id
                print(f"[OK] Inserted card: {card_data['name']} (ID: {card_id})")
            except Exception as e:
                error_msg = f"Failed to insert card {card_data['name']}: {e}"
                print(f"[ERROR] {error_msg}")
                results['errors'].append(error_msg)
                results['failed'] += 1
        
        # Now process variants and prices for all cards (both existing and newly inserted)
        for (name, card_number, rarity), card_list in cards_by_key.items():
            try:
                card_key = (name, card_number, rarity)
                if card_key not in card_key_to_id:
                    # Card insertion failed earlier
                    continue
                
                card_id = card_key_to_id[card_key]
                
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
                                condition_name = card_entry.get('condition', 'Near Mint')
                                condition_id = self._get_condition_id_for_price(condition_name)
                                
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
