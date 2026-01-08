import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.sealed_repository import insert_sealed_product, get_sealed_product_by_name_and_set
from db.repositories.sealed_product_prices_repository import insert_sealed_product_price

class SealedProductsService:
    """
    Service layer for sealed product business logic.
    Orchestrates writes to sealed_products and sealed_product_prices tables.
    """
    
    # Thread pool size for concurrent sealed product processing
    # Reduced to 4 to avoid socket exhaustion and connection pool limits
    THREAD_POOL_SIZE = 4
    
    def _insert_sealed_price_task(self, price_data, product_name, market_price):
        """
        Helper method for threading sealed product price insertions.
        
        Args:
            price_data: Dictionary of price data to insert
            product_name: Product name for logging
            market_price: Price value for logging
            
        Returns:
            Tuple of (price_id, error_msg) or (None, error_msg) on failure
        """
        try:
            price_id = insert_sealed_product_price(price_data)
            print(f"  [OK] Inserted price: ${market_price} (Price ID: {price_id})")
            return price_id, None
        except Exception as e:
            error_msg = f"Failed to insert price for {product_name}: {e}"
            print(f"  [ERROR] {error_msg}")
            return None, error_msg
    
    def _process_sealed_product_task(self, product, set_id):
        """
        Process a single sealed product (runs in thread pool).
        
        Args:
            product: Sealed product dictionary
            set_id: Set ID for looking up existing products
            
        Returns:
            Tuple of (product_inserted, price_data, errors)
        """
        product_name = product.get('name')
        product_type = product.get('product_type', 'Sealed Product')
        price_to_insert = None
        errors = []
        product_inserted = 0
        
        try:
            # Check if sealed product already exists
            existing_product = get_sealed_product_by_name_and_set(product_name, set_id)
            
            if existing_product:
                sealed_product_id = existing_product['id']
                print(f"[INFO]  Sealed product already exists: {product_name} (ID: {sealed_product_id})")
            else:
                # Insert new sealed product
                product_data = {
                    'set_id': set_id,
                    'name': product_name,
                    'product_type': product_type,
                }
                
                sealed_product_id = insert_sealed_product(product_data)
                product_inserted = 1
                print(f"[OK] Inserted sealed product: {product_name} (ID: {sealed_product_id})")
            
            # Build price data for later insertion
            prices = product.get('prices', {})
            market_price = prices.get('market')
            
            if market_price is not None:
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
                
                price_to_insert = (price_data, product_name, market_price)
            else:
                print(f"  [WARN]  No market price found for {product_name}")
        
        except Exception as e:
            error_msg = f"Failed to process sealed product {product_name}: {e}"
            print(f"[ERROR] {error_msg}")
            errors.append(error_msg)
        
        return product_inserted, price_to_insert, errors
    
    def insert_sealed_products_with_prices(self, set_id, sealed_products):
        """
        Process and insert sealed products with their prices into database.
        
        This method orchestrates:
        1. Insert sealed product into 'sealed_products' table (in threads)
        2. Insert pricing data into 'sealed_product_prices' table for historical tracking (in threads)
        
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
        
        # Process sealed products SEQUENTIALLY
        # Sequential processing is more reliable and consistent
        print(f"\n[INFO] Starting sequential processing of {len(sealed_products)} sealed products...")
        
        for product in sealed_products:
            try:
                product_inserted, price_data, errors = self._process_sealed_product_task(product, set_id)
                results['inserted_products'] += product_inserted
                results['errors'].extend(errors)
                
                # Insert price immediately (sequential)
                if price_data:
                    price_data_tuple, product_name, market_price = price_data
                    try:
                        price_id, error_msg = self._insert_sealed_price_task(price_data_tuple, product_name, market_price)
                        if price_id:
                            results['inserted_prices'] += 1
                        elif error_msg:
                            results['errors'].append(error_msg)
                    except Exception as e:
                        error_msg = f"Unexpected error in sealed price insertion: {e}"
                        print(f"[ERROR] {error_msg}")
                        results['errors'].append(error_msg)
            
            except Exception as e:
                error_msg = f"Unexpected error processing sealed product: {e}"
                print(f"[ERROR] {error_msg}")
                results['errors'].append(error_msg)
        
        print(f"[INFO] Sequential sealed product processing complete")
        
        return results
