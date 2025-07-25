import numpy as np
import pandas as pd
from typing import Callable, List, Dict

def simulate_pack_distribution(open_pack_fn: Callable[[], float], n: int = 100000) -> List[float]:
    """Simulates opening n packs using the provided simulation function."""
    return [open_pack_fn() for _ in range(n)]

def run_simulation(open_pack_fn: Callable[[], float], n: int = 100000) -> Dict[str, object]:
    """Runs a Monte Carlo simulation and returns statistical summaries."""
    results = simulate_pack_distribution(open_pack_fn, n)
    results_array = np.array(results)

    return {
        "mean": results_array.mean(),
        "std_dev": results_array.std(),
        "min": results_array.min(),
        "max": results_array.max(),
        "percentiles": {
            "5th": np.percentile(results_array, 5),
            "25th": np.percentile(results_array, 25),
            "50th (median)": np.percentile(results_array, 50),
            "75th": np.percentile(results_array, 75),
            "95th": np.percentile(results_array, 95),
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
):
    def simulate_one_pack():
        total_value = 0.0

        # Sample commons
        total_value += common_cards['Price ($)'].sample(slots_per_rarity['common'], replace=True).sum()

        # Sample uncommons
        total_value += uncommon_cards['Price ($)'].sample(slots_per_rarity['uncommon'], replace=True).sum()

        # Sample rare slot
        rare_rarities = list(rare_slot_config.keys())
        rare_probs = list(rare_slot_config.values())
        chosen_rare_rarity = np.random.choice(rare_rarities, p=rare_probs)
        
        if chosen_rare_rarity == 'rare':
            sampled_card = rare_cards['Price ($)'].sample(1).iloc[0]
        else:
            eligible_hits = hit_cards[hit_cards['Rarity'].str.lower().str.strip() == chosen_rare_rarity]
            sampled_card = eligible_hits['Price ($)'].sample(1).iloc[0] if not eligible_hits.empty else 0.0
        total_value += sampled_card

        # Sample reverse slot 1
        slot1_rarities = list(reverse_slot_config["slot_1"].keys())
        slot1_probs = list(reverse_slot_config["slot_1"].values())
        chosen_slot1_rarity = np.random.choice(slot1_rarities, p=slot1_probs)
        
        if chosen_slot1_rarity == 'regular reverse':
            sampled_card = reverse_pool['EV_Reverse'].sample(1).iloc[0]
        else:
            eligible_hits = hit_cards[hit_cards['Rarity'].str.lower().str.strip() == chosen_slot1_rarity]
            sampled_card = eligible_hits['Price ($)'].sample(1).iloc[0] if not eligible_hits.empty else 0.0
        total_value += sampled_card

        # Sample reverse slot 2
        slot2_rarities = list(reverse_slot_config["slot_2"].keys())
        slot2_probs = list(reverse_slot_config["slot_2"].values())
        chosen_slot2_rarity = np.random.choice(slot2_rarities, p=slot2_probs)

        if chosen_slot2_rarity == 'regular reverse':
            sampled_card = reverse_pool['EV_Reverse'].sample(1).iloc[0]
        else:
            eligible_hits = hit_cards[hit_cards['Rarity'].str.lower().str.strip() == chosen_slot2_rarity]
            sampled_card = eligible_hits['Price ($)'].sample(1).iloc[0] if not eligible_hits.empty else 0.0
        total_value += sampled_card

        return total_value

    return simulate_one_pack


def print_simulation_summary(sim_results, n_simulations=100000):
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