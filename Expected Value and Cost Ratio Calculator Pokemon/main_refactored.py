"""
Main entry point for EVR Calculator - Database-driven version
Uses database as primary source with constants configuration
Maintains exact compatibility with Excel-based calculations
"""

import sys
import os
import difflib

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data.excel_format_database_loader import ExcelFormatDatabaseLoader
from src.calculators.packCalculations.otherCalculations import PackCalculations
from src.calculators.packCalculations.evrCalculator import PackEVCalculator
from constants.tcg.pokemon.scarletAndVioletEra.setMap import SET_CONFIG_MAP, SET_ALIAS_MAP


def get_config_for_set(user_input):
    """Resolve set input to configuration"""
    key = user_input.lower().strip()

    # Try alias map first
    if key in SET_ALIAS_MAP:
        mapped_key = SET_ALIAS_MAP[key]
        return SET_CONFIG_MAP[mapped_key]

    # Try exact key in config map
    if key in SET_CONFIG_MAP:
        return SET_CONFIG_MAP[key]

    # Try fuzzy matching against aliases and set names
    possible_inputs = list(SET_ALIAS_MAP.keys()) + list(SET_CONFIG_MAP.keys())
    matches = difflib.get_close_matches(key, possible_inputs, n=1, cutoff=0.6)
    if matches:
        print(f"We think you mean: {matches[0]}")
        return SET_CONFIG_MAP.get(SET_ALIAS_MAP.get(matches[0], matches[0]))
    
    raise ValueError(f"Set '{user_input}' not found")


def main():
    print("\n" + "="*80)
    print("EVR CALCULATOR - Refactored (Database-driven, Independent Processes)")
    print("="*80 + "\n")
    
    # Get set from user (default to 151 for testing)
    set_name = input("What set are we working on? (default: Scarlet and Violet 151) ").strip()
    if not set_name:
        set_name = "Scarlet and Violet 151"
    
    try:
        config = get_config_for_set(set_name)
        print(f"\nUsing set: {config.SET_NAME}")
        
        # =================================================================
        # STEP 1: Load card data from database (Excel-compatible format)
        # =================================================================
        print("\n[1/3] Loading card data from database...")
        loader = ExcelFormatDatabaseLoader(config)
        df, pack_price = loader.load_and_prepare_set_data(config.SET_NAME, config=config)
        
        # =================================================================
        # STEP 2: Run PACK EV CALCULATIONS (matches develop exactly)
        # =================================================================
        print("\n[2/3] Running pack EV calculations...")
        calculator = PackCalculations(config)
        
        # Prepare DataFrame with EV calculations
        calculator._calculate_ev_columns(df)
        
        # Calculate reverse EV
        ev_reverse_total = calculator.calculate_reverse_ev(df)
        
        # Calculate EV totals by rarity
        ev_totals = calculator.calculate_rarity_ev_totals(df, ev_reverse_total)
        
        # Calculate total EV with special pack adjustments
        total_ev, regular_pack_contribution, god_pack_ev, demi_god_pack_ev = \
            calculator.calculate_total_ev(ev_totals, df)
        
        print(f"Total EV: ${total_ev:.2f}")
        
        # =================================================================
        # STEP 3: Run MONTE CARLO SIMULATION
        # =================================================================
        print("[3/3] Running Monte Carlo simulation...")
        from src.calculators.packCalculations.monteCarloSim import make_simulate_pack_fn, run_simulation, print_simulation_summary
        from src.utils.card_grouping import group_cards_by_rarity
        from collections import defaultdict
        
        # Group cards by rarity
        card_groups = group_cards_by_rarity(config, df)
        
        # Initialize tracking
        rarity_pull_counts = defaultdict(int)
        rarity_value_totals = defaultdict(float)
        
        # Create simulation function
        simulate_one_pack = make_simulate_pack_fn(
            common_cards=card_groups["common"],
            uncommon_cards=card_groups["uncommon"],
            rare_cards=card_groups["rare"],
            hit_cards=card_groups["hit"],
            reverse_pool=card_groups["reverse"],
            rare_slot_config=config.RARE_SLOT_PROBABILITY,
            reverse_slot_config=config.REVERSE_SLOT_PROBABILITIES,
            slots_per_rarity=config.SLOTS_PER_RARITY,
            config=config,
            df=df,
            rarity_pull_counts=rarity_pull_counts,
            rarity_value_totals=rarity_value_totals,
        )
        
        # Run simulation
        sim_results = run_simulation(simulate_one_pack, rarity_pull_counts, rarity_value_totals, n=100000)
        
        # Print results
        print_simulation_summary(sim_results)
        
        # Calculate metrics
        simulated_ev = sim_results["mean"]
        net_value = simulated_ev - pack_price
        roi = simulated_ev / pack_price if pack_price > 0 else 0
        
        print(f"\nExpected Value Per Pack: {simulated_ev:.10f}")
        print(f"Cost Per Pack: {pack_price:.2f}")
        print(f"Net Value Upon Opening: {net_value:.10f}")
        print(f"ROI Upon Opening: {roi:.10f}")
        print(f"ROI Percent Upon Opening: {(roi - 1) * 100:.2f}")
        
        print("\n=== CALCULATION COMPLETE ===")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

