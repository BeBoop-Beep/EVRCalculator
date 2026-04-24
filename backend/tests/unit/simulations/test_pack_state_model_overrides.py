from collections import defaultdict

import numpy as np
import pandas as pd
import pytest

from backend.constants.tcg.pokemon.megaEvolutionEra.ascendedHeroes import SetAscendedHeroesConfig
from backend.constants.tcg.pokemon.megaEvolutionEra.megaEvolution import SetMegaEvolutionConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.blackBolt import SetBlackBoltConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.paldeanFates import SetPaldeanFatesConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.whiteFlare import SetWhiteFlareConfig
from backend.simulations.monteCarloSimV2 import (
    make_simulate_pack_fn_v2,
    resolve_slot_outcomes_from_state,
    run_simulation_v2,
    sample_pack_state,
    validate_pack_state_model,
)
from backend.simulations.utils.packStateModels.packStateCoercion import coerce_slot_outcomes
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
            "Reverse Variant Price ($)": [0.35, 0.40, 0.28, 0.32],
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


@pytest.mark.parametrize(
    "cfg",
    [SetPrismaticEvolutionsConfig, SetBlackBoltConfig, SetWhiteFlareConfig],
)
def test_pokeball_pattern_token_remains_reachable_in_state_outcomes(cfg):
    model = resolve_pack_state_model(cfg)
    assert any(
        "poke ball pattern" in slot_outcomes.values()
        for slot_outcomes in model["state_outcomes"].values()
    )


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

def test_hyper_hit_in_reverse_2_collapses_all_rare_combinations_into_one_state():
    """Rule 1: any combination with hyper rare in reverse_2 collapses to hyper_only.

    P(hyper_only) must equal P(hyper rare in slot_2) × 1 × 1, because EVERY raw
    combination (rare_out, r1_out, hyper rare) collapses to (rare, reg, hyper rare) via Rule 1.
    """
    p_hyper_slot2 = 0.04

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
                "hyper rare": p_hyper_slot2,
                "regular reverse": 1.0 - p_hyper_slot2,
            },
        }

    model = resolve_pack_state_model(_Config)
    # Every combination with hyper rare in slot_2 collapses to hyper_only (Rule 1 fires)
    # regardless of what is in the rare slot or slot_1
    assert pytest.approx(p_hyper_slot2, abs=1e-9) == model["state_probabilities"]["hyper_only"]


@pytest.mark.parametrize(
    "raw_outcomes",
    [
        {"rare": "double rare", "reverse_1": "regular reverse", "reverse_2": "special illustration rare"},
        {"rare": "rare", "reverse_1": "ace spec rare", "reverse_2": "special illustration rare"},
        {"rare": "ultra rare", "reverse_1": "regular reverse", "reverse_2": "illustration rare"},
        {"rare": "rare", "reverse_1": "shiny rare", "reverse_2": "special illustration rare"},
        {"rare": "rare", "reverse_1": "shiny rare", "reverse_2": "illustration rare"},
    ],
    ids=[
        "sir_plus_double_rare_allowed",
        "sir_plus_ace_spec_allowed",
        "ir_plus_ultra_rare_allowed",
        "shiny_rare_plus_sir_allowed",
        "shiny_rare_plus_ir_allowed",
    ],
)
def test_sv_conditional_rules_allow_expected_hit_combinations(raw_outcomes):
    constraints = resolve_pack_state_model(SetPaldeanFatesConfig)["constraints"]
    assert coerce_slot_outcomes(raw_outcomes, constraints) == raw_outcomes


@pytest.mark.parametrize(
    "raw_outcomes, expected",
    [
        (
            {"rare": "ultra rare", "reverse_1": "regular reverse", "reverse_2": "special illustration rare"},
            {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "special illustration rare"},
        ),
        (
            {"rare": "rare", "reverse_1": "illustration rare", "reverse_2": "hyper rare"},
            {"rare": "rare", "reverse_1": "regular reverse", "reverse_2": "hyper rare"},
        ),
        (
            {"rare": "hyper rare", "reverse_1": "regular reverse", "reverse_2": "illustration rare"},
            {"rare": "hyper rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"},
        ),
        (
            {"rare": "hyper rare", "reverse_1": "regular reverse", "reverse_2": "special illustration rare"},
            {"rare": "hyper rare", "reverse_1": "regular reverse", "reverse_2": "regular reverse"},
        ),
    ],
    ids=[
        "sir_plus_ultra_rare_forbidden",
        "ir_plus_hyper_rare_forbidden",
        "hyper_rare_plus_ir_forbidden",
        "hyper_rare_plus_sir_forbidden",
    ],
)
def test_sv_conditional_rules_forbid_targeted_hit_combinations(raw_outcomes, expected):
    constraints = resolve_pack_state_model(SetPaldeanFatesConfig)["constraints"]
    assert coerce_slot_outcomes(raw_outcomes, constraints) == expected


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

@pytest.mark.parametrize(
    "cfg",
    [SetBlackBoltConfig, SetWhiteFlareConfig],
    ids=["black_bolt", "white_flare"],
)
def test_bwr_named_state_probability_includes_forbidden_reverse2_demotions(cfg):
    """BB/WF BWR is a singleton-exclusive hit: any reverse outcomes collapse to baseline."""
    model = resolve_pack_state_model(cfg)
    p_bwr   = cfg.RARE_SLOT_PROBABILITY["black white rare"]
    expected = p_bwr
    assert pytest.approx(expected, abs=1e-9) == model["state_probabilities"]["black_white_rare_only"]


@pytest.mark.parametrize(
    "cfg",
    [SetWhiteFlareConfig],
    ids=["white_flare"],
)
def test_illustration_rare_and_ultra_rare_coexistence_is_legal(cfg):
    """ultra rare + illustration rare is a reachable legal state for White Flare.

    # Confirmed legal state per SV era pack-opening review: ultra rare + illustration rare can coexist.
    """
    model = resolve_pack_state_model(cfg)

    has_legal_combo = any(
        slot_outcomes["rare"] == "ultra rare"
        and slot_outcomes["reverse_2"] == "illustration rare"
        and model["state_probabilities"].get(state_name, 0.0) > 0.0
        for state_name, slot_outcomes in model["state_outcomes"].items()
    )

    assert has_legal_combo, (
        "Expected at least one state with rare='ultra rare' and reverse_2='illustration rare' "
        "but none was found in the White Flare model."
    )


@pytest.mark.parametrize(
    "cfg",
    [SetBlackBoltConfig, SetWhiteFlareConfig],
    ids=["black_bolt", "white_flare"],
)
@pytest.mark.parametrize(
    "forbidden_reverse_2",
    ["illustration rare", "special illustration rare"],
    ids=["ir", "sir"],
)
def test_bwr_conditional_exclusion_blocks_forbidden_reverse_2_outcomes(cfg, forbidden_reverse_2):
    """Guardrail: BB/WF must not resolve to BWR with forbidden reverse_2 rarities."""
    model = resolve_pack_state_model(cfg)

    has_forbidden_resolved_state = any(
        slot_outcomes["rare"] == "black white rare"
        and slot_outcomes["reverse_2"] == forbidden_reverse_2
        and model["state_probabilities"].get(state_name, 0.0) > 0.0
        for state_name, slot_outcomes in model["state_outcomes"].items()
    )

    assert not has_forbidden_resolved_state


@pytest.mark.parametrize(
    "cfg",
    [SetBlackBoltConfig, SetWhiteFlareConfig],
    ids=["black_bolt", "white_flare"],
)
def test_bwr_singleton_collapses_reverse_1_non_regular_outcomes(cfg):
    """Guardrail: singleton-exclusive BWR suppresses reverse_1 non-regular outcomes."""
    model = resolve_pack_state_model(cfg)

    has_reachable_bwr_master_ball = any(
        slot_outcomes["rare"] == "black white rare"
        and slot_outcomes["reverse_1"] == "master ball pattern"
        and model["state_probabilities"].get(state_name, 0.0) > 0.0
        for state_name, slot_outcomes in model["state_outcomes"].items()
    )

    assert not has_reachable_bwr_master_ball


@pytest.mark.parametrize(
    "cfg",
    [SetBlackBoltConfig, SetWhiteFlareConfig],
    ids=["black_bolt", "white_flare"],
)
@pytest.mark.parametrize(
    "raw_outcomes",
    [
        {"rare": "black white rare", "reverse_1": "poke ball pattern", "reverse_2": "regular reverse"},
        {"rare": "black white rare", "reverse_1": "regular reverse", "reverse_2": "illustration rare"},
        {"rare": "black white rare", "reverse_1": "master ball pattern", "reverse_2": "special illustration rare"},
    ],
    ids=[
        "bwr_plus_pokeball",
        "bwr_plus_ir",
        "bwr_plus_masterball_plus_sir",
    ],
)
def test_bwr_singleton_coercion_examples_collapse_to_black_white_rare_only(cfg, raw_outcomes):
    constraints = resolve_pack_state_model(cfg)["constraints"]
    expected = {
        "rare": "black white rare",
        "reverse_1": "regular reverse",
        "reverse_2": "regular reverse",
    }
    assert coerce_slot_outcomes(raw_outcomes, constraints) == expected


def test_normal_sv_set_without_singleton_exclusive_hits_is_unchanged():
    constraints = resolve_pack_state_model(SetPaldeanFatesConfig)["constraints"]
    raw_outcomes = {
        "rare": "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "special illustration rare",
    }
    assert coerce_slot_outcomes(raw_outcomes, constraints) == raw_outcomes


@pytest.mark.parametrize(
    "cfg",
    [SetBlackBoltConfig, SetWhiteFlareConfig],
    ids=["black_bolt", "white_flare"],
)
def test_special_illustration_rare_behavior_is_unchanged_for_non_bwr_paths(cfg):
    constraints = resolve_pack_state_model(cfg)["constraints"]
    raw_outcomes = {
        "rare": "ultra rare",
        "reverse_1": "regular reverse",
        "reverse_2": "special illustration rare",
    }
    expected = {
        "rare": "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "special illustration rare",
    }
    assert coerce_slot_outcomes(raw_outcomes, constraints) == expected


@pytest.mark.parametrize(
    "cfg",
    [SetBlackBoltConfig, SetWhiteFlareConfig],
    ids=["black_bolt", "white_flare"],
)
def test_non_bwr_premium_reverse2_state_remains_reachable(cfg):
    """Guardrail: constraints should not eliminate all premium reverse_2 outcomes."""
    model = resolve_pack_state_model(cfg)
    premium_reverse_2 = {"illustration rare", "special illustration rare"}

    has_reachable_non_bwr_premium = any(
        slot_outcomes["rare"] != "black white rare"
        and slot_outcomes["reverse_2"] in premium_reverse_2
        and model["state_probabilities"].get(state_name, 0.0) > 0.0
        for state_name, slot_outcomes in model["state_outcomes"].items()
    )

    assert has_reachable_non_bwr_premium


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

def test_mega_era_sets_expose_mega_hyper_and_reverse_1_ultra_override_shapes():
    """Overrides register structural shapes for mega-hyper and reverse_1 ultra placements."""
    asc = SetAscendedHeroesConfig.get_pack_state_overrides()
    meg = SetMegaEvolutionConfig.get_pack_state_overrides()

    assert asc["state_outcomes"]["mega_hyper_only"]["reverse_2"] == "mega hyper rare"
    assert meg["state_outcomes"]["reverse_1_ultra_plus_rare"]["reverse_1"] == "ultra rare"


def test_ascended_heroes_disallows_illegal_normal_pack_reverse_pairings():
    model = build_scarlet_and_violet_pack_state_model(SetAscendedHeroesConfig)

    for state_name, slot_outcomes in model["state_outcomes"].items():
        prob = model["state_probabilities"].get(state_name, 0.0)
        if prob <= 0.0:
            continue

        r1 = slot_outcomes["reverse_1"]
        r2 = slot_outcomes["reverse_2"]
        rare = slot_outcomes["rare"]

        assert not (r1 == "illustration rare" and r2 == "illustration rare")
        assert not (r1 == "special illustration rare" and r2 == "special illustration rare")
        assert not ({r1, r2} == {"illustration rare", "special illustration rare"})
        assert not (rare == "mega attack rare" and "special illustration rare" in {r1, r2})


def test_ascended_heroes_keeps_legal_mega_attack_plus_ir_and_singleton_mega_hyper():
    model = build_scarlet_and_violet_pack_state_model(SetAscendedHeroesConfig)

    has_mega_attack_plus_ir = False
    for state_name, slot_outcomes in model["state_outcomes"].items():
        prob = model["state_probabilities"].get(state_name, 0.0)
        if prob <= 0.0:
            continue

        rare = slot_outcomes["rare"]
        r1 = slot_outcomes["reverse_1"]
        r2 = slot_outcomes["reverse_2"]

        if rare == "mega attack rare" and "illustration rare" in {r1, r2}:
            has_mega_attack_plus_ir = True

    assert has_mega_attack_plus_ir
    assert "mega_hyper_only" in model["state_outcomes"]
    assert model["state_outcomes"]["mega_hyper_only"] == {
        "rare": "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "mega hyper rare",
    }
    assert model["state_probabilities"]["mega_hyper_only"] > 0.0


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
    custom_hit = pd.DataFrame(
        {
            "Card Name": ["Custom Rare A"],
            "Price ($)": [15.0],
            "Rarity": ["custom rare"],
        }
    )
    hit_cards = pd.concat([pools["hit"], custom_hit], ignore_index=True)
    df = pd.concat([pools["df"], custom_hit], ignore_index=True)

    fn = make_simulate_pack_fn_v2(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=hit_cards,
        reverse_pool=pools["reverse"],
        slots_per_rarity=ForcedOverride.SLOTS_PER_RARITY,
        config=ForcedOverride,
        df=df,
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


def test_no_conditional_exclusions_key_keeps_expected_baseline_resolution():
    class NoConditionalRules:
        ERA = "Scarlet and Violet"
        RARE_SLOT_PROBABILITY = {"rare": 1.0}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"regular reverse": 1.0},
            "slot_2": {"regular reverse": 0.75, "illustration rare": 0.25},
        }

    model = resolve_pack_state_model(NoConditionalRules)

    assert model["state_probabilities"] == {
        "baseline": 0.75,
        "ir_plus_rare": 0.25,
    }
    assert model["state_outcomes"]["baseline"] == {
        "rare": "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "regular reverse",
    }
    assert model["state_outcomes"]["ir_plus_rare"] == {
        "rare": "rare",
        "reverse_1": "regular reverse",
        "reverse_2": "illustration rare",
    }


def test_empty_conditional_exclusions_adds_no_delta_to_key_omitted_model():
    class OmittedConditionalRules:
        ERA = "Scarlet and Violet"
        RARE_SLOT_PROBABILITY = {"rare": 0.6, "double rare": 0.4}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"regular reverse": 1.0},
            "slot_2": {"regular reverse": 0.8, "illustration rare": 0.2},
        }

    class EmptyConditionalRules(OmittedConditionalRules):
        @staticmethod
        def get_pack_state_overrides():
            return {
                "constraints": {
                    "conditional_slot_exclusions": [],
                },
            }

    omitted_model = resolve_pack_state_model(OmittedConditionalRules)
    empty_model = resolve_pack_state_model(EmptyConditionalRules)

    assert empty_model["state_probabilities"] == omitted_model["state_probabilities"]
    assert empty_model["state_outcomes"] == omitted_model["state_outcomes"]
    omitted_constraints = {
        k: v
        for k, v in omitted_model["constraints"].items()
        if k != "conditional_slot_exclusions"
    }
    empty_constraints = {
        k: v
        for k, v in empty_model["constraints"].items()
        if k != "conditional_slot_exclusions"
    }
    assert empty_constraints == omitted_constraints
    assert (
        empty_model["constraints"].get("conditional_slot_exclusions", [])
        == omitted_model["constraints"].get("conditional_slot_exclusions", [])
    )


def test_prismatic_has_no_conditional_exclusions_and_named_state_behaviour_unchanged():
    model = resolve_pack_state_model(SetPrismaticEvolutionsConfig)

    assert "conditional_slot_exclusions" in model["constraints"]
    assert model["state_outcomes"]["pattern_plus_double_rare"] == {
        "rare": "double rare",
        "reverse_1": "poke ball pattern",
        "reverse_2": "regular reverse",
    }
    assert model["state_outcomes"]["ace_spec_plus_double_rare"] == {
        "rare": "double rare",
        "reverse_1": "ace spec rare",
        "reverse_2": "regular reverse",
    }
    assert model["state_probabilities"]["pattern_plus_double_rare"] > 0.0
    assert model["state_probabilities"]["ace_spec_plus_double_rare"] > 0.0


def test_exclusive_hits_semantics_unchanged_without_conditional_rules_present():
    class ExclusiveOnlyNoConditional:
        ERA = "Scarlet and Violet"
        RARE_SLOT_PROBABILITY = {"double rare": 1.0}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"ace spec rare": 1.0},
            "slot_2": {"hyper rare": 1.0},
        }

    model = resolve_pack_state_model(ExclusiveOnlyNoConditional)
    assert set(model["state_probabilities"].keys()) == {"hyper_only"}
    assert pytest.approx(1.0, abs=1e-12) == model["state_probabilities"]["hyper_only"]


def test_sir_combinations_validate_when_allowed_by_rules(pools):
    """Validation must not reject SIR + double rare / ace spec combinations."""
    class ValidSIRConfigs:
        ERA = "Scarlet and Violet"
        # Allow SIR + double rare
        RARE_SLOT_PROBABILITY = {"rare": 0.5, "double rare": 0.5}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"regular reverse": 1.0},
            "slot_2": {"special illustration rare": 1.0},
        }

    # This should NOT raise ValidationError
    validate_pack_state_model(ValidSIRConfigs, pools)


def test_sir_plus_ace_spec_validates(pools):
    """SIR + ace spec should be valid (non-blocking bonus hit)."""
    class SIRPlusAceSpec:
        ERA = "Scarlet and Violet"
        RARE_SLOT_PROBABILITY = {"rare": 1.0}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"ace spec rare": 1.0},
            "slot_2": {"special illustration rare": 1.0},
        }

    # This should NOT raise ValidationError
    validate_pack_state_model(SIRPlusAceSpec, pools)


def test_still_blocked_combos_fail_or_coerce(pools):
    """Ensure SIR + ultra rare still coerces/blocks as per rules."""
    class SIRPlusUltra:
        ERA = "Scarlet and Violet"
        RARE_SLOT_PROBABILITY = {"ultra rare": 1.0}
        REVERSE_SLOT_PROBABILITIES = {
            "slot_1": {"regular reverse": 1.0},
            "slot_2": {"special illustration rare": 1.0},
        }

    # Coercion should demote ultra rare to rare (per conditional rules)
    model = resolve_pack_state_model(SIRPlusUltra)
    resolved_state = model["state_outcomes"]["sir_only"]
    # After coercion, rare slot should be "rare" (demoted from ultra rare)
    assert resolved_state["rare"] == "rare"
    assert resolved_state["reverse_2"] == "special illustration rare"
    # Validation should pass (coerced state is valid)
    validate_pack_state_model(SIRPlusUltra, pools)
