import logging

import pandas as pd

from backend.calculations.utils.reverse_pool import build_reverse_eligible_pool
from backend.simulations.utils.simulationTokenResolver import get_row_match_keys


logger = logging.getLogger(__name__)


def _log_value_counts(label: str, values: pd.Series, max_rows: int = 20) -> None:
    series = values.fillna("<NA>").astype(str)
    counts = series.value_counts(dropna=False)
    logger.warning("[POOL_INPUT_PROFILE] %s unique=%d total=%d", label, int(len(counts)), int(len(series)))
    for value, count in counts.head(max_rows).items():
        logger.warning("[POOL_INPUT_PROFILE] %s value=%s count=%d", label, value, int(count))
    if len(counts) > max_rows:
        logger.warning(
            "[POOL_INPUT_PROFILE] %s truncated_unique_values=%d",
            label,
            int(len(counts) - max_rows),
        )


def _build_pattern_overlay_mask(df: pd.DataFrame) -> pd.Series:
    pattern_keys, _ = get_row_match_keys(df, mode='pattern')
    return pattern_keys.ne('')


def _build_hit_pool_mask(df: pd.DataFrame) -> pd.Series:
    if 'rarity_group' in df.columns:
        base_hit_mask = df['rarity_group'].fillna('').astype(str).str.strip().eq('hits')
    else:
        rarity_keys, _ = get_row_match_keys(df, mode='base_rarity')
        base_hit_mask = rarity_keys.ne('') & ~rarity_keys.isin({'common', 'uncommon', 'rare'})

    pattern_hit_mask = _build_pattern_overlay_mask(df)
    return base_hit_mask | pattern_hit_mask


def get_sim_base_rarity(df: pd.DataFrame) -> pd.Series:
    """Return base rarity keys for simulation pool building.
    Prefers base_rarity_key (BASE-RARITY ONLY column) over rarity_key.
    """
    if 'base_rarity_key' in df.columns:
        return df['base_rarity_key'].fillna('').astype(str)
    if 'rarity_key' in df.columns:
        return df['rarity_key'].fillna('').astype(str)
    return pd.Series('', index=df.index, dtype='object')


def get_sim_pattern(df: pd.DataFrame) -> pd.Series:
    """Return pattern keys for simulation pool building.
    pattern_key is the ONLY source of overlay truth.
    """
    if 'pattern_key' in df.columns:
        return df['pattern_key'].fillna('').astype(str)
    pattern_keys, _ = get_row_match_keys(df, mode='pattern')
    return pattern_keys


def _build_base_pool_mask(df: pd.DataFrame, rarity_key: str) -> pd.Series:
    base_rarity_keys, _ = get_row_match_keys(df, mode='base_rarity')
    pattern_overlay_mask = _build_pattern_overlay_mask(df)
    # Rows with a non-empty pattern_key belong exclusively to the pattern/hit pool.
    # They MUST be excluded from base rarity (common/uncommon/rare) pools to
    # prevent EV inflation from masterball/pokeball rows leaking into base slots.
    return base_rarity_keys.eq(rarity_key) & ~pattern_overlay_mask

def extract_scarletandviolet_card_groups(config, df):
    # Track source rows so overlapping semantic pool views can still avoid
    # duplicate slot sampling when needed.
    source_df = df.copy()
    if '__source_row_index__' not in source_df.columns:
        source_df['__source_row_index__'] = source_df.index

    reverse_df = build_reverse_eligible_pool(config, source_df)
    hit_pool_mask = _build_hit_pool_mask(source_df)

    for column in (
        'Rarity',
        'rarity_raw',
        'rarity_key',
        'pattern_key',
        'aggregation_key',
        'classification_key',
    ):
        if column in source_df.columns:
            _log_value_counts(column, source_df[column])

    base_rarity_keys, base_rarity_key_source = get_row_match_keys(source_df, mode='base_rarity')
    logger.warning("[POOL_INPUT_PROFILE] base_rarity_key_source=%s", base_rarity_key_source)
    _log_value_counts("base_rarity_key", base_rarity_keys)
    logger.warning(
        "[POOL_INPUT_PROFILE] base_rarity_key_counts common=%d uncommon=%d rare=%d",
        int(base_rarity_keys.eq('common').sum()),
        int(base_rarity_keys.eq('uncommon').sum()),
        int(base_rarity_keys.eq('rare').sum()),
    )

    common_pool = source_df[_build_base_pool_mask(source_df, 'common')]
    uncommon_pool = source_df[_build_base_pool_mask(source_df, 'uncommon')]
    rare_pool = source_df[_build_base_pool_mask(source_df, 'rare')]
    hit_pool = source_df[hit_pool_mask]

    pattern_keys_source, _ = get_row_match_keys(df, mode='pattern')
    pokeball_pattern_mask = pattern_keys_source.eq('pokeball_pattern')
    master_ball_pattern_mask = pattern_keys_source.eq('master_ball_pattern')
    all_pattern_mask = pokeball_pattern_mask | master_ball_pattern_mask

    # --- HARD ASSERTIONS: pattern rows must not exist in base pools ---
    common_pattern_mask = _build_pattern_overlay_mask(common_pool)
    uncommon_pattern_mask = _build_pattern_overlay_mask(uncommon_pool)
    rare_pattern_mask = _build_pattern_overlay_mask(rare_pool)

    common_pattern_count = int(common_pattern_mask.sum()) if not common_pool.empty else 0
    uncommon_pattern_count = int(uncommon_pattern_mask.sum()) if not uncommon_pool.empty else 0
    rare_pattern_count = int(rare_pattern_mask.sum()) if not rare_pool.empty else 0

    if common_pattern_count > 0:
        leaked = common_pool.loc[common_pattern_mask, 'Card Name'].tolist() if 'Card Name' in common_pool.columns else []
        raise ValueError(
            f"[POOL_INTEGRITY] {common_pattern_count} pattern row(s) leaked into common_pool. "
            f"Sample: {leaked[:5]}"
        )
    if uncommon_pattern_count > 0:
        leaked = uncommon_pool.loc[uncommon_pattern_mask, 'Card Name'].tolist() if 'Card Name' in uncommon_pool.columns else []
        raise ValueError(
            f"[POOL_INTEGRITY] {uncommon_pattern_count} pattern row(s) leaked into uncommon_pool. "
            f"Sample: {leaked[:5]}"
        )
    if rare_pattern_count > 0:
        leaked = rare_pool.loc[rare_pattern_mask, 'Card Name'].tolist() if 'Card Name' in rare_pool.columns else []
        raise ValueError(
            f"[POOL_INTEGRITY] {rare_pattern_count} pattern row(s) leaked into rare_pool. "
            f"Sample: {leaked[:5]}"
        )

    pattern_indices = set(df.index[all_pattern_mask].tolist())
    base_pool_indices = (
        set(common_pool.index.tolist())
        | set(uncommon_pool.index.tolist())
        | set(rare_pool.index.tolist())
    )
    pattern_overlap_with_base_pools = len(base_pool_indices & pattern_indices)

    logger.info("[POOL_COMPOSITION] total_rows_in_source=%d", len(df))
    logger.info(
        "[POOL_COMPOSITION] common_pool_size=%d pattern_rows_in_common=%d",
        len(common_pool),
        common_pattern_count,
    )
    logger.info(
        "[POOL_COMPOSITION] uncommon_pool_size=%d pattern_rows_in_uncommon=%d",
        len(uncommon_pool),
        uncommon_pattern_count,
    )
    logger.info(
        "[POOL_COMPOSITION] rare_pool_size=%d pattern_rows_in_rare=%d",
        len(rare_pool),
        rare_pattern_count,
    )
    logger.info(
        "[POOL_COMPOSITION] base_pool_counts common=%d uncommon=%d rare=%d",
        len(common_pool),
        len(uncommon_pool),
        len(rare_pool),
    )
    logger.info("[POOL_COMPOSITION] hit_pool_size=%d (includes patterns)", len(hit_pool))
    logger.info("[POOL_COMPOSITION] reverse_pool_size=%d", len(reverse_df))
    logger.info("[POOL_COMPOSITION] pokeball_pattern_count=%d", int(pokeball_pattern_mask.sum()))
    logger.info("[POOL_COMPOSITION] master_ball_pattern_count=%d", int(master_ball_pattern_mask.sum()))
    logger.info(
        "[POOL_COMPOSITION] pattern_overlap_with_base_pools=%d (must be 0 — patterns must not leak into base pools)",
        pattern_overlap_with_base_pools,
    )

    # --- SIM_POOL_AUDIT debug output ---
    rare_prices = pd.to_numeric(rare_pool.get('Price ($)'), errors='coerce').dropna()
    print(
        f"[SIM_POOL_AUDIT]\n"
        f"  base_common_count={len(common_pool)}\n"
        f"  base_uncommon_count={len(uncommon_pool)}\n"
        f"  base_rare_count={len(rare_pool)}\n"
        f"  pokeball_count={int(pokeball_pattern_mask.sum())}\n"
        f"  masterball_count={int(master_ball_pattern_mask.sum())}\n"
        f"  rare_pool_price_mean={rare_prices.mean():.4f}\n"
        f"  rare_pool_price_max={rare_prices.max():.4f}"
    )

    return {
        "common": common_pool,
        "uncommon": uncommon_pool,
        "rare": rare_pool,
        "reverse": reverse_df,
        "hit": hit_pool,
    }
