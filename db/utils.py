def normalize_price_field(value):
    """Simple helper to coerce string/None -> float or None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        if isinstance(value, str):
            v = value.strip().lstrip("$")
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        return None