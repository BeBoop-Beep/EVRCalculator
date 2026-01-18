"""
Main entry point for EVR Calculator
Demonstrates using completely independent manual calculator and simulation engine
Both draw from the same database but operate independently.
"""

import sys
import os
import difflib

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data.database_card_loader import DatabaseCardLoader
from src.calculators.manual_calculator import ManualCalculator
from src.calculators.simulation_engine import SimulationEngine
from constants.tcg.pokemon.scarletAndVioletEra.setMap import SET_CONFIG_MAP, SET_ALIAS_MAP
# from db.services.simulation_service import SimulationService


def get_config_for_set(user_input):
    """Resolve set input to configuration"""
    key = user_input.lower().strip()

    # Try alias map first
    if key in SET_ALIAS_MAP:
        mapped_key = SET_ALIAS_MAP[key]
        return SET_CONFIG_MAP[mapped_key]

    # Try exact key in config map
    if key in SET_CONFIG_MAP:
        return SET_CONFIG_MAP[key]

    # Try fuzzy matching against aliases and set names
    possible_inputs = list(SET_ALIAS_MAP.keys()) + list(SET_CONFIG_MAP.keys())
    matches = difflib.get_close_matches(key, possible_inputs, n=1, cutoff=0.6)
    if matches:
        print(f"We think you mean: {matches[0]}")
        return SET_CONFIG_MAP.get(SET_ALIAS_MAP.get(matches[0], matches[0]))
    
    raise ValueError(f"Set '{user_input}' not found")


def main():
    print("\n" + "="*80)
    print("EVR CALCULATOR - Refactored (Database-driven, Independent Processes)")
    print("="*80 + "\n")
    
    # Get set from user (default to 151 for testing)
    set_name = input("What set are we working on? (default: Scarlet and Violet 151) ").strip()
    if not set_name:
        set_name = "Scarlet and Violet 151"
    
    try:
        config = get_config_for_set(set_name)
        print(f"\nUsing set: {config.SET_NAME}")
        
        # =================================================================
        # STEP 1: Load card data from database (shared data source)
        # =================================================================
        print("\n[1/3] Loading card data from database...")
        loader = DatabaseCardLoader()
        
        # Get pack price from config
        pack_price = getattr(config, 'PACK_PRICE', 4.00)  # Default to $4.00
        
        df, _ = loader.load_cards_for_set(config.SET_NAME, pack_price)
        reverse_df = loader.get_reverse_cards()
        
        # =================================================================
        # STEP 2: Run MANUAL calculations (independent process)
        # =================================================================
        print("\n[2/3] Running manual EV calculations...")
        manual_calc = ManualCalculator(config)
        manual_results = manual_calc.calculate(df, pack_price)
        
        # =================================================================
        # STEP 3: Run SIMULATION (independent process)
        # =================================================================
        print("[3/3] Running Monte Carlo simulation...")
        sim_engine = SimulationEngine(config)
        sim_results = sim_engine.run_simulation(df, pack_price, reverse_df, num_simulations=100000)
        
        # =================================================================
        # STEP 4: Save results to database (COMMENTED OUT FOR TESTING)
        # =================================================================
        # print("\n=== SAVING RESULTS TO DATABASE ===")
        # simulation_service = SimulationService()
        # 
        # # Prepare data for database save
        # save_data = {
        #     'set_name': config.SET_NAME,
        #     'manual_results': manual_results,
        #     'simulation_results': sim_results,
        # }
        # 
        # # Note: You may need to update SimulationService.save_pack_simulation()
        # # to accept both manual and simulation results independently
        # simulation_id = simulation_service.save_pack_simulation(
        #     set_name=config.SET_NAME,
        #     results={
        #         'total_manual_ev': manual_results['total_ev'],
        #         'simulated_ev': sim_results['simulated_ev'],
        #         'pack_price': pack_price,
        #         'hit_probability_percentage': manual_results['hit_probability_percent'],
        #         'net_value': sim_results['net_value'],
        #         'opening_pack_roi': sim_results['roi'],
        #         'opening_pack_roi_percent': sim_results['roi_percent'],
        #     },
        #     summary_data=manual_results['ev_breakdown'],
        #     sim_results=sim_results,
        #     top_10_hits=sim_results['top_hits']
        # )
        # 
        # if simulation_id:
        #     print(f"✅ Successfully saved to database with ID: {simulation_id}")
        # else:
        #     print("⚠️  Warning: Failed to save to database.")
        
        # =================================================================
        # STEP 5: Display comparison
        # =================================================================
        print("\n" + "="*80)
        print("RESULTS COMPARISON")
        print("="*80)
        print(f"\nSet: {config.SET_NAME}")
        print(f"Pack Price: ${pack_price:.2f}")
        print(f"\nManual Calculation:")
        print(f"  Expected Value: ${manual_results['total_ev']:.4f}")
        print(f"  ROI: {manual_results['roi_percent']:.2f}%")
        print(f"\nMonte Carlo Simulation ({100000:,} packs):")
        print(f"  Expected Value: ${sim_results['simulated_ev']:.4f}")
        print(f"  Std Dev: ${sim_results['std_dev']:.4f}")
        print(f"  ROI: {sim_results['roi_percent']:.2f}%")
        print(f"  5th Percentile: ${sim_results['percentiles']['5th']:.4f}")
        print(f"  95th Percentile: ${sim_results['percentiles']['95th']:.4f}")
        print(f"\nDifference: ${abs(manual_results['total_ev'] - sim_results['simulated_ev']):.4f}")
        print("="*80 + "\n")
        
    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
