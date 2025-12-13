import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Scraper.services.orchestrators.tcg_player_orchestrator import TCGScraper  # Import the class, not the module
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
        
        # Set to True to enable database ingestion
        scraper = TCGScraper(enable_db_ingestion=True)  # Change to False to skip DB
        payload = scraper.scrape(config, excel_path)  # Call the scrape method
        
        print("\n✅ DTO Payload created successfully")
        print(f"   Cards: {len(payload.get('cards', []))}")
        print(f"   Sealed Products: {len(payload.get('sealed_products', []))}")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    print("\nOperation completed successfully!")

if __name__ == "__main__":
    main()