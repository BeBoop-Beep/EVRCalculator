from ..clients.supabase_client import supabase

def get_set_by_name(name: str):
    return supabase.table("sets").select("*").eq("name", name).single().execute()

def get_set_id_by_name(name: str):
    res = get_set_by_name(name)
    return res.data["id"] if res.data else None

def insert_set(set_data: dict):
    """
    Insert a new set into the database
    
    Args:
        set_data: Dictionary with set information (name, abbreviation, tcg, release_date)
        
    Returns:
        List with inserted set data or None on failure
    """
    result = supabase.table("sets").insert(set_data).execute()
    return result.data if result else None
