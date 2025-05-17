from htmlScraper import htmlScraper
from newScraper import scrape_tcgplayer_xhr
from evrCalculator import calculate_pack_ev
from printEvCalculations import append_summary_to_existing_excel

import os
# Remove the incomplete evrEtb import if not needed

def main():
     # Rating to pull rate mapping (1/X)
    PULL_RATE_MAPPING = {
        'common' : 46, # 4/46 (there are 4 commons in each pack with 46 total commons is in the set)
        'uncommon': 33, # 3/33 (there are 3 uncommons in each pack with 33 total uncommons in the set)
        'rare': 21, # 3/21 (there are 1.21 rares in each pack with 21 total rares in the set)
        'double rare': 90,
        'illustration rare': 188,
        'special illustration rare': 225,
        'ultra rare': 248,
        'hyper rare': 154,
        # Special cases (checked first)
        # 'poke ball pattern': 302,
        # 'master ball pattern': 1362,
        # 'ace spec': 128
    }

    RARITY_MAPPING = {
    # Basic rarities
    'common': 'common',
    'uncommon': 'uncommon',
    'rare': 'rare',
    
    # Rares with special names
    'double rare': 'hits',  # Grouped with standard "rare"
    
    # All "hits" (high-value cards)
    'ultra rare': 'hits',
    'hyper rare': 'hits',
    'illustration rare': 'hits',                # Added this line
    'special illustration rare': 'hits'       
    }
    
    
    # Step 1: Scrape and gather HTML Doc
    setName = input("What set are we working on: \n")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(base_dir, 'excelDocs', setName, 'pokemon_data.xlsx')
    price_guide_url = 'https://infinite-api.tcgplayer.com/priceguide/set/23237/cards/?rows=5000&productTypeID=1'
    #Test URL:'https://www.tcgplayer.com/categories/trading-and-collectible-card-games/pokemon/price-guides/sv-scarlet-and-violet-151'
    # setURL = input("What url are we scraping: \n")
    print("Scraping Info from TCGPlayer...")
    # scrape_tcgplayer(setURL)  # This creates page_content.html
    scrape_tcgplayer_xhr(excel_path, price_guide_url, PULL_RATE_MAPPING)

    # #Step 2: Scrape HTML Doc info
    # print("\nProcessing HTML data...")
    # htmlScraper(excel_path, PULL_RATE_MAPPING)  # This processes page_content.html into Excelsca


    # # Step 3: Calculate EVR Per Pack
    print("\n Calculating EVR..")
    file_path = excel_path
    results, summary_data = calculate_pack_ev(file_path, RARITY_MAPPING)
    # print(f"results: ", results)
    # print(f"outputFile: ", output_file)
    append_summary_to_existing_excel(file_path, summary_data, results)

    # Step 4: Calculate EVR For ETBscarletAndViolet151

    print("\nOperation completed successfully!")
if __name__ == "__main__":
    main()