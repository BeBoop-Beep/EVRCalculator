import sys
import difflib
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.calculators.packCalculations import PackCalculationOrchestrator
from src.printEvCalculations import append_summary_to_existing_excel
from src.calculators.evrEtb import calculate_etb_metrics
from constants.tcg.pokemon.scarletAndVioletEra.setMap import SET_CONFIG_MAP, SET_ALIAS_MAP


def get_config_for_set(user_input):
    """Fuzzy match set name/alias to configuration"""
    key = user_input.lower().strip()

    # Try alias map first
    if key in SET_ALIAS_MAP:
        mapped_key = SET_ALIAS_MAP[key]
        return SET_CONFIG_MAP[mapped_key], mapped_key

    # Try exact key in config map
    if key in SET_CONFIG_MAP:
        return SET_CONFIG_MAP[key], key

    # Try fuzzy matching against aliases and set names
    possible_inputs = list(SET_ALIAS_MAP.keys()) + list(SET_CONFIG_MAP.keys())
    matches = difflib.get_close_matches(key, possible_inputs, n=1, cutoff=0.6)
    print("We think you mean :", matches[0])
    matched_key = SET_ALIAS_MAP.get(matches[0], matches[0])
    return SET_CONFIG_MAP[matched_key], matched_key


def main():
    """Main entry point demonstrating decoupled calculator and simulator"""
    
    setName = input("What set are we working on: \n")
    try:
        config, folder_name = get_config_for_set(setName)
        print(config.SET_NAME, ", ", config.CARD_DETAILS_URL)
        
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Use FOLDER_NAME from config if available, otherwise use folder_name
        actual_folder_name = getattr(config, 'FOLDER_NAME', folder_name)
        excel_path = os.path.join(project_root, 'excelDocs', actual_folder_name, 'pokemon_data.xlsx')

        # Initialize orchestrator
        orchestrator = PackCalculationOrchestrator(config)

        # ===== OPTION 1: Run Calculator and Simulator Independently =====
        print("\n--- RUNNING CALCULATOR ---")
        summary_data, total_manual_ev, top_10_hits, df, pack_price = orchestrator.calculate_manual_ev(excel_path)
        
        print("\n--- RUNNING SIMULATOR ---")
        sim_results, pack_metrics = orchestrator.run_monte_carlo_simulation(df, pack_price, n=100000, run_validations=True)

        # ===== OPTION 2 (Alternative): Use legacy method for backward compatibility =====
        # Uncomment below to use the original orchestrated flow instead:
        # results, summary_data, total_simulated_ev, sim_results, top_10_hits = orchestrator.calculate_pack_ev(excel_path)
        # return

        # Calculate ETB EV
        print("\n--- CALCULATING ETB EV ---")
        etb_metrics = calculate_etb_metrics(excel_path, 9, pack_metrics['total_ev'])

        # Calculate Booster Box EV (similar pattern)
        print("\n--- CALCULATING BOOSTER BOX EV ---")
        # Additional calculation as needed

        # Compile final results for output
        results = {
            "total_manual_ev": total_manual_ev,
            "actual_simulated_ev": pack_metrics['total_ev'],
            "pack_price": pack_price,
            "net_value": pack_metrics['net_value'],
            "opening_pack_roi": pack_metrics['opening_pack_roi'],
            "opening_pack_roi_percent": pack_metrics['opening_pack_roi_percent'],
        }

        # Export results to Excel
        append_summary_to_existing_excel(excel_path, summary_data, results, sim_results, top_10_hits)

    except ValueError as e:
        print(e)

    print("\nOperation completed successfully!")


if __name__ == "__main__":
    main()
