import logging

import pandas as pd

from backend.calculations.utils.reverse_pool import build_reverse_eligible_pool
from backend.simulations.utils.simulationTokenResolver import get_row_match_keys
from backend.utils.debug_output import debug_print


logger = logging.getLogger(__name__)


def _emit_sim_pool_debug(pool_name: str, pool_df: pd.DataFrame, price_col: str, sample_size: int = 10) -> None:
    row_count = int(len(pool_df))
    if row_count == 0:
        debug_print(
            f"[SIM_POOL_DEBUG] pool={pool_name} rows=0 price_col='{price_col}' min=0.0000 max=0.0000 mean=0.0000"
        )
        return

    prices = pd.to_numeric(pool_df.get(price_col), errors='coerce').dropna()
    min_price = float(prices.min()) if not prices.empty else 0.0
    max_price = float(prices.max()) if not prices.empty else 0.0
    mean_price = float(prices.mean()) if not prices.empty else 0.0

    debug_print(
        f"[SIM_POOL_DEBUG] pool={pool_name} rows={row_count} price_col='{price_col}' "
        f"min={min_price:.4f} max={max_price:.4f} mean={mean_price:.4f}"
    )

    for idx, (_, row) in enumerate(pool_df.head(sample_size).iterrows(), start=1):
        card_name = str(row.get('Card Name', '<missing>') or '<missing>')
        rarity = str(row.get('Rarity', row.get('rarity_key', '<missing>')) or '<missing>')
        price = pd.to_numeric(pd.Series([row.get(price_col)]), errors='coerce').fillna(0.0).iloc[0]
        card_number = row.get('Card Number', row.get('card_number', ''))
        variant_marker = row.get('Special Type', row.get('special_type_key', row.get('pattern_key', '')))
        variant_id = row.get('card_variant_id', '')
        debug_print(
            f"[SIM_POOL_DEBUG] sample[{idx}] pool={pool_name} name={card_name} rarity={rarity} "
            f"price={float(price):.4f} card_number={card_number or '<none>'} "
            f"variant_marker={variant_marker or '<none>'} "
            f"card_variant_id={variant_id if variant_id not in (None, '') else '<none>'}"
        )


def _log_value_counts(label: str, values: pd.Series, max_rows: int = 20) -> None:
    series = values.fillna("<NA>").astype(str)
    counts = series.value_counts(dropna=False)
    debug_print(f"[POOL_INPUT_PROFILE] {label} unique={int(len(counts))} total={int(len(series))}")
    for value, count in counts.head(max_rows).items():
        debug_print(f"[POOL_INPUT_PROFILE] {label} value={value} count={int(count)}")
    if len(counts) > max_rows:
        debug_print(
            f"[POOL_INPUT_PROFILE] {label} truncated_unique_values={int(len(counts) - max_rows)}"
        )


def is_variant_row(name: str) -> bool:
    """Return True if a card name represents a cosmetic/reverse variant (contains parentheses).

    Examples that return True:
        "Pikachu (Friend Ball)", "Bulbasaur (Energy Symbol Pattern)", "Eevee (Love Ball)"
    Examples that return False:
        "Pikachu", "Charizard ex", "Professor's Research"
    """
    return "(" in name and ")" in name


def _build_name_variant_mask(df: pd.DataFrame) -> pd.Series:
    """Return boolean mask for rows where Card Name is a parenthetical variant.

    Variant rows (e.g. '(Friend Ball)', '(Love Ball)', '(Energy Symbol Pattern)')
    belong exclusively to the reverse/pattern pool and must never enter base pools.
    """
    if 'Card Name' not in df.columns:
        return pd.Series(False, index=df.index)
    return df['Card Name'].fillna('').astype(str).apply(is_variant_row)


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
    name_variant_mask = _build_name_variant_mask(df)
    # Rows with a non-empty pattern_key belong exclusively to the pattern/hit pool.
    # They MUST be excluded from base rarity (common/uncommon/rare) pools to
    # prevent EV inflation from masterball/pokeball rows leaking into base slots.
    # Additionally, rows whose Card Name contains parentheses (e.g. "(Friend Ball)",
    # "(Energy Symbol Pattern)") are cosmetic/reverse variants and must also be
    # excluded from base pools — they route to the reverse pool instead.
    return base_rarity_keys.eq(rarity_key) & ~pattern_overlay_mask & ~name_variant_mask

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
    debug_print(f"[POOL_INPUT_PROFILE] base_rarity_key_source={base_rarity_key_source}")
    _log_value_counts("base_rarity_key", base_rarity_keys)
    debug_print(
        f"[POOL_INPUT_PROFILE] base_rarity_key_counts common={int(base_rarity_keys.eq('common').sum())} "
        f"uncommon={int(base_rarity_keys.eq('uncommon').sum())} "
        f"rare={int(base_rarity_keys.eq('rare').sum())}"
    )

    common_pool = source_df[_build_base_pool_mask(source_df, 'common')]
    uncommon_pool = source_df[_build_base_pool_mask(source_df, 'uncommon')]
    rare_pool = source_df[_build_base_pool_mask(source_df, 'rare')]
    hit_pool = source_df[hit_pool_mask]

    # Compute variant counts for diagnostics (before pool-integrity checks below).
    source_name_variant_mask = _build_name_variant_mask(source_df)
    total_name_variant_count = int(source_name_variant_mask.sum())

    pattern_keys_source, _ = get_row_match_keys(df, mode='pattern')
    pokeball_pattern_mask = pattern_keys_source.eq('pokeball_pattern')
    master_ball_pattern_mask = pattern_keys_source.eq('master_ball_pattern')
    all_pattern_mask = pokeball_pattern_mask | master_ball_pattern_mask

    # --- HARD ASSERTIONS: pattern rows and name-variant rows must not exist in base pools ---
    common_pattern_mask = _build_pattern_overlay_mask(common_pool)
    uncommon_pattern_mask = _build_pattern_overlay_mask(uncommon_pool)
    rare_pattern_mask = _build_pattern_overlay_mask(rare_pool)

    common_pattern_count = int(common_pattern_mask.sum()) if not common_pool.empty else 0
    uncommon_pattern_count = int(uncommon_pattern_mask.sum()) if not uncommon_pool.empty else 0
    rare_pattern_count = int(rare_pattern_mask.sum()) if not rare_pool.empty else 0

    # Check for name-variant leakage into base pools.
    common_name_variant_mask = _build_name_variant_mask(common_pool)
    uncommon_name_variant_mask = _build_name_variant_mask(uncommon_pool)
    rare_name_variant_mask = _build_name_variant_mask(rare_pool)
    common_name_variant_count = int(common_name_variant_mask.sum()) if not common_pool.empty else 0
    uncommon_name_variant_count = int(uncommon_name_variant_mask.sum()) if not uncommon_pool.empty else 0
    rare_name_variant_count = int(rare_name_variant_mask.sum()) if not rare_pool.empty else 0

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

    if common_name_variant_count > 0:
        leaked = common_pool.loc[common_name_variant_mask, 'Card Name'].tolist() if 'Card Name' in common_pool.columns else []
        raise ValueError(
            f"[POOL_INTEGRITY] {common_name_variant_count} name-variant row(s) leaked into common_pool. "
            f"Sample: {leaked[:5]}"
        )
    if uncommon_name_variant_count > 0:
        leaked = uncommon_pool.loc[uncommon_name_variant_mask, 'Card Name'].tolist() if 'Card Name' in uncommon_pool.columns else []
        raise ValueError(
            f"[POOL_INTEGRITY] {uncommon_name_variant_count} name-variant row(s) leaked into uncommon_pool. "
            f"Sample: {leaked[:5]}"
        )
    if rare_name_variant_count > 0:
        leaked = rare_pool.loc[rare_name_variant_mask, 'Card Name'].tolist() if 'Card Name' in rare_pool.columns else []
        raise ValueError(
            f"[POOL_INTEGRITY] {rare_name_variant_count} name-variant row(s) leaked into rare_pool. "
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
        "[POOL_COMPOSITION] total_name_variant_rows=%d (excluded from all base pools)",
        total_name_variant_count,
    )
    logger.info(
        "[POOL_COMPOSITION] common_pool_size=%d pattern_rows_in_common=%d name_variant_in_common=%d",
        len(common_pool),
        common_pattern_count,
        common_name_variant_count,
    )
    logger.info(
        "[POOL_COMPOSITION] uncommon_pool_size=%d pattern_rows_in_uncommon=%d name_variant_in_uncommon=%d",
        len(uncommon_pool),
        uncommon_pattern_count,
        uncommon_name_variant_count,
    )
    logger.info(
        "[POOL_COMPOSITION] rare_pool_size=%d pattern_rows_in_rare=%d name_variant_in_rare=%d",
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

    debug_print(
        "[SIM_POOL_DEBUG] "
        f"base_common_count={len(common_pool)} "
        f"base_uncommon_count={len(uncommon_pool)} "
        f"base_rare_count={len(rare_pool)} "
        f"reverse_pool_size={len(reverse_df)}"
    )
    _emit_sim_pool_debug('base_common', common_pool, 'Price ($)')
    _emit_sim_pool_debug('base_uncommon', uncommon_pool, 'Price ($)')
    _emit_sim_pool_debug('base_rare', rare_pool, 'Price ($)')
    _emit_sim_pool_debug('reverse', reverse_df, 'Reverse Variant Price ($)')

    # --- SIM_POOL_AUDIT debug output ---
    rare_prices = pd.to_numeric(rare_pool.get('Price ($)'), errors='coerce').dropna()
    debug_print(
        f"[SIM_POOL_AUDIT]\n"
        f"  source_total_rows={len(source_df)}\n"
        f"  name_variant_rows_excluded={total_name_variant_count}\n"
        f"  base_common_count={len(common_pool)}\n"
        f"  base_uncommon_count={len(uncommon_pool)}\n"
        f"  base_rare_count={len(rare_pool)}\n"
        f"  base_total={len(common_pool)+len(uncommon_pool)+len(rare_pool)}\n"
        f"  pokeball_count={int(pokeball_pattern_mask.sum())}\n"
        f"  masterball_count={int(master_ball_pattern_mask.sum())}\n"
        f"  reverse_pool_size={len(reverse_df)}\n"
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
