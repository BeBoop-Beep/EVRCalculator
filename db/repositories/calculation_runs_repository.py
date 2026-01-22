"""
Repository for calculation_runs table.
Tracks calculation execution history, status, and metadata for audit trail.
"""

from ..clients.supabase_client import supabase
from typing import Optional, List, Dict, Any
import uuid


def create_calculation_run(
    set_id: str,
    config_version: int = 1,
    user_id: Optional[str] = None,
    status: str = "pending",
    notes: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Create a new calculation run record.
    
    Args:
        set_id: UUID of the set being calculated
        config_version: Version of the configuration used (default: 1)
        user_id: Optional UUID of user (None for global calculations)
        status: Calculation status (pending, in_progress, complete, failed)
        notes: Optional notes about the calculation run
        
    Returns:
        Inserted calculation_run record or None
    """
    run_data = {
        "id": str(uuid.uuid4()),
        "set_id": set_id,
        "config_version": config_version,
        "user_id": user_id,
        "status": status,
        "notes": notes,
    }
    result = supabase.table("calculation_runs").insert(run_data).execute()
    return result.data[0] if result.data else None


def get_calculation_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Get a calculation run by ID."""
    result = supabase.table("calculation_runs").select("*").eq("id", run_id).single().execute()
    return result.data if result.data else None


def update_calculation_run_status(
    run_id: str,
    status: str,
    notes: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update calculation run status.
    
    Args:
        run_id: UUID of the calculation run
        status: New status (in_progress, complete, failed)
        notes: Optional notes to append
        
    Returns:
        Updated calculation_run record or None
    """
    update_data = {"status": status}
    if notes:
        update_data["notes"] = notes
    
    result = supabase.table("calculation_runs").update(update_data).eq("id", run_id).execute()
    return result.data[0] if result.data else None


def get_latest_calculation_runs(
    set_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Get latest calculation runs, optionally filtered by set and/or user.
    
    Args:
        set_id: Optional set UUID filter
        user_id: Optional user UUID filter
        limit: Maximum number of records to return
        
    Returns:
        List of calculation_run records
    """
    query = supabase.table("calculation_runs").select("*")
    
    if set_id:
        query = query.eq("set_id", set_id)
    if user_id:
        query = query.eq("user_id", user_id)
    
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data if result.data else []
