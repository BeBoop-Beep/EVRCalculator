def parse_sealed_prices(endpoints, tcg_client):
    """Fetch and parse all sealed product prices"""
    price_results = {}

    for label, url in endpoints.items():
        if not url:
            print(f"{label}: $Unavailable (No URL)")
            continue

        price = tcg_client.fetch_product_market_price(url)
        if price is not None:
            print(f"{label}: ${price}")
            price_results[label] = price
        else:
            print(f"{label}: $Unavailable")

    return price_results