from .pull_rate_helper import determine_pull_rate

def parse_card_data(raw_cards, pull_rate_mapping):
    """Parse raw card data from TCGPlayer into structured format"""
    card_data = {}

    for card in raw_cards:
        product_name = card.get('productName')
        condition = card.get('condition')
        printing = card.get('printing')
        market_price = card.get('marketPrice')
        rarity = card.get('rarity')

        #TODO: Use this condition later for filtering before simulations
        # if not (product_name and condition and market_price and "Near Mint" in condition):
        #     continue

        if not (product_name and condition and market_price):
                    continue
 
        if "code card" in product_name.lower():
            continue

        is_reverse = 'Reverse' in printing or 'Reverse Holofoil' in printing

        if product_name not in card_data:
            pull_rate, normalized_rarity = determine_pull_rate(product_name, rarity, pull_rate_mapping)

            card_data[product_name] = {
                'productName': product_name,
                'Price ($)': '',
                'Reverse Variant Price ($)': '',
                'rarity': normalized_rarity,
                'Pull Rate (1/X)': pull_rate,
            }

        if is_reverse:
            card_data[product_name]['Reverse Variant Price ($)'] = market_price
        else:
            card_data[product_name]['Price ($)'] = market_price

    return list(card_data.values())