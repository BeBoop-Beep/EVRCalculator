import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from db.services.sets_service import SetsService
from db.services.cards_service import CardsService
from db.services.sealed_products_service import SealedProductsService

class PokemonTCGOrchestrator:
    """
    Orchestrates the ingestion of Pokemon TCG data following the hierarchical dependency order:
    Collection → TCG → Era → Set → Cards/Sealed Products
    
    This ensures that parent entities are created before child entities that depend on them.
    """
    
    def __init__(self):
        self.sets_service = SetsService()
        self.cards_service = CardsService()
        self.sealed_products_service = SealedProductsService()
    
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
                    set_id = self.sets_service.get_or_create_set(data['set'])
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
                    cards_result = self.cards_service.insert_cards_with_variants_and_prices(set_id, data['cards'])
                    result['details']['cards'] = cards_result
                    inserted = cards_result.get('inserted', 0)
                    print(f"[OK] Processed {inserted} cards")
                except Exception as e:
                    print(f"[ERROR] Error processing cards: {e}")
                    raise
            
            # Step 3: Process Sealed Products (depends on set_id)
            if 'sealed_products' in data and set_id:
                try:
                    sealed_result = self.sealed_products_service.insert_sealed_products_with_prices(
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
