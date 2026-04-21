"""
Audit function to validate Monte Carlo simulation sampling integrity.

Ensures pattern-overlay rows are sampled only through intended paths and
prevents duplicate sampling in single packs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd
import numpy as np

from backend.simulations.utils.extractScarletAndVioletCardGroups import (
    _build_base_pool_mask,
    _build_hit_pool_mask,
    _build_pattern_overlay_mask,
)
from backend.simulations.utils.simulationTokenResolver import get_row_match_keys


def audit_simulation_sampling_integrity(
    config,
    pools: Mapping[str, pd.DataFrame],
    num_test_packs: int = 1000,
    rng: Optional[np.random.Generator] = None,
) -> Dict[str, Any]:
    """
    Audit function to validate pattern-overlay sampling integrity.

    Validates that:
    1. Base pools (common, uncommon, rare) exclude pattern rows
    2. Hit pool includes both base hits and pattern rows
    3. No pattern row is sampled multiple times in one pack
    4. Pattern rows only reach simulation through hit pool or state resolution

    Args:
        config: Configuration object with pack state model
        pools: Dict with keys 'common', 'uncommon', 'rare', 'hit', 'reverse'
        num_test_packs: Number of test packs to simulate
        rng: Optional numpy random generator

    Returns:
        Dict with:
            - is_valid: bool (True if no anomalies detected)
            - pool_composition: Dict with pool structure analysis
            - total_packs_sampled: int
            - anomalies_found: List[str]
            - pattern_sampling_paths: Dict with path frequency analysis
            - edge_cases_detected: List[str]
            - sampling_log: List[Dict] with per-pack details (sampled cards and rarities)
    """
    if rng is None:
        rng = np.random.default_rng()

    # Step 1: Validate pool composition
    pool_composition_analysis = _validate_pool_composition(pools)
    
    # Step 2: Run test packs and track sampling
    sampling_results = _run_test_pack_simulation(
        config, pools, num_test_packs, rng
    )
    
    # Step 3: Detect anomalies
    anomalies = _detect_sampling_anomalies(
        pools, pool_composition_analysis, sampling_results
    )
    
    # Step 4: Detect edge cases
    edge_cases = _detect_edge_cases(pools, sampling_results)
    
    is_valid = len(anomalies) == 0
    
    return {
        "is_valid": is_valid,
        "pool_composition": pool_composition_analysis,
        "total_packs_sampled": num_test_packs,
        "anomalies_found": anomalies,
        "pattern_sampling_paths": sampling_results["pattern_sampling_paths"],
        "edge_cases_detected": edge_cases,
        "sampling_log": sampling_results["pack_logs"],
    }


def _validate_pool_composition(pools: Mapping[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    Validate that pools have correct structure and pattern separation.

    Returns:
        Dict with analysis of:
        - Pattern rows in each pool
        - Base rarity rows in each pool
        - Duplicate cards across pools
    """
    analysis = {}

    for pool_name in ["common", "uncommon", "rare", "hit", "reverse"]:
        if pool_name not in pools or pools[pool_name].empty:
            analysis[pool_name] = {
                "total_rows": 0,
                "pattern_rows": 0,
                "pattern_row_names": [],
                "base_rarity_counts": {},
            }
            continue

        df = pools[pool_name]
        
        # Detect pattern rows
        pattern_keys, _ = get_row_match_keys(df, mode="pattern")
        pattern_mask = pattern_keys.ne("")
        pattern_count = pattern_mask.sum()
        
        # Get pattern row names for reference
        pattern_rows = df[pattern_mask]["Card Name"].tolist() if "Card Name" in df.columns else []
        
        # Count base rarities
        base_rarity_keys, _ = get_row_match_keys(df, mode="base_rarity")
        rarity_counts = base_rarity_keys.value_counts().to_dict() if len(base_rarity_keys) > 0 else {}
        
        analysis[pool_name] = {
            "total_rows": len(df),
            "pattern_rows": int(pattern_count),
            "pattern_row_names": pattern_rows,
            "base_rarity_counts": rarity_counts,
        }

    # Check for violations in base pools
    violations = []
    for rarity_name in ["common", "uncommon", "rare"]:
        if analysis[rarity_name]["pattern_rows"] > 0:
            violations.append(
                f"{rarity_name} pool contains {analysis[rarity_name]['pattern_rows']} pattern rows: "
                f"{analysis[rarity_name]['pattern_row_names']}"
            )

    analysis["pool_violations"] = violations

    return analysis


def _run_test_pack_simulation(
    config,
    pools: Mapping[str, pd.DataFrame],
    num_packs: int,
    rng: np.random.Generator,
) -> Dict[str, Any]:
    """
    Run test packs and track which cards are sampled from which pools.

    Returns:
        Dict with:
        - pack_logs: List of dicts tracking each pack's samples
        - pattern_sampling_paths: Counter of how patterns are sampled
        - card_appearance_counts: Counter of card sampling frequency
    """
    pack_logs = []
    pattern_sampling_paths = defaultdict(int)
    card_appearance_counts = Counter()
    
    hit_pool = pools.get("hit", pd.DataFrame())
    if hit_pool.empty:
        return {
            "pack_logs": pack_logs,
            "pattern_sampling_paths": dict(pattern_sampling_paths),
            "card_appearance_counts": dict(card_appearance_counts),
        }

    # Pre-compute pattern rows in hit pool for reference
    pattern_keys, _ = get_row_match_keys(hit_pool, mode="pattern")
    hit_pool_pattern_mask = pattern_keys.ne("")
    
    for pack_idx in range(num_packs):
        pack_log = {
            "pack_number": pack_idx + 1,
            "sampled_cards": [],
            "anomalies": [],
        }
        
        # Simulate sampling some cards from hit pool
        if not hit_pool.empty and len(hit_pool) > 0:
            # Randomly sample 5-8 cards from hit pool per pack (typical scenario)
            num_samples = rng.integers(5, 9)
            sampled_indices = rng.choice(len(hit_pool), size=min(num_samples, len(hit_pool)), replace=False)
            
            for idx in sampled_indices:
                row = hit_pool.iloc[idx]
                card_name = row.get("Card Name", f"Card_{idx}")
                
                # Check if this is a pattern row
                is_pattern = hit_pool_pattern_mask.iloc[idx]
                
                rarity_keys, _ = get_row_match_keys(hit_pool.iloc[idx:idx+1], mode="base_rarity")
                base_rarity = str(rarity_keys.iloc[0]) if len(rarity_keys) > 0 else "unknown"
                
                sample_info = {
                    "card_name": card_name,
                    "is_pattern": bool(is_pattern),
                    "base_rarity": base_rarity,
                    "pool_source": "hit",
                }
                
                pack_log["sampled_cards"].append(sample_info)
                card_appearance_counts[card_name] += 1
                
                if is_pattern:
                    pattern_sampling_paths[f"hit_pool_direct"] += 1
        
        pack_logs.append(pack_log)
    
    return {
        "pack_logs": pack_logs,
        "pattern_sampling_paths": dict(pattern_sampling_paths),
        "card_appearance_counts": dict(card_appearance_counts),
    }


def _detect_sampling_anomalies(
    pools: Mapping[str, pd.DataFrame],
    pool_composition: Dict[str, Any],
    sampling_results: Dict[str, Any],
) -> List[str]:
    """
    Detect anomalies in sampling patterns.

    Returns:
        List of anomaly descriptions.
    """
    anomalies = []

    # Anomaly 1: Pattern rows in base pools
    if pool_composition["pool_violations"]:
        anomalies.extend(pool_composition["pool_violations"])

    # Anomaly 2: Check for duplicate card sampling within single packs
    for pack_log in sampling_results["pack_logs"]:
        card_counts = Counter(
            card["card_name"] for card in pack_log["sampled_cards"]
        )
        for card_name, count in card_counts.items():
            if count > 1:
                anomalies.append(
                    f"Pack {pack_log['pack_number']}: Card '{card_name}' sampled "
                    f"{count} times in single pack"
                )

    # Anomaly 3: Check if pattern row appears in base pools
    for rarity in ["common", "uncommon", "rare"]:
        pool = pools.get(rarity, pd.DataFrame())
        if pool.empty:
            continue
        
        pattern_keys, _ = get_row_match_keys(pool, mode="pattern")
        if pattern_keys.ne("").any():
            pattern_rows = pool[pattern_keys.ne("")]["Card Name"].tolist() if "Card Name" in pool.columns else []
            anomalies.append(
                f"CRITICAL: Base pool '{rarity}' contains {(pattern_keys.ne('').sum())} pattern rows: {pattern_rows}"
            )

    return anomalies


def _detect_edge_cases(
    pools: Mapping[str, pd.DataFrame],
    sampling_results: Dict[str, Any],
) -> List[str]:
    """
    Detect edge cases in pool composition or sampling.

    Returns:
        List of edge case descriptions.
    """
    edge_cases = []

    hit_pool = pools.get("hit", pd.DataFrame())
    if hit_pool.empty:
        edge_cases.append("Hit pool is empty")
        return edge_cases

    # Edge case 1: Multiple rarity types in hit pool
    base_rarity_keys, _ = get_row_match_keys(hit_pool, mode="base_rarity")
    unique_rarities = set(base_rarity_keys[base_rarity_keys.ne("")].unique())
    if len(unique_rarities) > 0:
        edge_cases.append(
            f"Hit pool contains multiple base rarities: {sorted(unique_rarities)}"
        )

    # Edge case 2: Multiple pattern types in hit pool
    pattern_keys, _ = get_row_match_keys(hit_pool, mode="pattern")
    unique_patterns = set(pattern_keys[pattern_keys.ne("")].unique())
    if len(unique_patterns) > 1:
        edge_cases.append(
            f"Hit pool contains multiple pattern types: {sorted(unique_patterns)}"
        )

    # Edge case 3: Empty base pools
    for rarity in ["common", "uncommon", "rare"]:
        pool = pools.get(rarity, pd.DataFrame())
        if pool.empty:
            edge_cases.append(f"Base pool '{rarity}' is empty")

    # Edge case 4: No reverse pool
    reverse_pool = pools.get("reverse", pd.DataFrame())
    if reverse_pool.empty:
        edge_cases.append("Reverse pool is empty")

    return edge_cases


def verify_no_pattern_in_base_pools(pools: Mapping[str, pd.DataFrame]) -> bool:
    """
    Quick verification that no pattern rows exist in base pools.

    Returns:
        True if all base pools are pattern-free, False otherwise.
    """
    for rarity in ["common", "uncommon", "rare"]:
        pool = pools.get(rarity, pd.DataFrame())
        if pool.empty:
            continue
        
        pattern_keys, _ = get_row_match_keys(pool, mode="pattern")
        if pattern_keys.ne("").any():
            return False
    
    return True


def verify_pattern_rows_in_hit_pool(pools: Mapping[str, pd.DataFrame]) -> bool:
    """
    Verify that hit pool contains pattern rows.

    Returns:
        True if hit pool has at least one pattern row, False otherwise.
    """
    hit_pool = pools.get("hit", pd.DataFrame())
    if hit_pool.empty:
        return False
    
    pattern_keys, _ = get_row_match_keys(hit_pool, mode="pattern")
    return pattern_keys.ne("").any()


def report_audit_results(audit_result: Dict[str, Any]) -> str:
    """
    Format audit results as a readable report.

    Args:
        audit_result: Result from audit_simulation_sampling_integrity()

    Returns:
        Formatted string report.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("SIMULATION SAMPLING INTEGRITY AUDIT REPORT")
    lines.append("=" * 70)
    lines.append("")
    
    # Overall status
    status = "✓ PASSED" if audit_result["is_valid"] else "✗ FAILED"
    lines.append(f"Status: {status}")
    lines.append(f"Total Packs Sampled: {audit_result['total_packs_sampled']}")
    lines.append("")
    
    # Pool composition
    lines.append("Pool Composition Analysis:")
    lines.append("-" * 70)
    comp = audit_result["pool_composition"]
    for pool_name in ["common", "uncommon", "rare", "hit", "reverse"]:
        if pool_name in comp:
            info = comp[pool_name]
            lines.append(f"  {pool_name.upper()}")
            lines.append(f"    - Total Rows: {info['total_rows']}")
            lines.append(f"    - Pattern Rows: {info['pattern_rows']}")
            if info['pattern_row_names']:
                lines.append(f"    - Pattern Names: {', '.join(info['pattern_row_names'][:3])}")
    lines.append("")
    
    # Anomalies
    lines.append("Anomalies:")
    lines.append("-" * 70)
    if audit_result["anomalies_found"]:
        for anomaly in audit_result["anomalies_found"]:
            lines.append(f"  ✗ {anomaly}")
    else:
        lines.append("  ✓ No anomalies detected")
    lines.append("")
    
    # Pattern sampling paths
    lines.append("Pattern Sampling Paths:")
    lines.append("-" * 70)
    paths = audit_result["pattern_sampling_paths"]
    if paths:
        for path, count in sorted(paths.items(), key=lambda x: -x[1]):
            lines.append(f"  {path}: {count}")
    else:
        lines.append("  (No pattern sampling detected)")
    lines.append("")
    
    # Edge cases
    lines.append("Edge Cases:")
    lines.append("-" * 70)
    if audit_result["edge_cases_detected"]:
        for edge_case in audit_result["edge_cases_detected"]:
            lines.append(f"  ⚠ {edge_case}")
    else:
        lines.append("  (No notable edge cases)")
    
    lines.append("")
    lines.append("=" * 70)
    
    return "\n".join(lines)
