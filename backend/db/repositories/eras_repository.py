from ..clients.supabase_client import supabase

def get_era_id_by_name(era_name: str):
    """
    Get era ID by name
    
    Args:
        era_name: Name of the era (e.g., 'Scarlet & Violet')
        
    Returns:
        UUID of the era or None if not found
    """
    if not era_name:
        return None
    
    try:
        result = supabase.table("eras").select("id").eq("name", era_name).single().execute()
        return result.data['id'] if result and result.data else None
    except Exception as e:
        print(f"[WARN]  Error looking up era {era_name}: {e}")
        return None
