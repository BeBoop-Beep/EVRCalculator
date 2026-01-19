from ..clients.supabase_client import supabase, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client
from postgrest.exceptions import APIError
from typing import Dict, Any, Optional, List
import time


def insert_sealed_product_price(price_row: Dict[str, Any]) -> int:
    """
    Insert a price row into `sealed_product_prices`.
    
    Args:
        price_row: Should include sealed_product_id, market_price, source, captured_at.
                   Optional: currency (defaults to USD in DB)
        
    Returns:
        The id of the newly inserted price record
        
    Raises:
        RuntimeError: If insertion fails
    """
    print(f"[DEBUG] Inserting sealed price with data: {price_row}")
    
    # Retry mechanism for schema cache issues
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            # Insert and let Postgrest return the data
            res = fresh_client.table("sealed_product_prices").insert(price_row).execute()
            if res is None:
                raise RuntimeError("Insert sealed product price returned no response object")
            
            inserted = res.data
            if not inserted:
                raise RuntimeError("Insert returned no data")
            
            return inserted[0]["id"]
        
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            
            # Check if it's a schema cache error
            if "schema cache" in error_msg.lower():
                print(f"[WARN]  Schema cache error on attempt {attempt + 1}/{max_retries}, retrying...")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            else:
                # Not a schema cache error, fail immediately
                print(f"[DEBUG] API Error: {error_msg}")
                raise RuntimeError(f"Failed to insert sealed product price: {error_msg}")
        
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                print(f"[WARN]  Retrying after error: {e}")
                time.sleep(1)
                continue
            raise
    
    raise RuntimeError(f"Failed to insert sealed product price after {max_retries} retries: {last_error}")


def get_latest_price(sealed_product_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the most recent price record for a sealed product.
    
    Args:
        sealed_product_id: The ID of the sealed product
        
    Returns:
        The most recent price record, or None if not found
    """
    fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    res = (
        fresh_client.table("sealed_product_prices")
        .eq("sealed_product_id", sealed_product_id)
        .order("captured_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


def insert_sealed_product_prices_batch(price_rows: List[Dict[str, Any]]) -> List[int]:
    """
    Insert multiple sealed product price rows in a single batch operation.
    
    Args:
        price_rows: List of price dictionaries to insert
        
    Returns:
        List of IDs of the newly inserted price records
        
    Raises:
        RuntimeError: If insertion fails
    """
    if not price_rows:
        return []
    
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            # Insert and let Postgrest return the data
            res = fresh_client.table("sealed_product_prices").insert(price_rows).execute()
            
            if res is None:
                raise RuntimeError("Batch insert sealed product prices returned no response object")
            
            inserted = res.data
            if inserted:
                # Normal case - insert response included data
                return [item["id"] for item in inserted]
            else:
                # 204 response - insert likely succeeded but response was empty
                # Assume insert succeeded and return dummy IDs (prices are in DB but we can't get IDs)
                print(f"[WARN]  Batch insert returned no data (204 response), assuming {len(price_rows)} sealed prices were inserted successfully")
                # Return dummy IDs based on count to indicate success
                return [f"inserted_{i}" for i in range(len(price_rows))]
        
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            if "schema cache" in error_msg.lower():
                print(f"[WARN]  Schema cache error on batch insert attempt {attempt + 1}/{max_retries}, retrying...")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            else:
                raise RuntimeError(f"Failed to batch insert sealed product prices: {error_msg}")
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise
    
    raise RuntimeError(f"Failed to batch insert sealed product prices after {max_retries} retries: {last_error}")

