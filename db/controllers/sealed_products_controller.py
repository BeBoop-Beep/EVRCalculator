import sys
import os
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.sealed_repository import insert_sealed_products

class SealedProductsController:
    """Handles sealed product-specific business logic"""
    
    def ingest_sealed_products(self, set_id, sealed_products):
        """
        Process and insert sealed products into database
        
        Args:
            set_id: UUID of the set these products belong to
            sealed_products: List of sealed product dictionaries
            
        Returns:
            Dictionary with insertion results
        """
        products_to_insert = []
        
        for product in sealed_products:
            product_data = {
                'set_id': set_id,
                'name': product.get('name'),
                'product_type': product.get('product_type', 'Sealed Product'),
                'market_price': product.get('prices', {}).get('market'),
                'low_price': product.get('prices', {}).get('low'),
                'currency': 'USD',
                'source': 'TCGPlayer',
                'captured_at': datetime.utcnow().isoformat(),
            }
            products_to_insert.append(product_data)
        
        if not products_to_insert:
            return {'inserted': 0, 'skipped': 0}
        
        # Insert sealed products
        result = insert_sealed_products(products_to_insert)
        inserted_count = len(result) if result else 0
        
        return {
            'inserted': inserted_count,
            'skipped': len(products_to_insert) - inserted_count
        }
