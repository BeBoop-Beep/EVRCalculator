import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Scraper.scrapers.tcg_scraper import TCGScraper  # Import the class, not the module
from Scraper.config.get_set_config import get_config_for_set

def main():
    # # Step 1: Scrape and gather HTML Doc  # #
    setName = input("What set are we working on: \n")
    try:
        config = get_config_for_set(setName)
        print(config.SET_NAME, ", ", config.SCRAPE_URL)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        excel_path = os.path.join(project_root, 'excelDocs', config.SET_NAME, 'pokemon_data.xlsx')

        print("Scraping Info from TCGPlayer...")
        scraper = TCGScraper()  # Instantiate the class
        scraper.scrape(config, excel_path)  # Call the scrape method

    except ValueError as e:
        print(e)

    print("\nOperation completed successfully!")

if __name__ == "__main__":
    main()