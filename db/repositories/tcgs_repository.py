from ..clients.supabase_client import supabase

def get_tcg_id_by_name(tcg_name: str):
    """
    Get TCG ID by name
    
    Args:
        tcg_name: Name of the TCG (e.g., 'Pokemon', 'Magic', etc.)
        
    Returns:
        UUID of the TCG or None if not found
    """
    if not tcg_name:
        return None
    
    try:
        result = supabase.table("tcgs").select("id").eq("name", tcg_name).single().execute()
        return result.data['id'] if result and result.data else None
    except Exception as e:
        print(f"[WARN]  Error looking up TCG {tcg_name}: {e}")
        return None
