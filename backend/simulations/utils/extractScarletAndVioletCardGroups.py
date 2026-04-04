import pandas as pd

def extract_scarletandviolet_card_groups(config, df):
    reverse_eligible_rarities = config.get_reverse_eligible_rarities()

    # Filter reverse-eligible cards that have valid reverse pricing
    reverse_df = df[
        df['rarity_raw'].isin(reverse_eligible_rarities) &
        df['Reverse Variant Price ($)'].notna() &
        (df['Reverse Variant Price ($)'] != "")
    ].copy()

    # Parse the price as a float
    reverse_df['EV_Reverse'] = pd.to_numeric(reverse_df['Reverse Variant Price ($)'], errors='coerce')
    reverse_df = reverse_df[reverse_df['EV_Reverse'].notna()]

    return {
        "common": df[df['rarity_group'] == 'common'],
        "uncommon": df[df['rarity_group'] == 'uncommon'],
        "rare": df[df['rarity_group'] == 'rare'],
        "reverse": reverse_df,
        "hit": df[df['rarity_group'] == 'hits'],
    }
