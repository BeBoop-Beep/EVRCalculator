import numpy as np
import pandas as pd

from typing import Callable, List, Dict
from src.utils.monteCarloSimUtils.specialPackLogic import sample_god_pack, sample_demi_god_pack

def simulate_pack_distribution(open_pack_fn: Callable[[], float], n: int = 100000) -> List[float]:
    """Simulates opening n packs using the provided simulation function."""
    return [open_pack_fn() for _ in range(n)]

def run_simulation(
    open_pack_fn: Callable[[], float],
    rarity_pull_counts: Dict[str, int],
    rarity_value_totals: Dict[str, float],
    n: int = 100000
) -> Dict[str, object]:

    """Runs a Monte Carlo simulation and returns statistical summaries."""
    results = simulate_pack_distribution(open_pack_fn, n)
    results_array = np.array(results)

    values = []
    for _ in range(n):
        values.append(open_pack_fn())


    return {
        "values": values,
        "rarity_pull_counts": rarity_pull_counts,
        "rarity_value_totals": rarity_value_totals,
        "mean": results_array.mean(),
        "std_dev": results_array.std(),
        "min": results_array.min(),
        "max": results_array.max(),
        "percentiles": {
            "5th": np.percentile(results_array, 5),
            "25th": np.percentile(results_array, 25),
            "50th (median)": np.percentile(results_array, 50),
            "75th": np.percentile(results_array, 75),
            "90th": np.percentile(results_array, 90),
            "95th": np.percentile(results_array, 95),
            "99th": np.percentile(results_array, 99),
        },
        "distribution": results_array
    }

def make_simulate_pack_fn(
    common_cards,
    uncommon_cards,
    rare_cards,
    hit_cards,
    reverse_pool,  # renamed from reverse_cards
    rare_slot_config,
    reverse_slot_config,
    slots_per_rarity,
    config, 
    df,
    rarity_pull_counts,
    rarity_value_totals,
    log_choices=None,
):
    # sir_cards = hit_cards[hit_cards['Rarity'].str.strip().str.lower() == 'special illustration rare']
    # print(sir_cards['Card Name'].value_counts())
    # print(reverse_slot_config['slot_2'])
    def simulate_one_pack(return_slots=False):
        # Global trackers
        total_value = 0.0
        chosen_slots = {}
       
        # Step 1: God Pack Roll
        god_cfg = getattr(config, "GOD_PACK_CONFIG", {})
        if god_cfg.get("enabled", False):
            pull_rate = god_cfg.get("pull_rate", 0)
            if np.random.rand() < pull_rate:
                return sample_god_pack(god_cfg, df)

        # Step 2: Demi-God Pack Roll
        demi_cfg = getattr(config, "DEMI_GOD_PACK_CONFIG", {})
        if demi_cfg.get("enabled", False):
            pull_rate = demi_cfg.get("pull_rate", 0)
            if np.random.rand() < pull_rate:
                return sample_demi_god_pack(demi_cfg, df, common_cards, uncommon_cards)

        # Step 3: Normal Sampling Logic 
        # Sample commons
        total_value += common_cards['Price ($)'].sample(slots_per_rarity['common'], replace=True).sum()

        # Sample uncommons
        total_value += uncommon_cards['Price ($)'].sample(slots_per_rarity['uncommon'], replace=True).sum()

        # Sample rare slot
        rare_rarities = list(rare_slot_config.keys())
        rare_probs = list(rare_slot_config.values())
        chosen_rare_rarity = np.random.choice(rare_rarities, p=rare_probs)
        chosen_slots["rare"] = chosen_rare_rarity
        
        if chosen_rare_rarity == 'rare':
            sampled_card = rare_cards['Price ($)'].sample(1).iloc[0]
        else:
            eligible_hits = hit_cards[hit_cards['Rarity'].str.lower().str.strip() == chosen_rare_rarity]
            sampled_card = eligible_hits['Price ($)'].sample(1).iloc[0] if not eligible_hits.empty else 0.0
        total_value += sampled_card
        rarity_pull_counts[chosen_rare_rarity] += 1
        rarity_value_totals[chosen_rare_rarity] += sampled_card

        # Sample reverse slot 1
        slot1_rarities = list(reverse_slot_config["slot_1"].keys())
        slot1_probs = list(reverse_slot_config["slot_1"].values())
        chosen_slot1_rarity = np.random.choice(slot1_rarities, p=slot1_probs)
        chosen_slots["reverse_1"] = chosen_slot1_rarity
        
        if chosen_slot1_rarity == 'regular reverse':
            # Only sample if reverse_pool is not empty
            if not reverse_pool.empty:
                sampled_card = reverse_pool['EV_Reverse'].sample(1).iloc[0]
            else:
                sampled_card = 0.0
        else:
            eligible_hits = hit_cards[hit_cards['Rarity'].str.lower().str.strip() == chosen_slot1_rarity]
            sampled_card = eligible_hits['Price ($)'].sample(1).iloc[0] if not eligible_hits.empty else 0.0
        total_value += sampled_card
        rarity_pull_counts[chosen_slot1_rarity] += 1
        rarity_value_totals[chosen_slot1_rarity] += sampled_card


        # Sample reverse slot 2
        slot2_rarities = list(reverse_slot_config["slot_2"].keys())
        slot2_probs = list(reverse_slot_config["slot_2"].values())
        chosen_slot2_rarity = np.random.choice(slot2_rarities, p=slot2_probs)
        chosen_slots["reverse_2"] = chosen_slot2_rarity

        if chosen_slot2_rarity == 'regular reverse':
            # Only sample if reverse_pool is not empty
            if not reverse_pool.empty:
                sampled_card = reverse_pool['EV_Reverse'].sample(1).iloc[0]
            else:
                sampled_card = 0.0
        else:
            eligible_hits = hit_cards[hit_cards['Rarity'].str.lower().str.strip() == chosen_slot2_rarity]
            sampled_card = eligible_hits['Price ($)'].sample(1).iloc[0] if not eligible_hits.empty else 0.0
        total_value += sampled_card
        rarity_pull_counts[chosen_slot2_rarity] += 1
        rarity_value_totals[chosen_slot2_rarity] += sampled_card

        if log_choices is not None:
            log_choices.append(chosen_slots.copy())
        if return_slots:
            return total_value, chosen_slots
        return total_value
    
        

    return simulate_one_pack


def print_simulation_summary(sim_results, n_simulations=100000):
    values = sim_results["values"]
    pull_counts = sim_results["rarity_pull_counts"]
    value_totals = sim_results["rarity_value_totals"]

    print(f"Monte Carlo Simulation Results ({n_simulations} simulations):")
    print("-" * 50)
    print(f"Mean Value:          ${sim_results['mean']:.2f}")
    print(f"Standard Deviation:  ${sim_results['std_dev']:.2f}")
    print(f"Minimum Value:       ${sim_results['min']:.2f}")
    print(f"Maximum Value:       ${sim_results['max']:.2f}")
    print()

    print("Percentiles:")
    for perc_label, perc_val in sim_results['percentiles'].items():
        print(f"  {perc_label}:       ${perc_val:.2f}")

    print("-" * 50)

    print()

    print("\n=== Pull Summary by Rarity (All Slots) ===")
    for rarity, count in pull_counts.items():
        total_val = value_totals[rarity]
        avg_val = total_val / count if count else 0
        print(f"{rarity:30s} | pulled: {count:7d} | avg value: ${avg_val:.2f} | total EV: ${total_val:.2f}")

    print()