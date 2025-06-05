import difflib
import os

from src.scrapers.newScraper import scrape_tcgplayer_xhr
from src.calculators.evrCalculator import calculate_pack_ev
from src.printEvCalculations import append_summary_to_existing_excel
from constants.scarletAndVioletEra.setMap import SET_CONFIG_MAP, SET_ALIAS_MAP


def main():
    # Rating to pull rate mapping (1/X)
    def get_config_for_set(user_input):
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
        print("We think you mean :", matches[0])
        return SET_CONFIG_MAP[matches[0]]
    
    # # Step 1: Scrape and gather HTML Doc  # #
    setName = input("What set are we working on: \n")
    try:
        config = get_config_for_set(setName)
        print(config.SET_NAME, ", ", config.SCRAPE_URL)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        excel_path = os.path.join(base_dir, 'excelDocs', config.SET_NAME, 'pokemon_data.xlsx')

        print("Scraping Info from TCGPlayer...")
        scrape_tcgplayer_xhr(excel_path, config)

        # # Step 2: Calculate EVR Per Pack # #
        print("\n Calculating EVR..")
        file_path = excel_path
        results, summary_data = calculate_pack_ev(file_path, config)
        append_summary_to_existing_excel(file_path, summary_data, results)

        # # Step 3: Calculate EVR For ETBscarletAndViolet151  # #

    except ValueError as e:
        print(e)

    print("\nOperation completed successfully!")
if __name__ == "__main__":
    main()