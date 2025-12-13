import sys
import os
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.cards_repository import get_card_by_set_and_name
from db.repositories.card_variant_prices_repository import insert_card_prices

class PricesController:
    """Handles price-specific business logic"""
    
    def ingest_prices(self, set_id, cards):
        """
        Process and insert card prices into database
        
        Args:
            set_id: UUID of the set
            cards: List of card dictionaries with price information
            
        Returns:
            Dictionary with insertion results
        """
        prices_to_insert = []
        cards_not_found = []
        
        for card in cards:
            # Get the card from DB to get its ID
            card_record = get_card_by_set_and_name(set_id, card.get('name'))
            if not card_record:
                cards_not_found.append(card.get('name'))
                continue
            
            card_id = card_record['id']
            prices = card.get('prices', {})
            market_price = prices.get('market')
            
            if market_price:
                price_data = {
                    'card_id': card_id,
                    'condition_id': None,  # Not tracking condition yet
                    'grading_company_id': None,
                    'grade_value': None,
                    'market_value': market_price,
                    'reverse_variant_price': prices.get('reverse'),
                    'holo_variant_price': prices.get('holo'),
                    'currency': 'USD',
                    'source': 'TCGPlayer',
                    'captured_at': datetime.utcnow().isoformat(),
                }
                prices_to_insert.append(price_data)
        
        if cards_not_found:
            print(f"⚠️ {len(cards_not_found)} cards not found in DB")
        
        if not prices_to_insert:
            return {'inserted': 0, 'skipped': len(cards)}
        
        result = insert_card_prices(prices_to_insert)
        inserted_count = len(result) if result else 0
        
        return {
            'inserted': inserted_count,
            'skipped': len(cards) - inserted_count
        }
