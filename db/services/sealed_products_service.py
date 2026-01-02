import sys
import os
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.sealed_repository import insert_sealed_product, get_sealed_product_by_name_and_set
from db.repositories.sealed_product_prices_repository import insert_sealed_product_price

class SealedProductsService:
    """
    Service layer for sealed product business logic.
    Orchestrates writes to sealed_products and sealed_product_prices tables.
    """
    
    def insert_sealed_products_with_prices(self, set_id, sealed_products):
        """
        Process and insert sealed products with their prices into database.
        
        This method orchestrates:
        1. Insert sealed product into 'sealed_products' table
        2. Insert pricing data into 'sealed_product_prices' table for historical tracking
        
        Args:
            set_id: UUID of the set these products belong to
            sealed_products: List of sealed product dictionaries
            
        Returns:
            Dictionary with detailed insertion results
        """
        if not sealed_products:
            return {
                'inserted_products': 0,
                'inserted_prices': 0,
                'failed': 0,
                'errors': []
            }
        
        results = {
            'inserted_products': 0,
            'inserted_prices': 0,
            'failed': 0,
            'errors': []
        }
        
        for product in sealed_products:
            try:
                product_name = product.get('name')
                product_type = product.get('product_type', 'Sealed Product')
                
                # Check if sealed product already exists
                existing_product = get_sealed_product_by_name_and_set(product_name, set_id)
                
                if existing_product:
                    sealed_product_id = existing_product['id']
                    print(f"ℹ️  Sealed product already exists: {product_name} (ID: {sealed_product_id})")
                else:
                    # Insert new sealed product
                    product_data = {
                        'set_id': set_id,
                        'name': product_name,
                        'product_type': product_type,
                    }
                    
                    sealed_product_id = insert_sealed_product(product_data)
                    results['inserted_products'] += 1
                    print(f"✅ Inserted sealed product: {product_name} (ID: {sealed_product_id})")
                
                # ALWAYS insert price data for this scrape
                # Prices are historical and stored in a separate table
                prices = product.get('prices', {})
                market_price = prices.get('market')
                
                if market_price is not None:
                    try:
                        price_data = {
                            'sealed_product_id': sealed_product_id,
                            'market_price': market_price,
                            'source': product.get('source') or prices.get('source'),
                            'captured_at': datetime.utcnow().isoformat(),
                        }
                        
                        # Only include currency if provided (defaults to USD in DB)
                        currency = prices.get('currency') or product.get('currency')
                        if currency:
                            price_data['currency'] = currency
                        
                        # Insert into sealed_product_prices for historical tracking
                        price_id = insert_sealed_product_price(price_data)
                        results['inserted_prices'] += 1
                        print(f"  ✅ Inserted price: ${market_price} (Price ID: {price_id})")
                    
                    except Exception as e:
                        error_msg = f"Failed to insert price for {product_name}: {e}"
                        print(f"  ❌ {error_msg}")
                        results['errors'].append(error_msg)
                else:
                    print(f"  ⚠️  No market price found for {product_name}")
            
            except Exception as e:
                error_msg = f"Failed to process sealed product {product.get('name')}: {e}"
                print(f"❌ {error_msg}")
                results['errors'].append(error_msg)
                results['failed'] += 1
        
        return results
