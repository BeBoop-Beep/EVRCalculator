import sys
import os

# Add path to import controllers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.controllers.sets_controller import SetsController
from db.controllers.cards_controller import CardsController
from db.controllers.prices_controller import PricesController
from db.controllers.sealed_products_controller import SealedProductsController

class IngestService:
    """Service layer for data ingestion - coordinates domain-specific business logic"""
    
    def __init__(self):
        self.sets_controller = SetsController()
        self.cards_controller = CardsController()
        self.prices_controller = PricesController()
        self.sealed_products_controller = SealedProductsController()
    
    def process_ingestion(self, payload):
        """
        Orchestrate data ingestion by distributing to domain controllers
        
        Args:
            payload: Dictionary containing set, cards, and sealed_products
            
        Returns:
            Dictionary with ingestion results
        """
        try:
            print("\n🔄 Starting database ingestion...")
            
            # Step 1: Handle set data
            set_data = payload.get('set', {})
            set_id = self.sets_controller.get_or_create_set(set_data)
            if not set_id:
                raise Exception("Failed to get/create set")
            
            print(f"✅ Set ready: {set_data.get('name')} (ID: {set_id})")
            
            # Step 2: Handle cards
            cards = payload.get('cards', [])
            cards_result = self.cards_controller.ingest_cards(set_id, cards)
            print(f"✅ Processed {cards_result['inserted']} cards")
            
            # Step 3: Handle card prices
            prices_result = self.prices_controller.ingest_prices(set_id, cards)
            print(f"✅ Processed {prices_result['inserted']} prices")
            
            # Step 4: Handle sealed products
            sealed_products = payload.get('sealed_products', [])
            sealed_result = {'inserted': 0, 'skipped': 0}
            if sealed_products:
                sealed_result = self.sealed_products_controller.ingest_sealed_products(set_id, sealed_products)
                print(f"✅ Processed {sealed_result['inserted']} sealed products")
            
            result = {
                'success': True,
                'set_id': set_id,
                'cards': cards_result,
                'prices': prices_result,
                'sealed_products': sealed_result
            }
            
            print(f"\n✅ Ingestion complete!")
            return result
            
        except Exception as e:
            print(f"❌ Ingestion service error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

