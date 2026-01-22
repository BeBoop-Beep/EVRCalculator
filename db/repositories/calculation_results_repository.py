"""
Repository for calculation result tables:
- calculation_price_snapshots: Exact prices used at time of calculation
- manual_calculation_results: Manual EV calculations by rarity
- simulation_summary: Main simulation statistics
- simulation_percentiles: Distribution percentiles
- top_hits_prices: Top 10 most valuable cards pulled
- valuation_context: Market conditions and contextual notes
"""

from ..clients.supabase_client import supabase
from typing import Optional, List, Dict, Any
import uuid


# ============================================================================
# CALCULATION PRICE SNAPSHOTS REPOSITORY
# ============================================================================

def insert_price_snapshots_batch(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Insert price snapshots in batch.
    
    Args:
        snapshots: List of price snapshot records
        
    Returns:
        List of inserted records
    """
    if not snapshots:
        return []
    
    result = supabase.table("calculation_price_snapshots").insert(snapshots).execute()
    return result.data if result.data else []


def get_price_snapshots_for_run(calculation_run_id: str) -> List[Dict[str, Any]]:
    """Get all price snapshots for a calculation run."""
    result = (
        supabase.table("calculation_price_snapshots")
        .select("*")
        .eq("calculation_run_id", calculation_run_id)
        .execute()
    )
    return result.data if result.data else []


# ============================================================================
# MANUAL CALCULATION RESULTS REPOSITORY
# ============================================================================

def insert_manual_calculation_results(
    calculation_run_id: str,
    results_by_rarity: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Insert manual EV calculation results (breakdown by rarity).
    
    Args:
        calculation_run_id: UUID of the calculation run
        results_by_rarity: Dictionary with rarity keys and EV values/statistics
        
    Returns:
        Inserted record or None
    """
    record = {
        "id": str(uuid.uuid4()),
        "calculation_run_id": calculation_run_id,
        "results_data": results_by_rarity,  # JSONB field
    }
    result = supabase.table("manual_calculation_results").insert(record).execute()
    return result.data[0] if result.data else None


def get_manual_results(calculation_run_id: str) -> Optional[Dict[str, Any]]:
    """Get manual calculation results for a run."""
    result = (
        supabase.table("manual_calculation_results")
        .select("*")
        .eq("calculation_run_id", calculation_run_id)
        .single()
        .execute()
    )
    return result.data if result.data else None


# ============================================================================
# SIMULATION SUMMARY REPOSITORY
# ============================================================================

def insert_simulation_summary(
    calculation_run_id: str,
    summary_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Insert simulation summary (main statistics: mean, std_dev, min, max).
    
    Args:
        calculation_run_id: UUID of the calculation run
        summary_data: Dictionary with mean, std_dev, min, max, num_simulations
        
    Returns:
        Inserted record or None
    """
    record = {
        "id": str(uuid.uuid4()),
        "calculation_run_id": calculation_run_id,
        "mean_ev": summary_data.get("mean"),
        "std_dev": summary_data.get("std_dev"),
        "min_ev": summary_data.get("min"),
        "max_ev": summary_data.get("max"),
        "num_simulations": summary_data.get("num_simulations"),
        "summary_data": summary_data,  # Full JSONB backup
    }
    result = supabase.table("simulation_summary").insert(record).execute()
    return result.data[0] if result.data else None


def get_simulation_summary(calculation_run_id: str) -> Optional[Dict[str, Any]]:
    """Get simulation summary for a run."""
    result = (
        supabase.table("simulation_summary")
        .select("*")
        .eq("calculation_run_id", calculation_run_id)
        .single()
        .execute()
    )
    return result.data if result.data else None


# ============================================================================
# SIMULATION PERCENTILES REPOSITORY
# ============================================================================

def insert_simulation_percentiles(
    calculation_run_id: str,
    percentiles_data: Dict[str, float],
) -> Optional[Dict[str, Any]]:
    """
    Insert simulation percentiles (5th, 25th, 50th, 75th, 90th, 95th, 99th).
    
    Args:
        calculation_run_id: UUID of the calculation run
        percentiles_data: Dictionary with percentile keys and values
        
    Returns:
        Inserted record or None
    """
    record = {
        "id": str(uuid.uuid4()),
        "calculation_run_id": calculation_run_id,
        "percentile_5": percentiles_data.get("5"),
        "percentile_25": percentiles_data.get("25"),
        "percentile_50": percentiles_data.get("50"),
        "percentile_75": percentiles_data.get("75"),
        "percentile_90": percentiles_data.get("90"),
        "percentile_95": percentiles_data.get("95"),
        "percentile_99": percentiles_data.get("99"),
        "percentiles_data": percentiles_data,  # Full JSONB backup
    }
    result = supabase.table("simulation_percentiles").insert(record).execute()
    return result.data[0] if result.data else None


def get_simulation_percentiles(calculation_run_id: str) -> Optional[Dict[str, Any]]:
    """Get simulation percentiles for a run."""
    result = (
        supabase.table("simulation_percentiles")
        .select("*")
        .eq("calculation_run_id", calculation_run_id)
        .single()
        .execute()
    )
    return result.data if result.data else None


# ============================================================================
# TOP HITS PRICES REPOSITORY
# ============================================================================

def insert_top_hits_batch(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Insert top hit cards in batch.
    
    Args:
        hits: List of top hit records
        
    Returns:
        List of inserted records
    """
    if not hits:
        return []
    
    result = supabase.table("top_hits_prices").insert(hits).execute()
    return result.data if result.data else []


def get_top_hits(calculation_run_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get top hit cards for a calculation run."""
    result = (
        supabase.table("top_hits_prices")
        .select("*")
        .eq("calculation_run_id", calculation_run_id)
        .order("rank", asc=True)
        .limit(limit)
        .execute()
    )
    return result.data if result.data else []


# ============================================================================
# VALUATION CONTEXT REPOSITORY
# ============================================================================

def insert_valuation_context(
    calculation_run_id: str,
    context_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Insert valuation context (market conditions, notes, external factors).
    
    Args:
        calculation_run_id: UUID of the calculation run
        context_data: Dictionary with market conditions, notes, etc.
        
    Returns:
        Inserted record or None
    """
    record = {
        "id": str(uuid.uuid4()),
        "calculation_run_id": calculation_run_id,
        "context_data": context_data,  # JSONB field
    }
    result = supabase.table("valuation_context").insert(record).execute()
    return result.data[0] if result.data else None


def get_valuation_context(calculation_run_id: str) -> Optional[Dict[str, Any]]:
    """Get valuation context for a calculation run."""
    result = (
        supabase.table("valuation_context")
        .select("*")
        .eq("calculation_run_id", calculation_run_id)
        .single()
        .execute()
    )
    return result.data if result.data else None
