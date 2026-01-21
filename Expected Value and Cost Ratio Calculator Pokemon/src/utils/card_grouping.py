"""
Database-compatible card grouping utility
Groups cards by rarity for simulation and calculation purposes.
Works with database-loaded DataFrames.
"""

import pandas as pd


def group_cards_by_rarity(config, df, reverse_df=None):
    """
    Group cards by rarity category for simulation
    Handles both regular rarities and special variants (pokeball, master ball, ace spec, sir)
    
    Args:
        config: Set configuration
        df: DataFrame with card data
        reverse_df: Optional DataFrame with reverse-holo variant cards
        
    Returns:
        Dictionary with card groups:
        {
            'common': DataFrame,
            'uncommon': DataFrame,
            'rare': DataFrame,
            'reverse': DataFrame,
            'hit': DataFrame,
        }
    """
    
    df = df.copy()
    
    # Get rarity mapping from config
    rarity_mapping = getattr(config, 'RARITY_MAPPING', {})
    
    # Map rarities using config mapping
    df['rarity_group'] = df['rarity_raw'].map(rarity_mapping)
    df['rarity_group'] = df['rarity_group'].fillna(df['rarity_raw'])
    
    # Special handling for variants with special_type
    # These should go to 'hits' group regardless of their base rarity
    has_special_type = (df['special_type'].notna()) & (df['special_type'] != '')
    df.loc[has_special_type, 'rarity_group'] = 'hits'
    
    # Prepare reverse cards if provided
    reverse_pool = pd.DataFrame()
    if reverse_df is not None and not reverse_df.empty:
        reverse_pool = reverse_df.copy()
    
    result = {
        "common": df[df['rarity_group'] == 'common'],
        "uncommon": df[df['rarity_group'] == 'uncommon'],
        "rare": df[df['rarity_group'] == 'rare'],
        "reverse": reverse_pool,
        "hit": df[df['rarity_group'] == 'hits'],
    }
    
    print(f"\nCard Groups:")
    print(f"  Common: {len(result['common'])} cards")
    print(f"  Uncommon: {len(result['uncommon'])} cards")
    print(f"  Rare: {len(result['rare'])} cards")
    print(f"  Hits: {len(result['hit'])} cards")
    print(f"  Reverse: {len(result['reverse'])} cards" + (" (from database)" if not reverse_pool.empty else " (not available)"))
    
    return result
