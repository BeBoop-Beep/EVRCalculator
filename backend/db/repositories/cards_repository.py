from ..clients.supabase_client import supabase, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client
from postgrest.exceptions import APIError
from typing import Optional, Dict, Any, List
import time

# Define allowed fields for each table to prevent schema mismatches
# Only these fields will be sent to the database on insert operations
TABLE_ALLOWED_FIELDS = {
    'cards': {'set_id', 'name', 'rarity', 'card_number'},
    'card_variants': {'card_id', 'printing_type', 'special_type', 'edition'},
    'card_variant_price_observations': {'card_variant_id', 'condition_id', 'market_price', 'low_price'},
    'sealed_products': {'set_id', 'product_type', 'name'},
    'sealed_product_price_observations': {'sealed_product_id', 'market_price', 'low_price'},
}

def _filter_row_fields(table_name: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filter a row dictionary to only include allowed fields for a given table.
    This prevents schema mismatches when extra fields are accidentally included.
    
    Args:
        table_name: Name of the table (e.g., 'cards', 'card_variants')
        row: Dictionary with row data
        
    Returns:
        Filtered dictionary with only allowed fields
    """
    allowed_fields = TABLE_ALLOWED_FIELDS.get(table_name)
    if not allowed_fields:
        # If table not in mapping, return row as-is (no filtering)
        return row
    
    return {k: v for k, v in row.items() if k in allowed_fields}

def insert_card(card_row: Dict[str, Any]) -> int:
    """Insert a card row into `cards` and return the new id.
        card_row should include: set_id, name, rarity, card_number
    """
    # Retry mechanism for schema cache issues
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = fresh_client.table("cards").insert(card_row).execute()
            if res is None:
                raise RuntimeError("Insert card returned no response object")
            # Supabase returns list of inserted rows
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
                raise RuntimeError(f"Failed to insert card: {error_msg}")
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise
    raise RuntimeError(f"Failed to insert card after {max_retries} retries: {last_error}")


def insert_cards_batch(card_rows: List[Dict[str, Any]]) -> List[int]:
    """
    Batch insert multiple card rows into `cards` table and return list of new IDs.
    
    Args:
        card_rows: List of card dictionaries to insert
        
    Returns:
        List of IDs of inserted cards
    """
    if not card_rows:
        return []
    
    # Filter to ONLY allowed fields for this table using generic helper
    filtered_card_rows = [_filter_row_fields('cards', card_row) for card_row in card_rows]
    
    if not filtered_card_rows:
        return []
    
    # Retry mechanism for schema cache issues
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = fresh_client.table("cards").insert(filtered_card_rows).execute()
            if res is None:
                raise RuntimeError("Batch insert cards returned no response object")
            # Supabase returns list of inserted rows
            inserted = res.data
            if not inserted:
                raise RuntimeError("Batch insert returned no data")
            # Return list of IDs
            return [row["id"] for row in inserted]
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            # Check if it's a schema cache error
            if "schema cache" in error_msg.lower():
                print(f"[WARN] Schema cache error on attempt {attempt + 1}/{max_retries}, retrying...")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
            else:
                # Not a schema cache error, fail immediately
                raise RuntimeError(f"Failed to batch insert cards: {error_msg}")
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise
    raise RuntimeError(f"Failed to batch insert cards after {max_retries} retries: {last_error}")


def get_card_by_name_and_set(name: str, set_id: int) -> Optional[Dict[str, Any]]:
    """Return a single card record matching name+set_id, or None."""
    res = (
        supabase.table("cards")
        .select("id, set_id, name, rarity, card_number")
        .eq("name", name)
        .eq("set_id", set_id)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


def get_card_by_name_number_rarity_and_set(name: str, card_number: str, rarity: str, set_id: int) -> Optional[Dict[str, Any]]:
    """Return a single card record matching name+card_number+rarity+set_id, or None."""
    res = (
        supabase.table("cards")
        .select("id, set_id, name, rarity, card_number")
        .eq("name", name)
        .eq("card_number", card_number)
        .eq("rarity", rarity)
        .eq("set_id", set_id)
        .maybe_single()
        .execute()
    )
    return res.data if res and res.data else None


def get_all_cards_for_set(set_id: int) -> list:
    """Return all card records for a given set."""
    res = (
        supabase.table("cards")
        .select(
            "id, set_id, name, rarity, card_number, image_small_url, image_large_url, pokemon_tcg_api_id, image_last_synced_at"
        )
        .eq("set_id", set_id)
        .execute()
    )
    return res.data if res and res.data else []


def update_card_image_sync_fields(card_id: str, update_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update card image sync fields for a single card row."""
    payload = {
        key: value
        for key, value in update_fields.items()
        if key in {"pokemon_tcg_api_id", "image_small_url", "image_large_url", "image_last_synced_at"}
        and value is not None
    }

    if not payload:
        raise ValueError("No non-null card sync fields were provided")

    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = (
                fresh_client.table("cards")
                .update(payload)
                .eq("id", card_id)
                .execute()
            )
            if res is None:
                raise RuntimeError("Update card returned no response object")
            updated = res.data
            if not updated:
                raise RuntimeError(f"Update returned no data for card_id={card_id}")
            return updated[0]
        except APIError as e:
            error_msg = str(e)
            last_error = error_msg
            duplicate_api_id_conflict = (
                "23505" in error_msg
                and "pokemon_tcg_api_id" in payload
            )

            if duplicate_api_id_conflict:
                fallback_payload = {k: v for k, v in payload.items() if k != "pokemon_tcg_api_id"}
                if fallback_payload:
                    try:
                        fallback_res = (
                            fresh_client.table("cards")
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
            raise RuntimeError(f"Failed to update card sync fields: {error_msg}")
        except RuntimeError as e:
            last_error = str(e)
            if "schema cache" in str(e).lower() and attempt < max_retries - 1:
                time.sleep(1)
                continue
            raise

    raise RuntimeError(f"Failed to update card after {max_retries} retries: {last_error}")


def update_card_image_sync_fields_batch(updates: List[Dict[str, Any]]) -> int:
    """Apply card image sync field updates sequentially and return the number of updated rows."""
    updated_count = 0

    for update in updates:
        card_id = update.get("card_id")
        if not card_id:
            raise ValueError("Each card sync update must include card_id")

        payload = {key: value for key, value in update.items() if key != "card_id"}
        update_card_image_sync_fields(card_id, payload)
        updated_count += 1

    return updated_count