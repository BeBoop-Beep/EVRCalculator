from ..clients.supabase_client import supabase
from supabase import create_client
from postgrest.exceptions import APIError
from typing import Optional, Dict, Any
import time


def insert_sealed_product(sealed_product_row: Dict[str, Any]) -> int:
    """
    Insert a sealed product row into `sealed_products` and return the new id.
    
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
            res = fresh_client.table("sealed_products").insert(sealed_product_row).execute()
            if res is None:
                raise RuntimeError("Insert sealed product returned no response object")
            
            inserted = res.data
            if not inserted:
                raise RuntimeError("Insert returned no data")
            
            return inserted[0]["id"]
        
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
            
            if "schema cache" in error_msg.lower():
                print(f"[WARN]  Schema cache error on attempt {attempt + 1}/{max_retries}, retrying...")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            else:
                raise RuntimeError(f"Failed to get sealed product: {error_msg}")
        
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise
    
    raise RuntimeError(f"Failed to get sealed product after {max_retries} retries: {last_error}")


