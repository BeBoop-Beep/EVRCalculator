import numpy as np

def sample_god_pack(strategy_config, df):
    strategy = strategy_config.get("strategy", {})
    strategy_type = strategy.get("type", "fixed")

    if strategy_type == "fixed":
        cards = strategy.get("cards", [])
        card_values = df[df["Card Name"].isin(cards)]["Price ($)"]
        return card_values.sum()

    elif strategy_type == "random":
        rules = strategy.get("rules", {})
        count = rules.get("count", 1)
        rarities = rules.get("rarities", [])

        total_value = 0.0

        if not rarities:
            return total_value

        if isinstance(rarities, list):
            # If 'rarities' is a single list, treat all cards as same rarity pool
            eligible = df[df["Rarity"].isin(rarities)]
            if not eligible.empty:
                total_value += eligible["Price ($)"].sample(count, replace=True).sum()

        elif isinstance(rarities, dict):
            # New strategy: multiple rarity slots defined as counts
            for rarity, qty in rarities.items():
                pool = df[df["Rarity"].str.lower().str.strip() == rarity.lower().strip()]
                if not pool.empty:
                    total_value += pool["Price ($)"].sample(qty, replace=True).sum()

        return total_value

    return 0.0

def sample_demi_god_pack(strategy_config, df, common_cards, uncommon_cards):
    rules = strategy_config.get("strategy", {}).get("rules", {})
    count = rules.get("count", 1)
    rarities = rules.get("rarities", [])
    
    # Commons and uncommons are still sampled normally
    total_value = 0.0
    total_value += common_cards['Price ($)'].sample(4, replace=True).sum()
    total_value += uncommon_cards['Price ($)'].sample(3, replace=True).sum()
    
    # Sample X cards from high-rarity pool
    eligible_high_rarity = df[df["Rarity"].isin(rarities)]
    if not eligible_high_rarity.empty:
        total_value += eligible_high_rarity['Price ($)'].sample(count, replace=True).sum()
  
    return total_value