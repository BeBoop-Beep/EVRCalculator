import sys
import difflib
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(base_dir)

# Ensure package imports work whether this file is run as a module or script path.
if repo_root not in sys.path:
    sys.path.append(repo_root)
if base_dir not in sys.path:
    sys.path.append(base_dir)
legacy_calc_dir = os.path.join(base_dir, 'Expected Value and Cost Ratio Calculator Pokemon')
if legacy_calc_dir not in sys.path:
    sys.path.append(legacy_calc_dir)

from backend.calculations.packCalcsRefractored import calculate_pack_stats
from backend.simulations import calculate_pack_simulations
from backend.calculations.evrEtb import calculate_etb_metrics
from backend.calculations.evr import compute_all_derived_metrics, print_derived_metrics_summary
from constants.tcg.pokemon.scarletAndVioletEra.setMap import SET_CONFIG_MAP, SET_ALIAS_MAP


def resolve_excel_path(repo_root, folder_name):
    base_excel_dir = os.path.join(repo_root, 'data', 'excelDocs')
    existing_dirs = {
        d.lower(): d
        for d in os.listdir(base_excel_dir)
        if os.path.isdir(os.path.join(base_excel_dir, d))
    }

    candidates = [folder_name]
    if folder_name.endswith('s'):
        candidates.append(folder_name[:-1])
    else:
        candidates.append(f"{folder_name}s")

    if 'Evolutions' in folder_name:
        candidates.append(folder_name.replace('Evolutions', 'Evolution'))
    if 'Evolution' in folder_name:
        candidates.append(folder_name.replace('Evolution', 'Evolutions'))

    # De-duplicate while preserving order.
    seen = set()
    ordered_candidates = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            ordered_candidates.append(candidate)
            seen.add(candidate)

    for candidate in ordered_candidates:
        exact_path = os.path.join(base_excel_dir, candidate, 'pokemon_data.xlsx')
        if os.path.exists(exact_path):
            return exact_path

        resolved_folder = existing_dirs.get(candidate.lower())
        if resolved_folder:
            resolved_path = os.path.join(base_excel_dir, resolved_folder, 'pokemon_data.xlsx')
            if os.path.exists(resolved_path):
                return resolved_path

    raise FileNotFoundError(
        f"Could not find pokemon_data.xlsx for '{folder_name}'. Tried: {ordered_candidates}"
    )


def main():
    # Rating to pull rate mapping (1/X)
    def get_config_for_set(user_input):
        key = user_input.lower().strip()

        # Try alias map first
        if key in SET_ALIAS_MAP:
            mapped_key = SET_ALIAS_MAP[key]
            return SET_CONFIG_MAP[mapped_key], mapped_key

        # Try exact key in config map
        if key in SET_CONFIG_MAP:
            return SET_CONFIG_MAP[key], key

        # Try fuzzy matching against aliases and set names
        possible_inputs = list(SET_ALIAS_MAP.keys()) + list(SET_CONFIG_MAP.keys())
        matches = difflib.get_close_matches(key, possible_inputs, n=1, cutoff=0.6)
        
        if matches:
            matched_key = matches[0]
            # Check if it's an alias and resolve to actual key
            if matched_key in SET_ALIAS_MAP:
                matched_key = SET_ALIAS_MAP[matched_key]
            print("We think you mean :", matched_key)
            return SET_CONFIG_MAP[matched_key], matched_key
        
        # No matches found
        raise ValueError(f"Set '{user_input}' not found. Please check the set name and try again.")
    
    # # Step 1: Scrape and gather HTML Doc  # #
    setName = input("What set are we working on: \n")
    try:
        config, folder_name = get_config_for_set(setName)
        print(config.SET_NAME, ", ", config.CARD_DETAILS_URL)
        repo_root = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(repo_root)
        excel_path = resolve_excel_path(repo_root, folder_name)

        # # Step 2: Calculate EVR Per Pack # #
        print("\n Calculating EVR..")
        file_path = excel_path
        results, summary_data, top_10_hits, pack_price = calculate_pack_stats(file_path, config)

        sim_results, pack_metrics = calculate_pack_simulations(file_path, config)
        total_ev = pack_metrics['total_ev']

        results.update({
            "acutal_simulated_ev": pack_metrics['total_ev'],
            "net_value": pack_metrics['net_value'],
            "opening_pack_roi": pack_metrics['opening_pack_roi'],
            "opening_pack_roi_percent": pack_metrics['opening_pack_roi_percent'],
        })

        # # Step 2b: Derived decision metrics # #
        derived = compute_all_derived_metrics(
            sim_results.get("values", []),
            pack_price,
            card_ev_contributions=results.get("hit_ev_contributions"),
            total_pack_ev=pack_metrics.get('total_ev'),
            hit_ev=results.get("hit_ev"),
            hit_cards_count=len(results.get("hit_ev_contributions", {})) if results.get("hit_ev_contributions") else None,
        )
        print_derived_metrics_summary(derived)
       

        # # Step 3: Calculate ETB EV # #
        print("\n Calculating ETB EV..")
        etb_metrics = calculate_etb_metrics(file_path, 9, total_ev)

        # # Step 3: Calculate Booster Box EV  # #
        print("\n Calculating Booster Box EV..")
        # etb_metrics = calculate_etb_metrics(file_path, 9, total_ev)

        # append_summary_to_existing_excel(file_path, summary_data, results, sim_results, top_10_hits)
    except (ValueError, FileNotFoundError) as e:
        print(e)

    print("\nOperation completed successfully!")
if __name__ == "__main__":
    main()