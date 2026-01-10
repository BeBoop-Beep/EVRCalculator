import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.sealed_repository import insert_sealed_product, get_sealed_product_by_name_and_set, insert_sealed_products_batch
from db.repositories.sealed_product_prices_repository import insert_sealed_product_price, insert_sealed_product_prices_batch

class SealedProductsService:
    """
    Service layer for sealed product business logic.
    Orchestrates writes to sealed_products and sealed_product_prices tables.
    """
    
    # Thread pool size for concurrent sealed product processing
    # Reduced to 4 to avoid socket exhaustion and connection pool limits
    THREAD_POOL_SIZE = 4
    
    def __init__(self):
        """Initialize service"""
        pass
    
    def _prepare_sealed_product_data(self, product, set_id):
        """
        Prepare (parse and validate) sealed product data WITHOUT database writes.
        This runs in parallel threads - safe because no DB access.
        
        Args:
            product: Sealed product dictionary
            set_id: Set ID for looking up existing products
            
        Returns:
            Tuple of (product_data, price_data, product_name, errors)
        """
        product_name = product.get('name')
        product_type = product.get('product_type', 'Sealed Product')
        errors = []
        
        try:
            product_data = {
                'set_id': set_id,
                'name': product_name,
                'product_type': product_type,
            }
            
            # Prepare price data
            prices = product.get('prices', {})
            market_price = prices.get('market')
            
            price_data = None
            
            if market_price is not None:
                try:
                    price_data = {
                        'market_price': market_price,
                        'source': product.get('source') or prices.get('source'),
                        'captured_at': datetime.utcnow().isoformat(),
                    }
                    
                    # Only include currency if provided
                    currency = prices.get('currency') or product.get('currency')
                    if currency:
                        price_data['currency'] = currency
                
                except Exception as e:
                    error_msg = f"Failed to prepare price for {product_name}: {e}"
                    errors.append(error_msg)
            
            return product_data, price_data, product_name, errors
        
        except Exception as e:
            error_msg = f"Failed to prepare sealed product {product_name}: {e}"
            errors.append(error_msg)
            return None, None, product_name, errors
    
    def _database_writer_thread_sealed(self, work_partition, results_queue, write_lock, writer_id):
        """
        Worker thread that processes a partition of sealed product work items sequentially.
        Uses local + shared product cache to minimize DB lookups and lock contention.
        - Inserts new products immediately to get IDs
        - Batches prices with correct product IDs
        
        Args:
            work_partition: List containing (product_data, price_data, product_name) tuples
            results_queue: Queue to put results into
            write_lock: RLock for thread-safe database access
            writer_id: ID of this writer thread (for logging)
        """
        products_inserted = 0
        prices_inserted = 0
        prices_batch = []
        BATCH_SIZE = 50  # Batch prices in groups of 50
        
        # Local product cache: (set_id, product_name) -> product_id
        # This prevents redundant DB lookups for the same product within this partition
        product_cache = {}
        
        print(f"[Writer {writer_id}] Starting with {len(work_partition)} items")
        
        for item_index, item in enumerate(work_partition):
            try:
                product_data, price_data, product_name = item
                sealed_product_id = None
                
                # Create cache key for this product
                cache_key = (product_data['set_id'], product_name)
                
                # Check local cache first (FAST - no lock, no DB call)
                if cache_key in product_cache:
                    sealed_product_id = product_cache[cache_key]
                    # Only log periodically to reduce spam
                    if item_index % 50 == 0:
                        print(f"[Writer {writer_id}] [CACHE] Using cached product: {product_name} (ID: {sealed_product_id})")
                else:
                    # Check shared cache (lock-protected, but only briefly)
                    with self._cache_lock:
                        if cache_key in self._shared_product_cache:
                            sealed_product_id = self._shared_product_cache[cache_key]
                            print(f"[Writer {writer_id}] [SHARED] Found product in shared cache: {product_name} (ID: {sealed_product_id})")
                        else:
                            sealed_product_id = None
                    
                    if sealed_product_id is None:
                        # Not in any cache - check DB (NO lock - Supabase handles concurrency)
                        existing_product = get_sealed_product_by_name_and_set(product_name, product_data['set_id'])
                        
                        if existing_product:
                            sealed_product_id = existing_product['id']
                            print(f"[Writer {writer_id}] [DB] Sealed product already exists: {product_name} (ID: {sealed_product_id})")
                        else:
                            # Insert new product immediately to get its ID
                            # NO lock here - Supabase client handles concurrent inserts safely
                            try:
                                sealed_product_id = insert_sealed_product(product_data)
                                products_inserted += 1
                                print(f"[Writer {writer_id}] [OK] Inserted sealed product: {product_name} (ID: {sealed_product_id})")
                            except Exception as e:
                                print(f"[Writer {writer_id}] [ERROR] Failed to insert sealed product: {e}")
                                results_queue.put(('ERROR', str(e)))
                                continue
                        
                        # Add to shared cache so other threads can find it (lock-protected, brief)
                        with self._cache_lock:
                            self._shared_product_cache[cache_key] = sealed_product_id
                    
                    # Also add to local cache
                    product_cache[cache_key] = sealed_product_id
                
                # Now add price for this product to batch with correct ID
                if price_data:
                    price_data['sealed_product_id'] = sealed_product_id
                    prices_batch.append(price_data)
                
                # Flush price batch when it reaches the threshold
                if len(prices_batch) >= BATCH_SIZE:
                    try:
                        inserted_ids = insert_sealed_product_prices_batch(prices_batch)
                        prices_inserted += len(inserted_ids)
                        print(f"[Writer {writer_id}] [BATCH] Flushed {len(inserted_ids)} sealed product prices")
                        prices_batch = []
                    except Exception as e:
                        print(f"[Writer {writer_id}] [ERROR] Batch sealed price insert failed: {e}")
                        results_queue.put(('ERROR', str(e)))
                        prices_batch = []
            
            except Exception as e:
                error_msg = f"Writer thread {writer_id} error processing item {item_index}: {e}"
                print(f"[ERROR] {error_msg}")
                results_queue.put(('ERROR', error_msg))
        
        # Flush any remaining price batch
        if prices_batch:
            try:
                ids = insert_sealed_product_prices_batch(prices_batch)
                prices_inserted += len(ids)
                print(f"[Writer {writer_id}] [BATCH] Flushed final {len(ids)} sealed product prices")
            except Exception as e:
                print(f"[Writer {writer_id}] [ERROR] Failed to batch insert final sealed prices: {e}")
                results_queue.put(('ERROR', str(e)))
            prices_batch = []
        
    
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
        
        # Phase 1: Prepare all sealed product data in parallel (no DB access - safe)
        print(f"\n[INFO] Phase 1: Preparing {len(sealed_products)} sealed products in parallel...")
        
        work_items = []
        all_errors = []
        
        with ThreadPoolExecutor(max_workers=self.THREAD_POOL_SIZE) as executor:
            futures = {}
            
            # Submit all preparation tasks
            for i, product in enumerate(sealed_products):
                future = executor.submit(
                    self._prepare_sealed_product_data,
                    product,
                    set_id
                )
                futures[future] = i
            
            # Collect prepared data and accumulate it
            for future in as_completed(futures):
                try:
                    product_data, price_data, product_name, errors = future.result(timeout=60)
                    all_errors.extend(errors)
                    
                    if product_data:
                        work_items.append((product_data, price_data, product_name))
                    
                except TimeoutError:
                    error_msg = f"Timeout (60s) preparing sealed products"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
                except Exception as e:
                    error_msg = f"Error preparing sealed products: {e}"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
        
        # Phase 2: Sequential batch writing (eliminates race conditions)
        print(f"\n[INFO] Phase 2: Sequential batch writing of {len(work_items)} prepared items...")
        
        print(f"[INFO] Writing {len(work_items)} sealed products sequentially with batch operations...")
        
        # Single-threaded sequential writing with batching
        product_cache = {}  # Local cache to track inserted products
        prices_batch = []
        BATCH_SIZE = 50  # Conservative batch size for sealed products
        
        for item_index, (product_data, price_data, product_name) in enumerate(work_items):
            try:
                cache_key = (product_data['set_id'], product_name)
                sealed_product_id = None
                
                # Check local cache first
                if cache_key in product_cache:
                    sealed_product_id = product_cache[cache_key]
                    if item_index % 50 == 0:
                        print(f"[CACHE] Using cached product: {product_name} (ID: {sealed_product_id})")
                else:
                    # Check if already exists in DB
                    existing_product = get_sealed_product_by_name_and_set(product_name, product_data['set_id'])
                    if existing_product:
                        sealed_product_id = existing_product['id']
                        print(f"[DB] Sealed product already exists: {product_name} (ID: {sealed_product_id})")
                    else:
                        # Insert new product immediately to get its ID
                        sealed_product_id = insert_sealed_product(product_data)
                        results['inserted_products'] += 1
                        print(f"[OK] Inserted sealed product: {product_name} (ID: {sealed_product_id})")
                    
                    # Cache it
                    product_cache[cache_key] = sealed_product_id
                
                # Add price to batch with correct product ID
                if price_data:
                    price_data['sealed_product_id'] = sealed_product_id
                    prices_batch.append(price_data)
                
                # Flush price batch when it reaches threshold
                if len(prices_batch) >= BATCH_SIZE:
                    try:
                        inserted_ids = insert_sealed_product_prices_batch(prices_batch)
                        results['inserted_prices'] += len(inserted_ids)
                        print(f"[BATCH] Flushed {len(inserted_ids)} sealed product prices")
                        prices_batch = []
                    except Exception as e:
                        print(f"[ERROR] Batch price insert failed: {e}")
                        all_errors.append(str(e))
                        prices_batch = []
            
            except Exception as e:
                error_msg = f"Error processing item {item_index}: {e}"
                print(f"[ERROR] {error_msg}")
                all_errors.append(error_msg)
        
        # Flush final price batch
        if prices_batch:
            try:
                ids = insert_sealed_product_prices_batch(prices_batch)
                results['inserted_prices'] += len(ids)
                print(f"[BATCH] Flushed final {len(ids)} sealed product prices")
            except Exception as e:
                print(f"[ERROR] Failed to batch insert final prices: {e}")
                all_errors.append(str(e))
        
        results['errors'].extend(all_errors)
        
        print(f"[INFO] Sequential batch writing complete. Inserted {results['inserted_products']} products, {results['inserted_prices']} prices")
        
        return results
