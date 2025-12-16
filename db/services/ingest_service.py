import sys
import os

# Add path to import controllers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.controllers.sets_controller import SetsController
from db.controllers.cards_controller import CardsController
from db.controllers.prices_controller import PricesController
from db.controllers.sealed_products_controller import SealedProductsController
from constants.ingest.ingest_handlers import INGEST_HANDLERS

class IngestService:
    """Generic service for ingesting any product type - routes based on available data"""
    
    def __init__(self):
        self.sets_controller = SetsController()
        self.cards_controller = CardsController()
        self.prices_controller = PricesController()
        self.sealed_products_controller = SealedProductsController()
    
    def ingest(self, data):
        """
        Generic ingest method that handles any product type
        Routes based on available data sections and their handlers
        
        Args:
            data: Dictionary containing optional sections (set, cards, prices, sealed_products, etc.)
            
        Returns:
            Dictionary with ingestion results
        """
        try:
            print("\n🔄 Starting data ingestion...")
            
            result = {
                'success': True,
                'set_id': None,
            }
            
            set_id = None
            
            # Process each section that has data
            for section_name, handler_config in INGEST_HANDLERS.items():
                section_data = data.get(section_name)
                
                # Skip if no data for this section
                if not section_data:
                    continue
                
                # Check dependencies (default to False if not specified)
                requires_set_id = handler_config.get('requires_set_id', False)
                if requires_set_id and not set_id:
                    print(f"⚠️  {section_name} requires set_id - skipping")
                    continue
                
                # Get controller and method
                controller = getattr(self, handler_config['controller'])
                method = getattr(controller, handler_config['method'])
                
                # Call handler with appropriate args
                try:
                    if requires_set_id:
                        handler_result = method(set_id, section_data)
                    else:
                        handler_result = method(section_data)
                    
                    # Store result
                    result[section_name] = handler_result
                    
                    # Capture set_id if this handler returns it
                    returns_set_id = handler_config.get('returns_set_id', False)
                    if returns_set_id:
                        set_id = handler_result
                        result['set_id'] = set_id
                        print(f"✅ {section_name} ready (ID: {set_id})")
                    else:
                        inserted = handler_result.get('inserted', 0)
                        print(f"✅ Processed {inserted} {section_name}")
                        
                except Exception as e:
                    print(f"❌ Error processing {section_name}: {e}")
                    raise
            
            print(f"\n✅ Ingestion complete!")
            return result
            
        except Exception as e:
            print(f"❌ Ingestion error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

