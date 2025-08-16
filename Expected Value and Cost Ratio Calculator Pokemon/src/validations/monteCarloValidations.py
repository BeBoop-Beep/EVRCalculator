import numpy as np
from scipy.stats import chisquare

def validate_and_debug_slot(
    rare_slot_config,
    reverse_slot_config,
    config,
    n=500000
):
    print("This test checks if your slot probability configs are correct and behave as expected with random sampling.")
    # Disable god/demi-god packs for clean test
    config.GOD_PACK_CONFIG["enabled"] = False
    config.DEMI_GOD_PACK_CONFIG["enabled"] = False

    # Define all slots to test
    slots_to_test = {
        "rare": rare_slot_config,
        "reverse_1": reverse_slot_config["slot_1"],
        "reverse_2": reverse_slot_config["slot_2"]
    }

    # Loop over each slot
    for slot_name, slot_config in slots_to_test.items():
        rarity_pull_counts = {k: 0 for k in slot_config.keys()}

        # Simulate pulls for this slot only
        for _ in range(n):
            rarities = list(slot_config.keys())
            probs = list(slot_config.values())
            chosen_rarity = np.random.choice(rarities, p=probs)
            rarity_pull_counts[chosen_rarity] += 1

        # Print validation results for this slot
        print(f"\n=== SLOT CONFIG PROBABILITY CHECK: {slot_name} slot ===")
        observed_counts = []
        expected_counts = []
        total_pulls = sum(rarity_pull_counts.values())

        for rarity, expected_prob in slot_config.items():
            observed_prob = rarity_pull_counts[rarity] / total_pulls
            observed_counts.append(rarity_pull_counts[rarity])
            expected_counts.append(expected_prob * total_pulls)
            error_pct = abs(observed_prob - expected_prob) / expected_prob * 100 if expected_prob else 0
            status = "✅" if error_pct < 2 else "❌"
            print(f"{rarity:25s} Expected={expected_prob:.5f}, Simulated={observed_prob:.5f}, "
                  f"Error={error_pct:.2f}% {status}")

            if error_pct >= 2:
                print(f"  ⚠ Over/under sampling {rarity}. Pull count: {rarity_pull_counts[rarity]}")

        # Run chi-square test
        chi2_stat, p_value = chisquare(observed_counts, expected_counts)
        print(f"Chi-square test p-value: {p_value:.6f}")
        if p_value < 0.05:
            print("  ❌ Statistically significant difference (reject null hypothesis)")
        else:
            print("  ✅ No statistically significant difference")
    print("\nIf these results match your expected probabilities, your configs are correct.")

def validate_full_pack_logic(
    slot_logs,
    simulate_one_pack,
    rare_slot_config,
    reverse_slot_config,
    n=500000
):
    print("This test checks if your actual simulation logic produces the expected rarity distributions for each slot.")
    counts = {
        "rare": {k: 0 for k in rare_slot_config.keys()},
        "reverse_1": {k: 0 for k in reverse_slot_config["slot_1"].keys()},
        "reverse_2": {k: 0 for k in reverse_slot_config["slot_2"].keys()},
    }

    for chosen_slots in slot_logs:
        counts["rare"][chosen_slots["rare"]] += 1
        counts["reverse_1"][chosen_slots["reverse_1"]] += 1
        counts["reverse_2"][chosen_slots["reverse_2"]] += 1

    # Compare observed vs expected
    for slot, config in [("rare", rare_slot_config),
                         ("reverse_1", reverse_slot_config["slot_1"]),
                         ("reverse_2", reverse_slot_config["slot_2"])]:
        print(f"\n=== FULL SIMULATION VALIDATION: {slot} ===")
        total = sum(counts[slot].values())
        obs = []
        exp = []
        for rarity, expected_prob in config.items():
            observed_prob = counts[slot][rarity] / total
            obs.append(counts[slot][rarity])
            exp.append(expected_prob * total)
            err = abs(observed_prob - expected_prob) / expected_prob * 100 if expected_prob else 0
            print(f"{rarity:25s} Expected={expected_prob:.5f} "
                  f"Simulated={observed_prob:.5f} Error={err:.2f}%")
        chi2, pval = chisquare(obs, exp)
        print(f"Chi-square p-value: {pval:.6f}")
    print("\nIf these results match your expected probabilities, your simulation logic is correct.")