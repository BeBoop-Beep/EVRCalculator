from ..clients.supabase_client import supabase
from typing import Dict, List

def get_set_by_name(name: str):
    return supabase.table("sets").select("*").eq("name", name).single().execute()

def get_set_id_by_name(name: str):
    res = get_set_by_name(name)
    return res.data["id"] if res and res.data else None

def insert_set(set_data: dict):
    """
    Insert a new set into the database
    
    Args:
        set_data: Dictionary with set information (name, abbreviation, tcg, release_date)
        
    Returns:
        List with inserted set data or None on failure
    """
    result = supabase.table("sets").insert(set_data).execute()
    if result is None:
        raise RuntimeError("Insert set returned no response object")
    return result.data if result.data else None


def insert_sets(set_rows: List[Dict]):
    """Insert many set rows in one request and return inserted payloads."""
    if not set_rows:
        return []

    result = supabase.table("sets").insert(set_rows).execute()
    if result is None:
        raise RuntimeError("Bulk insert sets returned no response object")
    return result.data if result.data else None


def get_sets_by_tcg_id(tcg_id: str):
    """Return all sets for a TCG."""
    response = supabase.table("sets").select("*").eq("tcg_id", tcg_id).execute()
    return response.data if response and response.data else []


def update_set_by_id(set_id: str, set_data: dict):
    """Update one set row and return the updated payload."""
    response = supabase.table("sets").update(set_data).eq("id", set_id).execute()
    if response is None:
        raise RuntimeError("Update set returned no response object")
    return response.data if response.data else None


def get_scrape_ready_sets_by_tcg_id(tcg_id: str) -> List[Dict]:
    """Return scrape-ready sets for a TCG, ordered by release_date then name."""
    response = (
        supabase.table("sets")
        .select("id, name, canonical_key, card_details_url, sealed_details_url, release_date, era_id")
        .eq("tcg_id", tcg_id)
        .eq("ready_for_daily_scrape", True)
        .order("release_date")
        .order("name")
        .execute()
    )
    return response.data if response and response.data else []
