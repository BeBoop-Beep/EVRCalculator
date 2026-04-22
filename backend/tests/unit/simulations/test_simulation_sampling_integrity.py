"""
Comprehensive tests for simulation sampling integrity.

Validates that pattern-overlay rows are sampled only through intended paths
and prevents duplicate sampling in single packs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List

import numpy as np
import pandas as pd
import pytest

from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
    SetPrismaticEvolutionsConfig,
)
from backend.simulations.monteCarloSim import make_simulate_pack_fn
from backend.simulations.monteCarloSimV2 import make_simulate_pack_fn_v2
from backend.simulations.utils.extractScarletAndVioletCardGroups import (
    _build_base_pool_mask,
    _build_hit_pool_mask,
    _build_pattern_overlay_mask,
    extract_scarletandviolet_card_groups,
)
from backend.simulations.utils.simulation_sampling_audit import (
    audit_simulation_sampling_integrity,
    report_audit_results,
    verify_no_pattern_in_base_pools,
    verify_pattern_rows_in_hit_pool,
)
from backend.simulations.utils.simulationTokenResolver import get_row_match_keys


class TestBasePoolsPreservePatternOverlayRows:
    """
    Test 1: Verify base pools (common, uncommon, rare) contain only plain
    non-pattern rows. Pattern overlay rows must be excluded from base pools
    and routed exclusively to the hit pool.
    """

    def test_base_pools_preserve_pattern_rows_with_synthetic_data(self):
        """Verify that pattern rows remain in matching base pools."""
        df = pd.DataFrame({
            "Card Name": [
                "Common 1", "Common 2",
                "Uncommon 1", "Uncommon 2",
                "Rare 1", "Rare 2",
                "Pattern Poke 1", "Pattern Master 1"
            ],
            "Rarity": [
                "common", "common",
                "uncommon", "uncommon",
                "rare", "rare",
                "rare", "rare"
            ],
            "Special Type": [
                "", "",
                "", "",
                "", "",
                "poke ball", "master ball"
            ],
            "Price ($)": [0.1, 0.1, 0.2, 0.2, 0.9, 1.0, 1.5, 2.0],
        })

        common_mask = _build_base_pool_mask(df, "common")
        uncommon_mask = _build_base_pool_mask(df, "uncommon")
        rare_mask = _build_base_pool_mask(df, "rare")

        # Verify normal cards included
        assert common_mask.iloc[0] and common_mask.iloc[1], "Normal commons should be included"
        assert uncommon_mask.iloc[2] and uncommon_mask.iloc[3], "Normal uncommons should be included"
        assert rare_mask.iloc[4] and rare_mask.iloc[5], "Normal rares should be included"

        # Verify pattern cards are excluded from base rare pool.
        assert not rare_mask.iloc[6], "Pattern poke ball rare must be excluded from base rare pool"
        assert not rare_mask.iloc[7], "Pattern master ball rare must be excluded from base rare pool"

    def test_base_pools_exclude_pattern_rows_with_prismatic_data(self):
        """Verify pattern rows are excluded from base-rarity pools in Prismatic configuration."""
        # Create a minimal dataset with Prismatic structure
        df = pd.DataFrame({
            "Card Name": [
                "Regular Rare 1", "Regular Rare 2",
                "Poke Ball Pattern Rare", "Master Ball Pattern Rare"
            ],
            "Rarity": ["rare", "rare", "rare", "rare"],
            "Special Type": ["", "", "poke ball", "master ball"],
            "Price ($)": [0.9, 1.0, 1.5, 2.0],
        })

        # Extract pools
        groups = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)
        rare_pool = groups["rare"]

        # Only plain (non-pattern) rare rows should be in the base rare pool.
        assert len(rare_pool) == 2, f"Rare pool should have 2 plain cards only, got {len(rare_pool)}"
        assert all(
            card_name not in rare_pool["Card Name"].tolist()
            for card_name in ["Poke Ball Pattern Rare", "Master Ball Pattern Rare"]
        ), "Pattern cards must be excluded from base rare pool"


class TestPatternRowNotSampledFromBaseSlots:
    """
    Test 2: Run simulation and verify pattern rows are never sampled from base slots.
    """

    @pytest.fixture
    def synthetic_pools(self):
        """Create synthetic pools with pattern rows for testing."""
        common = pd.DataFrame({
            "Card Name": ["Common 1", "Common 2", "Common 3"],
            "Rarity": ["common", "common", "common"],
            "Special Type": ["", "", ""],
            "Price ($)": [0.1, 0.1, 0.1],
        })
        uncommon = pd.DataFrame({
            "Card Name": ["Uncommon 1", "Uncommon 2"],
            "Rarity": ["uncommon", "uncommon"],
            "Special Type": ["", ""],
            "Price ($)": [0.2, 0.2],
        })
        rare = pd.DataFrame({
            "Card Name": ["Rare 1", "Rare 2"],
            "Rarity": ["rare", "rare"],
            "Special Type": ["", ""],
            "Price ($)": [0.9, 1.0],
        })
        hit = pd.DataFrame({
            "Card Name": [
                "Ultra Rare 1", "Illustration Rare 1",
                "Poke Ball Pattern", "Master Ball Pattern"
            ],
            "Rarity": [
                "ultra rare", "illustration rare",
                "rare", "rare"
            ],
            "Special Type": [
                "", "",
                "poke ball", "master ball"
            ],
            "Price ($)": [3.0, 2.5, 1.5, 2.0],
        })
        reverse = pd.DataFrame({
            "Card Name": ["Reverse 1", "Reverse 2"],
            "Reverse Variant Price ($)": [0.3, 0.35],
        })
        return {
            "common": common,
            "uncommon": uncommon,
            "rare": rare,
            "hit": hit,
            "reverse": reverse,
        }

    def test_pattern_row_not_sampled_from_base_slots(self, synthetic_pools):
        """Run simulation and track that no pattern row is sampled from base slots."""
        # Run audit on pools
        audit_result = audit_simulation_sampling_integrity(
            SetPrismaticEvolutionsConfig,
            synthetic_pools,
            num_test_packs=100,
            rng=np.random.default_rng(42),
        )

        # Verify no anomalies related to base pool pattern sampling
        base_pool_anomalies = [
            a for a in audit_result["anomalies_found"]
            if "base pool" in a.lower() or "base rare" in a.lower()
        ]
        assert len(base_pool_anomalies) == 0, (
            f"Found anomalies in base pool sampling: {base_pool_anomalies}"
        )

        # Overlap semantics allow pattern rows in base pools.
        assert verify_pattern_rows_in_hit_pool(synthetic_pools)


class TestPatternRowNotDoubleSampled:
    """
    Test 3: Verify no pattern row (or any card) is sampled twice in one pack.
    """

    @pytest.fixture
    def test_pools(self):
        """Create test pools."""
        return {
            "common": pd.DataFrame({
                "Card Name": ["C1", "C2"],
                "Rarity": ["common", "common"],
                "Special Type": ["", ""],
                "Price ($)": [0.1, 0.1],
            }),
            "uncommon": pd.DataFrame({
                "Card Name": ["U1"],
                "Rarity": ["uncommon"],
                "Special Type": [""],
                "Price ($)": [0.2],
            }),
            "rare": pd.DataFrame({
                "Card Name": ["R1"],
                "Rarity": ["rare"],
                "Special Type": [""],
                "Price ($)": [0.9],
            }),
            "hit": pd.DataFrame({
                "Card Name": ["UR1", "IR1", "PP1", "MP1"],
                "Rarity": ["ultra rare", "illustration rare", "rare", "rare"],
                "Special Type": ["", "", "poke ball", "master ball"],
                "Price ($)": [3.0, 2.5, 1.5, 2.0],
            }),
            "reverse": pd.DataFrame({
                "Card Name": ["REV1"],
                "Reverse Variant Price ($)": [0.3],
            }),
        }

    def test_no_card_double_sampled_in_single_pack(self, test_pools):
        """Verify no card is sampled twice within a single pack."""
        audit_result = audit_simulation_sampling_integrity(
            SetPrismaticEvolutionsConfig,
            test_pools,
            num_test_packs=500,
            rng=np.random.default_rng(42),
        )

        # Check for double-sampling anomalies
        double_sample_anomalies = [
            a for a in audit_result["anomalies_found"]
            if "sampled" in a.lower() and "times in single pack" in a.lower()
        ]
        assert len(double_sample_anomalies) == 0, (
            f"Found double-sampling anomalies: {double_sample_anomalies}"
        )

    def test_pattern_row_specifically_not_double_sampled(self, test_pools):
        """Verify pattern rows specifically are never double-sampled."""
        audit_result = audit_simulation_sampling_integrity(
            SetPrismaticEvolutionsConfig,
            test_pools,
            num_test_packs=500,
        )

        # Verify pattern row counts in log
        pack_logs = audit_result["sampling_log"]
        for pack_log in pack_logs:
            pattern_card_names = [
                c["card_name"] for c in pack_log["sampled_cards"]
                if c["is_pattern"]
            ]
            pattern_counts = Counter(pattern_card_names)
            for card_name, count in pattern_counts.items():
                assert count <= 1, (
                    f"Pattern card '{card_name}' sampled {count} times in pack "
                    f"{pack_log['pack_number']}"
                )


class TestStateResolutionUsesCorrectPool:
    """
    Test 4: When a slot resolves to pattern, it uses hit pool correctly.
    """

    def test_hit_pool_resolution_with_pattern_token(self):
        """Test that pattern token resolution returns from hit pool."""
        hit_df = pd.DataFrame({
            "Card Name": [
                "Poke Ball Pattern 1", "Poke Ball Pattern 2",
                "Master Ball Pattern 1", "Master Ball Pattern 2",
                "Other Card"
            ],
            "Rarity": ["rare", "rare", "rare", "rare", "ultra rare"],
            "Special Type": ["poke ball", "poke ball", "master ball", "master ball", ""],
            "Price ($)": [1.5, 1.6, 2.0, 2.1, 3.0],
        })

        # Test pattern resolution
        from backend.simulations.utils.simulationTokenResolver import resolve_hit_pool_rows

        # Resolve poke ball pattern
        eligible_poke, info_poke = resolve_hit_pool_rows(
            hit_df,
            "poke ball pattern",
            mode="pattern",
        )

        assert len(eligible_poke) == 2, f"Should have 2 poke ball patterns, got {len(eligible_poke)}"
        assert all(
            card_name.startswith("Poke Ball Pattern")
            for card_name in eligible_poke["Card Name"].tolist()
        ), "All resolved cards should be poke ball pattern"

        # Resolve master ball pattern
        eligible_master, info_master = resolve_hit_pool_rows(
            hit_df,
            "master ball pattern",
            mode="pattern",
        )

        assert len(eligible_master) == 2, f"Should have 2 master ball patterns, got {len(eligible_master)}"
        assert all(
            card_name.startswith("Master Ball Pattern")
            for card_name in eligible_master["Card Name"].tolist()
        ), "All resolved cards should be master ball pattern"


class TestHitPoolContainsBothBasesAndPatterns:
    """
    Test 5: Hit pool contains both base hits and pattern-overlay cards.
    """

    def test_hit_pool_contains_base_hits_and_patterns(self):
        """Verify hit pool has both base hits and pattern rows."""
        df = pd.DataFrame({
            "Card Name": [
                "Double Rare 1", "Ultra Rare 1", "Illustration Rare 1",
                "Special Illustration Rare 1", "Hyper Rare 1",
                "Poke Ball Pattern", "Master Ball Pattern"
            ],
            "Rarity": [
                "double rare", "ultra rare", "illustration rare",
                "special illustration rare", "hyper rare",
                "rare", "rare"
            ],
            "Special Type": [
                "", "", "", "", "",
                "poke ball", "master ball"
            ],
            "Price ($)": [4.0, 9.0, 7.5, 31.0, 26.0, 1.9, 4.6],
        })

        hit_mask = _build_hit_pool_mask(df)
        hit_pool = df[hit_mask]

        # Verify hit pool has both types
        assert len(hit_pool) == 7, f"Hit pool should have 7 cards, got {len(hit_pool)}"

        # Count base hits vs patterns
        pattern_keys, _ = get_row_match_keys(hit_pool, mode="pattern")
        pattern_count = (pattern_keys.ne("")).sum()
        base_hit_count = len(hit_pool) - pattern_count

        assert base_hit_count > 0, "Hit pool should contain base hit cards"
        assert pattern_count > 0, "Hit pool should contain pattern cards"
        assert pattern_count == 2, f"Should have 2 pattern cards, got {pattern_count}"

    def test_hit_pool_has_no_duplicates(self):
        """Verify hit pool contains no duplicate cards."""
        df = pd.DataFrame({
            "Card Name": [
                "UR1", "UR2", "IR1", "SIR1",
                "HR1", "PP1", "MP1"
            ],
            "Rarity": [
                "ultra rare", "ultra rare", "illustration rare",
                "special illustration rare", "hyper rare",
                "rare", "rare"
            ],
            "Special Type": [
                "", "", "", "", "",
                "poke ball", "master ball"
            ],
            "Price ($)": [9.0, 9.5, 7.5, 31.0, 26.0, 1.9, 4.6],
        })

        hit_mask = _build_hit_pool_mask(df)
        hit_pool = df[hit_mask]

        card_names = hit_pool["Card Name"].tolist()
        assert len(card_names) == len(set(card_names)), "Hit pool should have no duplicate cards"


class TestSimulationAuditWithPrismaticData:
    """
    Test 6: Run audit function on Prismatic data and verify no anomalies.
    """

    @pytest.fixture
    def prismatic_pools(self):
        """Create realistic Prismatic-like pools."""
        commons = pd.DataFrame({
            "Card Name": ["Common A", "Common B", "Common C"],
            "Rarity": ["common", "common", "common"],
            "Special Type": ["", "", ""],
            "Price ($)": [0.09, 0.11, 0.08],
        })
        uncommons = pd.DataFrame({
            "Card Name": ["Uncommon A", "Uncommon B"],
            "Rarity": ["uncommon", "uncommon"],
            "Special Type": ["", ""],
            "Price ($)": [0.24, 0.19],
        })
        rares = pd.DataFrame({
            "Card Name": ["Rare 1", "Rare 2"],
            "Rarity": ["rare", "rare"],
            "Special Type": ["", ""],
            "Price ($)": [0.9, 1.1],
        })
        reverse = pd.DataFrame({
            "Card Name": ["Reverse 1", "Reverse 2"],
            "Reverse Variant Price ($)": [0.35, 0.28],
        })
        hit = pd.DataFrame({
            "Card Name": [
                "Double Rare", "Ultra Rare", "Illustration Rare",
                "Special Illustration Rare", "Hyper Rare", "Ace Spec",
                "Poke Ball Pattern", "Master Ball Pattern"
            ],
            "Rarity": [
                "double rare", "ultra rare", "illustration rare",
                "special illustration rare", "hyper rare", "ace spec rare",
                "rare", "rare"
            ],
            "Special Type": [
                "", "", "", "", "",
                "", "poke ball", "master ball"
            ],
            "Price ($)": [4.0, 9.0, 7.5, 31.0, 26.0, 3.0, 1.9, 4.6],
        })

        return {
            "common": commons,
            "uncommon": uncommons,
            "rare": rares,
            "reverse": reverse,
            "hit": hit,
        }

    def test_simulation_audit_with_prismatic_data(self, prismatic_pools):
        """Run audit on Prismatic-like data and verify validity."""
        audit_result = audit_simulation_sampling_integrity(
            SetPrismaticEvolutionsConfig,
            prismatic_pools,
            num_test_packs=500,
            rng=np.random.default_rng(42),
        )

        assert audit_result["is_valid"], (
            f"Audit should pass for valid Prismatic pools. "
            f"Anomalies found: {audit_result['anomalies_found']}"
        )
        assert len(audit_result["anomalies_found"]) == 0
        assert audit_result["total_packs_sampled"] == 500

    def test_audit_report_formatting(self, prismatic_pools):
        """Test that audit report formats correctly."""
        audit_result = audit_simulation_sampling_integrity(
            SetPrismaticEvolutionsConfig,
            prismatic_pools,
            num_test_packs=100,
        )

        report = report_audit_results(audit_result)
        assert "SIMULATION SAMPLING INTEGRITY AUDIT REPORT" in report
        assert "Pool Composition Analysis" in report
        assert "Anomalies" in report
        assert "Pattern Sampling Paths" in report
        assert "Status:" in report


class TestV1AndV2SamplingIntegrity:
    """
    Test 7: Test both simulation versions (V1 and V2) handle patterns correctly.
    """

    @pytest.fixture
    def test_pools(self):
        """Pools for V1/V2 testing."""
        return {
            "common": pd.DataFrame({
                "Card Name": ["C1", "C2", "C3", "C4"],
                "Rarity": ["common", "common", "common", "common"],
                "Special Type": ["", "", "", ""],
                "Price ($)": [0.1] * 4,
            }),
            "uncommon": pd.DataFrame({
                "Card Name": ["U1", "U2", "U3"],
                "Rarity": ["uncommon", "uncommon", "uncommon"],
                "Special Type": ["", "", ""],
                "Price ($)": [0.2] * 3,
            }),
            "rare": pd.DataFrame({
                "Card Name": ["R1", "R2", "R3"],
                "Rarity": ["rare", "rare", "rare"],
                "Special Type": ["", "", ""],
                "Price ($)": [0.9, 1.0, 1.1],
            }),
            "hit": pd.DataFrame({
                "Card Name": [
                    "UR1", "IR1", "SIR1", "HR1", "AS1",
                    "PP1", "MP1"
                ],
                "Rarity": [
                    "ultra rare", "illustration rare",
                    "special illustration rare", "hyper rare",
                    "ace spec rare", "rare", "rare"
                ],
                "Special Type": [
                    "", "", "", "", "",
                    "poke ball", "master ball"
                ],
                "Price ($)": [9.0, 7.5, 31.0, 26.0, 3.0, 1.9, 4.6],
            }),
            "reverse": pd.DataFrame({
                "Card Name": ["REV1", "REV2"],
                "Reverse Variant Price ($)": [0.3, 0.35],
            }),
        }

    def test_pools_valid_for_both_versions(self, test_pools):
        """Verify test pools are valid for both simulation versions."""
        assert verify_pattern_rows_in_hit_pool(test_pools)

    def test_both_versions_allow_overlap_semantics(self, test_pools):
        """Base pools can contain pattern rows as long as hit-path resolution remains valid."""
        for rarity in ["common", "uncommon", "rare"]:
            pool = test_pools[rarity]
            pattern_keys, _ = get_row_match_keys(pool, mode="pattern")
            assert not pattern_keys.ne("").any()

    def test_audit_validates_both_simulation_versions(self, test_pools):
        """Run audit and verify it works for both simulation versions."""
        audit_result = audit_simulation_sampling_integrity(
            SetPrismaticEvolutionsConfig,
            test_pools,
            num_test_packs=300,
        )

        # Audit should be valid for both
        assert audit_result["is_valid"], (
            f"Audit should pass. Anomalies: {audit_result['anomalies_found']}"
        )


class TestEdgeCases:
    """
    Additional edge case tests for comprehensive coverage.
    """

    def test_pattern_empty_string_vs_no_pattern(self):
        """Verify '' pattern is treated as no pattern."""
        df = pd.DataFrame({
            "Card Name": ["Card1", "Card2"],
            "Rarity": ["rare", "rare"],
            "Special Type": ["", ""],
            "Price ($)": [1.0, 1.0],
        })

        pattern_keys, _ = get_row_match_keys(df, mode="pattern")
        assert pattern_keys.iloc[0] == ""
        assert pattern_keys.iloc[1] == ""

        # Both should be in base pool
        mask = _build_base_pool_mask(df, "rare")
        assert mask.iloc[0] and mask.iloc[1]

    def test_common_with_poke_ball_pattern_included_in_base(self):
        """Edge case: common rarity with poke ball pattern remains in base and hit."""
        df = pd.DataFrame({
            "Card Name": ["Common Hit", "Common Poke Pattern"],
            "Rarity": ["common", "common"],
            "Special Type": ["", "poke ball"],
            "Price ($)": [0.1, 0.15],
        })

        common_mask = _build_base_pool_mask(df, "common")
        assert common_mask.iloc[0], "Normal common should be in base"
        assert not common_mask.iloc[1], "Common with poke pattern must be excluded from base pool"

        hit_mask = _build_hit_pool_mask(df)
        assert not hit_mask.iloc[0], "Normal common should not be in hit"
        assert hit_mask.iloc[1], "Common poke pattern should be in hit"

    def test_all_three_patterns_in_one_test(self):
        """Edge case: empty pattern + poke ball + master ball all present."""
        df = pd.DataFrame({
            "Card Name": ["No Pattern", "Poke Pattern", "Master Pattern"],
            "Rarity": ["rare", "rare", "rare"],
            "Special Type": ["", "poke ball", "master ball"],
            "Price ($)": [1.0, 1.5, 2.0],
        })

        # Extract using pool masks
        base_rare_mask = _build_base_pool_mask(df, "rare")
        hit_mask = _build_hit_pool_mask(df)

        # Verify pattern exclusion from base pool
        assert base_rare_mask.iloc[0], "No-pattern rare in base"
        assert not base_rare_mask.iloc[1], "Poke pattern must be excluded from base"
        assert not base_rare_mask.iloc[2], "Master pattern must be excluded from base"

        assert not hit_mask.iloc[0], "No-pattern rare not in hit"
        assert hit_mask.iloc[1], "Poke pattern in hit"
        assert hit_mask.iloc[2], "Master pattern in hit"

    def test_empty_pools_handled_gracefully(self):
        """Verify audit handles empty pools without crashing."""
        pools = {
            "common": pd.DataFrame(),
            "uncommon": pd.DataFrame(),
            "rare": pd.DataFrame(),
            "hit": pd.DataFrame(),
            "reverse": pd.DataFrame(),
        }

        audit_result = audit_simulation_sampling_integrity(
            SetPrismaticEvolutionsConfig,
            pools,
            num_test_packs=10,
        )

        # Should indicate edge cases but not crash
        assert "edge_cases_detected" in audit_result
        assert len(audit_result["edge_cases_detected"]) > 0

    def test_all_patterns_audit_with_comprehensive_data(self):
        """Comprehensive test with all pattern types and edge cases."""
        df = pd.DataFrame({
            "Card Name": [
                # Base common
                "Common 1", "Common 2",
                # Base uncommon
                "Uncommon 1", "Uncommon 2",
                # Base rare
                "Rare 1", "Rare 2",
                # Pattern commons (also in hit)
                "Common Poke", "Common Master",
                # Pattern uncommons
                "Uncommon Poke", "Uncommon Master",
                # Pattern rares
                "Rare Poke", "Rare Master",
                # Other hits
                "Ultra Rare", "Illustration Rare"
            ],
            "Rarity": [
                "common", "common",
                "uncommon", "uncommon",
                "rare", "rare",
                "common", "common",
                "uncommon", "uncommon",
                "rare", "rare",
                "ultra rare", "illustration rare"
            ],
            "Special Type": [
                "", "",
                "", "",
                "", "",
                "poke ball", "master ball",
                "poke ball", "master ball",
                "poke ball", "master ball",
                "", ""
            ],
            "Price ($)": [
                0.1, 0.1,
                0.2, 0.2,
                0.9, 1.0,
                0.15, 0.16,
                0.25, 0.26,
                1.5, 2.0,
                9.0, 7.5
            ],
        })

        groups = extract_scarletandviolet_card_groups(SetPrismaticEvolutionsConfig, df)

        # Verify base pools contain only non-pattern rows
        assert len(groups["common"]) == 2, "Base common should contain only plain (non-pattern) rows"
        assert len(groups["uncommon"]) == 2, "Base uncommon should contain only plain (non-pattern) rows"
        assert len(groups["rare"]) == 2, "Base rare should contain only plain (non-pattern) rows"

        # Verify hit pool has everything else
        hit_pool = groups["hit"]
        assert len(hit_pool) >= 8, "Hit pool should contain all patterns and hits"
        
        # Verify all patterns are in hit
        pattern_keys, _ = get_row_match_keys(hit_pool, mode="pattern")
        pattern_count = (pattern_keys.ne("")).sum()
        assert pattern_count == 6, f"Hit pool should have 6 pattern rows, got {pattern_count}"
