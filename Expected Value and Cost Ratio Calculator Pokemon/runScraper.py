from webscaperForHtml import scrape_tcgplayer
from htmlScraper import htmlScraper
from evrCalculator import is_hit
# Remove the incomplete evrEtb import if not needed

def main():
    #Test URL:'https://www.tcgplayer.com/categories/trading-and-collectible-card-games/pokemon/price-guides/sv-scarlet-and-violet-151'
    # setURL = input("What url are we scraping: \n")
    
    # print("Scraping Info from TCGPlayer...")
    # scrape_tcgplayer(setURL)  # This creates page_content.html

    # setName = input("What set are we working on: \n")
    # print("\nProcessing HTML data...")
    # htmlScraper(setName)  # This processes page_content.html into Excel

    
    # print("\nOperation completed successfully!")

if __name__ == "__main__":
    main()