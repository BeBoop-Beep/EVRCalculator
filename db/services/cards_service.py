import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.cards_repository import insert_card, insert_cards_batch, get_card_by_name_and_set, get_card_by_name_number_rarity_and_set, get_all_cards_for_set
from db.repositories.card_variant_repository import insert_card_variant, get_card_variant_by_card_and_type, insert_card_variants_batch
from db.repositories.card_variant_prices_repository import insert_card_variant_price, insert_card_variant_prices_batch
from db.repositories.conditions_repository import get_all_conditions, get_condition_by_name

class CardsService:
    """
    Service layer for card business logic.
    Orchestrates writes across cards, card_variants, and card_variant_prices tables.
    """
    
    # Thread pool size for concurrent card processing
    # Reduced to 5 to avoid socket exhaustion and connection pool limits
    THREAD_POOL_SIZE = 5
    
    def __init__(self):
        """Initialize service and cache conditions"""
        self._conditions_cache = None
    
    def _get_conditions_map(self):
        """
        Get a map of condition names to condition IDs.
        Caches the result to avoid repeated DB calls.
        
        Returns:
            Dictionary mapping condition names to condition IDs
        """
        if self._conditions_cache is None:
            conditions = get_all_conditions()
            self._conditions_cache = {cond['name']: cond['id'] for cond in conditions}
        return self._conditions_cache
    
    def _get_condition_id_for_price(self, condition_name):
        """
        Determine the condition ID from condition name.
        
        Args:
            condition_name: The condition name from the card entry (e.g., 'Near Mint', 'Lightly Played')
            
        Returns:
            The condition ID to use
            
        Raises:
            ValueError: If condition cannot be found in database
        """
        conditions_map = self._get_conditions_map()
        
        if condition_name not in conditions_map:
            available = list(conditions_map.keys())
            raise ValueError(f"Condition '{condition_name}' not found in database. Available: {available}")
        
        return conditions_map[condition_name]
    
    def _extract_variant_info(self, card):
        """
        Extract variant information from card data.
        
        Args:
            card: Card dictionary from payload
            
        Returns:
            Tuple of (printing_type, special_type, edition)
        """
        variant = card.get('variant')
        printing = (card.get('printing') or '').strip().lower()
        
        # Determine printing type based on the 'printing' field from payload
        printing_type = 'non-holo'
        if 'holofoil' in printing or 'holo' in printing:
            if 'reverse' in printing:
                printing_type = 'reverse-holo'
            else:
                printing_type = 'holo'
        
        # Extract special type (ex, v, vmax, etc.) from variant field
        special_type = variant if variant else None
        
        # Edition can be extracted if needed
        edition = None
        
        return printing_type, special_type, edition
    
    def _prepare_card_data(self, card_key, card_id, card_list):
        """
        Prepare (parse and validate) card data WITHOUT database writes.
        This runs in parallel threads - safe because no DB access.
        
        Args:
            card_key: Tuple of (name, card_number, rarity)
            card_id: The ID of the card in database
            card_list: List of card entries for this card
            
        Returns:
            List of tuples: (variant_data, price_data_list, errors)
        """
        name, card_number, rarity = card_key
        work_items = []
        errors = []
        
        try:
            for card_entry in card_list:
                try:
                    # Extract variant information (no DB access, just parsing)
                    printing_type, special_type, edition = self._extract_variant_info(card_entry)
                    
                    variant_data = {
                        'card_id': card_id,
                        'printing_type': printing_type,
                        'special_type': special_type,
                        'edition': edition,
                    }
                    
                    # Prepare price data
                    prices = card_entry.get('prices', {})
                    market_price = prices.get('market')
                    
                    price_data_list = []
                    
                    if market_price is not None:
                        try:
                            condition_name = card_entry.get('condition', 'Near Mint')
                            try:
                                condition_id = self._get_condition_id_for_price(condition_name)
                            except ValueError as e:
                                error_msg = f"Invalid condition '{condition_name}' for {name}: {e}"
                                errors.append(error_msg)
                                continue
                            
                            price_data = {
                                'condition_id': condition_id,
                                'market_price': market_price,
                                'currency': prices.get('currency') or 'USD',
                                'source': card_entry.get('source') or prices.get('source'),
                                'captured_at': datetime.utcnow().isoformat(),
                                'high_price': prices.get('high'),
                                'low_price': prices.get('low'),
                            }
                            price_data_list.append(price_data)
                        except Exception as e:
                            error_msg = f"Failed to prepare price for {name}: {e}"
                            errors.append(error_msg)
                    
                    work_items.append((variant_data, price_data_list, card_key))
                
                except Exception as e:
                    error_msg = f"Failed to prepare variant for {name}: {e}"
                    errors.append(error_msg)
        
        except Exception as e:
            error_msg = f"Failed to prepare card {name}: {e}"
            errors.append(error_msg)
        
        return work_items, errors
    
    def _database_writer_thread(self, work_partition, results_queue, write_lock, writer_id):
        """
        Worker thread that processes its own partition of work.
        No shared queue = no redundant variant checks across writers.
        Each writer handles unique cards independently.
        Uses local variant cache + shared variant cache to minimize DB lookups.
        
        Args:
            work_partition: List of (variant_data, price_data_list, card_key) tuples for this writer
            results_queue: Queue to put results into
            write_lock: RLock for thread-safe database access
            writer_id: ID of this writer thread (for logging)
        """
        variants_inserted = 0
        prices_inserted = 0
        prices_batch = []
        BATCH_SIZE = 100  # Batch prices in groups of 100
        
        # Local variant cache: (card_id, printing_type, special_type, edition) -> variant_id
        # This prevents redundant DB lookups for the same variant within this partition
        variant_cache = {}
        
        print(f"[Writer {writer_id}] Starting with {len(work_partition)} items")
        
        for item_index, item in enumerate(work_partition):
            try:
                variant_data, price_data_list, card_key = item
                card_variant_id = None
                
                # Create cache key for this variant
                cache_key = (
                    variant_data['card_id'],
                    variant_data['printing_type'],
                    variant_data['special_type'],
                    variant_data['edition']
                )
                
                # Check local cache first (FAST - no lock, no DB call)
                if cache_key in variant_cache:
                    card_variant_id = variant_cache[cache_key]
                    # Only log periodically to reduce spam
                    if item_index % 50 == 0:
                        print(f"[Writer {writer_id}] [CACHE] Using cached variant: {variant_data['printing_type']}/{variant_data['special_type']} (ID: {card_variant_id})")
                else:
                    # Check shared cache (lock-protected, but only briefly)
                    with self._cache_lock:
                        if cache_key in self._shared_variant_cache:
                            card_variant_id = self._shared_variant_cache[cache_key]
                            print(f"[Writer {writer_id}] [SHARED] Found variant in shared cache: {variant_data['printing_type']}/{variant_data['special_type']} (ID: {card_variant_id})")
                        else:
                            card_variant_id = None
                    
                    if card_variant_id is None:
                        # Not in any cache - check DB (NO lock - Supabase handles concurrency)
                        existing_variant = get_card_variant_by_card_and_type(
                            variant_data['card_id'],
                            variant_data['printing_type'],
                            variant_data['special_type'],
                            variant_data['edition']
                        )
                        
                        if existing_variant:
                            card_variant_id = existing_variant['id']
                            print(f"[Writer {writer_id}] [DB] Variant already exists: {variant_data['printing_type']}/{variant_data['special_type']} (ID: {card_variant_id})")
                        else:
                            # Insert new variant immediately to get its ID
                            # NO lock here - Supabase client handles concurrent inserts safely
                            try:
                                card_variant_id = insert_card_variant(variant_data)
                                variants_inserted += 1
                                print(f"[Writer {writer_id}] [OK] Inserted variant: {variant_data['printing_type']}/{variant_data['special_type']} (ID: {card_variant_id})")
                            except Exception as e:
                                print(f"[Writer {writer_id}] [ERROR] Failed to insert variant: {e}")
                                results_queue.put(('ERROR', str(e)))
                                continue
                        
                        # Add to shared cache so other threads can find it (lock-protected, brief)
                        with self._cache_lock:
                            self._shared_variant_cache[cache_key] = card_variant_id
                    
                    # Also add to local cache
                    variant_cache[cache_key] = card_variant_id
                
                # Now add all prices for this variant to the batch with correct ID
                for price_data in price_data_list:
                    price_data['card_variant_id'] = card_variant_id
                    prices_batch.append(price_data)
                
                # Flush price batch when it reaches the threshold
                if len(prices_batch) >= BATCH_SIZE:
                    try:
                        inserted_ids = insert_card_variant_prices_batch(prices_batch)
                        prices_inserted += len(inserted_ids)
                        print(f"[Writer {writer_id}] [BATCH] Flushed {len(inserted_ids)} prices to DB")
                        prices_batch = []
                    except Exception as e:
                        print(f"[Writer {writer_id}] [ERROR] Batch price insert failed: {e}")
                        results_queue.put(('ERROR', str(e)))
                        prices_batch = []
            
            except Exception as e:
                error_msg = f"Writer thread {writer_id} error on item {item_index}: {e}"
                print(f"[ERROR] {error_msg}")
                results_queue.put(('ERROR', error_msg))
        
        # Flush any remaining price batch
        if prices_batch:
            try:
                ids = insert_card_variant_prices_batch(prices_batch)
                prices_inserted += len(ids)
                print(f"[Writer {writer_id}] [BATCH] Flushed final {len(ids)} prices to DB")
            except Exception as e:
                print(f"[Writer {writer_id}] [ERROR] Failed to batch insert final prices: {e}")
                results_queue.put(('ERROR', str(e)))
        
        
        return work_items, errors
    
    def insert_cards_with_variants_and_prices(self, set_id, cards):
        """
        Process and insert multiple cards with their variants and prices into database.
        
        This method orchestrates the complete flow:
        1. Insert card into 'cards' table
        2. For each unique variant of the card, insert into 'card_variants' table
        3. For each variant, insert price data into 'card_variant_prices' table
        
        Args:
            set_id: UUID of the set these cards belong to
            cards: List of card dictionaries from payload
            
        Returns:
            Dictionary with detailed insertion results
        """
        if not cards:
            return {
                'inserted_cards': 0,
                'inserted_variants': 0,
                'inserted_prices': 0,
                'failed': 0,
                'errors': []
            }
        
        results = {
            'inserted_cards': 0,
            'inserted_variants': 0,
            'inserted_prices': 0,
            'failed': 0,
            'errors': []
        }
        
        # Group cards by unique identifier to avoid duplicates
        # Include rarity in the key because different rarities of the same card are different cards
        cards_by_key = {}
        for card in cards:
            key = (card.get('name'), card.get('card_number'), card.get('rarity'))
            if key not in cards_by_key:
                cards_by_key[key] = []
            cards_by_key[key].append(card)
        
        # Fetch all existing cards for this set once to avoid repeated DB calls
        existing_cards = get_all_cards_for_set(set_id)
        existing_cards_set = {(card['name'], card['card_number'], card['rarity']): card['id'] for card in existing_cards}
        
        # Build a list of new cards to insert (checking against both DB and incoming payload)
        new_cards_to_insert = []
        new_cards_set = set()  # Track what we've already added to new_cards_to_insert
        card_key_to_id = {}  # Will store (name, card_number, rarity) -> card_id for new cards
        
        for (name, card_number, rarity), card_list in cards_by_key.items():
            card_key = (name, card_number, rarity)
            
            # Skip if it already exists in DB
            if card_key in existing_cards_set:
                card_key_to_id[card_key] = existing_cards_set[card_key]
                print(f"[INFO]  Card already exists: {name} (ID: {existing_cards_set[card_key]})")
                continue
            
            # Skip if we've already added this to the new_cards_to_insert list
            if card_key in new_cards_set:
                continue
            
            # Add to new cards list
            card_data = {
                'set_id': set_id,
                'name': name,
                'rarity': rarity,
                'card_number': card_number,
                'copies_in_pack': card_list[0].get('pull_rate'),
            }
            new_cards_to_insert.append(card_data)
            new_cards_set.add(card_key)
        
        # Batch insert all new cards at once
        if new_cards_to_insert:
            try:
                print(f"[INFO] Batch inserting {len(new_cards_to_insert)} new cards...")
                card_ids = insert_cards_batch(new_cards_to_insert)
                results['inserted_cards'] += len(card_ids)
                
                # Map card keys to IDs
                for i, card_data in enumerate(new_cards_to_insert):
                    card_key = (card_data['name'], card_data['card_number'], card_data['rarity'])
                    card_key_to_id[card_key] = card_ids[i]
                    print(f"[OK] Inserted card: {card_data['name']} (ID: {card_ids[i]})")
            except Exception as e:
                error_msg = f"Failed to batch insert cards: {e}"
                print(f"[ERROR] {error_msg}")
                results['errors'].append(error_msg)
                results['failed'] += 1
        
        # Phase 1: Prepare all card data in parallel (no DB access - safe)
        print(f"\n[INFO] Phase 1: Preparing {len(card_key_to_id)} cards in parallel...")
        
        work_items = []
        all_errors = []
        
        with ThreadPoolExecutor(max_workers=self.THREAD_POOL_SIZE) as executor:
            futures = {}
            
            # Submit all preparation tasks
            for card_key, card_id in card_key_to_id.items():
                card_list = cards_by_key[card_key]
                future = executor.submit(
                    self._prepare_card_data,
                    card_key,
                    card_id,
                    card_list
                )
                futures[future] = card_key
            
            # Collect prepared data and accumulate it
            for future in as_completed(futures):
                try:
                    prepared_work_items, errors = future.result(timeout=60)
                    all_errors.extend(errors)
                    
                    # Add all work items to the list for Phase 2
                    work_items.extend(prepared_work_items)
                    
                except TimeoutError:
                    error_msg = f"Timeout (60s) preparing cards"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
                except Exception as e:
                    error_msg = f"Error preparing cards: {e}"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
        
        # Phase 2: Sequential batch writing (eliminates race conditions)
        print(f"\n[INFO] Phase 2: Sequential batch writing of {len(work_items)} prepared items...")
        
        print(f"[INFO] Writing {len(work_items)} card variants sequentially with batch operations...")
        
        # Single-threaded sequential writing with batching
        variant_cache = {}  # Local cache for (card_id, printing, special_type, edition) -> variant_id
        prices_batch = []
        BATCH_SIZE = 300  # Larger batches = fewer DB round trips
        
        for item_index, (variant_data, price_data_list, card_key) in enumerate(work_items):
            try:
                # Extract card info from card_key
                card_id = card_key_to_id[card_key]
                
                # Check if variant already exists
                variant_key = (card_id, variant_data.get('printing_type'), 
                              variant_data.get('special_type'), variant_data.get('edition'))
                
                variant_id = None
                
                # Check local cache first
                if variant_key in variant_cache:
                    variant_id = variant_cache[variant_key]
                    if item_index % 50 == 0:
                        print(f"[CACHE] Using cached variant for card {card_key[0]} (ID: {variant_id})")
                else:
                    # Check DB
                    existing_variant = get_card_variant_by_card_and_type(
                        card_id, 
                        variant_data.get('printing_type'),
                        variant_data.get('special_type'),
                        variant_data.get('edition')
                    )
                    if existing_variant:
                        variant_id = existing_variant['id']
                        print(f"[DB] Variant already exists for card {card_key[0]} (ID: {variant_id})")
                    else:
                        # Insert new variant
                        variant_id = insert_card_variant(variant_data)
                        results['inserted_variants'] += 1
                        print(f"[OK] Inserted variant for card {card_key[0]} (ID: {variant_id})")
                    
                    # Cache it
                    variant_cache[variant_key] = variant_id
                
                # Add prices to batch with correct variant ID
                for price in price_data_list:
                    price['card_variant_id'] = variant_id
                    prices_batch.append(price)
                
                # Flush price batch when it reaches threshold
                if len(prices_batch) >= BATCH_SIZE:
                    try:
                        inserted_ids = insert_card_variant_prices_batch(prices_batch)
                        results['inserted_prices'] += len(inserted_ids)
                        print(f"[BATCH] Flushed {len(inserted_ids)} card variant prices (batch size: {BATCH_SIZE})")
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
                ids = insert_card_variant_prices_batch(prices_batch)
                results['inserted_prices'] += len(ids)
                print(f"[BATCH] Flushed final {len(ids)} card variant prices")
            except Exception as e:
                print(f"[ERROR] Failed to batch insert final prices: {e}")
                all_errors.append(str(e))
        
        results['errors'].extend(all_errors)
        
        print(f"[INFO] Sequential batch writing complete. Inserted {results['inserted_variants']} variants, {results['inserted_prices']} prices")
        
        return results
