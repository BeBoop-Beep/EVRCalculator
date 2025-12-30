import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.services.cards_service import CardsService

class CardsController:
    """Controller for card-related operations"""
    
    def __init__(self):
        self.cards_service = CardsService()
    
    def ingest_cards(self, set_id, cards):
        """
        Delegate card ingestion to service layer
        
        Args:
            set_id: UUID of the set these cards belong to
            cards: List of card dictionaries
            
        Returns:
            Dictionary with insertion results
        """
        return self.cards_service.insert_cards(set_id, cards)
