from ..clients.supabase_client import supabase, SUPABASE_URL, SUPABASE_KEY
from supabase import create_client
from postgrest.exceptions import APIError
from typing import Optional, Dict, Any, List
import time

def insert_card(card_row: Dict[str, Any]) -> int:
    """Insert a card row into `cards` and return the new id.
        card_row should include: set_id, name, rarity, copies_in_pack (optional)
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
    
    # Retry mechanism for schema cache issues
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            fresh_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            res = fresh_client.table("cards").insert(card_rows).execute()
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
        .select("*")
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
        .select("*")
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
        .select("*")
        .eq("set_id", set_id)
        .execute()
    )
    return res.data if res and res.data else []