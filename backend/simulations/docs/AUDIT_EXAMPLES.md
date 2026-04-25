"""
SIMULATION SAMPLING AUDIT - PRACTICAL EXAMPLES AND CASE STUDIES
Demonstrates real-world usage of the audit function
"""

# ==============================================================================
# EXAMPLE 1: BASIC AUDIT - VERIFY PRISMATIC POOLS
# ==============================================================================

"""
Use Case: You've just loaded Prismatic set data and want to verify
the pools are correctly separated before running simulations.

Expected Behavior:
- Prismatic has master_ball_pattern cards (rare rarity + pattern)
- These should NOT appear in base rare pool
- They should appear in hit pool
- Audit should pass with no anomalies
"""

EXAMPLE_1_CODE = """
import pandas as pd
import numpy as np
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups
from backend.simulations.utils.simulation_sampling_audit import (
    audit_simulation_sampling_integrity,
    report_audit_results,
)
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig

# Load your Prismatic card data
df = pd.read_csv("prismatic_cards.csv")

# Extract pools
pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

# Run audit on 1000 packs
audit_result = audit_simulation_sampling_integrity(
    SetPrismaticEvolutionsConfig,
    pools,
    num_test_packs=1000,
    rng=np.random.default_rng(42),
)

# Print detailed report
print(report_audit_results(audit_result))

# Expected output:
# ================================================================
# SIMULATION SAMPLING INTEGRITY AUDIT REPORT
# ================================================================
# Status: ✓ PASSED
# Total Packs Sampled: 1000
#
# Pool Composition Analysis:
# --------------------------------------------------------
#   COMMON
#     - Total Rows: 108
#     - Pattern Rows: 0          ✓ Good
#     - Pattern Names: 
#   UNCOMMON
#     - Total Rows: 81
#     - Pattern Rows: 0          ✓ Good
#   RARE
#     - Total Rows: 43
#     - Pattern Rows: 0          ✓ Good
#   HIT
#     - Total Rows: 52
#     - Pattern Rows: 8          ✓ Good - patterns are here!
#     - Pattern Names: Master Ball Pattern 1, Master Ball Pattern 2, ...
#   REVERSE
#     - Total Rows: 21
#     - Pattern Rows: 0          ✓ Good
#
# Anomalies:
# --------------------------------------------------------
#   ✓ No anomalies detected
#
# Pattern Sampling Paths:
# --------------------------------------------------------
#   hit_pool_direct: 3847
#
# Edge Cases:
# --------------------------------------------------------
#   Hit pool contains multiple base rarities: ['ultra_rare', 'illustration_rare', ...]
#   (This is normal and expected)
# ================================================================

# Access results programmatically
if audit_result["is_valid"]:
    print("✓ Pools are correctly configured!")
    print(f"  Common pool: {audit_result['pool_composition']['common']['total_rows']} cards")
    print(f"  Hit pool pattern cards: {audit_result['pool_composition']['hit']['pattern_rows']}")
else:
    print("✗ ERROR: Audit failed!")
    for anomaly in audit_result["anomalies_found"]:
        print(f"  - {anomaly}")
"""


# ==============================================================================
# EXAMPLE 2: DETECT AND DEBUG POOL COMPOSITION ISSUE
# ==============================================================================

"""
Use Case: Something went wrong during data import and pattern rows
leaked into base pools. Use audit to detect and diagnose.

Simulated Issue:
- Due to a bug, some pattern cards have pattern_key = '' (empty)
- These cards end up in base rare pool incorrectly
"""

EXAMPLE_2_CODE = """
import pandas as pd
from backend.simulations.utils.simulation_sampling_audit import (
    audit_simulation_sampling_integrity,
    report_audit_results,
)
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutionsConfig import SetPrismaticEvolutionsConfig

# Problematic data: pattern_key is empty for master ball cards
df = pd.DataFrame({
    "Card Name": [
        "Common 1", "Common 2",
        "Rare 1", "Rare 2",
        "Master Ball Pattern 1",  # BUG: pattern_key is ''
        "Master Ball Pattern 2",  # BUG: pattern_key is ''
    ],
    "Rarity": ["common", "common", "rare", "rare", "rare", "rare"],
    "Special Type": ["", "", "", "", "master ball", "master ball"],
    "pattern_key": ["", "", "", "", "", ""],  # BUG: should be "master_ball_pattern"
    "Price ($)": [0.1, 0.1, 0.9, 1.0, 2.0, 2.0],
})

# Extract pools (which will apply incorrect masks)
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups
pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

# Run audit - it will detect the problem
audit_result = audit_simulation_sampling_integrity(
    SetPrismaticEvolutionsConfig,
    pools,
    num_test_packs=100,
)

# Expected: Audit fails
if not audit_result["is_valid"]:
    print("✗ Audit detected issues!")
    for anomaly in audit_result["anomalies_found"]:
        print(f"  - {anomaly}")
    
    # Debug output
    print("\\nPool Analysis:")
    comp = audit_result["pool_composition"]
    print(f"Rare pool contains {comp['rare']['pattern_rows']} pattern rows (should be 0)")
    if comp['rare']['pattern_row_names']:
        print(f"  Pattern names: {comp['rare']['pattern_row_names']}")
    
    print(f"Hit pool contains {comp['hit']['pattern_rows']} pattern rows (should be > 0)")
    
    # FIX: Update pattern_key extraction
    print("\\nFIX: Ensure pattern_key is populated correctly for all Special Types")
    print("  Check: normalize_special_type_key() and derive_pattern_key()")
else:
    print("✓ No issues detected")

# Expected audit output:
# ✗ Audit detected issues!
#   - CRITICAL: Base pool 'rare' contains 2 pattern rows: 
#     ['Master Ball Pattern 1', 'Master Ball Pattern 2']
#   - CRITICAL: Base pool 'rare' contains pattern rows: [...]
#
# Pool Analysis:
# Rare pool contains 2 pattern rows (should be 0)
#   Pattern names: ['Master Ball Pattern 1', 'Master Ball Pattern 2']
# Hit pool contains 0 pattern rows (should be > 0)
#
# FIX: Ensure pattern_key is populated correctly...
"""


# ==============================================================================
# EXAMPLE 3: DETECT DUPLICATE SAMPLING IN SIMULATION
# ==============================================================================

"""
Use Case: A small hit pool causes statistical issues - the same card
gets sampled multiple times in a pack. Use audit to quantify.

Simulated Issue:
- Very small hit pool (3 cards)
- Multiple reverse slots sampling from hit pool
- Statistical possibility of same card twice
"""

EXAMPLE_3_CODE = """
import pandas as pd
import numpy as np
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups
from backend.simulations.utils.simulation_sampling_audit import audit_simulation_sampling_integrity
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig

# Problem scenario: tiny hit pool
df = pd.DataFrame({
    "Card Name": [
        "Common 1", "Uncommon 1", "Rare 1",
        "Hit 1", "Hit 2", "Hit 3",  # Only 3 hit cards!
    ],
    "Rarity": [
        "common", "uncommon", "rare",
        "ultra rare", "illustration rare", "hyper rare",
    ],
    "Special Type": ["", "", "", "", "", ""],
    "Price ($)": [0.1, 0.2, 0.9, 9.0, 7.5, 26.0],
})

pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

# Run audit with large number of packs to find duplicates
audit_result = audit_simulation_sampling_integrity(
    SetPrismaticEvolutionsConfig,
    pools,
    num_test_packs=5000,  # Run many packs to increase chance of finding duplicates
    rng=np.random.default_rng(42),
)

# Check results
if not audit_result["is_valid"]:
    print("✗ Duplicates detected!")
    anomalies = audit_result["anomalies_found"]
    duplicate_anomalies = [a for a in anomalies if "sampled" in a and "times in single pack" in a]
    
    print(f"Found {len(duplicate_anomalies)} duplicate sampling cases:")
    for anomaly in duplicate_anomalies[:10]:  # Show first 10
        print(f"  - {anomaly}")
    
    print(f"\\nTotal packs sampled: {audit_result['total_packs_sampled']}")
    print(f"Duplicate rate: {len(duplicate_anomalies)} / {audit_result['total_packs_sampled']}")
    
    # RECOMMENDATION
    print("\\nRECOMMENDATION: Increase hit pool size")
    print(f"Current: {pools['hit'].shape[0]} cards")
    print(f"Recommended: > 20 cards to avoid duplicates")
else:
    print("✓ No duplicates detected in 5000 packs")
    print("Pool is large enough")

# Expected output:
# ✗ Duplicates detected!
# Found 247 duplicate sampling cases:
#   - Pack 23: Card 'Hit 1' sampled 2 times in single pack
#   - Pack 45: Card 'Hit 2' sampled 2 times in single pack
#   - Pack 78: Card 'Hit 3' sampled 2 times in single pack
#   ...
#
# Total packs sampled: 5000
# Duplicate rate: 247 / 5000 (4.94%)
#
# RECOMMENDATION: Increase hit pool size
# Current: 3 cards
# Recommended: > 20 cards to avoid duplicates
"""


# ==============================================================================
# EXAMPLE 4: COMPREHENSIVE DATA VALIDATION BEFORE PRODUCTION
# ==============================================================================

"""
Use Case: You're about to deploy new card data for a new set.
Run comprehensive validation to ensure everything works.
"""

EXAMPLE_4_CODE = """
import pandas as pd
import numpy as np
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups
from backend.simulations.utils.simulation_sampling_audit import (
    audit_simulation_sampling_integrity,
    report_audit_results,
    verify_no_pattern_in_base_pools,
    verify_pattern_rows_in_hit_pool,
)
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig

def validate_card_data_for_production(csv_file, set_config, verbose=True):
    \"\"\"Comprehensive validation before production deployment.\"\"\"
    
    print("=" * 70)
    print("PRODUCTION DATA VALIDATION")
    print("=" * 70)
    
    # Step 1: Load and basic checks
    print("\\n[1/5] Loading and validating basic structure...")
    try:
        df = pd.read_csv(csv_file)
        print(f"  ✓ Loaded {len(df)} cards")
        
        required_columns = ["Rarity", "Special Type", "Price ($)"]
        for col in required_columns:
            assert col in df.columns, f"Missing column: {col}"
        print(f"  ✓ All required columns present")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Step 2: Extract pools
    print("\\n[2/5] Extracting pools...")
    try:
        pools = extract_scarletandviolet_card_groups(set_config, df)
        print(f"  ✓ Common: {len(pools['common'])} cards")
        print(f"  ✓ Uncommon: {len(pools['uncommon'])} cards")
        print(f"  ✓ Rare: {len(pools['rare'])} cards")
        print(f"  ✓ Hit: {len(pools['hit'])} cards")
        print(f"  ✓ Reverse: {len(pools['reverse'])} cards")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False
    
    # Step 3: Quick validation
    print("\\n[3/5] Quick validation...")
    if not verify_no_pattern_in_base_pools(pools):
        print(f"  ✗ ERROR: Pattern rows in base pools!")
        return False
    print(f"  ✓ Base pools are pattern-free")
    
    if not verify_pattern_rows_in_hit_pool(pools):
        print(f"  ✗ WARNING: No pattern rows in hit pool")
        # Note: this might be OK for some sets
    else:
        print(f"  ✓ Hit pool contains pattern rows")
    
    # Step 4: Full audit
    print("\\n[4/5] Running comprehensive audit (2000 packs)...")
    audit_result = audit_simulation_sampling_integrity(
        set_config,
        pools,
        num_test_packs=2000,
        rng=np.random.default_rng(42),
    )
    
    if audit_result["is_valid"]:
        print(f"  ✓ Audit PASSED")
        print(f"  ✓ No anomalies detected")
        print(f"  ✓ {audit_result['total_packs_sampled']} packs sampled successfully")
    else:
        print(f"  ✗ Audit FAILED")
        for anomaly in audit_result["anomalies_found"][:5]:
            print(f"    - {anomaly}")
        if len(audit_result["anomalies_found"]) > 5:
            print(f"    ... and {len(audit_result['anomalies_found']) - 5} more")
        return False
    
    # Step 5: Edge case analysis
    print("\\n[5/5] Edge case analysis...")
    if audit_result["edge_cases_detected"]:
        for edge_case in audit_result["edge_cases_detected"]:
            print(f"  ⚠ {edge_case}")
    else:
        print(f"  ✓ No notable edge cases")
    
    # Final report
    print("\\n" + "=" * 70)
    print("VALIDATION RESULT: ✓ PASSED - READY FOR PRODUCTION")
    print("=" * 70)
    
    if verbose:
        print("\\n" + report_audit_results(audit_result))
    
    return True

# Usage:
# success = validate_card_data_for_production(
#     "new_set_cards.csv",
#     SetPrismaticEvolutionsConfig,
#     verbose=True
# )
# if success:
#     print("\\n✓ Data is ready for production deployment!")
#     # Deploy...
"""


# ==============================================================================
# EXAMPLE 5: CONTINUOUS INTEGRATION - AUTOMATED AUDIT IN CI/CD
# ==============================================================================

"""
Use Case: Integrate audit into your CI/CD pipeline to automatically
validate card data on every commit.
"""

EXAMPLE_5_CODE = """
# File: .github/workflows/validate-card-data.yml
# Runs audit automatically on every pull request

name: Validate Card Data

on:
  push:
    paths:
      - 'data/**/*.csv'
  pull_request:
    paths:
      - 'data/**/*.csv'

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.8'
      
      - name: Install dependencies
        run: |
          pip install pytest pandas numpy
      
      - name: Run simulation sampling audit tests
        run: |
          pytest backend/tests/unit/simulations/test_simulation_sampling_integrity.py -v
      
      - name: Validate card data integrity
        run: |
          python backend/scripts/validate_card_data.py \\
            --data-file data/new_set.csv \\
            --audit-packs 1000 \\
            --report audit_report.txt
      
      - name: Upload audit report
        if: failure()
        uses: actions/upload-artifact@v2
        with:
          name: audit_report
          path: audit_report.txt
      
      - name: Comment on PR
        if: failure()
        uses: actions/github-script@v6
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '❌ Audit failed - see audit_report artifact'
            })


# File: backend/scripts/validate_card_data.py
# Python script to run audit from command line

import argparse
import pandas as pd
from backend.simulations.utils.simulation_sampling_audit import (
    audit_simulation_sampling_integrity,
    report_audit_results,
)
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig
from backend.simulations.utils.extractScarletAndVioletCardGroups import extract_scarletandviolet_card_groups

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-file', required=True)
    parser.add_argument('--audit-packs', type=int, default=1000)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    
    # Load data
    df = pd.read_csv(args.data_file)
    
    # Extract pools
    pools = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)
    
    # Run audit
    audit_result = audit_simulation_sampling_integrity(
        SetPrismaticEvolutionsConfig,
        pools,
        num_test_packs=args.audit_packs,
    )
    
    # Write report
    with open(args.report, 'w') as f:
        f.write(report_audit_results(audit_result))
    
    # Exit with proper code
    exit(0 if audit_result["is_valid"] else 1)

if __name__ == '__main__':
    main()
"""


# ==============================================================================
# SUMMARY: WHEN TO USE EACH EXAMPLE
# ==============================================================================

"""
Example 1: Basic Audit
When: You've loaded new data and want quick verification
Time: 5-10 seconds
Result: Detailed report showing pool composition and any issues

Example 2: Detect Pool Issues
When: Something went wrong during data import
Time: 5-10 seconds
Result: Specific identification of which pool has issues

Example 3: Detect Duplicates
When: Simulation results look suspicious or pool is small
Time: 30-60 seconds
Result: Quantification of duplicate sampling frequency

Example 4: Production Validation
When: About to deploy new set data
Time: 30-60 seconds
Result: Comprehensive validation report

Example 5: CI/CD Integration
When: Setting up automated validation
Time: Per-commit checks
Result: Automatic detection of data quality issues

All examples use the same audit_simulation_sampling_integrity() function
with different parameters and interpretations.
"""

print(__doc__)
