from ..clients.supabase_client import supabase
from supabase import create_client
from postgrest.exceptions import APIError
from typing import Optional, Dict, Any, List
import time


def insert_sealed_product(sealed_product_row: Dict[str, Any]) -> int:
    """
    Insert a sealed product row into `sealed_products` and return the new id.
    Falls back to SELECT if insert response is empty (handles 204 responses).
    
    Args:
        sealed_product_row: Should include set_id, name, product_type
        
    Returns:
        The id of the newly inserted sealed product
        
    Raises:
        RuntimeError: If insertion fails
    """
    from ..clients.supabase_client import SUPABASE_URL, SUPABASE_KEY
    
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            # Insert and let Postgrest return the data
            res = fresh_client.table("sealed_products").insert(sealed_product_row).execute()
            if res is None:
                raise RuntimeError("Insert sealed product returned no response object")
            
            inserted = res.data
            if inserted:
                # Normal case - insert response included data
                return inserted[0]["id"]
            else:
                # 204 response - insert likely succeeded but response was empty
                # Fall back to SELECT to get the inserted record
                print(f"[WARN]  Insert returned no data, falling back to SELECT...")
                existing = get_sealed_product_by_name_and_set(
                    sealed_product_row['name'],
                    sealed_product_row['set_id']
                )
                if existing:
                    print(f"[OK] Retrieved inserted sealed product via SELECT (ID: {existing['id']})")
                    return existing['id']
                else:
                    raise RuntimeError("Insert returned no data and SELECT fallback found nothing")
        
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            
            if "schema cache" in error_msg.lower():
                print(f"[WARN]  Schema cache error on attempt {attempt + 1}/{max_retries}, retrying...")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            else:
                raise RuntimeError(f"Failed to insert sealed product: {error_msg}")
        
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                print(f"[WARN]  Retrying after error: {e}")
                time.sleep(1)
                continue
            raise
    
    raise RuntimeError(f"Failed to insert sealed product after {max_retries} retries: {last_error}")


def get_sealed_product_by_name_and_set(name: str, set_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a sealed product by name and set.
    Includes retry logic for transient failures.
    
    Args:
        name: The name of the sealed product
        set_id: The ID of the set
        
    Returns:
        The sealed product record, or None if not found
    """
    from ..clients.supabase_client import SUPABASE_URL, SUPABASE_KEY
    
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = (
                fresh_client.table("sealed_products")
                .select("*")
                .eq("name", name)
                .eq("set_id", set_id)
                .maybe_single()
                .execute()
            )
            return res.data if res and res.data else None
        
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            
            if "schema cache" in error_msg.lower() and attempt < max_retries - 1:
                print(f"[WARN]  Schema cache error on SELECT sealed product attempt {attempt + 1}/{max_retries}, retrying...")
                time.sleep(1)
                continue
            # For other errors (including 204), return None and let caller handle it
            if attempt == max_retries - 1:
                print(f"[WARN]  Failed to get sealed product after {max_retries} attempts: {error_msg}")
            # Don't raise - return None
            return None
        except Exception as e:
            last_error = str(e)
            if attempt == max_retries - 1:
                print(f"[WARN]  Unexpected error getting sealed product: {e}")
            # Don't raise - return None
            return None
    
    return None


def insert_sealed_products_batch(sealed_products: List[Dict[str, Any]]) -> List[int]:
    """
    Insert multiple sealed products in a single batch operation.
    
    Args:
        sealed_products: List of sealed product dictionaries to insert
        
    Returns:
        List of IDs of the newly inserted sealed products
        
    Raises:
        RuntimeError: If insertion fails
    """
    from ..clients.supabase_client import SUPABASE_URL, SUPABASE_KEY
    
    if not sealed_products:
        return []
    
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            # Insert and let Postgrest return the data
            res = fresh_client.table("sealed_products").insert(sealed_products).execute()
            
            if res is None:
                raise RuntimeError("Batch insert sealed products returned no response object")
            
            inserted = res.data
            if not inserted:
                raise RuntimeError("Batch insert returned no data")
            
            # Return list of IDs
            return [item["id"] for item in inserted]
        
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            if "schema cache" in error_msg.lower():
                print(f"[WARN]  Schema cache error on batch insert attempt {attempt + 1}/{max_retries}, retrying...")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            else:
                raise RuntimeError(f"Failed to batch insert sealed products: {error_msg}")
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise
    
    raise RuntimeError(f"Failed to batch insert sealed products after {max_retries} retries: {last_error}")



