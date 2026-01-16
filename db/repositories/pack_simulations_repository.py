"""Repository for pack_simulations table operations"""
from ..clients.supabase_client import supabase

def insert_pack_simulation(simulation_data: dict):
    """
    Insert a new pack simulation record
    
    Args:
        simulation_data: Dictionary with simulation data including:
            - set_id (UUID)
            - total_manual_ev (Decimal)
            - simulated_ev (Decimal)
            - pack_price (Decimal)
            - net_value (Decimal)
            - opening_pack_roi (Decimal)
            - opening_pack_roi_percent (Decimal)
            - hit_probability_percentage (Decimal, optional)
            - no_hit_probability_percentage (Decimal, optional)
            - simulation_count (int, optional, defaults to 100000)
        
    Returns:
        Inserted simulation record with id
    """
    result = supabase.table("pack_simulations").insert(simulation_data).execute()
    if result is None:
        raise RuntimeError("Insert pack simulation returned no response object")
    return result.data[0] if result.data else None

def get_simulation_by_id(simulation_id: str):
    """Get a pack simulation by ID"""
    return supabase.table("pack_simulations").select("*").eq("id", simulation_id).single().execute()

def get_simulations_by_set_id(set_id: str):
    """Get all simulations for a specific set"""
    return supabase.table("pack_simulations").select("*").eq("set_id", set_id).order("created_at", desc=True).execute()

def get_latest_simulation_by_set_id(set_id: str):
    """Get the most recent simulation for a specific set"""
    result = supabase.table("pack_simulations").select("*").eq("set_id", set_id).order("created_at", desc=True).limit(1).execute()
    return result.data[0] if result.data else None

def update_pack_simulation(simulation_id: str, updates: dict):
    """Update an existing pack simulation"""
    result = supabase.table("pack_simulations").update(updates).eq("id", simulation_id).execute()
    return result.data[0] if result.data else None

def delete_pack_simulation(simulation_id: str):
    """Delete a pack simulation and all related data (cascades)"""
    result = supabase.table("pack_simulations").delete().eq("id", simulation_id).execute()
    return result.data
