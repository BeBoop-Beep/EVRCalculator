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
        
        print("raw cards length: ", len(raw_cards))
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
    
    def parse_sealed_products(self, price_endpoints, client, set_name):
        """
        Parse sealed product prices
        
        Args:
            price_endpoints: Dictionary of product type -> URL
            client: TCGPlayerClient instance
            set_name: Name of the set for product naming
            
        Returns:
            List of cleaned sealed product dictionaries
        """
        prices = parse_sealed_prices(price_endpoints, client)
        return self._clean_sealed_prices(prices, set_name)
    
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
        
        # Quick check for Max Rod
        max_rod_cards = [c for c in cleaned if 'Max Rod' in c['name']]
        print(f"Max Rod variants found: {len(max_rod_cards)}")
        if max_rod_cards:
            print("Max Rod entries:", json.dumps(max_rod_cards, indent=2))
        
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