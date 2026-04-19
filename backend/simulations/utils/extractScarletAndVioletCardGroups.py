import pandas as pd

from backend.calculations.utils.reverse_pool import build_reverse_eligible_pool

def extract_scarletandviolet_card_groups(config, df):
    reverse_df = build_reverse_eligible_pool(config, df)

    return {
        "common": df[df['rarity_group'] == 'common'],
        "uncommon": df[df['rarity_group'] == 'uncommon'],
        "rare": df[df['rarity_group'] == 'rare'],
        "reverse": reverse_df,
        "hit": df[df['rarity_group'] == 'hits'],
    }
