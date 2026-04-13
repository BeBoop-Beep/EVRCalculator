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
            print(f"[DEBUG] insert_card_variant -> card_variants | card_id={card_variant_row.get('card_id')} printing_type={card_variant_row.get('printing_type')} special_type={card_variant_row.get('special_type')} edition={card_variant_row.get('edition')}")
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

    if special_type is not None:
        query = query.eq("special_type", special_type)
    else:
        query = query.is_("special_type", "null")

    if edition is not None:
        query = query.eq("edition", edition)
    else:
        query = query.is_("edition", "null")

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


def get_card_variants_by_card_ids(card_ids: List[int]) -> List[Dict[str, Any]]:
    """Retrieve all card variants for a list of card IDs."""
    if not card_ids:
        return []

    res = (
        supabase.table("card_variants")
        .select("id, card_id, pokemon_tcg_api_id")
        .in_("card_id", card_ids)
        .execute()
    )
    return res.data if res and res.data else []


def update_card_variant_image_sync_fields(card_id: str, update_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update card image sync fields for a single card variant."""
    payload = {
        key: value
        for key, value in update_fields.items()
        if key in {"pokemon_tcg_api_id", "image_small_url", "image_large_url", "image_last_synced_at"}
        and value is not None
    }

    if not payload:
        raise ValueError("No non-null card variant sync fields were provided")

    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = (
                fresh_client.table("card_variants")
                .update(payload)
                .eq("id", card_id)
                .execute()
            )
            if res is None:
                raise RuntimeError("Update card variant returned no response object")
            updated = res.data
            if not updated:
                raise RuntimeError(f"Update returned no data for card_id={card_id}")
            return updated[0]
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            duplicate_api_id_conflict = (
                "23505" in error_msg
                and "card_variants_pokemon_tcg_api_id_key" in error_msg
                and "pokemon_tcg_api_id" in payload
            )

            if duplicate_api_id_conflict:
                fallback_payload = {k: v for k, v in payload.items() if k != "pokemon_tcg_api_id"}
                if fallback_payload:
                    try:
                        fallback_res = (
                            fresh_client.table("card_variants")
                            .update(fallback_payload)
                            .eq("id", card_id)
                            .execute()
                        )
                        if fallback_res and fallback_res.data:
                            return fallback_res.data[0]
                    except Exception:
                        # Fall through to the regular error path below.
                        pass

            if "schema cache" in error_msg.lower() and attempt < max_retries - 1:
                print(f"[WARN]  Schema cache error on attempt {attempt + 1}/{max_retries}, retrying...")
                time.sleep(1)
                continue
            raise RuntimeError(f"Failed to update card variant sync fields: {error_msg}")
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise

    raise RuntimeError(f"Failed to update card variant after {max_retries} retries: {last_error}")


def update_card_variant_image_sync_fields_batch(updates: List[Dict[str, Any]]) -> int:
    """Apply card image sync field updates sequentially and return the number of updated rows."""
    updated_count = 0

    for update in updates:
        card_id = update.get("card_id")
        if not card_id:
            raise ValueError("Each card sync update must include card_id")

        payload = {key: value for key, value in update.items() if key != "card_id"}
        update_card_variant_image_sync_fields(card_id, payload)
        updated_count += 1

    return updated_count


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
            print(f"[DEBUG] insert_card_variants_batch -> card_variants | count={len(card_variants)}")
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

