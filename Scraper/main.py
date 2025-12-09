import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Scraper.services.tcg_player_orchestrator import TCGScraper  # Import the class, not the module
from Scraper.config.get_set_config import get_config_for_set

def main():
    # # Step 1: Scrape and gather HTML Doc  # #
    setName = input("What set are we working on: \n")
    try:
        config = get_config_for_set(setName)
        print(config.SET_NAME, ", ", config.CARD_DETAILS_URL)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        excel_path = os.path.join(project_root, 'excelDocs', config.SET_NAME, 'pokemon_data.xlsx')

        print("Scraping Info from TCGPlayer...")
        scraper = TCGScraper()  # Instantiate the class
        payload = scraper.scrape(config, excel_path, setName)  # Call the scrape method
        
        #TODO: WE are failing before we make it to this print. Find out where and why. 
        print("\nDTO Payload")
        print("printing DTO: ", payload)

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    print("\nOperation completed successfully!")

if __name__ == "__main__":
    main()