"""Phase 7: the Collector Appeal formula fingerprint.

The fingerprint's whole job is to answer one question honestly: "was this stored
score computed under the rules we use today?" Every test below pins one way that
answer could go wrong - either by failing to move when the mathematics moves
(certifying stale rows as current), or by moving when nothing material changed
(marking every row permanently stale, which is the same as having no fingerprint).
"""

from __future__ import annotations

import copy
import inspect
import json
import re

import pytest

from backend.desirability import collector_appeal_fingerprint as fp
from backend.desirability.collector_appeal_fingerprint import (
    FINGERPRINT_CURRENT,
    FINGERPRINT_MISSING,
    FINGERPRINT_STALE,
    build_collector_appeal_identity,
    canonical_representation,
    collect_assumptions,
    current_fingerprint,
    fingerprint_assumptions,
    fingerprint_status,
    is_row_stale,
    read_row_fingerprint,
)


def _mutate(path, value):
    """Copy the live assumptions and change one thing at ``path``."""
    assumptions = copy.deepcopy(collect_assumptions())
    target = assumptions
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return assumptions


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_identical_assumptions_produce_identical_hashes():
    assert fingerprint_assumptions() == fingerprint_assumptions()
    assert current_fingerprint() == current_fingerprint()


def test_fingerprint_is_a_sha256_hex_digest():
    assert re.fullmatch(r"[0-9a-f]{64}", current_fingerprint())


def test_reordered_mappings_produce_identical_hashes():
    """Dict insertion order must not fork the hash."""
    base = collect_assumptions()
    shuffled = {key: base[key] for key in reversed(list(base))}
    shuffled["dependencies"] = {
        key: base["dependencies"][key] for key in reversed(list(base["dependencies"]))
    }
    assert fingerprint_assumptions(shuffled) == fingerprint_assumptions(base)


def test_nested_mapping_reordering_produces_identical_hashes():
    base = collect_assumptions()
    reordered = copy.deepcopy(base)
    policy = reordered["dependencies"]["missing_data_policy"]
    reordered["dependencies"]["missing_data_policy"] = {
        key: policy[key] for key in reversed(list(policy))
    }
    assert fingerprint_assumptions(reordered) == fingerprint_assumptions(base)


def test_equivalent_float_literals_do_not_fork_the_hash():
    """0.50 and 0.5 are the same lambda and must hash identically."""
    assert fingerprint_assumptions(_mutate(["lambda"], 0.50)) == fingerprint_assumptions(
        _mutate(["lambda"], 0.5)
    )


def test_canonical_representation_is_stable_and_sorted():
    representation = canonical_representation()
    assert representation == canonical_representation()
    parsed = json.loads(representation)
    assert list(parsed) == sorted(parsed)
    assert list(parsed["dependencies"]) == sorted(parsed["dependencies"])


# ---------------------------------------------------------------------------
# Every material assumption must invalidate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path,new_value",
    [
        # The selected candidate and its one tuned-looking number.
        (["lambda"], 0.75),
        (["formula"], "CA6"),
        (["formula_version"], "collector_appeal_ca7_bounded_bonus_v2"),
        (["formula_expression"], "CA7 = D * (0.5 + 0.5 * P)"),
        # Constructs.
        (["dependencies", "desirability_version"], "universal_set_desirability_v4"),
        (["dependencies", "desirability_eligibility_version"], "universal_desirability_eligibility_v3"),
        (["dependencies", "dual_path_version"], "dual_path_depth_v2"),
        # Transforms AND their anchors - anchors matter most, because
        # recalibrating one changes every score with no version string moving.
        (["dependencies", "access_transform_version"], "access_transform_v2"),
        (["dependencies", "scarcity_transform_version"], "scarcity_transform_v2"),
        (["dependencies", "easy_probability_anchor"], 0.05),
        (["dependencies", "elite_probability_anchor"], 0.0005),
        (["dependencies", "demand_baseline"], 60.0),
        # Eligibility + rarity.
        (["dependencies", "hit_eligibility_version"], "hit_policy_v3"),
        (["dependencies", "hit_buckets"], ["accessible_hit", "major_hit", "premium_chase"]),
        (["dependencies", "rarity_mapping_version"], "rarity_normalization_v2"),
        (["dependencies", "rarity_override_version"], "rarity_overrides_v2"),
        # Subjects.
        (["dependencies", "subject_demand_source_version"], "pokemon_desirability_composite_v2"),
        (["dependencies", "subject_weighting_version"], "desirability_factor_v2"),
        # Product policy.
        (["dependencies", "product_classifier_version"], "product_support_v2"),
        (["dependencies", "rankability_contract_version"], "rankability_contract_v2"),
        (["dependencies", "set_components_version"], "pokemon_set_desirability_components_v3"),
        # Policies.
        (["dependencies", "missing_data_policy_version"], "collector_appeal_missing_data_v2"),
        (["dependencies", "rounding_policy_version"], "collector_appeal_rounding_v2"),
    ],
)
def test_changing_any_material_assumption_changes_the_fingerprint(path, new_value):
    assert fingerprint_assumptions(_mutate(path, new_value)) != current_fingerprint(), (
        f"changing {'.'.join(path)} did not move the fingerprint"
    )


def test_changing_a_nested_policy_rule_changes_the_fingerprint():
    """A policy flip that keeps the version string is the dangerous case: the
    fingerprint must catch it even when nobody remembered to bump a version."""
    mutated = _mutate(["dependencies", "missing_data_policy"], {
        "missing_input_returns": "0.0",
        "never_substitutes_zero": False,
        "unmodeled_subjects": "count_as_zero",
        "no_desirable_subject": "dual_path_depth_is_zero",
    })
    assert fingerprint_assumptions(mutated) != current_fingerprint()


def test_changing_a_rounding_rule_changes_the_fingerprint():
    mutated = _mutate(["dependencies", "rounding_policy"], {
        "clamp_domain": [0.0, 100.0],
        "clamp_applied_to": ["d"],
        "round_half": "half_up",
        "stored_decimal_places": 2,
    })
    assert fingerprint_assumptions(mutated) != current_fingerprint()


def test_hit_bucket_membership_change_invalidates():
    """Admitting or removing a bucket re-partitions every card."""
    base = collect_assumptions()
    widened = _mutate(["dependencies", "hit_buckets"], sorted(base["dependencies"]["hit_buckets"] + ["bulk"]))
    assert fingerprint_assumptions(widened) != current_fingerprint()


# ---------------------------------------------------------------------------
# Staleness classification
# ---------------------------------------------------------------------------

def _row(fingerprint=None, *, block=True):
    diagnostics = {}
    if block:
        diagnostics["collector_appeal"] = {"formula": "CA7", "lambda": 0.5}
        if fingerprint is not None:
            diagnostics["collector_appeal"]["fingerprint"] = fingerprint
    return {"set_id": "s1", "diagnostics_json": diagnostics}


def test_matching_fingerprint_is_current():
    assert fingerprint_status(_row(current_fingerprint())) == FINGERPRINT_CURRENT
    assert is_row_stale(_row(current_fingerprint())) is False


def test_mismatched_fingerprint_is_stale():
    assert fingerprint_status(_row("0" * 64)) == FINGERPRINT_STALE
    assert is_row_stale(_row("0" * 64)) is True


def test_missing_fingerprint_is_classified_missing_not_current():
    """Every production row today has no Collector Appeal block at all. Missing
    must never be silently accepted as current."""
    assert fingerprint_status(_row(None)) == FINGERPRINT_MISSING
    assert fingerprint_status(_row(block=False)) == FINGERPRINT_MISSING
    assert fingerprint_status({"set_id": "s1"}) == FINGERPRINT_MISSING
    assert fingerprint_status({"set_id": "s1", "diagnostics_json": None}) == FINGERPRINT_MISSING


def test_missing_and_stale_are_distinct_but_both_require_rebuild():
    """Different facts, different responses - but neither is 'current'."""
    assert fingerprint_status(_row(None)) != fingerprint_status(_row("0" * 64))
    assert is_row_stale(_row(None)) is True
    assert is_row_stale(_row("0" * 64)) is True


def test_read_row_fingerprint_returns_none_rather_than_guessing():
    assert read_row_fingerprint({"diagnostics_json": {"collector_appeal": {}}}) is None
    assert read_row_fingerprint({"diagnostics_json": {"collector_appeal": {"fingerprint": ""}}}) is None
    assert read_row_fingerprint({"diagnostics_json": "not a mapping"}) is None


def test_status_accepts_an_explicit_expected_fingerprint():
    row = _row("abc123")
    assert fingerprint_status(row, expected="abc123") == FINGERPRINT_CURRENT
    assert fingerprint_status(row, expected="def456") == FINGERPRINT_STALE


# ---------------------------------------------------------------------------
# No volatile, environment-specific or source-control content
# ---------------------------------------------------------------------------

def test_fingerprint_contains_no_timestamps_or_paths_or_environment():
    representation = canonical_representation()
    for banned in (
        "202", "generated_at", "built_at", "timestamp", "run_id",
        "C:\\", "/home/", "D:\\", "\\Users\\", "supabase", "http", "localhost",
        "SUPABASE", "KEY", "TOKEN", "PASSWORD", "hostname", ".venv",
    ):
        assert banned not in representation, f"volatile/environment content in fingerprint: {banned}"


def test_fingerprint_does_not_use_a_git_commit_sha():
    """Source-control identity is not scoring identity - a docstring edit must
    not invalidate every stored score."""
    representation = canonical_representation()
    for banned in ("git", "commit", "sha1", "branch", "source_control_ref"):
        assert banned not in representation.lower()


def test_source_control_ref_is_recorded_but_excluded_from_the_hash():
    without = build_collector_appeal_identity()
    with_ref = build_collector_appeal_identity(source_control_ref="056b6a5")
    assert with_ref["source_control_ref"] == "056b6a5"
    assert with_ref["fingerprint"] == without["fingerprint"]


def test_fingerprint_is_stable_across_processes():
    """Guards against PYTHONHASHSEED leaking into the digest via set/dict order."""
    import subprocess
    import sys

    code = (
        "from backend.desirability.collector_appeal_fingerprint import current_fingerprint;"
        "print(current_fingerprint())"
    )
    outputs = set()
    for seed in ("0", "1", "random"):
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, env={**__import__("os").environ, "PYTHONHASHSEED": seed},
        )
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout.strip())
    assert len(outputs) == 1, f"fingerprint varies with PYTHONHASHSEED: {outputs}"
    assert outputs.pop() == current_fingerprint()


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_fingerprint_generation_performs_no_database_access():
    """Fingerprinting must be callable with no network and no credentials."""
    source = inspect.getsource(fp)
    for banned in ("supabase", "public_read_client", "service_role", "requests", "httpx", ".execute(", "psycopg"):
        assert banned not in source, f"database surface in fingerprint module: {banned}"


def test_fingerprint_module_imports_no_client_or_price_surface():
    tree = __import__("ast").parse(inspect.getsource(fp))
    imported = set()
    for node in __import__("ast").walk(tree):
        if isinstance(node, (__import__("ast").Import, __import__("ast").ImportFrom)):
            imported.add(getattr(node, "module", "") or "")
            for alias in node.names:
                imported.add(alias.name)
    for banned in ("backend.db.clients.supabase_client", "requests", "httpx"):
        assert banned not in imported
    assert not any("market" in name or "price" in name for name in imported), (
        "Collector Appeal must remain price-independent"
    )


def test_score_computation_remains_price_independent():
    from backend.desirability.collector_appeal import compute_collector_appeal

    signature = inspect.signature(compute_collector_appeal)
    assert set(signature.parameters) == {"d", "p", "lam"}
    assert compute_collector_appeal(0.9, 0.3) == pytest.approx(0.9 + 0.5 * 0.3 * 0.1)


def test_collect_assumptions_is_a_pure_snapshot_of_live_constants():
    """The fingerprint must track the real constants, not a duplicated copy that
    could drift and certify stale rows as current."""
    from backend.desirability.collector_appeal import CA7_PRODUCTION_LAMBDA
    from backend.desirability.opening_appeal import EASY_PROBABILITY, ELITE_PROBABILITY
    from backend.desirability.rarity_buckets import HIT_POLICY_VERSION

    assumptions = collect_assumptions()
    assert assumptions["lambda"] == CA7_PRODUCTION_LAMBDA == 0.50
    assert assumptions["dependencies"]["easy_probability_anchor"] == EASY_PROBABILITY
    assert assumptions["dependencies"]["elite_probability_anchor"] == ELITE_PROBABILITY
    assert assumptions["dependencies"]["hit_eligibility_version"] == HIT_POLICY_VERSION


def test_identity_payload_matches_the_requested_diagnostics_shape():
    identity = build_collector_appeal_identity()
    assert identity["formula"] == "CA7"
    assert identity["lambda"] == 0.50
    assert identity["fingerprint_algorithm"] == "sha256"
    for key in (
        "desirability_version", "dual_path_version", "access_transform_version",
        "scarcity_transform_version", "hit_eligibility_version", "rarity_mapping_version",
        "product_classifier_version", "missing_data_policy_version",
    ):
        assert key in identity["dependencies"], f"missing required dependency: {key}"
