from webscaperForHtml import scrape_tcgplayer
from htmlScraper import htmlScraper
from evrCalculator import calculate_pack_ev, print_results

import os
# Remove the incomplete evrEtb import if not needed

def main():
    #Test URL:'https://www.tcgplayer.com/categories/trading-and-collectible-card-games/pokemon/price-guides/sv-scarlet-and-violet-151'
    setURL = input("What url are we scraping: \n")
    
    print("Scraping Info from TCGPlayer...")
    scrape_tcgplayer(setURL)  # This creates page_content.html

    setName = input("What set are we working on: \n")
    # Excel integration
    base_dir = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(base_dir, 'excelDocs', setName, 'pokemon_data.xlsx')
    print("\nProcessing HTML data...")
    htmlScraper(excel_path)  # This processes page_content.html into Excelsca

    print("\n Calculating EVR..")
    file_path = excel_path
    results, output_file = calculate_pack_ev(file_path)
    print(f"results: ", results)
    print(f"outputFile: ", output_file)
    print_results(results)

    # print("\nOperation completed successfully!")
if __name__ == "__main__":
    main()