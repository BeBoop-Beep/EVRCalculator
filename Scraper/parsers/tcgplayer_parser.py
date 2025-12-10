from ..helpers.card_helper import clean_price_value, process_card
from ..helpers.sealed_price_helper import parse_sealed_prices

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
        raw_cards = raw_data.get("result", [])
        card_data = {}
        
        for card in raw_cards:
            
            product_name, card_dict = process_card(card, self.pull_rate_mapping)
            
            # Skip invalid cards
            if product_name is None:
                continue
            
            # Create unique key to differentiate card variants
            # Include: product name, special type, printing, and condition
            special_type = card_dict.get('specialType', '')
            printing = card_dict.get('printing', '')
            condition = card_dict.get('condition', '')
            
            # Build composite key
            key_parts = [product_name]
            if special_type:
                key_parts.append(special_type)
            if printing:
                key_parts.append(printing)
            if condition:
                key_parts.append(condition)
            
            unique_key = "|".join(key_parts)
            
            # Store card data with unique key (keeps each variant separate)
            card_data[unique_key] = card_dict
            
        cards = list(card_data.values())
        
        return self._clean_card_data(cards)
    
    def parse_sealed_products(self, config, client, set_name):
        """
        Parse sealed product data from a single URL.

        Args:
            config: Configuration object containing SEALED_DETAILS_URL
            client: TCGPlayerClient instance
            set_name: Name of the set for naming

        Returns:
            List of cleaned sealed product dictionaries
        """

        # Fetch data from the URL
        sealed_raw = client.fetch_price_data(config.SEALED_DETAILS_URL)
        raw_products = sealed_raw.get("result", [])

        # Deduplicate strictly by productName
        product_map = {}

        for product in raw_products:
            product_name = product.get("productName")
            if not product_name:
                continue

            # Build sealed product dict WITHOUT their productID
            product_dict = {
                "name": product_name,
                "marketPrice": product.get("marketPrice"),
                "lowPrice": product.get("lowPrice"),
                "set": product.get("set"),
                "setAbbrv": product.get("setAbbrv"),
                "type": product.get("type"),
            }

            # Use productName as the unique key
            unique_key = product_name
            product_map[unique_key] = product_dict

        cleaned_products = list(product_map.values())

        # Use your existing cleaner
        return self._clean_sealed_data(cleaned_products, set_name)

    
    def _clean_card_data(self, cards):
        """Clean and validate card data before DTO conversion"""
        cleaned = []
        for card in cards:
            
            cleaned_card = {
                'name': card.get('productName', '').strip(),
                'card_number': card.get('number'),
                'rarity': card.get('rarity', '').strip(),
                'variant': card.get('specialType'), 
                'condition': card.get('condition', '').strip(),
                'printing': card.get('printing', '').strip(),
                'pull_rate': card.get('Pull Rate (1/X)'),
                'prices': {
                    'market': clean_price_value(card.get('Price ($)')),
                }
            }
            
            # Only include cards with valid data
            if cleaned_card['name'] and cleaned_card['prices']['market'] is not None:
                cleaned.append(cleaned_card)
        
        # Write full output to file for inspection
        import json
        with open('cleaned_cards_debug.json', 'w', encoding='utf-8') as f:
            json.dump(cleaned, f, indent=2)
        print(f'counted cards: {len(cleaned)} (full list written to cleaned_cards_debug.json)')
        
        return cleaned
    
    def _clean_sealed_prices(self, prices, set_name):
        """Clean and validate sealed product prices and convert to list of dicts"""
        cleaned = []
        for product_type, price in prices.items():
            cleaned_price = clean_price_value(price)
            if cleaned_price is not None:
                cleaned.append({
                    'name': f"{set_name} {product_type}",  # e.g., "Prismatic Evolutions Booster Box"
                    'product_type': product_type,  # e.g., "Booster Box", "ETB"
                    'prices': {
                        'market': cleaned_price
                    }
                })
        return cleaned
    
    def _clean_sealed_data(self, products, set_name):
        """Clean and validate sealed product data"""
        cleaned = []
        for product in products:
            market_price = clean_price_value(product.get('marketPrice'))
            product_name = product.get('name', '').strip()
            
            if market_price is not None and product_name:
                cleaned.append({
                    'name': product_name,
                    'product_type': product.get('type', 'Sealed Product'),
                    'set_name': set_name,
                    'prices': {
                        'market': market_price,
                        'low': clean_price_value(product.get('lowPrice'))
                    }
                })
        return cleaned