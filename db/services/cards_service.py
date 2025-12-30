import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.cards_repository import insert_card

class CardsService:
    """Service layer for card business logic"""
    
    def insert_cards(self, set_id, cards):
        """
        Process and insert multiple cards into database
        
        Args:
            set_id: UUID of the set these cards belong to
            cards: List of card dictionaries
            
        Returns:
            Dictionary with insertion results
        """
        if not cards:
            return {'inserted': 0, 'failed': 0}
        
        inserted_count = 0
        failed_count = 0
        
        for card in cards:
            try:
                card_data = {
                    'set_id': set_id,
                    'name': card.get('name'),
                    'rarity': card.get('rarity'),
                    'type': card.get('type'),  # Can be None
                    'copies_in_pack': card.get('pull_rate'),
                }
                
                # Insert card one at a time
                insert_card(card_data)
                inserted_count += 1
                
            except Exception as e:
                print(f"❌ Failed to insert card {card.get('name')}: {e}")
                failed_count += 1
        
        return {
            'inserted': inserted_count,
            'failed': failed_count
        }
