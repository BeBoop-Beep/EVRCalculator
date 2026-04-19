import numpy as np
import pandas as pd


SPECIAL_PATTERN_NAME_REGEX = r"Master Ball|Poke Ball"
REVERSE_PRICE_COLUMN = "Reverse Variant Price ($)"


def get_normalized_reverse_eligible_rarities(config) -> set[str]:
    provider = getattr(config, "get_reverse_eligible_rarities", None)
    if not callable(provider):
        raise ValueError("Config must define get_reverse_eligible_rarities() for reverse EV calculations.")

    return {
        str(rarity).strip().lower()
        for rarity in provider()
        if rarity is not None and str(rarity).strip()
    }


def get_normalized_rarity_series(df: pd.DataFrame) -> pd.Series:
    if "rarity_raw" in df.columns:
        source = df["rarity_raw"]
    elif "Rarity" in df.columns:
        source = df["Rarity"]
    else:
        raise ValueError("Reverse EV calculations require either 'rarity_raw' or 'Rarity'.")

    return source.astype(str).str.strip().str.lower()


def build_reverse_eligible_pool(config, df: pd.DataFrame) -> pd.DataFrame:
    if REVERSE_PRICE_COLUMN not in df.columns:
        return df.iloc[0:0].copy()

    rarity_normalized = get_normalized_rarity_series(df)
    reverse_eligible_rarities = get_normalized_reverse_eligible_rarities(config)
    eligible_mask = rarity_normalized.isin(reverse_eligible_rarities)

    if "Card Name" in df.columns:
        explicit_pattern_rarities = {
            rarity for rarity in reverse_eligible_rarities if "pattern" in rarity or "ball" in rarity
        }
        pattern_mask = df["Card Name"].astype(str).str.contains(
            SPECIAL_PATTERN_NAME_REGEX,
            case=False,
            na=False,
        )
        eligible_mask = eligible_mask & ~(pattern_mask & ~rarity_normalized.isin(explicit_pattern_rarities))

    reverse_prices = pd.to_numeric(df[REVERSE_PRICE_COLUMN], errors="coerce")
    reverse_pool = df.loc[eligible_mask & reverse_prices.notna()].copy()
    reverse_pool[REVERSE_PRICE_COLUMN] = reverse_prices.loc[reverse_pool.index].astype(float)
    return reverse_pool


def get_regular_reverse_probability(slot_name: str, slot_config: dict) -> float:
    if not isinstance(slot_config, dict) or not slot_config:
        raise ValueError(f"Reverse slot '{slot_name}' must define a non-empty probability mapping.")

    normalized_probs = pd.to_numeric(pd.Series(slot_config), errors="coerce")
    if normalized_probs.isna().any():
        raise ValueError(f"Reverse slot '{slot_name}' contains a non-numeric probability.")

    if ((normalized_probs < 0) | (normalized_probs > 1)).any():
        raise ValueError(f"Reverse slot '{slot_name}' contains a probability outside [0, 1].")

    prob_sum = float(normalized_probs.sum())
    if not np.isclose(prob_sum, 1.0, atol=1e-8):
        raise ValueError(f"Reverse slot '{slot_name}' probabilities must sum to 1.0. Found {prob_sum:.12f}")

    regular_reverse_prob = float(normalized_probs.get("regular reverse", 0.0))
    if regular_reverse_prob < 0 or regular_reverse_prob > 1:
        raise ValueError(f"Reverse slot '{slot_name}' regular reverse probability is invalid.")

    return regular_reverse_prob