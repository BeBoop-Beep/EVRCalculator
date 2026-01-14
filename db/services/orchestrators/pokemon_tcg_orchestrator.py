import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from db.controllers.sets_controller import SetsController
from db.controllers.cards_controller import CardsController
from db.controllers.prices_controller import PricesController
from db.controllers.sealed_products_controller import SealedProductsController

class PokemonTCGOrchestrator:
    """
    Orchestrates the ingestion of Pokemon TCG data following the hierarchical dependency order:
    Collection → TCG → Era → Set → Cards/Sealed Products
    
    This ensures that parent entities are created before child entities that depend on them.
    """
    
    def __init__(self):
        self.sets_controller = SetsController()
        self.cards_controller = CardsController()
        self.prices_controller = PricesController()
        self.sealed_products_controller = SealedProductsController()
    
    def ingest(self, data):
        """
        Orchestrate the ingestion of Pokemon TCG data in dependency order.
        
        Args:
            data: Dictionary containing optional sections (gameContext, cards, prices, sealed_products)
                  Must contain a 'gameContext' section to establish context for other sections
            
        Returns:
            Dictionary with ingestion results including set_id
        """
        try:
            print("\n[ROUTING] Starting Pokemon TCG data ingestion...")
            print(f"[DEBUG] Data keys received: {list(data.keys())}")
            
            result = {
                'success': True,
                'set_id': None,
                'details': {}
            }
            
            set_id = None
            
            # HIERARCHICAL ORDER: Collection → TCG → Era → Set → Cards/Sealed Products
            # Note: Collection, TCG, and Era are typically handled within the set creation process
            
            # Step 1: Process Set (this establishes the root context)
            if 'set' in data:
                try:
                    set_id = self.sets_controller.get_or_create_set(data['set'])
                    result['set_id'] = set_id
                    result['details']['set'] = {
                        'status': 'success',
                        'set_id': set_id
                    }
                    print(f"[OK] Set ready (ID: {set_id})")
                except Exception as e:
                    print(f"[ERROR] Error creating set: {e}")
                    raise
            else:
                print("[WARN]  No set data provided - subsequent operations may fail")
            
            # Step 2: Process Cards (depends on set_id)
            if 'cards' in data and set_id:
                try:
                    cards_result = self.cards_controller.ingest_cards(set_id, data['cards'])
                    result['details']['cards'] = cards_result
                    inserted = cards_result.get('inserted', 0)
                    print(f"[OK] Processed {inserted} cards")
                except Exception as e:
                    print(f"[ERROR] Error processing cards: {e}")
                    raise
            
            # Step 3: Process Sealed Products (depends on set_id)
            if 'sealed_products' in data and set_id:
                try:
                    sealed_result = self.sealed_products_controller.ingest_sealed_products(
                        set_id, 
                        data['sealed_products']
                    )
                    result['details']['sealed_products'] = sealed_result
                    inserted = sealed_result.get('inserted', 0)
                    print(f"[OK] Processed {inserted} sealed products")
                except Exception as e:
                    print(f"[ERROR] Error processing sealed products: {e}")
                    raise
            
            print(f"\n[OK] Pokemon TCG ingestion complete!")
            return result
            
        except Exception as e:
            print(f"[ERROR] Pokemon TCG ingestion error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
