"""Repository for simulation_percentiles table operations"""
from ..clients.supabase_client import supabase

def insert_simulation_percentiles(percentiles_data: dict):
    """
    Insert percentile data for a simulation
    
    Args:
        percentiles_data: Dictionary with:
            - simulation_id (UUID)
            - percentile_5th (Decimal, optional)
            - percentile_25th (Decimal, optional)
            - percentile_50th (Decimal, optional)
            - percentile_75th (Decimal, optional)
            - percentile_90th (Decimal, optional)
            - percentile_95th (Decimal, optional)
            - percentile_99th (Decimal, optional)
        
    Returns:
        Inserted percentiles record
    """
    result = supabase.table("simulation_percentiles").insert(percentiles_data).execute()
    if result is None:
        raise RuntimeError("Insert simulation percentiles returned no response object")
    return result.data[0] if result.data else None

def get_percentiles_by_simulation_id(simulation_id: str):
    """Get percentiles for a specific simulation"""
    result = supabase.table("simulation_percentiles").select("*").eq("simulation_id", simulation_id).single().execute()
    return result.data if result.data else None
