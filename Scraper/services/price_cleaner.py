def clean_price_value(price_str):
    if not price_str:
        return None
    if isinstance(price_str, (int, float)):
        return price_str
    price_str = price_str.strip()
    if price_str.lower().startswith("$"):
        try:
            return float(price_str[1:])
        except ValueError:
            return None
    if price_str.lower() in ["unavailable", "n/a", "no url"]:
        return None
    try:
        # Try converting directly to float if no $
        return float(price_str)
    except ValueError:
        return None
