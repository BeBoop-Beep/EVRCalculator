from ..clients.supabase_client import supabase, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client
from postgrest.exceptions import APIError
from typing import Optional, Dict, Any, List
import time


def insert_card_variant(card_variant_row: Dict[str, Any]) -> int:
    """
    Insert a card variant row into `card_variants` and return the new id.
    
    Args:
        card_variant_row: Should include card_id, printing_type, special_type (optional), edition (optional)
        
    Returns:
        The id of the newly inserted card variant
        
    Raises:
        RuntimeError: If insertion fails
    """
    # Retry mechanism for schema cache issues
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = fresh_client.table("card_variants").insert(card_variant_row).execute()
            if res is None:
                raise RuntimeError("Insert card variant returned no response object")
            
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
                raise RuntimeError(f"Failed to insert card variant: {error_msg}")
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise
    raise RuntimeError(f"Failed to insert card variant after {max_retries} retries: {last_error}")


def get_card_variant_by_card_and_type(
    card_id: int, 
    printing_type: str, 
    special_type: Optional[str] = None,
    edition: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a card variant by card_id and printing characteristics.
    
    Args:
        card_id: The ID of the card
        printing_type: The printing type (e.g., 'holo', 'reverse-holo', 'non-holo')
        special_type: Optional special type (e.g., 'ex', 'v', 'vmax')
        edition: Optional edition info
        
    Returns:
        The card variant record, or None if not found
    """
    query = (
        supabase.table("card_variants")
        .select("*")
        .eq("card_id", card_id)
        .eq("printing_type", printing_type)
    )
    
    if special_type:
        query = query.eq("special_type", special_type)
    if edition:
        query = query.eq("edition", edition)
    
    res = query.maybe_single().execute()
    return res.data if res and res.data else None


def get_card_variants_by_card_id(card_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve all card variants for a given card.
    
    Args:
        card_id: The ID of the card
        
    Returns:
        List of card variant records
    """
    res = supabase.table("card_variants").select("*").eq("card_id", card_id).execute()
    return res.data if res and res.data else []


def insert_card_variants_batch(card_variants: List[Dict[str, Any]]) -> List[int]:
    """
    Insert multiple card variant rows in a single batch operation.
    
    Args:
        card_variants: List of card variant dictionaries to insert
        
    Returns:
        List of IDs of the newly inserted card variants
        
    Raises:
        RuntimeError: If insertion fails
    """
    if not card_variants:
        return []
    
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = fresh_client.table("card_variants").insert(card_variants).execute()
            
            if res is None:
                raise RuntimeError("Batch insert card variants returned no response object")
            
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
                raise RuntimeError(f"Failed to batch insert card variants: {error_msg}")
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise
    
    raise RuntimeError(f"Failed to batch insert card variants after {max_retries} retries: {last_error}")

