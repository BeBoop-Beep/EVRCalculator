from ..helpers.card_helper import parse_card_data
from ..helpers.sealed_price_helper import parse_sealed_prices
from ..helpers.price_cleaner_helper import clean_price_value

class TCGPlayerParser:
    def __init__(self, pull_rate_mapping):
        """
        Initialize the parser with configuration
        
        Args:
            pull_rate_mapping: Dictionary mapping rarities to pull rates
        """
        self.pull_rate_mapping = pull_rate_mapping
    
    def parse_cards(self, raw_data):
        """
        Parse raw card data from TCGPlayer API
        
        Args:
            raw_data: Raw JSON response from TCGPlayer
            
        Returns:
            List of parsed and cleaned card dictionaries
        """
        cards = parse_card_data(raw_data.get("result", []), self.pull_rate_mapping)
        return self._clean_card_data(cards)
    
    def parse_sealed_products(self, price_endpoints, client):
        """
        Parse sealed product prices
        
        Args:
            price_endpoints: Dictionary of product type -> URL
            client: TCGPlayerClient instance
            
        Returns:
            Dictionary of cleaned sealed product prices
        """
        prices = parse_sealed_prices(price_endpoints, client)
        return self._clean_sealed_prices(prices)
    
    def _clean_card_data(self, cards):
        """Clean and validate card data before DTO conversion"""
        cleaned = []
        for card in cards:
            cleaned_card = {
                'name': card.get('productName', '').strip(),
                'rarity': card.get('rarity', '').strip(),
                'pull_rate': card.get('Pull Rate (1/X)'),
                'price': clean_price_value(card.get('Price ($)')),
                'reverse_price': clean_price_value(card.get('Reverse Variant Price ($)'))
            }
            # Only include cards with valid data
            if cleaned_card['name'] and cleaned_card['price'] is not None:
                cleaned.append(cleaned_card)
        return cleaned
    
    def _clean_sealed_prices(self, prices):
        """Clean and validate sealed product prices"""
        return {
            product: clean_price_value(price)
            for product, price in prices.items()
            if price is not None
        }