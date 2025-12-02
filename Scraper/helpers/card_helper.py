import re
from .pull_rate_helper import determine_pull_rate

def clean_condition(condition):
    """Remove printing suffixes from condition string"""
    if not condition:
        return condition
    
    # List of printing suffixes to remove
    printing_suffixes = [
        'Reverse Holofoil',
        'Reverse',
        'Holofoil',
        '1st Edition',
        'Unlimited'
    ]
    
    # Remove each suffix from the condition
    cleaned = condition.strip()
    for suffix in printing_suffixes:
        cleaned = cleaned.replace(suffix, '').strip()
    
    return cleaned

def clean_product_name(product_name, remove_special_patterns=False):
    """
    Remove card number suffix and optionally special type patterns from product name
    
    Args:
        product_name: The raw product name
        remove_special_patterns: If True, also remove special type patterns like (Poke Ball Pattern)
    """
    if not product_name:
        return product_name
    
    # Remove pattern like " - 040/165" or " - 123/456"
    cleaned = re.sub(r'\s*-\s*\d+/\d+\s*$', '', product_name)
    
    if remove_special_patterns:
        # Remove special type patterns from the name
        special_patterns = [
            r'\s*\(Master Ball[^)]*\)',
            r'\s*\(Poke Ball[^)]*\)',
            r'\s*\(Poké Ball[^)]*\)',
            r'\s*\(ACE SPEC[^)]*\)',
        ]
        for pattern in special_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()

def determine_special_type(product_name, rarity=None):
    """
    Determine if card has a special type designation based on product name or rarity
    
    Args:
        product_name: The product name (before cleaning special patterns)
        rarity: The card's rarity string (may contain special type info)
        
    Returns:
        String indicating special type or None
    """
    if not product_name:
        return None
    
    # Check rarity field first (for cards like ACE SPEC that only appear in rarity)
    if rarity:
        rarity_lower = rarity.lower()
        if "ace spec" in rarity_lower:
            return "ACE SPEC"
    
    # Then check product name for pattern-based special types
    name_lower = product_name.lower()
    
    # Check more specific patterns first to avoid substring matching issues
    if "master ball" in name_lower:
        return "Master Ball"
    elif "ace spec" in name_lower:
        return "ACE SPEC"
    elif "poke ball" in name_lower or "poké ball" in name_lower or "pokeball" in name_lower:
        return "Pokeball" 
    
    return None

def clean_price_value(price_str):
    """Convert price string to float, handling various formats"""
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

def process_card(card, pull_rate_mapping):
    """
    Process a single card from raw TCGPlayer data
    
    Args:
        card: Raw card dictionary from TCGPlayer API
        pull_rate_mapping: Dictionary mapping rarities to pull rates
        
    Returns:
        Tuple of (product_name, card_dict) if valid, or (None, None) if card should be skipped
    """
    # First pass: clean product name but keep special patterns for detection
    product_name_raw = clean_product_name(card.get('productName'), remove_special_patterns=False)
    
    # Get rarity for special type detection
    rarity = card.get('rarity')
    
    # Determine special type before removing it from the name (check both name and rarity)
    special_type = determine_special_type(product_name_raw, rarity)
    
    # Second pass: clean product name and remove special patterns
    product_name = clean_product_name(card.get('productName'), remove_special_patterns=True)
    condition = clean_condition(card.get('condition'))
    number = card.get('number')
    printing = card.get('printing')
    market_price = card.get('marketPrice')
    # rarity already extracted above for special type detection

    # Validation: skip cards with missing required fields
    if not (product_name and condition and market_price):
        return None, None
    
    # Skip code cards
    if "code card" in product_name.lower():
        return None, None

    # Determine pull rate and normalized rarity
    pull_rate, normalized_rarity = determine_pull_rate(product_name, rarity, pull_rate_mapping)

    # Build card data structure
    card_dict = {
        'productName': product_name,
        'number': number,
        'printing': printing,
        'condition': condition,
        'rarity': normalized_rarity,
        'specialType': special_type,
        'Pull Rate (1/X)': pull_rate,
        'Price ($)': market_price,
    }

    return product_name, card_dict