"""
Shared data preparation orchestration for all services.
Handles the generic ThreadPoolExecutor pattern for parallel data prep (Phase 1).
"""

from concurrent.futures import ThreadPoolExecutor, as_completed


class DataPreparationOrchestrator:
    """
    Generic orchestrator for Phase 1 data preparation.
    Handles ThreadPoolExecutor management and error collection.
    """
    
    @staticmethod
    def prepare_data_in_parallel(items, prepare_fn, thread_pool_size, timeout=60):
        """
        Prepare items in parallel using ThreadPoolExecutor.
        
        Args:
            items: List of items to prepare (can be cards, products, etc.)
            prepare_fn: Function that takes (item, index) and returns (prepared_data, errors)
            thread_pool_size: Number of worker threads
            timeout: Timeout per task in seconds
            
        Returns:
            Tuple of (work_items, all_errors)
            - work_items: List of prepared items
            - all_errors: List of all errors that occurred
        """
        work_items = []
        all_errors = []
        
        print(f"\n[INFO] Phase 1: Preparing {len(items)} items in parallel...")
        
        with ThreadPoolExecutor(max_workers=thread_pool_size) as executor:
            futures = {}
            
            # Submit all preparation tasks
            for i, item in enumerate(items):
                future = executor.submit(prepare_fn, item, i)
                futures[future] = i
            
            # Collect prepared data as futures complete
            for future in as_completed(futures):
                item_index = futures[future]
                try:
                    prepared_data, errors = future.result(timeout=timeout)
                    all_errors.extend(errors)
                    
                    if prepared_data:
                        work_items.append(prepared_data)
                    
                except TimeoutError:
                    error_msg = f"Timeout ({timeout}s) preparing item {item_index}"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
                except Exception as e:
                    error_msg = f"Error preparing item {item_index}: {e}"
                    print(f"[ERROR] {error_msg}")
                    all_errors.append(error_msg)
        
        print(f"[INFO] Phase 1 complete: Prepared {len(work_items)} items with {len(all_errors)} errors")
        return work_items, all_errors
