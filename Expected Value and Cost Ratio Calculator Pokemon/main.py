import sys
import difflib
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.calculators.packCalculations import calculate_pack_stats
from src.printEvCalculations import append_summary_to_existing_excel
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
        print("We think you mean :", matches[0])
        matched_key = SET_ALIAS_MAP.get(matches[0], matches[0])
        return SET_CONFIG_MAP[matched_key], matched_key
    
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
        results, summary_data, total_ev, sim_results, top_10_hits = calculate_pack_stats(file_path, config)
       

        # # Step 3: Calculate ETB EV # #
        print("\n Calculating ETB EV..")
        etb_metrics = calculate_etb_metrics(file_path, 9, total_ev)

        # # Step 3: Calculate Booster Box EV  # #
        print("\n Calculating Booster Box EV..")
        # etb_metrics = calculate_etb_metrics(file_path, 9, total_ev)

        append_summary_to_existing_excel(file_path, summary_data, results, sim_results, top_10_hits)
    except ValueError as e:
        print(e)

    print("\nOperation completed successfully!")
if __name__ == "__main__":
    main()