import sys
import difflib
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.calculators.packCalcsRefractored import calculate_pack_stats
from src.simulations import calculate_pack_simulations
from src.calculators.evrEtb import calculate_etb_metrics
from constants.tcg.pokemon.scarletAndVioletEra.setMap import SET_CONFIG_MAP, SET_ALIAS_MAP


def main():
    # Rating to pull rate mapping (1/X)
    def get_config_for_set(user_input):
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
        
        if matches:
            matched_key = matches[0]
            # Check if it's an alias and resolve to actual key
            if matched_key in SET_ALIAS_MAP:
                matched_key = SET_ALIAS_MAP[matched_key]
            print("We think you mean :", matched_key)
            return SET_CONFIG_MAP[matched_key], matched_key
        
        # No matches found
        raise ValueError(f"Set '{user_input}' not found. Please check the set name and try again.")
    
    # # Step 1: Scrape and gather HTML Doc  # #
    setName = input("What set are we working on: \n")
    try:
        config, folder_name = get_config_for_set(setName)
        print(config.SET_NAME, ", ", config.CARD_DETAILS_URL)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        excel_path = os.path.join(project_root, 'excelDocs', folder_name, 'pokemon_data.xlsx')

        # # Step 2: Calculate EVR Per Pack # #
        print("\n Calculating EVR..")
        file_path = excel_path
        results, summary_data, top_10_hits, pack_price = calculate_pack_stats(file_path, config)

        sim_results, pack_metrics = calculate_pack_simulations(file_path, config)
        total_ev = pack_metrics['total_ev']

        results.update({
            "acutal_simulated_ev": pack_metrics['total_ev'],
            "net_value": pack_metrics['net_value'],
            "opening_pack_roi": pack_metrics['opening_pack_roi'],
            "opening_pack_roi_percent": pack_metrics['opening_pack_roi_percent'],
        })
       

        # # Step 3: Calculate ETB EV # #
        print("\n Calculating ETB EV..")
        etb_metrics = calculate_etb_metrics(file_path, 9, total_ev)

        # # Step 3: Calculate Booster Box EV  # #
        print("\n Calculating Booster Box EV..")
        # etb_metrics = calculate_etb_metrics(file_path, 9, total_ev)

        # append_summary_to_existing_excel(file_path, summary_data, results, sim_results, top_10_hits)
    except ValueError as e:
        print(e)

    print("\nOperation completed successfully!")
if __name__ == "__main__":
    main()