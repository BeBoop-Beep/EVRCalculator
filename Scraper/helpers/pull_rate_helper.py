def determine_pull_rate(card_name, rarity_text, pull_rate_mapping):
    """Determine pull rate and normalized rarity for a card"""
    card_name_lower = card_name.lower()
    rarity_lower = rarity_text.lower().strip()

    # Check special cases first
    if 'master ball' in card_name_lower:
        return 1362, 'master ball'
    if 'pokeball' in card_name_lower:
        return 302, 'pokeball'
    if 'ace spec rare' in rarity_lower:
        return 128, 'ace spec rare'

    # Use exact matching first
    for rarity_key in pull_rate_mapping:
        if rarity_lower == rarity_key:
            return pull_rate_mapping[rarity_key], rarity_key

    # Fallback fuzzy match
    for rarity_key in pull_rate_mapping:
        if rarity_key in rarity_lower:
            return pull_rate_mapping[rarity_key], rarity_key

    return None, rarity_text