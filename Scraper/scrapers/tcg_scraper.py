from ..clients.tcgplayer_client import TCGPlayerClient
from ..parsers.card_parser import parse_card_data
from ..parsers.sealed_price_parser import parse_sealed_prices
from ..exporters.excel_writer import save_to_excel

class TCGScraper:
    def __init__(self):
        self.client = TCGPlayerClient()
    
    def scrape(self, config, excel_path):
        """Main scraping workflow"""
        # Fetch and parse cards
        raw_data = self.client.fetch_card_data(config.SCRAPE_URL)
        cards = parse_card_data(raw_data.get("result", []), config.PULL_RATE_MAPPING)
        
        # Fetch sealed prices
        prices = parse_sealed_prices(config.PRICE_ENDPOINTS, self.client)
        
        # Save to Excel
        save_to_excel(cards, prices, excel_path)