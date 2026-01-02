import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.services.sealed_products_service import SealedProductsService

class SealedProductsController:
    """Controller for receiving and validating sealed product ingestion requests"""
    
    def __init__(self):
        self.sealed_products_service = SealedProductsService()
    
    def ingest_sealed_products(self, set_id, sealed_products):
        """
        Receive sealed products payload and delegate to ingestion service.
        
        Args:
            set_id: UUID of the set these products belong to
            sealed_products: List of sealed product dictionaries
            
        Returns:
            Dictionary with ingestion results
        """
        if not sealed_products:
            return {
                'inserted_products': 0,
                'inserted_prices': 0,
                'failed': 0
            }
        
        try:
            result = self.sealed_products_service.insert_sealed_products_with_prices(
                set_id,
                sealed_products
            )
            return result
        except Exception as e:
            print(f"❌ Controller error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
