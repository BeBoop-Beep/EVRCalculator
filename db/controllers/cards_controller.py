import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.cards_repository import insert_cards

class CardsController:
    """Handles card-specific business logic"""
    
    def ingest_cards(self, set_id, cards):
        """
        Process and insert cards into database
        
        Args:
            set_id: UUID of the set these cards belong to
            cards: List of card dictionaries
            
        Returns:
            Dictionary with insertion results
        """
        cards_to_insert = []
        
        for card in cards:
            card_data = {
                'set_id': set_id,
                'name': card.get('name'),
                'rarity': card.get('rarity'),
                'type': card.get('type'),  # Can be None
                'copies_in_pack': card.get('pull_rate'),
            }
            cards_to_insert.append(card_data)
        
        if not cards_to_insert:
            return {'inserted': 0, 'skipped': 0}
        
        # Insert cards (upsert to avoid duplicates)
        result = insert_cards(cards_to_insert)
        inserted_count = len(result) if result else 0
        
        return {
            'inserted': inserted_count,
            'skipped': len(cards_to_insert) - inserted_count
        }
