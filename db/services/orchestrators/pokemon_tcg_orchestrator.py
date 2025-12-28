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
            Dictionary with ingestion results including gameContext_id
        """
        try:
            print("\n🔄 Starting Pokemon TCG data ingestion...")
            
            result = {
                'success': True,
                'gameContext_id': None,
                'details': {}
            }
            
            gameContext_id = None
            
            # HIERARCHICAL ORDER: Collection → TCG → Era → Set → Cards/Sealed Products
            # Note: Collection, TCG, and Era are typically handled within the set creation process
            
            # Step 1: Process Set (this establishes the root context)
            if 'gameContext' in data:
                try:
                    gameContext_id = self.sets_controller.get_or_create_set(data['gameContext'])
                    result['gameContext_id'] = gameContext_id
                    result['details']['gameContext'] = {
                        'status': 'success',
                        'gameContext_id': gameContext_id
                    }
                    print(f"✅ GameContext ready (ID: {gameContext_id})")
                except Exception as e:
                    print(f"❌ Error creating gameContext: {e}")
                    raise
            else:
                print("⚠️  No gameContext data provided - subsequent operations may fail")
            
            # Step 2: Process Cards (depends on gameContext_id)
            if 'cards' in data and gameContext_id:
                try:
                    cards_result = self.cards_controller.ingest_cards(gameContext_id, data['cards'])
                    result['details']['cards'] = cards_result
                    inserted = cards_result.get('inserted', 0)
                    print(f"✅ Processed {inserted} cards")
                except Exception as e:
                    print(f"❌ Error processing cards: {e}")
                    raise
            
            # Step 3: Process Prices (depends on gameContext_id and cards)
            if 'prices' in data and gameContext_id:
                try:
                    prices_result = self.prices_controller.ingest_prices(gameContext_id, data['prices'])
                    result['details']['prices'] = prices_result
                    inserted = prices_result.get('inserted', 0)
                    print(f"✅ Processed {inserted} prices")
                except Exception as e:
                    print(f"❌ Error processing prices: {e}")
                    raise
            
            # Step 4: Process Sealed Products (depends on gameContext_id)
            if 'sealed_products' in data and gameContext_id:
                try:
                    sealed_result = self.sealed_products_controller.ingest_sealed_products(
                        gameContext_id, 
                        data['sealed_products']
                    )
                    result['details']['sealed_products'] = sealed_result
                    inserted = sealed_result.get('inserted', 0)
                    print(f"✅ Processed {inserted} sealed products")
                except Exception as e:
                    print(f"❌ Error processing sealed products: {e}")
                    raise
            
            print(f"\n✅ Pokemon TCG ingestion complete!")
            return result
            
        except Exception as e:
            print(f"❌ Pokemon TCG ingestion error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
