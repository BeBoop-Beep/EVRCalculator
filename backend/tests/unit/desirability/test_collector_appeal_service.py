"""The production Collector Appeal service, the public cohort, and the paths.

Fixture-based on purpose. The golden D and P values below are the REAL values
production computed - lifted from the committed dry-run artifact
(docs/research/collector_appeal_production_dry_run.json, generated against
production) - so these tests pin the service to the same numbers the audit
certified without needing a database.

That separation is deliberate: a test that reads production cannot fail for a
reason a reader can act on. If CA7 drifts, this fails and names the set; if the
SOURCE DATA moves, the artifact and these constants disagree and that is a
different, visible event. See test_source_manifest_change_is_distinguishable.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from backend.db.services import collector_appeal_service as service
from backend.desirability.collector_appeal import (
    CA7_PRODUCTION_LAMBDA,
    compute_chase_appeal,
    compute_collector_appeal,
    compute_collector_appeal_candidates,
)
from backend.desirability.collector_appeal_fingerprint import current_fingerprint
from backend.desirability.collector_appeal_inputs import (
    build_subject_index,
    select_subject_paths,
)
from backend.desirability.public_analytics_policy import (
    ANALYTICS_READY,
    HIDDEN_PENDING_VALIDATION,
    PublicCohortIntegrityError,
    SWORD_AND_SHIELD_ERA_ID,
    assert_cohort_integrity,
    build_public_cohort,
    is_public_analytics_eligible,
    public_analytics_status,
)
from backend.desirability.universal_set_desirability import COVERAGE_FULL

# The frozen identity from the phase brief. Any change here is a stop condition.
FROZEN_FINGERPRINT = "a98b948c693b87afdb1e4b0d19df03aa3ae650d35ca62b38eea41c126240b774"

# Real production inputs and outputs, per the dry-run artifact.
GOLDEN = {
    "Ascended Heroes": {"d": 95.4809, "p": 0.27143, "ca7": 0.960942},
    "Chaos Rising": {"d": 69.8947, "p": 0.371909, "ca7": 0.754929},
    "Shrouded Fable": {"d": 51.0746, "p": 0.233709, "ca7": 0.567918},
    "Prismatic Evolutions": {"d": 93.2775, "p": 0.398772, "ca7": 0.946179},
}

ARTIFACT = Path("docs/research/collector_appeal_production_dry_run.json")


# ---------------------------------------------------------------------------
# Source and formula
# ---------------------------------------------------------------------------

def test_formula_fingerprint_is_unchanged():
    assert current_fingerprint() == FROZEN_FINGERPRINT


def test_lambda_is_frozen_at_the_selected_value():
    assert CA7_PRODUCTION_LAMBDA == 0.50


def test_service_imports_the_formula_rather_than_restating_it():
    """The service must not contain its own copy of CA7."""
    source = Path("backend/db/services/collector_appeal_service.py").read_text(encoding="utf-8")
    assert "compute_collector_appeal" in source
    # The shape of the formula must appear nowhere in the service.
    assert "1.0 - d" not in source
    assert "* (1 -" not in source
    assert "0.5 *" not in source


def test_no_price_field_enters_collector_appeal_construction():
    for module in (
        "backend/db/services/collector_appeal_service.py",
        "backend/desirability/collector_appeal_inputs.py",
    ):
        source = Path(module).read_text(encoding="utf-8").lower()
        for banned in ("market_price", "set_value", "expected_value", "profit"):
            # Prose may discuss them; code must not read them.
            assert f'"{banned}"' not in source, f"{module} references {banned}"
            assert f"get('{banned}')" not in source
            assert f'get("{banned}")' not in source


# ---------------------------------------------------------------------------
# Golden sets
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_golden_set_ca7_reproduces(name):
    case = GOLDEN[name]
    computed = compute_collector_appeal(case["d"] / 100.0, case["p"])
    assert computed == pytest.approx(case["ca7"], abs=5e-7), name


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_golden_set_ca7_through_the_service_payload(name):
    """The SERVICE - not just the formula - must produce the golden number."""
    case = GOLDEN[name]
    payload = service._build_set_payload(
        set_id=f"set-{name}",
        universal_row={
            "set_name": name,
            "score": case["d"],
            "coverage": {"status": COVERAGE_FULL},
            "version": "universal_set_desirability_v3",
        },
        subjects=_subjects_with_dual_path_depth(case["p"]),
        pull_modeled=True,
    )
    assert payload["status"] == "available"
    assert payload["collectorAppeal"]["rawValue"] == pytest.approx(case["ca7"], abs=5e-6)
    assert payload["collectorAppeal"]["score"] == pytest.approx(case["ca7"] * 100.0, abs=5e-4)
    assert payload["rosterDesirability"]["score"] == case["d"]


def test_golden_values_still_match_the_dry_run_artifact():
    """A source-manifest change is distinguishable from a formula change.

    If production's D or P moves, this test fails while the formula tests keep
    passing - which says "the inputs moved", not "the mathematics moved".
    """
    if not ARTIFACT.exists():  # pragma: no cover - artifact is committed
        pytest.skip("dry-run artifact not present")
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    by_name = {row.get("set_name"): row for row in artifact["products"]}
    for name, case in GOLDEN.items():
        block = (by_name[name].get("proposed_diagnostics") or {})["collector_appeal_ca7"]
        assert block["value"] == pytest.approx(case["ca7"], abs=5e-7), name
        assert block["inputs"]["roster_desirability_d"] == pytest.approx(case["d"], abs=5e-4)
        assert block["inputs"]["dual_path_depth_p"] == pytest.approx(case["p"], abs=5e-6)


def test_artifact_fingerprint_matches_the_frozen_one():
    if not ARTIFACT.exists():  # pragma: no cover
        pytest.skip("dry-run artifact not present")
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["expected_fingerprint"] == FROZEN_FINGERPRINT


# ---------------------------------------------------------------------------
# No fallback
# ---------------------------------------------------------------------------

def test_missing_dual_path_yields_unavailable_not_desirability():
    """The 10% pillar must never silently become Universal Desirability."""
    payload = service._build_set_payload(
        set_id="no-pull-model",
        universal_row={"set_name": "X", "score": 88.0, "coverage": {"status": COVERAGE_FULL}},
        subjects=None,
        pull_modeled=False,
    )
    assert payload["status"] == "unavailable"
    assert payload["collectorAppeal"]["score"] is None
    assert payload["coverage"]["reasons"] == [service.REASON_NO_PULL_MODEL]
    # D is still reported as its own supporting metric - but not AS Collector Appeal.
    assert payload["rosterDesirability"]["score"] == 88.0


def test_pull_model_present_but_no_modeled_subject_is_a_distinct_reason():
    payload = service._build_set_payload(
        set_id="lost-origin-shaped",
        universal_row={"set_name": "X", "score": 70.0, "coverage": {"status": COVERAGE_FULL}},
        subjects=None,
        pull_modeled=True,
    )
    assert payload["coverage"]["reasons"] == [service.REASON_NO_MODELED_SUBJECT]


def test_incomplete_coverage_yields_unavailable():
    payload = service._build_set_payload(
        set_id="partial",
        universal_row={"set_name": "X", "score": 70.0, "coverage": {"status": "partial"}},
        subjects=_subjects_with_dual_path_depth(0.3),
        pull_modeled=True,
    )
    assert payload["status"] == "unavailable"
    assert payload["coverage"]["reasons"] == [service.REASON_COVERAGE]
    assert payload["rosterDesirability"]["score"] is None


def test_missing_inputs_never_become_zero():
    assert compute_collector_appeal(None, 0.4) is None
    assert compute_collector_appeal(0.4, None) is None
    assert compute_chase_appeal(None, 0.4) is None


def test_service_never_reads_universal_desirability_as_collector_appeal():
    source = Path("backend/db/services/collector_appeal_service.py").read_text(encoding="utf-8")
    # No branch may assign a desirability score into the collectorAppeal slot.
    assert 'collectorAppeal"] = ' not in source
    assert "or d_score" not in source
    assert "or d_unit" not in source


# ---------------------------------------------------------------------------
# Chase Appeal
# ---------------------------------------------------------------------------

def test_chase_appeal_agrees_with_the_research_grids_ca2():
    """The shipped function and the research candidate must never drift."""
    for d in (0.0, 0.2, 0.5, 0.83, 1.0):
        for m in (0.0, 0.15, 0.61, 1.0):
            grid = compute_collector_appeal_candidates(
                d=d, a_star=0.4, m_star=m, dual_path_depth=0.3
            )["CA2_chase"]
            assert compute_chase_appeal(d, m) == pytest.approx(grid, abs=1e-12)


def test_chase_appeal_is_not_a_rip_pillar():
    from backend.desirability.scoring_config import DEFAULT_RIP_WEIGHTS

    assert "chase" not in {key.lower() for key in DEFAULT_RIP_WEIGHTS}
    assert len([w for w in DEFAULT_RIP_WEIGHTS.values() if w > 0]) == 4


# ---------------------------------------------------------------------------
# Dual-Path presentation
# ---------------------------------------------------------------------------

def test_dual_path_depth_is_reported_on_its_raw_structural_scale():
    payload = service._build_set_payload(
        set_id="s",
        universal_row={"set_name": "X", "score": 95.4809, "coverage": {"status": COVERAGE_FULL}},
        subjects=_subjects_with_dual_path_depth(0.27143),
        pull_modeled=True,
    )
    depth = payload["dualPathDepth"]
    assert depth["rawValue"] == pytest.approx(0.27143, abs=5e-6)
    # displayPercent is a formatting of the SAME number, not a rescale.
    assert depth["displayPercent"] == pytest.approx(27.1, abs=0.05)
    # P must not be dressed up as a 0-100 grade with a tier.
    assert "tier" not in depth


# ---------------------------------------------------------------------------
# Subject-path identity and determinism
# ---------------------------------------------------------------------------

def _card(card_id, name, probability, *, rarity="Ultra Rare", number="1", priority=5):
    return {
        "canonical_card_id": card_id,
        "card_name": name,
        "pull_probability": probability,
        "rarity": rarity,
        "card_number": number,
        "printed_number": number,
        "image_url": f"https://img/{card_id}.png",
        "rarity_priority": priority,
        "slot_group": "Rare slot model",
        "subject_key": "ref:94",
        "subject_name": "Gengar",
        "subject_demand": 90.0,
    }


def test_subject_paths_identify_a_specific_printing():
    subject = {
        "subject_key": "ref:94",
        "cards": [_card("id-easy", "Gengar", 1 / 50), _card("id-elite", "Gengar ex", 1 / 1500)],
    }
    paths = select_subject_paths(subject)
    assert paths["accessiblePath"]["canonicalCardId"] == "id-easy"
    assert paths["elitePath"]["canonicalCardId"] == "id-elite"
    for path in (paths["accessiblePath"], paths["elitePath"]):
        # A name alone is not an identity: several printings share a name.
        assert path["cardName"]
        assert path["canonicalCardId"]
        assert path["cardNumber"]
        assert path["rarity"]
        assert path["imageUrl"]
        assert path["modeledProbability"] is not None
        assert path["impliedOdds"] is not None


def test_implied_odds_are_one_in_n_from_the_modeled_probability():
    subject = {"cards": [_card("a", "X", 1 / 250), _card("b", "Y", 1 / 1000)]}
    paths = select_subject_paths(subject)
    assert paths["accessiblePath"]["impliedOdds"] == pytest.approx(250.0, abs=0.05)
    assert paths["elitePath"]["impliedOdds"] == pytest.approx(1000.0, abs=0.05)


def test_tied_probabilities_resolve_deterministically_not_by_input_order():
    """Dictionary order must never pick the displayed winner."""
    a = _card("id-aaa", "Alpha", 1 / 200, rarity="Ultra Rare", number="10", priority=5)
    b = _card("id-bbb", "Beta", 1 / 200, rarity="Special Illustration Rare", number="20", priority=9)
    forward = select_subject_paths({"cards": [a, b]})
    reversed_ = select_subject_paths({"cards": [b, a]})
    assert forward["accessiblePath"]["canonicalCardId"] == reversed_["accessiblePath"]["canonicalCardId"]
    assert forward["elitePath"]["canonicalCardId"] == reversed_["elitePath"]["canonicalCardId"]
    # At equal probability the accessible end takes the LEAST premium rarity.
    assert forward["accessiblePath"]["canonicalCardId"] == "id-aaa"
    assert forward["elitePath"]["canonicalCardId"] == "id-bbb"


def test_subject_with_no_modeled_card_yields_no_paths():
    assert select_subject_paths({"cards": [{"card_name": "X"}]}) is None
    assert select_subject_paths({"cards": []}) is None


# ---------------------------------------------------------------------------
# Public cohort
# ---------------------------------------------------------------------------

def _set_row(set_id, name, era_id):
    return {"set_id": set_id, "name": name, "era_id": era_id}


SV_ERA = "dfb0dfa1-6a8e-4335-850f-e003867e19ee"
ME_ERA = "fb22f860-ae41-4879-a41a-857ca11bf0da"


def test_sword_and_shield_is_hidden_pending_validation():
    assert public_analytics_status(_set_row("1", "Evolving Skies", SWORD_AND_SHIELD_ERA_ID)) == (
        HIDDEN_PENDING_VALIDATION
    )
    assert not is_public_analytics_eligible(_set_row("1", "Evolving Skies", SWORD_AND_SHIELD_ERA_ID))


def test_sword_and_shield_is_hidden_by_era_name_when_era_id_is_absent():
    assert public_analytics_status({"name": "Evolving Skies", "era": "Sword and Shield"}) == (
        HIDDEN_PENDING_VALIDATION
    )


def test_current_public_cohort_is_exactly_21_sets():
    """The 33 simulated sets, classified. 21 ready, 12 SWSH withheld."""
    swsh = [
        "Astral Radiance", "Battle Styles", "Brilliant Stars", "Chilling Reign",
        "Darkness Ablaze", "Evolving Skies", "Fusion Strike", "Lost Origin",
        "Rebel Clash", "Silver Tempest", "Sword & Shield", "Vivid Voltage",
    ]
    ready = [
        "Ascended Heroes", "Black Bolt", "Chaos Rising", "Destined Rivals",
        "Journey Together", "Mega Evolution", "Obsidian Flames", "Paldea Evolved",
        "Paldean Fates", "Paradox Rift", "Perfect Order", "Phantasmal Flames",
        "Prismatic Evolutions", "Scarlet and Violet 151", "Scarlet and Violet Base Set",
        "Shrouded Fable", "Stellar Crown", "Surging Sparks", "Temporal Forces",
        "Twilight Masquerade", "White Flare",
    ]
    rows = [_set_row(f"swsh-{i}", n, SWORD_AND_SHIELD_ERA_ID) for i, n in enumerate(swsh)]
    rows += [_set_row(f"ready-{i}", n, SV_ERA) for i, n in enumerate(ready)]

    cohort = build_public_cohort(rows)
    assert cohort["eligibleSetCount"] == 21
    assert cohort["excludedCountsByReason"][HIDDEN_PENDING_VALIDATION] == 12
    assert len(cohort["eligibleSetIds"]) == 21
    assert all(set_id.startswith("ready-") for set_id in cohort["eligibleSetIds"])


def test_hidden_sets_are_absent_from_the_cohort_entirely():
    """Not merely flagged - absent. A flagged row can still be ranked."""
    rows = [
        _set_row("a", "Prismatic Evolutions", SV_ERA),
        _set_row("b", "Evolving Skies", SWORD_AND_SHIELD_ERA_ID),
    ]
    cohort = build_public_cohort(rows)
    assert cohort["eligibleSetIds"] == ["a"]
    assert "b" not in cohort["eligibleSetIds"]


def test_cohort_integrity_fails_when_an_eligible_set_lacks_collector_appeal():
    cohort = build_public_cohort([_set_row("a", "Prismatic Evolutions", SV_ERA)])
    with pytest.raises(PublicCohortIntegrityError) as excinfo:
        assert_cohort_integrity(cohort, {"a": None})
    assert "cannot be ranked" in str(excinfo.value)


def test_cohort_integrity_passes_when_every_eligible_set_has_collector_appeal():
    cohort = build_public_cohort(
        [_set_row("a", "Prismatic Evolutions", SV_ERA), _set_row("b", "Chaos Rising", ME_ERA)]
    )
    assert_cohort_integrity(cohort, {"a": 94.6, "b": 75.5})


def test_unknown_set_shape_is_not_treated_as_ready():
    assert public_analytics_status(None) != ANALYTICS_READY
    assert not is_public_analytics_eligible("not-a-set")


def test_backend_policy_agrees_with_the_frontend_status_vocabulary():
    """The two guards must speak one vocabulary or they disagree silently."""
    js = Path("frontend/lib/pokemon/pokemonSetPublicCoverage.js").read_text(encoding="utf-8")
    for status in (ANALYTICS_READY, HIDDEN_PENDING_VALIDATION):
        assert f'"{status}"' in js
    assert SWORD_AND_SHIELD_ERA_ID in js


# ---------------------------------------------------------------------------
# Contract shape
# ---------------------------------------------------------------------------

def test_payload_exposes_the_explicit_new_fields():
    payload = service._build_set_payload(
        set_id="s",
        universal_row={"set_name": "X", "score": 90.0, "coverage": {"status": COVERAGE_FULL}},
        subjects=_subjects_with_dual_path_depth(0.3),
        pull_modeled=True,
    )
    for field in ("rosterDesirability", "dualPathDepth", "collectorAppeal", "chaseAppeal"):
        assert field in payload, field


def test_payload_does_not_expose_raw_source_rows():
    payload = service._build_set_payload(
        set_id="s",
        universal_row={
            "set_name": "X",
            "score": 90.0,
            "coverage": {"status": COVERAGE_FULL},
            "subject_rollups_json": [{"secret": 1}],
            "diagnostics_json": {"secret": 1},
        },
        subjects=_subjects_with_dual_path_depth(0.3),
        pull_modeled=True,
    )
    blob = json.dumps(payload)
    assert "subject_rollups_json" not in blob
    assert "diagnostics_json" not in blob
    assert "secret" not in blob


def test_fingerprint_is_internal_metadata_not_a_per_set_public_field():
    payload = service._build_set_payload(
        set_id="s",
        universal_row={"set_name": "X", "score": 90.0, "coverage": {"status": COVERAGE_FULL}},
        subjects=_subjects_with_dual_path_depth(0.3),
        pull_modeled=True,
    )
    assert "fingerprint" not in json.dumps(payload).lower()


def _import_lines(path: str):
    """Only real import statements - prose about a module is not a dependency."""
    return [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.startswith(("import ", "from "))
    ]


@pytest.mark.parametrize(
    "path",
    [
        "backend/db/services/collector_appeal_service.py",
        "backend/desirability/collector_appeal_inputs.py",
    ],
)
def test_request_path_does_not_import_a_research_script_or_shell_out(path):
    """A service must not reach into backend/scripts or spawn a process."""
    for line in _import_lines(path):
        assert "backend.scripts" not in line, f"{path}: {line}"
        assert "subprocess" not in line, f"{path}: {line}"
        assert "argparse" not in line, f"{path}: {line}"


def test_the_import_guard_would_actually_catch_a_research_import():
    """The guard above is only evidence if it can fail."""
    lines = _import_lines("backend/scripts/collector_appeal_production_dry_run.py")
    assert any("backend.scripts" in line for line in lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _subjects_with_dual_path_depth(target_p: float):
    """A one-subject roster whose Dual-Path Depth is exactly ``target_p``.

    With a single desirable subject the demand share is 1.0, so
    ``P = access(p_easiest) * scarcity(p_rarest)``. Rather than solve the
    transforms analytically, the easiest card is pinned at the easy anchor
    (access = 1.0) so ``P = scarcity(p_rarest)``, and the rarest card's
    probability is solved from the scarcity transform's own definition - so the
    fixture is built FROM the canonical transform, not from a hand-copied curve
    that could silently disagree with it.
    """
    from backend.desirability.opening_appeal import (
        EASY_PROBABILITY,
        ELITE_PROBABILITY,
        access_transform,
    )

    # scarcity(p) = 1 - access(p); access is log10-linear between the anchors.
    # Solve access(p) = 1 - target_p for p.
    target_access = 1.0 - target_p
    log_easy, log_elite = math.log10(EASY_PROBABILITY), math.log10(ELITE_PROBABILITY)
    log_p = log_elite + target_access * (log_easy - log_elite)
    rarest_probability = 10 ** log_p

    assert access_transform(rarest_probability) == pytest.approx(target_access, abs=1e-9)

    return [
        {
            "subject_key": "ref:1",
            "subject_name": "Fixture",
            "subject_demand": 95.0,
            "appeal_excess": 45.0,
            "cards": [
                {
                    "canonical_card_id": "easy",
                    "card_name": "Fixture",
                    "pull_probability": EASY_PROBABILITY,
                    "rarity": "Double Rare",
                    "card_number": "1",
                    "printed_number": "1",
                    "image_url": "https://img/easy.png",
                    "rarity_priority": 3,
                    "slot_group": "Rare slot model",
                },
                {
                    "canonical_card_id": "elite",
                    "card_name": "Fixture ex",
                    "pull_probability": rarest_probability,
                    "rarity": "Special Illustration Rare",
                    "card_number": "2",
                    "printed_number": "2",
                    "image_url": "https://img/elite.png",
                    "rarity_priority": 9,
                    "slot_group": "Reverse slot model",
                },
            ],
        }
    ]


def test_the_dual_path_fixture_actually_produces_the_requested_depth():
    """The fixture is only evidence if it is itself correct."""
    from backend.desirability.collector_appeal import compute_dual_path_depth

    for target in (0.27143, 0.371909, 0.233709, 0.398772):
        depth = compute_dual_path_depth(_subjects_with_dual_path_depth(target))
        assert depth["value"] == pytest.approx(target, abs=1e-6)
