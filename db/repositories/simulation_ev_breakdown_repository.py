"""Repository for simulation_ev_breakdown table operations"""
from ..clients.supabase_client import supabase

def insert_ev_breakdown(breakdown_data: dict):
    """
    Insert EV breakdown data for a simulation
    
    Args:
        breakdown_data: Dictionary with:
            - simulation_id (UUID)
            - ev_common_total (Decimal, optional)
            - ev_uncommon_total (Decimal, optional)
            - ev_rare_total (Decimal, optional)
            - ev_reverse_total (Decimal, optional)
            - ev_ace_spec_total (Decimal, optional)
            - ev_pokeball_total (Decimal, optional)
            - ev_master_ball_total (Decimal, optional)
            - ev_illustration_rare_total (Decimal, optional)
            - ev_special_illustration_rare_total (Decimal, optional)
            - ev_double_rare_total (Decimal, optional)
            - ev_hyper_rare_total (Decimal, optional)
            - ev_ultra_rare_total (Decimal, optional)
            - reverse_multiplier (Decimal, optional)
            - rare_multiplier (Decimal, optional)
            - regular_pack_ev_contribution (Decimal, optional)
            - god_pack_ev_contribution (Decimal, optional)
            - demi_god_pack_ev_contribution (Decimal, optional)
        
    Returns:
        Inserted breakdown record
    """
    result = supabase.table("simulation_ev_breakdown").insert(breakdown_data).execute()
    if result is None:
        raise RuntimeError("Insert EV breakdown returned no response object")
    return result.data[0] if result.data else None

def get_ev_breakdown_by_simulation_id(simulation_id: str):
    """Get EV breakdown for a specific simulation"""
    result = supabase.table("simulation_ev_breakdown").select("*").eq("simulation_id", simulation_id).single().execute()
    return result.data if result.data else None
