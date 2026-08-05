"""`--all-supported` cohort selection.

THE BUG THIS COVERS
-------------------
The parser defined `--all-supported`, but `main` called
`load_cohort(set_ids=args.set_id)` and never passed the flag. It was a no-op:
the run loaded all 34 published targets, the 12 Sword & Shield-era sets that are
deliberately unsupported for opening simulation had no Financial RIP V3, and
`--strict` blocked on them - reporting an intentional scope boundary as a data
defect.

THE PROPERTY THAT MATTERS MOST
------------------------------
Support is DECLARED, never inferred from whether a score happens to exist.
Filtering on `financialRipV3 is not None` would have produced the same 22 sets
today and would have been silently wrong: a supported set whose simulation
genuinely failed would drop out of the cohort instead of failing the gate. The
gate exists to catch exactly that, so several tests below pin the distinction
rather than only the count.
"""

from __future__ import annotations

import argparse
import ast
import inspect
from unittest.mock import patch

import pytest

from backend.scripts import build_rip_v3_collector_appeal_validation as script

# The 12 Sword & Shield-era sets intentionally unsupported for opening
# simulation. Listed HERE, in a test, as the expected outcome - never in the
# script, which must resolve support from the authoritative service.
UNSUPPORTED_SETS = (
    "Astral Radiance", "Battle Styles", "Brilliant Stars", "Chilling Reign",
    "Darkness Ablaze", "Evolving Skies", "Fusion Strike", "Lost Origin",
    "Rebel Clash", "Silver Tempest", "Sword & Shield", "Vivid Voltage",
)

SUPPORTED_KEYS = (
    "ascendedHeroes", "blackBolt", "chaosRising", "destinedRivals",
    "journeyTogether", "megaEvolution", "obsidianFlames", "paldeaEvolved",
    "paldeanFates", "paradoxRift", "perfectOrder", "phantasmalFlames",
    "pitchBlack", "prismaticEvolutions", "scarletAndViolet151",
    "scarletAndVioletBase", "shroudedFable", "stellarCrown", "surgingSparks",
    "temporalForces", "twilightMasquerade", "whiteFlare",
)

UNSUPPORTED_KEYS = (
    "astralRadiance", "battleStyles", "brilliantStars", "chillingReign",
    "darknessAblaze", "evolvingSkies", "fusionStrike", "lostOrigin",
    "rebelClash", "silverTempest", "swordAndShield", "vividVoltage",
)


def _target(name: str, key: str, *, v3_score=61.0):
    """A published target, shaped as `build_rows` consumes it."""
    financial = (
        {"score": v3_score, "status": "ready", "components": {}}
        if v3_score is not None
        else {}
    )
    return {
        "target_id": f"id-{key}",
        "name": name,
        "canonical_key": key,
        "financialRipV3": financial,
        "openingExperience": {
            "collectorAppeal": {"score": 80.0, "inputs": {"rosterDesirability": 0.85}},
            "desirableOutcomeFrequency": {"rawValue": 0.14, "status": "available"},
            "dualPathDepth": {"rawValue": 0.30},
            "legacyCollectorAppealCA7": {"score": 79.0},
            "chaseAppeal": {"score": 40.0, "eliteScarcity": 0.5},
            "coverage": {"reasons": []},
        },
    }


def _all_34_targets():
    supported = [_target(k, k) for k in SUPPORTED_KEYS]
    # Unsupported sets have no V3 and no pull model - exactly production's state.
    unsupported = [
        {
            "target_id": f"id-{key}",
            "name": name,
            "canonical_key": key,
            "financialRipV3": {},
            "openingExperience": {
                "collectorAppeal": {"inputs": {}},
                "desirableOutcomeFrequency": {"status": "unavailable"},
                "dualPathDepth": {},
                "coverage": {"reasons": ["dual_path_depth_unavailable_no_pull_model"]},
            },
        }
        for name, key in zip(UNSUPPORTED_SETS, UNSUPPORTED_KEYS)
    ]
    return supported + unsupported


def _load(**kwargs):
    """Run load_cohort against a stubbed targets payload and support list."""
    payload = {"targets": kwargs.pop("targets", _all_34_targets())}
    supported = kwargs.pop("supported", SUPPORTED_KEYS)

    fake_service = type("S", (), {"get_rip_statistics_targets_payload": staticmethod(lambda: payload)})
    fake_gate = type("G", (), {"supported_opening_set_keys": staticmethod(lambda: tuple(supported))})

    with patch.dict(
        "sys.modules",
        {
            "backend.db.services.explore_rip_statistics_service": fake_service,
            "backend.db.services.opening_simulation_gate": fake_gate,
        },
    ):
        return script.load_cohort(**kwargs)


# ---------------------------------------------------------------------------
# The regression
# ---------------------------------------------------------------------------

def test_all_supported_excludes_the_twelve_unsupported_sets():
    targets, _warnings, record = _load(all_supported=True)
    names = {t["name"] for t in targets}
    for name in UNSUPPORTED_SETS:
        assert name not in names, f"{name} is unsupported and must be excluded"
    assert len(targets) == 22


def test_all_supported_retains_every_supported_set():
    targets, _warnings, _record = _load(all_supported=True)
    keys = {t["canonical_key"] for t in targets}
    assert keys == set(SUPPORTED_KEYS)


def test_without_the_flag_the_full_published_cohort_is_loaded():
    """The default is unchanged - this fix narrows nothing by accident."""
    targets, _warnings, record = _load()
    assert len(targets) == 34
    assert record["mode"] == "all_targets"
    assert record["excludedSets"] == []


def test_the_flag_is_actually_threaded_through_main():
    """The literal defect: main built the cohort without consulting the flag."""
    source = inspect.getsource(script.main)
    assert "all_supported=args.all_supported" in source
    tree = ast.parse(inspect.getsource(script))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "load_cohort":
            passed = {kw.arg for kw in node.keywords}
            assert "all_supported" in passed, "load_cohort called without all_supported"


# ---------------------------------------------------------------------------
# Support is declared, not observed
# ---------------------------------------------------------------------------

def test_filtering_uses_declared_support_not_observed_v3_availability():
    """A SUPPORTED set with no V3 must stay IN the cohort so the gate can fail.

    This is the test that distinguishes the correct fix from the tempting one.
    If the filter keyed on `financialRipV3 is not None`, this set would vanish
    and the run would report a clean 21/21 while a real simulation failure went
    unmentioned.
    """
    targets = _all_34_targets()
    for target in targets:
        if target["canonical_key"] == "journeyTogether":
            target["financialRipV3"] = {}

    kept, _warnings, _record = _load(targets=targets, all_supported=True)
    keys = {t["canonical_key"] for t in kept}
    assert "journeyTogether" in keys, "a supported set was dropped for lacking V3"
    assert len(kept) == 22


def test_a_supported_set_missing_v3_still_fails_the_readiness_gate():
    targets = _all_34_targets()
    for target in targets:
        if target["canonical_key"] == "perfectOrder":
            target["financialRipV3"] = {}

    kept, _warnings, _record = _load(targets=targets, all_supported=True)
    readiness = script.assess_readiness(script.build_rows(kept))
    assert readiness["financialV3Missing"] == ["perfectOrder"]
    assert readiness["fullyReadyCount"] == 21


def test_unsupported_sets_do_not_trigger_a_readiness_failure():
    kept, _warnings, _record = _load(all_supported=True)
    readiness = script.assess_readiness(script.build_rows(kept))
    assert readiness["financialV3Missing"] == []
    assert readiness["cohortSize"] == 22
    assert readiness["fullyReadyCount"] == 22


def test_a_declared_supported_set_absent_from_targets_is_reported():
    """Silence would read as success under --strict, so it must surface."""
    targets = [t for t in _all_34_targets() if t["canonical_key"] != "whiteFlare"]
    kept, warnings, record = _load(targets=targets, all_supported=True)
    assert record["supportedKeysMissingFromTargets"] == ["whiteFlare"]
    assert any("whiteFlare" in w for w in warnings)
    assert len(kept) == 21


# ---------------------------------------------------------------------------
# Authoritative source, not a local list
# ---------------------------------------------------------------------------

def test_support_is_resolved_through_the_authoritative_gate_service():
    assert "supported_opening_set_keys" in inspect.getsource(script.resolve_supported_set_keys)
    assert "opening_simulation_gate" in inspect.getsource(script.resolve_supported_set_keys)


def test_the_script_contains_no_hand_maintained_set_name_list():
    """A second definition of 'supported' is the drift hazard to avoid.

    HIGHLIGHT_SETS (4 audit-case names, reported never filtered) is permitted;
    a 22- or 12-entry roster used for cohort selection is not.
    """
    source = inspect.getsource(script)
    for name in UNSUPPORTED_SETS:
        assert name not in source, f"'{name}' is hardcoded in the validation script"
    for key in SUPPORTED_KEYS:
        assert key not in source, f"'{key}' is hardcoded in the validation script"


def test_support_criterion_and_source_are_recorded_for_audit():
    _targets, _warnings, record = _load(all_supported=True)
    assert "opening_simulation_gate" in record["supportSource"]
    assert "USE_MONTE_CARLO_V2" in record["supportCriterion"]
    assert record["supportedKeyCount"] == 22
    assert record["publishedTargetCount"] == 34


# ---------------------------------------------------------------------------
# Manifest transparency
# ---------------------------------------------------------------------------

def test_excluded_sets_and_reasons_appear_in_the_manifest():
    targets, warnings, record = _load(all_supported=True)
    rows = script.build_rows(targets)
    readiness = script.assess_readiness(rows)
    args = argparse.Namespace(
        market_date=None, set_id=None, all_supported=True, seed=1,
        bootstrap_draws=10, uncertainty_draws=10,
    )
    manifest = script.build_manifest(
        args=args, rows=rows, readiness=readiness, warnings=warnings, support_record=record
    )
    cohort = manifest["cohort"]
    assert cohort["size"] == 22
    assert cohort["excludedSetCount"] == 12

    excluded_names = {e["setName"] for e in cohort["excludedSets"]}
    assert excluded_names == set(UNSUPPORTED_SETS)

    for entry in cohort["excludedSets"]:
        assert entry["canonicalKey"]
        assert entry["supportsOpeningSimulation"] is False
        assert "pull model" in entry["reason"]
    assert "opening_simulation_gate" in cohort["supportSource"]


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------

def test_all_supported_and_set_id_are_mutually_exclusive():
    """Intersecting them would let --all-supported look honoured while an id
    list did the real filtering, invalidating every readiness count."""
    with pytest.raises(SystemExit) as excinfo:
        script.main(["--all-supported", "--set-id", "abc"])
    assert excinfo.value.code == 2


def test_set_id_filtering_is_preserved():
    targets, _warnings, record = _load(set_ids=["id-perfectOrder", "id-blackBolt"])
    assert {t["canonical_key"] for t in targets} == {"perfectOrder", "blackBolt"}
    assert record["mode"] == "set_ids"


def test_unknown_set_id_is_warned_not_silently_dropped():
    _targets, warnings, _record = _load(set_ids=["id-nonexistent"])
    assert any("not present in cohort" in w for w in warnings)


# ---------------------------------------------------------------------------
# Read-only
# ---------------------------------------------------------------------------

def test_cohort_selection_performs_no_writes_or_simulation_launches():
    tree = ast.parse(inspect.getsource(script))
    banned = {"insert", "upsert", "rpc", "execute_sql", "delete", "table"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            assert getattr(node.func, "attr", None) not in banned

    source = inspect.getsource(script)
    for launcher in ("run_all_v2_sets(", "subprocess.run", "subprocess.Popen", "os.system"):
        assert launcher not in source, f"validation script may not invoke {launcher}"
