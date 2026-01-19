"""Service layer for pack simulation data persistence"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.pack_simulations_repository import insert_pack_simulation, get_simulation_by_id
from db.repositories.simulation_ev_breakdown_repository import insert_ev_breakdown
from db.repositories.simulation_statistics_repository import insert_simulation_statistics
from db.repositories.simulation_percentiles_repository import insert_simulation_percentiles
from db.repositories.simulation_rarity_stats_repository import insert_rarity_stats_batch
from db.repositories.simulation_top_hits_repository import insert_top_hits_batch

class SimulationService:
    """Service for saving complete simulation results to the database"""
    
    def save_pack_simulation(self, set_name: str, results: dict, summary_data: dict, sim_results: dict, top_10_hits):
        """
        Save pack simulation results to database (handles set lookup internally)
        
        Args:
            set_name: Name of the set (will lookup set record)
            results: Dictionary containing pack EV calculation results
            summary_data: Dictionary containing manual calculation breakdown
            sim_results: Dictionary containing Monte Carlo simulation statistics
            top_10_hits: DataFrame or list of top 10 hit cards
            
        Returns:
            str: simulation_id (UUID) of the created simulation record, or None on failure
        """
        try:
            # Get the set record
            from db.repositories.sets_repository import get_set_id_by_name
            
            set_id = get_set_id_by_name(set_name)
            
            if not set_id:
                print(f"[WARN] Set '{set_name}' not found in database. Cannot save simulation without a set record.")
                print("[INFO] Please ensure the set is created first via the scraper/ingest process.")
                return None
            
            # Save the simulation
            simulation_id = self.save_simulation_results(
                set_id=set_id,
                results=results,
                summary_data=summary_data,
                sim_results=sim_results,
                top_10_hits=top_10_hits
            )
            
            return simulation_id
            
        except Exception as e:
            print(f"[ERROR] Failed to save pack simulation: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_simulation_results(self, set_id: str, results: dict, summary_data: dict, sim_results: dict, top_10_hits):
        """
        Save complete simulation results to database
        
        Args:
            set_id: UUID of the set
            results: Dictionary containing pack EV calculation results
            summary_data: Dictionary containing manual calculation breakdown
            sim_results: Dictionary containing Monte Carlo simulation statistics
            top_10_hits: DataFrame or list of top 10 hit cards
            
        Returns:
            str: simulation_id (UUID) of the created simulation record
        """
        try:
            # 1. Insert main pack simulation record
            simulation_data = {
                'set_id': set_id,
                'total_manual_ev': float(results.get('total_manual_ev', 0)),
                'simulated_ev': float(results.get('acutal_simulated_ev', 0)),
                'pack_price': float(results.get('pack_price', 0)),
                'net_value': float(results.get('net_value', 0)),
                'opening_pack_roi': float(results.get('opening_pack_roi', 0)),
                'opening_pack_roi_percent': float(results.get('opening_pack_roi_percent', 0)),
                'hit_probability_percentage': float(results.get('hit_probability_percentage', 0)) if results.get('hit_probability_percentage') else None,
                'no_hit_probability_percentage': float(results.get('no_hit_probability_percentage', 0)) if results.get('no_hit_probability_percentage') else None,
                'simulation_count': 100000  # Default from the orchestrator
            }
            
            simulation_record = insert_pack_simulation(simulation_data)
            if not simulation_record:
                raise RuntimeError("Failed to create pack simulation record")
            
            simulation_id = simulation_record['id']
            print(f"[DB] Created pack simulation record: {simulation_id}")
            
            # 2. Insert EV breakdown
            breakdown_data = {
                'simulation_id': simulation_id,
                'ev_common_total': float(summary_data.get('ev_common_total', 0)) if summary_data.get('ev_common_total') else None,
                'ev_uncommon_total': float(summary_data.get('ev_uncommon_total', 0)) if summary_data.get('ev_uncommon_total') else None,
                'ev_rare_total': float(summary_data.get('ev_rare_total', 0)) if summary_data.get('ev_rare_total') else None,
                'ev_reverse_total': float(summary_data.get('ev_reverse_total', 0)) if summary_data.get('ev_reverse_total') else None,
                'ev_ace_spec_total': float(summary_data.get('ev_ace_spec_total', 0)) if summary_data.get('ev_ace_spec_total') else None,
                'ev_pokeball_total': float(summary_data.get('ev_pokeball_total', 0)) if summary_data.get('ev_pokeball_total') else None,
                'ev_master_ball_total': float(summary_data.get('ev_master_ball_total', 0)) if summary_data.get('ev_master_ball_total') else None,
                'ev_illustration_rare_total': float(summary_data.get('ev_IR_total', 0)) if summary_data.get('ev_IR_total') else None,
                'ev_special_illustration_rare_total': float(summary_data.get('ev_SIR_total', 0)) if summary_data.get('ev_SIR_total') else None,
                'ev_double_rare_total': float(summary_data.get('ev_double_rare_total', 0)) if summary_data.get('ev_double_rare_total') else None,
                'ev_hyper_rare_total': float(summary_data.get('ev_hyper_rare_total', 0)) if summary_data.get('ev_hyper_rare_total') else None,
                'ev_ultra_rare_total': float(summary_data.get('ev_ultra_rare_total', 0)) if summary_data.get('ev_ultra_rare_total') else None,
                'reverse_multiplier': float(summary_data.get('reverse_multiplier', 0)) if summary_data.get('reverse_multiplier') else None,
                'rare_multiplier': float(summary_data.get('rare_multiplier', 0)) if summary_data.get('rare_multiplier') else None,
                'regular_pack_ev_contribution': float(summary_data.get('regular_pack_ev_contribution', 0)) if summary_data.get('regular_pack_ev_contribution') else None,
                'god_pack_ev_contribution': float(summary_data.get('god_pack_ev_contribution', 0)) if summary_data.get('god_pack_ev_contribution') else None,
                'demi_god_pack_ev_contribution': float(summary_data.get('demi_god_pack_ev_contribution', 0)) if summary_data.get('demi_god_pack_ev_contribution') else None,
            }
            
            insert_ev_breakdown(breakdown_data)
            print(f"[DB] Created EV breakdown for simulation: {simulation_id}")
            
            # 3. Insert simulation statistics
            stats_data = {
                'simulation_id': simulation_id,
                'mean_value': float(sim_results.get('mean', 0)),
                'std_dev': float(sim_results.get('std_dev', 0)),
                'min_value': float(sim_results.get('min', 0)),
                'max_value': float(sim_results.get('max', 0)),
            }
            
            insert_simulation_statistics(stats_data)
            print(f"[DB] Created statistics for simulation: {simulation_id}")
            
            # 4. Insert percentiles
            percentiles = sim_results.get('percentiles', {})
            percentiles_data = {
                'simulation_id': simulation_id,
                'percentile_5th': float(percentiles.get('5th', 0)) if percentiles.get('5th') else None,
                'percentile_25th': float(percentiles.get('25th', 0)) if percentiles.get('25th') else None,
                'percentile_50th': float(percentiles.get('50th (median)', 0)) if percentiles.get('50th (median)') else None,
                'percentile_75th': float(percentiles.get('75th', 0)) if percentiles.get('75th') else None,
                'percentile_90th': float(percentiles.get('90th', 0)) if percentiles.get('90th') else None,
                'percentile_95th': float(percentiles.get('95th', 0)) if percentiles.get('95th') else None,
                'percentile_99th': float(percentiles.get('99th', 0)) if percentiles.get('99th') else None,
            }
            
            insert_simulation_percentiles(percentiles_data)
            print(f"[DB] Created percentiles for simulation: {simulation_id}")
            
            # 5. Insert rarity statistics
            rarity_pull_counts = sim_results.get('rarity_pull_counts', {})
            rarity_value_totals = sim_results.get('rarity_value_totals', {})
            
            rarity_stats_list = []
            for rarity_name in rarity_pull_counts.keys():
                pull_count = rarity_pull_counts.get(rarity_name, 0)
                total_value = rarity_value_totals.get(rarity_name, 0)
                average_value = total_value / pull_count if pull_count > 0 else 0
                
                rarity_stats_list.append({
                    'simulation_id': simulation_id,
                    'rarity_name': rarity_name,
                    'pull_count': int(pull_count),
                    'total_value': float(total_value),
                    'average_value': float(average_value),
                })
            
            if rarity_stats_list:
                insert_rarity_stats_batch(rarity_stats_list)
                print(f"[DB] Created {len(rarity_stats_list)} rarity stats for simulation: {simulation_id}")
            
            # 6. Insert top 10 hits
            top_hits_list = []
            if top_10_hits is not None:
                # Handle DataFrame
                if hasattr(top_10_hits, 'values'):
                    top_10_hits_rows = top_10_hits.values.tolist()
                else:
                    top_10_hits_rows = top_10_hits
                
                for rank, row_data in enumerate(top_10_hits_rows, start=1):
                    if len(row_data) >= 2:  # At minimum need card_name and price
                        card_name = row_data[0]
                        price = row_data[1]
                        effective_pull_rate = row_data[2] if len(row_data) > 2 else None
                        
                        top_hits_list.append({
                            'simulation_id': simulation_id,
                            'card_name': str(card_name),
                            'price': float(price),
                            'effective_pull_rate': float(effective_pull_rate) if effective_pull_rate else None,
                            'rank': rank,
                        })
                
                if top_hits_list:
                    insert_top_hits_batch(top_hits_list)
                    print(f"[DB] Created {len(top_hits_list)} top hit records for simulation: {simulation_id}")
            
            print(f"[DB] ✅ Successfully saved complete simulation results for set {set_id}")
            return simulation_id
            
        except Exception as e:
            print(f"[DB ERROR] Failed to save simulation results: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def get_simulation_with_all_data(self, simulation_id: str):
        """
        Retrieve a complete simulation record with all related data
        
        Args:
            simulation_id: UUID of the simulation
            
        Returns:
            Dictionary with all simulation data
        """
        from db.repositories.simulation_ev_breakdown_repository import get_ev_breakdown_by_simulation_id
        from db.repositories.simulation_statistics_repository import get_statistics_by_simulation_id
        from db.repositories.simulation_percentiles_repository import get_percentiles_by_simulation_id
        from db.repositories.simulation_rarity_stats_repository import get_rarity_stats_by_simulation_id
        from db.repositories.simulation_top_hits_repository import get_top_hits_by_simulation_id
        
        try:
            simulation = get_simulation_by_id(simulation_id).data
            
            return {
                'simulation': simulation,
                'ev_breakdown': get_ev_breakdown_by_simulation_id(simulation_id),
                'statistics': get_statistics_by_simulation_id(simulation_id),
                'percentiles': get_percentiles_by_simulation_id(simulation_id),
                'rarity_stats': get_rarity_stats_by_simulation_id(simulation_id),
                'top_hits': get_top_hits_by_simulation_id(simulation_id),
            }
        except Exception as e:
            print(f"[DB ERROR] Failed to retrieve simulation data: {e}")
            return None
    
    def get_latest_simulation_for_set(self, set_name: str):
        """
        Get the most recent simulation for a specific set
        
        Args:
            set_name: Name of the set
            
        Returns:
            Dictionary with complete simulation data, or None if not found
        """
        from db.repositories.sets_repository import get_set_id_by_name
        from db.repositories.pack_simulations_repository import get_latest_simulation_by_set_id
        
        try:
            set_id = get_set_id_by_name(set_name)
            if not set_id:
                print(f"[WARN] Set '{set_name}' not found in database")
                return None
            
            latest_sim = get_latest_simulation_by_set_id(set_id)
            if not latest_sim:
                print(f"[INFO] No simulations found for set '{set_name}'")
                return None
            
            return self.get_simulation_with_all_data(latest_sim['id'])
            
        except Exception as e:
            print(f"[ERROR] Failed to retrieve latest simulation: {e}")
            return None
