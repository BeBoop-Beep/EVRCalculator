import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
import os

def calculate_pack_ev(file_path, config):
    pack_multipliers = config.get_rarity_pack_multiplier()
    common_multiplier = pack_multipliers.get('common', 1)
    uncommon_multiplier = pack_multipliers.get('uncommon', 1)
    rare_multiplier = config.RARE_SLOT_PROBABILITY['rare']

    slot1_rr = config.REVERSE_SLOT_PROBABILITIES["slot_1"]["regular_reverse"]
    slot2_rr = config.REVERSE_SLOT_PROBABILITIES["slot_2"]["regular_reverse"]
    reverse_multiplier = slot1_rr + slot2_rr

    print("multipliers: ", common_multiplier, uncommon_multiplier, rare_multiplier, reverse_multiplier)

    # ----- Load and Prepare Data -----
    try:
        df = pd.read_excel(file_path)
        print(file_path)
    except FileNotFoundError:
        df = pd.read_csv(file_path)

    # Ensure required columns exist
    required_cols = ['Rarity', 'Price ($)', 'Pull Rate (1/X)', 'Pack Price']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Input data must contain a '{col}' column.")

    # Clean Pull Rate column first (remove $ and commas)
    df['Pull Rate (1/X)'] = (
        df['Pull Rate (1/X)']
        .astype(str)
        .str.replace('[$,]', '', regex=True)
        .replace('', pd.NA)
    )

    # Process other columns
    df['rarity_raw'] = df['Rarity'].astype(str).str.lower().str.strip()
    df['rarity_group'] = df['rarity_raw'].map(config.RARITY_MAPPING).fillna('other')
    PACK_PRICE = pd.to_numeric(df["Pack Price"].iloc[0], errors='coerce')

    # Convert to numeric after cleaning
    df['Price ($)'] = pd.to_numeric(df['Price ($)'], errors='coerce')
    df['Pull Rate (1/X)'] = pd.to_numeric(df['Pull Rate (1/X)'], errors='coerce')
    df = df.dropna(subset=['Price ($)', 'Pull Rate (1/X)'])

    if (df['Pull Rate (1/X)'] == 0).any():
        df = df[df['Pull Rate (1/X)'] != 0]
        print("Warning: Removed cards with zero pull rate.")

    # ----- EV Calculations -----
    # Per Card EV Contribution
    df['EV'] = df['Price ($)'] / df['Pull Rate (1/X)']

    # ----- EV for Reverse Holos -----
    if 'Reverse Variant Price ($)' in df.columns:
        df['Reverse Variant Price ($)'] = pd.to_numeric(df['Reverse Variant Price ($)'], errors='coerce')

        # Exclude IR and SIR since they are treated separately
        is_standard_reverse = ~df['Rarity'].isin(['Illustration Rare', 'Special Illustration Rare'])

        # Calculate EV for standard reverse holos only
        df['EV_Reverse'] = 0
        df.loc[is_standard_reverse, 'EV_Reverse'] = df.loc[is_standard_reverse, 'Reverse Variant Price ($)'].fillna(0) / df.loc[is_standard_reverse, 'Pull Rate (1/X)']

        ev_reverse_total = df.loc[is_standard_reverse, 'EV_Reverse'].sum()
    else:
        ev_reverse_total = 0



    # Identify reverse cards that are also marked as hits
    reverse_hits_overlap = df[
        (df['rarity_group'] == 'hits') &
        (df['Reverse Variant Price ($)'].notna()) &
        (df['Reverse Variant Price ($)'] > 0)
    ]

    if not reverse_hits_overlap.empty:
        print("\n⚠️ Warning: The following 'hit' cards also have Reverse Variant Prices and may be double-counted:")
        print(reverse_hits_overlap[['Card Name', 'Rarity', 'Price ($)', 'Reverse Variant Price ($)', 'Pull Rate (1/X)']])
        print("Consider excluding these from reverse EV if they are pulled only in hit slots.")
    else:
        print("\n✅ No overlapping hit cards found in reverse variants — no double-counting risk.")

    # ----- EV by Rarity Group (already includes pack copies) -----
    master_ball_cards = df[df['Card Name'].str.contains('Master Ball', case=False, na=False)]
    pokeball_cards = df[df['Card Name'].str.contains('Poke Ball', case=False, na=False)]

    pattern_mask = df['Card Name'].str.contains('Master Ball|Poke Ball', case=False, na=False)
    ev_common_total = df[(df['Rarity'] == 'common') & ~pattern_mask]['EV'].sum()
    ev_uncommon_total = df[(df['Rarity'] == 'uncommon') & ~pattern_mask]['EV'].sum()
    ev_rare_total     = df[(df['Rarity'] == 'rare') & ~pattern_mask]['EV'].sum()
    ev_double_rare_total     = df.loc[df['Rarity'] == 'double rare',     'EV'].sum()
    ev_ace_spec_rare_total     = df.loc[df['Rarity'] == 'ace spec rare',     'EV'].sum()
    ev_hyper_rare_total   = df.loc[df['Rarity'] == 'hyper rare',   'EV'].sum()
    ev_ultra_rare_total = df.loc[df['Rarity'] == 'ultra rare', 'EV'].sum()
    ev_SIR_total     = df.loc[df['Rarity'] == 'special illustration rare',     'EV'].sum()
    ev_IR_total     = df.loc[df['Rarity'] == 'illustration rare',     'EV'].sum()
    ev_hits_total     = df.loc[df['rarity_group'] == 'hits',     'EV'].sum()
    ev_other_total    = df.loc[df['rarity_group'] == 'other',    'EV'].sum()
    ev_master_ball_total = master_ball_cards['EV'].sum()
    ev_pokeball_total = pokeball_cards['EV'].sum()


    print("ev_common_total: ",ev_common_total*common_multiplier)
    print("ev_uncommon_total: ",ev_uncommon_total*uncommon_multiplier)
    print("ev_rare_total: ",ev_rare_total*rare_multiplier)
    print("ev_reverse_total: ", ev_reverse_total*reverse_multiplier)
    print("ev_ace_spec_rare_total : ",ev_ace_spec_rare_total )
    print("ev_pokeball_total: ", ev_pokeball_total)
    print("ev_master_ball_total: ", ev_master_ball_total)
    print("ev_IR_total: ",ev_IR_total)
    print("ev_SIR_total: ",ev_SIR_total)
    print("ev_double_rare_total: ",ev_double_rare_total)
    print("ev_hyper_rare_total: ",ev_hyper_rare_total)
    print("ev_ultra_rare_total: ",ev_ultra_rare_total)
    print("rare_multiplier: ", rare_multiplier)
    print("reverse_multiplier: ", reverse_multiplier)
    print("ev_other_total: " , ev_other_total)
    ev_total_for_hits = ev_hyper_rare_total + ev_ultra_rare_total + ev_SIR_total + ev_IR_total
    print("Comparing: ev_total_for_hits: ", ev_total_for_hits, "  &  ev_hits_total: ", ev_hits_total)

    # ----- Totals -----
    total_ev = (
        ev_common_total*common_multiplier + 
        ev_uncommon_total*uncommon_multiplier + 
        ev_rare_total*rare_multiplier + 
        ev_double_rare_total + 
        ev_ace_spec_rare_total +
        ev_pokeball_total +
        ev_master_ball_total +
        ev_hyper_rare_total +
        ev_ultra_rare_total +
        ev_SIR_total +
        ev_IR_total +
        ev_other_total + 
        ev_reverse_total*reverse_multiplier
    )
    print("total_ev: ", total_ev)
    net_value = total_ev - PACK_PRICE
    roi = total_ev / PACK_PRICE
    roi_percent = (roi -1) * 100
    print("net_value", net_value)
    print("roi", roi)
    print("roi_percent", roi_percent)


    # ----- Probability of Pulling ≥1 "hit" Card -----
    hit_df = df[df['rarity_group'] == 'hits']
    hit_probs = 1 / hit_df['Pull Rate (1/X)']
    prob_no_hits = (1 - hit_probs).prod()
    no_hit_probability_percentage = prob_no_hits * 100
    hit_probability_percentage = (1 - prob_no_hits) * 100

    print("no_hit_probability_percentage", no_hit_probability_percentage)
    print("hit_probability_percentage", hit_probability_percentage)

    results = {
        "total_ev": total_ev,
        "net_value": net_value,
        "roi": roi,
        "hit_probability_percentage": hit_probability_percentage
    }

    summary_data = {
        "ev_common_total": ev_common_total*common_multiplier,
        "ev_uncommon_total": ev_uncommon_total*uncommon_multiplier,
        "ev_rare_total": ev_rare_total*rare_multiplier,
        "ev_reverse_total": ev_reverse_total*reverse_multiplier,
        "ev_ace_spec_total": ev_ace_spec_rare_total,
        "ev_pokeball_total": ev_pokeball_total,
        "ev_master_ball_total": ev_master_ball_total,
        "ev_IR_total": ev_IR_total,
        "ev_SIR_total": ev_SIR_total,
        "ev_double_rare_total": ev_double_rare_total,
        "ev_hyper_rare_total": ev_hyper_rare_total,
        "ev_ultra_rare_total": ev_ultra_rare_total,
        "reverse_multiplier": reverse_multiplier,
        "rare_multiplier": rare_multiplier,
        "ev_hits_total": ev_hits_total,
        "total_ev": total_ev,
        "net_value": net_value,
        "roi": roi,
        "roi_percent": roi_percent,
        "no_hit_probability_percentage": no_hit_probability_percentage,
        "hit_probability_percentage": hit_probability_percentage,
    }
    
    return results, summary_data

