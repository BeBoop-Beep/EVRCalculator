import numpy as np

from backend.configured_special_pack_resolver import resolve_configured_god_pack_rows

def sample_god_pack(god_cfg, df):
    strategy = god_cfg.get("strategy", {})
    strategy_type = strategy.get("type", "fixed")

    if strategy_type == "fixed":
        if "packs" in strategy:
            packs = strategy["packs"]
            chosen_pack = np.random.choice(packs)
            resolved_rows = resolve_configured_god_pack_rows(
                chosen_pack.get("cards", []),
                df,
                context_label=f"god.fixed_pack:{chosen_pack.get('name', '?')}",
            )
            trio_value = resolved_rows["Price ($)"].sum() if "Price ($)" in resolved_rows.columns else 0.0
            avg_common = df[df["Rarity"] == "common"]["Price ($)"].mean()
            avg_uncommon = df[df["Rarity"] == "uncommon"]["Price ($)"].mean()
            total_value = trio_value + 4 * avg_common + 3 * avg_uncommon
            # print("god pack: ", total_value)
            return total_value
        elif "cards" in strategy:
            cards = strategy.get("cards", [])
            resolved_rows = resolve_configured_god_pack_rows(
                cards,
                df,
                context_label="god.fixed_cards",
            )
            total_value = resolved_rows["Price ($)"].sum() if "Price ($)" in resolved_rows.columns else 0.0
            # print("god pack: ", total_value)
            return total_value

    elif strategy_type == "random":
        rules = strategy.get("rules", {})
        count = rules.get("count", 1)
        rarities = rules.get("rarities", [])

        total_value = 0.0

        if not rarities:
            return total_value

        if isinstance(rarities, list):
            eligible = df[df["Rarity"].isin(rarities)]
            if not eligible.empty:
                total_value += eligible["Price ($)"].sample(count, replace=True).sum()

        elif isinstance(rarities, dict):
            for rarity, qty in rarities.items():
                pool = df[df["Rarity"].str.lower().str.strip() == rarity.lower().strip()]
                if not pool.empty:
                    total_value += pool["Price ($)"].sample(qty, replace=True).sum()
        # print("god pack: ", total_value)
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