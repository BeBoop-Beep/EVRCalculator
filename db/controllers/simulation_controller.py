"""Controller for pack simulation operations"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.services.simulation_service import SimulationService

class SimulationController:
    """Controller for managing pack simulation data persistence (API layer)"""
    
    def __init__(self):
        self.simulation_service = SimulationService()
    
    def save_pack_simulation(self, set_name: str, results: dict, summary_data: dict, sim_results: dict, top_10_hits):
        """
        Save pack simulation results to database (API endpoint wrapper)
        
        Args:
            set_name: Name of the set
            results: Dictionary containing pack EV calculation results
            summary_data: Dictionary containing manual calculation breakdown
            sim_results: Dictionary containing Monte Carlo simulation statistics
            top_10_hits: DataFrame or list of top 10 hit cards
            
        Returns:
            str: simulation_id (UUID) of the created simulation record, or None on failure
        """
        # Just delegate to service - all logic is there
        return self.simulation_service.save_pack_simulation(
            set_name=set_name,
            results=results,
            summary_data=summary_data,
            sim_results=sim_results,
            top_10_hits=top_10_hits
        )
    
    def get_simulation(self, simulation_id: str):
        """
        Retrieve a complete simulation with all related data (API endpoint wrapper)
        
        Args:
            simulation_id: UUID of the simulation
            
        Returns:
            Dictionary with all simulation data
        """
        return self.simulation_service.get_simulation_with_all_data(simulation_id)
    
    def get_latest_simulation_for_set(self, set_name: str):
        """
        Get the most recent simulation for a specific set (API endpoint wrapper)
        
        Args:
            set_name: Name of the set
            
        Returns:
            Dictionary with complete simulation data, or None if not found
        """
        return self.simulation_service.get_latest_simulation_for_set(set_name)
