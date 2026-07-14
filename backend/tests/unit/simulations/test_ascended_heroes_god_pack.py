"""Ascended Heroes God Pack path-selection tests.

Audit context: Ascended Heroes configures a 1/2000 God Pack rate. A one-off
observation of 464 God Packs in 1,000,000 simulated packs (expected 500, sd
~22.35 -> ~1.6 sigma low) is plausible random variation, NOT a defect, so these
tests deliberately avoid asserting an exact God Pack count. They instead pin the
things that would actually be bugs:

  A. The configured probability resolves to exactly 1/2000 (demi disabled).
  B. The runtime path gate fires on a single ``rng.random() < pull_rate`` draw
     with no double application, so a value just below the boundary is a God
     Pack and a value just above it is a Normal pack.
  C. Pack-path counts are mutually exclusive and conserve: normal + god == n.
  D. A fixed-seed statistical sanity band (wide, ~6 sigma) confirms the realized
     rate is in the right neighborhood and that God Packs are reachable.
"""

from collections import defaultdict

import numpy as np
import pandas as pd
import pytest

from backend.constants.tcg.pokemon.megaEvolutionEra.ascendedHeroes import (
    SetAscendedHeroesConfig,
)
from backend.simulations.monteCarloSimV2 import (
    make_simulate_pack_fn_v2,
    run_simulation_v2,
)


class _AscendedLikeConfig:
    """Minimal SV-shaped config that keeps Ascended Heroes' 1/2000 God Pack rate
    but uses a cheap single-rarity random God strategy so the pools (and per-pack
    sampling) stay small. Path SELECTION and COUNTING are independent of the God
    Pack's internal card composition, which is covered elsewhere."""

    USE_MONTE_CARLO_V2 = True
    ERA = "Scarlet and Violet"
    SLOTS_PER_RARITY = {"common": 4, "uncommon": 3, "reverse": 2, "rare": 1}

    RARE_SLOT_PROBABILITY = {"double rare": 0.15, "ultra rare": 0.10, "rare": 0.75}
    REVERSE_SLOT_PROBABILITIES = {
        "slot_1": {"regular reverse": 1.0},
        "slot_2": {"regular reverse": 1.0},
    }

    # Baseline-only normal packs keep the hot path cheap (base rare + reverse
    # pools only) so these path-selection tests don't need a full hit pool.
    PACK_STATE_MODEL = {
        "state_probabilities": {"baseline": 1.0},
        "state_outcomes": {
            "baseline": {
                "rare": "rare",
                "reverse_1": "regular reverse",
                "reverse_2": "regular reverse",
            }
        },
    }

    GOD_PACK_CONFIG = {
        "enabled": True,
        "pull_rate": 1 / 2000,
        "strategy": {
            "type": "random",
            "rules": {
                "rarities": {
                    "special illustration rare": {"count": 1, "replacement": "with_replacement"},
                }
            },
        },
    }
    DEMI_GOD_PACK_CONFIG = {"enabled": False}


class ScriptedRng:
    """``np.random.Generator``-like wrapper that returns scripted values from
    ``.random()`` (the god/demi path gates) and delegates every other method to a
    real ``default_rng`` so downstream card sampling still works deterministically.
    """

    def __init__(self, random_values, seed=0):
        self._randoms = list(random_values)
        self._rng = np.random.default_rng(seed)

    def random(self, *args, **kwargs):
        if self._randoms:
            return self._randoms.pop(0)
        return self._rng.random(*args, **kwargs)

    def __getattr__(self, name):
        # Only reached for attributes not found on the instance/class, i.e.
        # everything except ``random`` -> forward to the real generator.
        return getattr(self._rng, name)


def _build_pools():
    common = pd.DataFrame(
        {
            "Card Name": [f"Common {i}" for i in range(5)],
            "Price ($)": [0.10] * 5,
            "Rarity": ["common"] * 5,
        }
    )
    uncommon = pd.DataFrame(
        {
            "Card Name": [f"Uncommon {i}" for i in range(4)],
            "Price ($)": [0.20] * 4,
            "Rarity": ["uncommon"] * 4,
        }
    )
    rare = pd.DataFrame(
        {"Card Name": ["Rare A", "Rare B"], "Price ($)": [0.75, 0.95], "Rarity": ["rare", "rare"]}
    )
    reverse = pd.DataFrame(
        {"Card Name": ["Reverse A", "Reverse B"], "Reverse Variant Price ($)": [0.35, 0.40]}
    )
    hit = pd.DataFrame(
        {
            "Card Name": ["SIR A", "SIR B"],
            "Price ($)": [30.0, 32.0],
            "Rarity": ["special illustration rare", "special illustration rare"],
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


def _make_fn(config, rng, path_counts=None):
    pools = _build_pools()
    return make_simulate_pack_fn_v2(
        common_cards=pools["common"],
        uncommon_cards=pools["uncommon"],
        rare_cards=pools["rare"],
        hit_cards=pools["hit"],
        reverse_pool=pools["reverse"],
        slots_per_rarity=config.SLOTS_PER_RARITY,
        config=config,
        df=pools["df"],
        rarity_pull_counts=defaultdict(int),
        rarity_value_totals=defaultdict(float),
        pack_logs=None,
        rng=rng,
        path_counts=path_counts,
    )


# ---------------------------------------------------------------------------
# A. Configuration test
# ---------------------------------------------------------------------------
def test_ascended_heroes_god_pack_probability_resolves_to_one_in_two_thousand():
    god_cfg = SetAscendedHeroesConfig.GOD_PACK_CONFIG
    assert god_cfg["enabled"] is True
    assert god_cfg["pull_rate"] == 1 / 2000
    assert god_cfg["pull_rate"] == pytest.approx(0.0005)
    # Demi-God is not part of Ascended Heroes, so it must never contribute a path.
    assert SetAscendedHeroesConfig.DEMI_GOD_PACK_CONFIG.get("enabled", False) is False


# ---------------------------------------------------------------------------
# B. Boundary / mocked-RNG test
# ---------------------------------------------------------------------------
def test_path_gate_selects_god_just_below_and_normal_just_above_boundary():
    # A single random draw just BELOW 1/2000 must enter the God path...
    below = ScriptedRng([0.0004])
    value, pack_data = _make_fn(_AscendedLikeConfig, below)(return_pack_data=True)
    assert pack_data["entry_path"] == "god"
    assert pack_data["state"] == "god_pack"
    assert value > 0  # God Pack is reachable and produces a nonzero value

    # ...and a single draw just ABOVE 1/2000 must fall through to a Normal pack.
    above = ScriptedRng([0.0006])
    _, normal_data = _make_fn(_AscendedLikeConfig, above)(return_pack_data=True)
    assert normal_data["entry_path"] == "normal"
    assert normal_data["state"] != "god_pack"


def test_disabled_god_pack_never_selects_god_even_when_draw_is_below_rate():
    class Disabled(_AscendedLikeConfig):
        GOD_PACK_CONFIG = {"enabled": False, "pull_rate": 1 / 2000, "strategy": {}}

    # Even a draw of 0.0 must not enter the God path when the config is disabled,
    # proving the gate honors ``enabled`` and does not apply the rate twice.
    rng = ScriptedRng([0.0])
    _, pack_data = _make_fn(Disabled, rng)(return_pack_data=True)
    assert pack_data["entry_path"] == "normal"


# ---------------------------------------------------------------------------
# C. Conservation test
# ---------------------------------------------------------------------------
def test_pack_path_counts_are_mutually_exclusive_and_conserve():
    # Use an inflated God rate so BOTH paths appear in a small run; conservation
    # (normal + god == n, one path per pack) must hold regardless of the rate.
    class HalfGod(_AscendedLikeConfig):
        GOD_PACK_CONFIG = {
            "enabled": True,
            "pull_rate": 0.5,
            "strategy": _AscendedLikeConfig.GOD_PACK_CONFIG["strategy"],
        }

    n = 2000
    path_counts = defaultdict(int)
    fn = _make_fn(HalfGod, np.random.default_rng(7), path_counts=path_counts)
    sim = run_simulation_v2(
        fn,
        defaultdict(int),
        defaultdict(float),
        n=n,
        pack_path_counts=path_counts,
    )

    counts = sim["pack_path_counts"]
    assert counts.get("normal", 0) + counts.get("god", 0) == n
    assert counts.get("demi_god", 0) == 0  # disabled -> never selected
    assert counts.get("god", 0) > 0 and counts.get("normal", 0) > 0  # both reachable


# ---------------------------------------------------------------------------
# D. Fixed-seed statistical sanity test (wide, non-flaky band)
# ---------------------------------------------------------------------------
def test_fixed_seed_god_rate_lands_in_wide_sanity_band_at_one_in_two_thousand():
    """At p = 1/2000 with n = 60,000 the expected God count is 30 (sd ~5.48).

    The seed is fixed so the run is deterministic; the assertion is a wide ~6
    sigma diagnostic band (roughly 1..63) plus a reachability check, NOT an
    exact-count assertion. This catches a broken rate (e.g. 0, or 10x/0.1x) while
    tolerating ordinary Monte Carlo variance.
    """
    n = 60_000
    p = 1 / 2000
    expected = n * p  # 30
    sd = (n * p * (1 - p)) ** 0.5  # ~5.48
    lower = max(1, int(expected - 6 * sd))  # reachability + very loose floor
    upper = int(expected + 6 * sd) + 1  # ~63

    path_counts = defaultdict(int)
    fn = _make_fn(_AscendedLikeConfig, np.random.default_rng(20240710), path_counts=path_counts)
    sim = run_simulation_v2(
        fn,
        defaultdict(int),
        defaultdict(float),
        n=n,
        pack_path_counts=path_counts,
    )

    god = sim["pack_path_counts"].get("god", 0)
    normal = sim["pack_path_counts"].get("normal", 0)
    assert god + normal == n
    assert lower <= god <= upper, (
        f"God count {god} outside wide sanity band [{lower}, {upper}] "
        f"(expected ~{expected:.0f}, sd ~{sd:.2f}) at p=1/2000, n={n}"
    )
