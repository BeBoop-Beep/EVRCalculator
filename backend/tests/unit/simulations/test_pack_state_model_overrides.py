from collections import defaultdict

import numpy as np
import pandas as pd
import pytest

from backend.constants.tcg.pokemon.megaEvolutionEra.ascendedHeroes import SetAscendedHeroesConfig
from backend.constants.tcg.pokemon.megaEvolutionEra.megaEvolution import SetMegaEvolutionConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.blackBolt import SetBlackBoltConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.whiteFlare import SetWhiteFlareConfig
from backend.simulations.monteCarloSimV2 import (
    make_simulate_pack_fn_v2,
    resolve_slot_outcomes_from_state,
    run_simulation_v2,
    sample_pack_state,
    validate_pack_state_model,
)
from backend.simulations.utils.packStateModels.packStateModelOrchestrator import resolve_pack_state_model
from backend.simulations.utils.packStateModels import scarletAndVioletPackStateModel as sv_model_module
from backend.simulations.utils.packStateModels.scarletAndVioletPackStateModel import (
    SV_ERA_DEFAULT_RARE_SLOT_PROBABILITY,
    SV_ERA_DEFAULT_REVERSE_SLOT_PROBABILITIES,
    build_scarlet_and_violet_pack_state_model,
)


@pytest.fixture
def pools():
    common = pd.DataFrame(
        {
            "Card Name": [f"Common {i}" for i in range(1, 8)],
            "Price ($)": [0.10, 0.12, 0.08, 0.11, 0.09, 0.13, 0.07],
            "Rarity": ["common"] * 7,
        }
    )
    uncommon = pd.DataFrame(
        {
            "Card Name": [f"Uncommon {i}" for i in range(1, 7)],
            "Price ($)": [0.20, 0.25, 0.18, 0.22, 0.19, 0.28],
            "Rarity": ["uncommon"] * 6,
        }
    )
    rare = pd.DataFrame(
        {
            "Card Name": ["Rare A", "Rare B", "Rare C", "Rare D"],
            "Price ($)": [0.75, 0.95, 1.10, 0.88],
            "Rarity": ["rare", "rare", "rare", "rare"],
        }
    )
    reverse = pd.DataFrame(
        {
            "Card Name": ["Reverse A", "Reverse B", "Reverse C", "Reverse D"],
            "EV_Reverse": [0.35, 0.40, 0.28, 0.32],
        }
    )
    hit = pd.DataFrame(
        {
            "Card Name": [
                "Double Rare A",
                "Ultra Rare A",
                "Illustration Rare A",
                "Special Illustration Rare A",
                "Hyper Rare A",
                "Mega Hyper Rare A",
                "Ace Spec A",
                "Poke Pattern A",
                "Master Pattern A",
                "Black White Rare A",
            ],
            "Price ($)": [
                4.00,
                9.50,
                7.25,
                28.0,
                22.0,
                33.0,
                3.75,
                2.20,
                5.0,
                14.0,
            ],
            "Rarity": [
                "double rare",
                "ultra rare",
                "illustration rare",
                "special illustration rare",
                "hyper rare",
                "mega hyper rare",
                "ace spec rare",
                "poke ball pattern",
                "master ball pattern",
                "black white rare",
            ],
        }
    )

    df = pd.concat([common, uncommon, rare, hit], ignore_index=True)
    return {
        "common": common,
        "uncommon": uncommon,
        "rare": rare,
        "reverse": reverse,
        "hit": hit,
        "df": df,
    }



# ---------------------------------------------------------------------------
# Requirement 5: Overrides can add named states without duplicating probabilities
# ---------------------------------------------------------------------------

def test_override_adds_named_state_for_reachable_slot_combination():
    """Override provides a canonical name for a combination that arises from slot probs.

    Without the override the same combination is auto-named; with the override it
    carries the human-readable registry name.  The base model's existing states
    (e.g. sir_only) are unaffected.
    """
    class _Base:
        ERA = "Scarlet and Violet"
        # slot_1 carries poke ball pattern → (double_rare, poke_ball, reg) is reachable
        RARE_SLOT_PROBABILITY = {"double rare": 0.15, "ultra rare": 0.10, "rare": 0.75}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"poke ball pattern": 0.20, "regular reverse": 0.80},
            "slot_2": {
                "special illustration rare": 0.02,
                "illustration rare": 0.08,
                "regular reverse": 0.90,
            },
        }

    class _WithNamedState(_Base):
        @staticmethod
        def get_pack_state_overrides():
            return {
                "state_outcomes": {
                    "my_pattern_dr_state": {
                        "rare":      "double rare",
                        "reverse_1": "poke ball pattern",
                        "reverse_2": "regular reverse",
                    }
                },
            }

    base_model  = resolve_pack_state_model(_Base)
    named_model = resolve_pack_state_model(_WithNamedState)

    # Override-introduced name appears in the named model with non-zero probability
    assert "my_pattern_dr_state" in named_model["state_outcomes"]
    assert named_model["state_probabilities"]["my_pattern_dr_state"] > 0

    # The base model auto-names the same combination differently (not the override name)
    assert "my_pattern_dr_state" not in base_model["state_outcomes"]

    # sir_only is structurally identical in both models (override didn't touch it)
    assert "sir_only" in named_model["state_outcomes"]
    assert named_model["state_outcomes"]["sir_only"] == base_model["state_outcomes"]["sir_only"]


# ---------------------------------------------------------------------------
# Requirement 4: No manual placeholder probability tables required
# ---------------------------------------------------------------------------

def test_overrides_without_state_probabilities_are_valid():
    """Structural-only overrides (no state_probabilities) produce a valid model."""
    class _Config:
        ERA = "Scarlet and Violet"
        RARE_SLOT_PROBABILITY = {"rare": 0.80, "double rare": 0.20}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"regular reverse": 0.90, "ace spec rare": 0.10},
            "slot_2": {"special illustration rare": 0.03, "regular reverse": 0.97},
        }

        @staticmethod
        def get_pack_state_overrides():
            # Only structural additions – NO state_probabilities provided
            return {
                "state_outcomes": {
                    "ace_spec_plus_double_rare": {
                        "rare": "double rare",
                        "reverse_1": "ace spec rare",
                        "reverse_2": "regular reverse",
                    }
                },
            }

    model = resolve_pack_state_model(_Config)
    probs = model["state_probabilities"]
    # Probabilities sum to 1 without any manually entered values
    assert pytest.approx(1.0, abs=1e-8) == sum(probs.values())
    # Every probability-bearing state has slot outcomes
    for state in probs:
        assert state in model["state_outcomes"]


def test_duplicate_state_shape_in_overrides_fails_loudly():
    class _Config:
        ERA = "Scarlet and Violet"

        @staticmethod
        def get_pack_state_overrides():
            return {
                "state_outcomes": {
                    # Exact duplicate of baseline shape is forbidden.
                    "forced_state": {
                        "rare": "rare",
                        "reverse_1": "regular reverse",
                        "reverse_2": "regular reverse",
                    }
                }
            }

    with pytest.raises(ValueError, match="Duplicate state-outcome shape"):
        resolve_pack_state_model(_Config)


# ---------------------------------------------------------------------------
# Requirement 1: Baseline probability derived from slot probabilities
# ---------------------------------------------------------------------------

def test_derived_baseline_probability_matches_slot_product():
    """P(baseline) = P(rare in rare slot) × P(reg_rev slot_1) × P(reg_rev slot_2).

    Any combination with a non-baseline outcome in any slot coerces to a different
    state.  The only combination that resolves to 'baseline' is
    (rare, regular reverse, regular reverse) from the slot tables.
    """
    p_rare   = 0.75
    p_dr     = 0.15
    p_ur     = 0.10
    p_s1_reg = 1.0    # slot_1 always regular → maximises baseline
    p_s2_reg = 0.90
    p_s2_sir = 0.05
    p_s2_ir  = 0.05

    class _Config:
        ERA = "Scarlet and Violet"
        RARE_SLOT_PROBABILITY = {
            "rare": p_rare, "double rare": p_dr, "ultra rare": p_ur,
        }
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"regular reverse": p_s1_reg},
            "slot_2": {
                "special illustration rare": p_s2_sir,
                "illustration rare": p_s2_ir,
                "regular reverse": p_s2_reg,
            },
        }

    model = resolve_pack_state_model(_Config)
    # baseline = (rare, reg, reg) only; Rule 1 demotes rare-slot when exclusive in r2
    expected = p_rare * p_s1_reg * p_s2_reg
    assert pytest.approx(expected, abs=1e-9) == model["state_probabilities"]["baseline"]


# ---------------------------------------------------------------------------
# Requirement 2: Derived probabilities sum to 1
# ---------------------------------------------------------------------------

def test_derived_state_probabilities_sum_to_one_for_various_configs():
    """All derived state probability dicts must sum to exactly 1.0."""
    configs = [
        SetPrismaticEvolutionsConfig,
        SetBlackBoltConfig,
        SetWhiteFlareConfig,
    ]
    for cfg in configs:
        model = resolve_pack_state_model(cfg)
        total = sum(model["state_probabilities"].values())
        assert pytest.approx(1.0, abs=1e-8) == total, (
            f"{cfg.__name__} state probabilities sum to {total}"
        )


# ---------------------------------------------------------------------------
# Requirement 3: Multiple combinations collapsing into the same state are summed
# ---------------------------------------------------------------------------

def test_exclusive_hit_in_reverse_2_collapses_all_rare_combinations_into_one_state():
    """Rule 1: any combination with SIR in reverse_2 collapses to sir_only.

    P(sir_only) must equal P(SIR in slot_2) × 1 × 1, because EVERY raw
    combination (rare_out, r1_out, SIR) collapses to (rare, reg, SIR) via Rule 1.
    """
    p_sir_slot2 = 0.04

    class _Config:
        ERA = "Scarlet and Violet"
        RARE_SLOT_PROBABILITY = {
            "rare": 0.75, "double rare": 0.15, "ultra rare": 0.10,
        }
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {
                "poke ball pattern": 0.20,
                "regular reverse": 0.80,
            },
            "slot_2": {
                "special illustration rare": p_sir_slot2,
                "regular reverse": 1.0 - p_sir_slot2,
            },
        }

    model = resolve_pack_state_model(_Config)
    # Every combination with SIR in slot_2 collapses to sir_only (Rule 1 fires)
    # regardless of what is in the rare slot or slot_1
    assert pytest.approx(p_sir_slot2, abs=1e-9) == model["state_probabilities"]["sir_only"]


# ---------------------------------------------------------------------------
# Requirement 5 (also 6): Set overrides introduce structure; probability is derived
# ---------------------------------------------------------------------------

def test_prismatic_override_applies_expected_delta():
    """PRE override registers pattern_plus_double_rare; probability is derived from PRE slot data."""
    model = resolve_pack_state_model(SetPrismaticEvolutionsConfig)
    assert "pattern_plus_double_rare" in model["state_outcomes"]
    assert model["state_outcomes"]["pattern_plus_double_rare"]["rare"] == "double rare"
    # Probability is non-zero (PRE's slot_1 has poke ball pattern)
    assert model["state_probabilities"]["pattern_plus_double_rare"] > 0.0


def test_black_bolt_and_white_flare_bwr_in_rare_slot():
    """BB/WF override registers black_white_rare_only state; probability derived from RARE_SLOT_PROBABILITY."""
    black_bolt_model = resolve_pack_state_model(SetBlackBoltConfig)
    white_flare_model = resolve_pack_state_model(SetWhiteFlareConfig)

    assert black_bolt_model["state_outcomes"]["black_white_rare_only"]["rare"] == "black white rare"
    assert white_flare_model["state_outcomes"]["black_white_rare_only"]["rare"] == "black white rare"


# ---------------------------------------------------------------------------
# Requirement 6: BB/WF BWR probability derived from config slot data
# ---------------------------------------------------------------------------

def test_black_bolt_bwr_probability_derived_from_rare_slot_config():
    """black_white_rare_only probability equals P(BWR in rare slot) × P(reg slot_1) × P(reg slot_2)."""
    from backend.constants.tcg.pokemon.scarletAndVioletEra.blackBolt import SetBlackBoltConfig as BB

    model = resolve_pack_state_model(BB)

    p_bwr = BB.RARE_SLOT_PROBABILITY["black white rare"]
    p_s1_reg = BB.REVERSE_SLOT_PROBABILITIES["slot_1"].get("regular reverse", 0.0)
    p_s2_reg = BB.REVERSE_SLOT_PROBABILITIES["slot_2"].get("regular reverse", 0.0)

    # BWR has no exclusive hit → no Rule 1 collapse; (bwr, reg, reg) is the only
    # raw combination that maps to black_white_rare_only
    expected = p_bwr * p_s1_reg * p_s2_reg
    assert pytest.approx(expected, abs=1e-9) == model["state_probabilities"]["black_white_rare_only"]


# ---------------------------------------------------------------------------
# Requirement 7: Prismatic derives pattern / ace-spec states from config probs
# ---------------------------------------------------------------------------

def test_prismatic_derives_ace_spec_and_pattern_states_from_config_probabilities():
    """PRE's pattern and ace-spec states have probabilities driven by slot_1 data."""
    from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import (
        SetPrismaticEvolutionsConfig as PRE,
    )

    model = resolve_pack_state_model(PRE)

    p_bp_slot1  = PRE.REVERSE_SLOT_PROBABILITIES["slot_1"]["poke ball pattern"]
    p_as_slot1  = PRE.REVERSE_SLOT_PROBABILITIES["slot_1"]["ace spec rare"]
    p_rare_rare = PRE.RARE_SLOT_PROBABILITY["rare"]
    p_s2_reg    = PRE.REVERSE_SLOT_PROBABILITIES["slot_2"]["regular reverse"]

    # pattern_plus_rare : (rare, poke_ball, reg) – no coercion needed (1 non-regular)
    expected_pbp_plus_rare = p_rare_rare * p_bp_slot1 * p_s2_reg
    assert pytest.approx(expected_pbp_plus_rare, abs=1e-9) == \
        model["state_probabilities"]["pattern_plus_rare"]

    # ace_spec_plus_rare : (rare, ace_spec, reg)
    expected_as_plus_rare = p_rare_rare * p_as_slot1 * p_s2_reg
    assert pytest.approx(expected_as_plus_rare, abs=1e-9) == \
        model["state_probabilities"]["ace_spec_plus_rare"]


# ---------------------------------------------------------------------------
# Requirement 8: Mega Hyper Rare handled via normal exclusive-hit logic
# ---------------------------------------------------------------------------

def test_mega_era_sets_expose_reverse_1_and_mega_hyper_override_shapes():
    """Overrides register structural shapes for reverse_1 placements."""
    asc = SetAscendedHeroesConfig.get_pack_state_overrides()
    meg = SetMegaEvolutionConfig.get_pack_state_overrides()

    assert asc["state_outcomes"]["mega_hyper_only"]["reverse_1"] == "mega hyper rare"
    assert meg["state_outcomes"]["reverse_1_ultra_plus_rare"]["reverse_1"] == "ultra rare"


def test_mega_hyper_rare_uses_normal_exclusive_hit_behaviour_when_slot_data_present():
    """mega hyper rare in reverse_1 is handled by Rule 1 (exclusive-hit singleton logic)."""
    class _Config:
        ERA = "Scarlet and Violet"
        RARE_SLOT_PROBABILITY = {"rare": 0.90, "double rare": 0.10}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"mega hyper rare": 0.03, "regular reverse": 0.97},
            "slot_2": {"regular reverse": 1.0},
        }

        @staticmethod
        def get_pack_state_overrides():
            return {
                "state_outcomes": {
                    "mega_hyper_only": {
                        "rare":      "rare",
                        "reverse_1": "mega hyper rare",
                        "reverse_2": "regular reverse",
                    }
                },
                "constraints": {
                    "exclusive_hits": {"mega hyper rare"},
                },
            }

    model = resolve_pack_state_model(_Config)

    # (double_rare, mega_hyper, reg) → Rule 1: exclusive in r1 → keep r1,
    # set rare="rare", r2=reg → (rare, mega_hyper, reg) = mega_hyper_only
    # So p(mega_hyper_only) = p(mega_hyper in slot_1) × 1 × 1 = 0.03
    assert pytest.approx(0.03, abs=1e-9) == model["state_probabilities"]["mega_hyper_only"]
    # No separate engine branches – it is just another exclusive hit state
    assert model["state_outcomes"]["mega_hyper_only"] == {
        "rare": "rare", "reverse_1": "mega hyper rare", "reverse_2": "regular reverse"
    }


# ---------------------------------------------------------------------------
# Requirement 5 + 9: New state sampled correctly; no prob override needed
# ---------------------------------------------------------------------------

def test_override_state_with_unique_rare_rarity_is_sampled():
    """A new state registered by override is sampled when its combination is 100% probable."""
    class _ForcedConfig:
        ERA = "Scarlet and Violet"
        # 100% custom rare → every pack is custom_only
        RARE_SLOT_PROBABILITY = {"custom rare": 1.0}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"regular reverse": 1.0},
            "slot_2": {"regular reverse": 1.0},
        }

        @staticmethod
        def get_pack_state_overrides():
            return {
                "state_outcomes": {
                    "custom_only": {
                        "rare":      "custom rare",
                        "reverse_1": "regular reverse",
                        "reverse_2": "regular reverse",
                    }
                },
            }

    sampled = sample_pack_state(_ForcedConfig, rng=np.random.default_rng(1))
    assert sampled["state"] == "custom_only"


# ---------------------------------------------------------------------------
# Requirement 9 + 11: Override constraints validated with derived probabilities
# ---------------------------------------------------------------------------

def test_override_constraints_and_states_validate_cleanly(pools):
    """A config with mega_hyper_only override and slot data for that rarity validates."""
    class _Config:
        ERA = "Scarlet and Violet"
        # Slot_1 carries mega hyper rare so the state has non-zero derived probability
        RARE_SLOT_PROBABILITY = {"rare": 0.90, "double rare": 0.10}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"mega hyper rare": 0.02, "regular reverse": 0.98},
            "slot_2": {"regular reverse": 1.0},
        }

        @staticmethod
        def get_pack_state_overrides():
            return {
                "state_outcomes": {
                    "mega_hyper_only": {
                        "rare":      "rare",
                        "reverse_1": "mega hyper rare",
                        "reverse_2": "regular reverse",
                    }
                },
                "constraints": {
                    "exclusive_hits": {"mega hyper rare"},
                },
            }

    model = resolve_pack_state_model(_Config)
    assert "mega_hyper_only" in model["state_outcomes"]
    # Full validation passes (probabilities, slot constraints, pool membership)
    validate_pack_state_model(_Config, pools)



def test_derivation_and_simulation_share_coercion_semantics():
    class _Config:
        ERA = "Scarlet and Violet"
        # Single raw combination that requires exclusive coercion.
        RARE_SLOT_PROBABILITY = {"double rare": 1.0}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"ace spec rare": 1.0},
            "slot_2": {"hyper rare": 1.0},
        }

    model = resolve_pack_state_model(_Config)
    assert set(model["state_probabilities"].keys()) == {"hyper_only"}

    # Derivation says the resolved shape is hyper_only.
    derived_shape = model["state_outcomes"]["hyper_only"]
    assert derived_shape == {
        "rare": "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "hyper rare",
    }

    # Simulation path must resolve the same shape for the same state.
    resolved = resolve_slot_outcomes_from_state({"state": "hyper_only"}, _Config)
    assert resolved == derived_shape



def test_debug_export_uses_resolved_override_state(pools):
    class ForcedOverride:
        ERA = "Scarlet and Violet"
        SLOTS_PER_RARITY = {"common": 4, "uncommon": 3, "reverse": 2, "rare": 1}
        GOD_PACK_CONFIG = {"enabled": False, "pull_rate": 0.0, "strategy": {}}
        DEMI_GOD_PACK_CONFIG = {"enabled": False, "pull_rate": 0.0, "strategy": {}}
        RARE_SLOT_PROBABILITY = {"custom rare": 1.0}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"regular reverse": 1.0},
            "slot_2": {"regular reverse": 1.0},
        }

        @staticmethod
        def get_pack_state_overrides():
            return {
                "state_outcomes": {
                    "forced_state": {
                        "rare": "custom rare",
                        "reverse_1": "regular reverse",
                        "reverse_2": "regular reverse",
                    }
                },
            }

    rarity_counts = defaultdict(int)
    rarity_values = defaultdict(float)
    logs = []

    fn = make_simulate_pack_fn_v2(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slots_per_rarity=ForcedOverride.SLOTS_PER_RARITY,
        config=ForcedOverride,
        df=pools["df"],
        rarity_pull_counts=rarity_counts,
        rarity_value_totals=rarity_values,
        pack_logs=logs,
        rng=np.random.default_rng(3),
    )

    sim = run_simulation_v2(lambda: fn(return_pack_data=True), rarity_counts, rarity_values, n=5, export_debug_df=True)
    assert len(sim["debug_df"]) == 5
    assert set(sim["debug_df"]["entry_path"]) == {"normal"}

    resolved_model = resolve_pack_state_model(ForcedOverride)
    observed_states = set(sim["debug_df"]["pack_state"])
    assert "forced_state" in resolved_model["state_outcomes"]
    for state_name, slot_outcomes in zip(sim["debug_df"]["pack_state"], sim["debug_df"]["slot_outcomes"]):
        assert state_name in resolved_model["state_outcomes"]
        assert slot_outcomes == resolved_model["state_outcomes"][state_name]
    assert observed_states.issubset(set(resolved_model["state_outcomes"].keys()))


def test_sv_base_defaults_are_unchanged_without_set_override():
    class NoOverride:
        ERA = "Scarlet and Violet"

    base_model = build_scarlet_and_violet_pack_state_model(NoOverride)
    assert "pattern_plus_double_rare" not in base_model["state_outcomes"]


def test_duplicate_state_shape_in_era_registry_fails_loudly(monkeypatch):
    duplicate_registry = {
        **sv_model_module.SV_DEFAULT_STATE_OUTCOMES,
        "baseline_alias": {
            "rare": "rare",
            "reverse_1": "regular reverse",
            "reverse_2": "regular reverse",
        },
    }
    monkeypatch.setattr(sv_model_module, "SV_DEFAULT_STATE_OUTCOMES", duplicate_registry)

    class NoOverride:
        ERA = "Scarlet and Violet"

    with pytest.raises(ValueError, match="Duplicate state-outcome shape"):
        build_scarlet_and_violet_pack_state_model(NoOverride)
