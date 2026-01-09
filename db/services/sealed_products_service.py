import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
import threading

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
        """Initialize service and shared caches"""
        # Shared product cache across all writers: (set_id, product_name) -> product_id
        # Protected by lock to ensure thread-safe access
        self._shared_product_cache = {}
        self._cache_lock = threading.Lock()
    
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
        
        print(f"[Writer {writer_id}] Completed: +{products_inserted} products, +{prices_inserted} prices (local cache: {len(product_cache)}, shared cache size: {len(self._shared_product_cache)})")
        results_queue.put(('DONE', products_inserted, prices_inserted))
    
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
        
        work_queue = Queue()
        results_queue = Queue()
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
            
            # Collect prepared data and queue it
            for future in as_completed(futures):
                try:
                    product_data, price_data, product_name, errors = future.result(timeout=60)
                    all_errors.extend(errors)
                    
                    if product_data:
                        work_queue.put((product_data, price_data, product_name))
                    
                except TimeoutError:
                    error_msg = f"Timeout (60s) preparing sealed products"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
                except Exception as e:
                    error_msg = f"Error preparing sealed products: {e}"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
        
        # Phase 2: Partition work and assign to writers (NO shared queue - no overlap!)
        print(f"\n[INFO] Phase 2: Partitioning {work_queue.qsize()} items into {self.THREAD_POOL_SIZE} equal parts...")
        
        # Convert queue to list for partitioning
        all_work_items = []
        while not work_queue.empty():
            all_work_items.append(work_queue.get())
        
        # Partition work evenly across writers
        partition_size = len(all_work_items) // self.THREAD_POOL_SIZE
        work_partitions = []
        for i in range(self.THREAD_POOL_SIZE):
            start_idx = i * partition_size
            end_idx = start_idx + partition_size if i < self.THREAD_POOL_SIZE - 1 else len(all_work_items)
            work_partitions.append(all_work_items[start_idx:end_idx])
        
        print(f"[INFO] Partition sizes: {[len(p) for p in work_partitions]}")
        
        # Phase 2: Write all data with partitioned work (NO overlap, true parallelism)
        print(f"\n[INFO] Phase 2: Starting {self.THREAD_POOL_SIZE} writer threads with partitioned work...")
        
        results_queue = Queue()
        write_lock = threading.RLock()  # Lock only for DB access, not for product checking
        writer_threads = []
        
        # Start writer threads with their own work partitions
        for writer_id in range(self.THREAD_POOL_SIZE):
            writer_thread = threading.Thread(
                target=self._database_writer_thread_sealed,
                args=(work_partitions[writer_id], results_queue, write_lock, writer_id),
                daemon=False,
                name=f"SealedWriter-{writer_id}"
            )
            writer_thread.start()
            writer_threads.append(writer_thread)
        
        # Collect results from all writers
        completed_writers = 0
        while completed_writers < self.THREAD_POOL_SIZE:
            try:
                result = results_queue.get(timeout=30)
                if result[0] == 'DONE':
                    results['inserted_products'] += result[1]
                    results['inserted_prices'] += result[2]
                    completed_writers += 1
                    print(f"[INFO] Writer completed: +{result[1]} products, +{result[2]} prices")
                elif result[0] == 'ERROR':
                    all_errors.append(result[1])
            except:
                break
        
        # Wait for all writer threads to finish
        for writer_thread in writer_threads:
            writer_thread.join(timeout=30)
        
        results['errors'].extend(all_errors)
        
        print(f"[INFO] Partitioned multi-threaded batch writing complete. Inserted {results['inserted_prices']} prices")
        
        return results
