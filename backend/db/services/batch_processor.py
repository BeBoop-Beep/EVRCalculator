"""
Generic multiprocessing batch processor for database ingestion services.
Provides reusable orchestration for parallel batch processing with sequential shipping.

Usage:
    Subclass BatchProcessor and implement:
    - _process_batch_worker(batch_data, batch_id)
    - _ship_batch_prices(prices, batch_id)
"""

import sys
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from abc import ABC, abstractmethod

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


class BatchProcessor(ABC):
    """
    Abstract base class for multiprocessing batch ingestion.
    Handles generic orchestration; subclasses implement specific logic.
    """
    
    # Configuration - override in subclass
    MAX_WORKERS = 4
    WORK_BATCH_SIZE = 300
    PRICE_BATCH_SIZE = 500
    PROCESS_TIMEOUT = 300  # 5 minutes
    USE_MULTIPROCESSING = True  # Set to False to skip multiprocessing and use sequential processing

    def _resolve_max_workers(self):
        hard_cap = int(os.getenv("SCRAPER_MAX_CONCURRENCY", "5"))
        requested = int(getattr(self, "MAX_WORKERS", 1) or 1)
        return max(1, min(requested, hard_cap))
    
    def divide_work_into_batches(self, work_items, batch_size=None):
        """
        Divide work items into fixed-size batches.
        
        Args:
            work_items: List of items to process
            batch_size: Size of each batch (uses class default if None)
            
        Returns:
            List of batches, where each batch is a list of items
        """
        if batch_size is None:
            batch_size = self.WORK_BATCH_SIZE
            
        batches = []
        for i in range(0, len(work_items), batch_size):
            batch = work_items[i:i + batch_size]
            batches.append(batch)
        return batches
    
    def process_batches_in_parallel(self, batches, prepare_batch_data_fn):
        """
        Process batches in parallel using multiprocessing (if enabled).
        Falls back to sequential processing if USE_MULTIPROCESSING is False.
        
        Args:
            batches: List of work batches to process
            prepare_batch_data_fn: Function that prepares batch data for worker
                                   Takes (batch, index) and returns batch_data
            
        Returns:
            Tuple of (batch_results, all_errors)
            - batch_results: List of results from worker processes
            - all_errors: List of errors that occurred during processing
        """
        batch_results = []
        all_errors = []
        
        if not self.USE_MULTIPROCESSING or len(batches) == 1:
            # Sequential processing (no multiprocessing)
            print(f"\n[INFO] Processing {len(batches)} batches sequentially...")
            for batch_id, batch in enumerate(batches):
                try:
                    batch_data = prepare_batch_data_fn(batch, batch_id)
                    batch_result = self._process_batch_worker(batch_data, batch_id)
                    batch_results.append(batch_result)
                    print(f"[INFO] Batch {batch_id} processing complete")
                except Exception as e:
                    error_msg = f"Batch {batch_id} processing failed: {e}"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
            return batch_results, all_errors
        
        # Parallel multiprocessing
        max_workers = self._resolve_max_workers()
        print(f"\n[INFO] Processing {len(batches)} batches in parallel with {max_workers} workers...")
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            next_batch_id = 0

            def _submit_next_batch():
                nonlocal next_batch_id
                if next_batch_id >= len(batches):
                    return False
                batch = batches[next_batch_id]
                batch_data = prepare_batch_data_fn(batch, next_batch_id)
                future = executor.submit(self._process_batch_worker, batch_data, next_batch_id)
                futures[future] = next_batch_id
                next_batch_id += 1
                return True

            # Keep only a small in-flight window to prevent task fan-out memory pressure.
            while len(futures) < max_workers and _submit_next_batch():
                pass

            while futures:
                done_future = next(as_completed(futures))
                batch_id = futures.pop(done_future)
                try:
                    batch_result = done_future.result(timeout=self.PROCESS_TIMEOUT)
                    batch_results.append(batch_result)
                    print(f"[INFO] Batch {batch_id} processing complete")
                except TimeoutError:
                    error_msg = f"Batch {batch_id} processing timeout ({self.PROCESS_TIMEOUT}s)"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
                except Exception as e:
                    error_msg = f"Batch {batch_id} processing failed: {e}"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)

                _submit_next_batch()
        
        return batch_results, all_errors
    
    def ship_results_sequentially(self, batch_results, results_accumulator):
        """
        Ship batch results sequentially (one batch at a time).
        
        Args:
            batch_results: List of batch results sorted by batch_id
            results_accumulator: Dict to accumulate results
                                 Expected keys: 'inserted_prices', 'errors'
            
        Returns:
            Tuple of (prices_expected, prices_shipped, all_errors)
        """
        all_errors = []
        
        # Sort batch results by batch_id to maintain order
        batch_results.sort(key=lambda x: x['batch_id'])
        
        print(f"\n[INFO] Sequential shipping of {len(batch_results)} completed batches...")
        
        total_prices_to_ship = sum(len(br.get('prices_to_ship', [])) for br in batch_results)
        print(f"[INFO] Total prices to ship across all batches: {total_prices_to_ship}")
        
        prices_expected = total_prices_to_ship
        prices_shipped = 0
        
        for batch_result in batch_results:
            batch_id = batch_result['batch_id']
            prices_to_ship = batch_result.get('prices_to_ship', [])
            batch_size = self.PRICE_BATCH_SIZE
            
            if prices_to_ship:
                print(f"[SHIP] Batch {batch_id}: Preparing {len(prices_to_ship)} prices for shipping")
            
            # Ship prices in sub-batches
            for sub_batch_idx, i in enumerate(range(0, len(prices_to_ship), batch_size)):
                price_batch = prices_to_ship[i:i + batch_size]
                batch_expected = len(price_batch)
                
                try:
                    ship_result = self._ship_batch_prices(price_batch, batch_id)
                    if isinstance(ship_result, dict):
                        batch_shipped = int(ship_result.get('inserted_count', 0))
                        results_accumulator['price_rows_attempted'] = (
                            results_accumulator.get('price_rows_attempted', 0)
                            + int(ship_result.get('attempted_rows', batch_expected))
                        )
                        results_accumulator['price_rows_skipped_duplicates'] = (
                            results_accumulator.get('price_rows_skipped_duplicates', 0)
                            + int(ship_result.get('skipped_duplicates', 0))
                        )
                        results_accumulator['price_rows_updated'] = (
                            results_accumulator.get('price_rows_updated', 0)
                            + int(ship_result.get('updated_count', 0))
                        )
                        results_accumulator['price_batch_operations'] = (
                            results_accumulator.get('price_batch_operations', 0)
                            + int(ship_result.get('db_batch_operations', 0))
                        )
                    else:
                        batch_shipped = int(ship_result)
                        results_accumulator['price_rows_attempted'] = (
                            results_accumulator.get('price_rows_attempted', 0) + batch_expected
                        )
                        results_accumulator['price_batch_operations'] = (
                            results_accumulator.get('price_batch_operations', 0) + 1
                        )

                    results_accumulator['inserted_prices'] += batch_shipped
                    prices_shipped += batch_shipped
                    
                    if batch_shipped != batch_expected:
                        warning_msg = f"[SHIP] Batch {batch_id} sub-batch {sub_batch_idx}: Expected {batch_expected} but only {batch_shipped} inserted (LOSS: {batch_expected - batch_shipped})"
                        print(warning_msg)
                        all_errors.append(warning_msg)
                    elif sub_batch_idx == 0 or sub_batch_idx % 5 == 0:
                        print(f"[SHIP] Batch {batch_id} sub-batch {sub_batch_idx}: Shipped {batch_shipped} prices ✓")
                        
                except Exception as e:
                    error_msg = f"[SHIP] Batch {batch_id} sub-batch {sub_batch_idx}: FAILED - {len(price_batch)} prices lost: {e}"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
            
            # Accumulate item-specific results
            for key in ['inserted_items', 'inserted_products', 'inserted_variants']:
                if key in batch_result:
                    results_accumulator[key] = results_accumulator.get(key, 0) + batch_result[key]
            
            # Accumulate errors
            if 'errors' in batch_result:
                results_accumulator['errors'].extend(batch_result['errors'])
        
        # Check for discrepancies
        if prices_shipped != prices_expected:
            discrepancy = prices_expected - prices_shipped
            discrepancy_msg = f"\n[WARNING] PRICE INSERTION DISCREPANCY: Expected {prices_expected}, Shipped {prices_shipped} (MISSING: {discrepancy} rows)"
            print(discrepancy_msg)
            all_errors.append(discrepancy_msg)
        
        return prices_expected, prices_shipped, all_errors
    
    @abstractmethod
    def _process_batch_worker(self, batch_data, batch_id):
        """
        Worker function that processes a single batch.
        Must be implemented by subclass.
        
        Args:
            batch_data: Prepared batch data (format defined by subclass)
            batch_id: ID of this batch for logging
            
        Returns:
            Dictionary with results including:
            - batch_id
            - prices_to_ship (list of price items)
            - inserted_items/inserted_products/inserted_variants (count)
            - errors (list of error messages)
        """
        pass
    
    @abstractmethod
    def _ship_batch_prices(self, price_batch, batch_id):
        """
        Ship a batch of prices to the database.
        Must be implemented by subclass.
        
        Args:
            price_batch: List of price items to insert
            batch_id: ID of the batch being shipped (for logging)
            
        Returns:
            Number of prices successfully inserted
        """
        pass
