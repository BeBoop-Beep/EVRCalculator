import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

class PricesController:
    """
    DEPRECATED: Prices are now handled within CardsService.insert_cards_with_variants_and_prices()
    This controller is kept for backwards compatibility but should not be used.
    """
    
    def __init__(self):
        pass
    
    def ingest_prices(self, set_id, cards):
        """
        DEPRECATED: Prices are handled during card ingestion.
        This method is kept as a stub and returns empty results.
        
        Args:
            set_id: UUID of the set
            cards: List of card dictionaries with price information
            
        Returns:
            Dictionary with empty insertion results
        """
        return {
            'inserted': 0,
            'skipped': 0,
            'note': 'Prices are handled within card ingestion process'
        }
