"""Which sets are approved for PUBLIC analytics, decided in the backend.

WHY THIS IS A BACKEND MODULE
----------------------------
The rule already existed, in ``frontend/lib/pokemon/pokemonSetPublicCoverage.js``,
and it was correct - but it ran too late to be the authority. The backend ranked
all 33 internally-simulated sets, and the frontend then hid 12 of them. So a
public page could truthfully render "Rank #1" off a rank computed against a
cohort that included sets the same page refused to show: the denominator said 33
while the list said 21, and both were "right" about their own half of the system.

Filtering a list is not the same as choosing a population. Ranks, tiers and
percentile cutoffs are properties OF a cohort - they must be computed after the
cohort is fixed, which means the cohort has to be fixed somewhere the ranking
code can see it. That is here.

The frontend helper stays. It still guards display and navigation, which is a
real job. It is simply no longer the only thing that knows.

THE RULE IS METADATA, NOT A LIST OF NAMES
-----------------------------------------
Sword & Shield is hidden because its pull/hit-rate coverage is incomplete, its
subsets need parent-checklist blending, and it predates the current set-page
architecture - not because someone enumerated twelve set names. So the check is
against ``era_id`` (the table-backed key), with the era display name as a
fallback for payloads that never had ``era_id`` threaded through. Retyping the
twelve names into a service would create a second source of truth that drifts
the first time a set is added.

WHAT THIS MODULE DOES NOT DECIDE
--------------------------------
Availability of a SCORE is a different question from approval for PUBLIC
display, and conflating them would let a data gap silently redefine the product
boundary (or a product decision silently look like a data gap). This module
answers only "is this set approved for public analytics?". Whether it has CA7 is
``collector_appeal_service``'s answer. The two are checked together, and a set
that is analytics_ready but has no CA7 is an ERROR, not a set to quietly drop -
see ``assert_cohort_integrity``.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

PUBLIC_ANALYTICS_POLICY_VERSION = "public_analytics_policy_v1_era_gated"

# Status codes. Mirrors POKEMON_SET_COVERAGE_STATUS in
# frontend/lib/pokemon/pokemonSetPublicCoverage.js - the strings are a shared
# contract, so a mismatch would be a silent disagreement between the two guards.
ANALYTICS_READY = "analytics_ready"
HIDDEN_PENDING_VALIDATION = "hidden_pending_validation"
COMING_SOON = "coming_soon"
SUBSET_NEEDS_PARENT_BLEND = "subset_needs_parent_blend"
UNSUPPORTED_SPECIAL = "unsupported_special"

# public.eras.id for Sword & Shield. The reliable, table-backed key.
SWORD_AND_SHIELD_ERA_ID = "cdae9eb9-0f9e-4d93-9fdf-4221cfbdb90d"

# Fallback for payloads carrying only the era display name. That name is itself
# sourced from the normalized ``eras`` table join, not free text.
HIDDEN_PENDING_VALIDATION_ERA_NAMES = frozenset({"sword and shield"})

# Side-collection subsets that are structurally part of a parent set's checklist.
# Deliberately independent of era membership so a future non-SWSH subset can be
# tagged without being mistaken for "SWSH, blanket hidden".
SUBSET_NEEDS_PARENT_BLEND_NAME_PATTERNS = ("trainer gallery", "galarian gallery")

# Promo-only / side products that are not standalone analytics candidates.
UNSUPPORTED_SPECIAL_NAME_PATTERNS = (
    "black star promo",
    "mcdonald",
    "pop series",
    "best of game",
    "futsal collection",
    "classic collection",
    "trainer kit",
    "starter set",
    "dragon vault",
    "southern islands",
    "pokemon go",
    "pokémon go",
)

# Why each non-ready status is withheld, in the words the API reports. Kept next
# to the codes so a caller cannot invent its own explanation for a decision it
# did not make.
STATUS_REASONS: Dict[str, str] = {
    HIDDEN_PENDING_VALIDATION: (
        "Pull/hit-rate coverage is incomplete and this era predates the current "
        "set-page architecture, so its analytics are not approved for public display."
    ),
    SUBSET_NEEDS_PARENT_BLEND: (
        "This is an insert-sheet subset of a parent set's checklist and cannot be "
        "analyzed standalone until it is blended with its parent."
    ),
    UNSUPPORTED_SPECIAL: (
        "Promo/side product, not a standalone booster analytics candidate."
    ),
    COMING_SOON: "Analytics for this set are not built yet.",
}


def _text(value: Any) -> str:
    return str(value if value is not None else "").strip().lower()


def _matches_any(text: str, patterns: Sequence[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _era_id(pokemon_set: Mapping[str, Any]) -> Optional[str]:
    for field in ("era_id", "eraId"):
        value = pokemon_set.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _era_name(pokemon_set: Mapping[str, Any]) -> Optional[str]:
    for field in ("era", "era_name", "eraName"):
        value = pokemon_set.get(field)
        if value is not None and _text(value):
            return _text(value)
    return None


def _is_sword_and_shield(pokemon_set: Mapping[str, Any]) -> bool:
    era_id = _era_id(pokemon_set)
    if era_id and era_id == SWORD_AND_SHIELD_ERA_ID:
        return True
    era_name = _era_name(pokemon_set)
    return bool(era_name and era_name in HIDDEN_PENDING_VALIDATION_ERA_NAMES)


def public_analytics_status(pokemon_set: Optional[Mapping[str, Any]]) -> str:
    """Classify one set. Pure: no I/O, no mutation, no scoring.

    Check order matches the frontend helper exactly. It matters: several SWSH
    products ALSO match an unsupported_special name pattern, and reordering the
    checks would relabel them - changing which reason a set is withheld for even
    though it stays withheld either way.
    """
    if not isinstance(pokemon_set, Mapping):
        # An unknown shape is not evidence of readiness. Defaulting to ready
        # here would let a malformed row into a public ranking.
        return COMING_SOON

    name = _text(pokemon_set.get("name") or pokemon_set.get("set_name"))

    if _matches_any(name, UNSUPPORTED_SPECIAL_NAME_PATTERNS):
        return UNSUPPORTED_SPECIAL
    if _matches_any(name, SUBSET_NEEDS_PARENT_BLEND_NAME_PATTERNS):
        return SUBSET_NEEDS_PARENT_BLEND
    if _is_sword_and_shield(pokemon_set):
        return HIDDEN_PENDING_VALIDATION
    return ANALYTICS_READY


def is_public_analytics_eligible(pokemon_set: Optional[Mapping[str, Any]]) -> bool:
    """True only for ``analytics_ready``. Every other status is excluded."""
    return public_analytics_status(pokemon_set) == ANALYTICS_READY


def build_public_cohort(sets: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Fix the public cohort BEFORE anything is ranked.

    Returns the eligible set ids plus a truthful census of what was excluded and
    why. The excluded counts are part of the contract rather than a log line: a
    cohort that shrinks from 21 to 20 should be visible in the payload, not
    discovered when a rank denominator changes.
    """
    eligible: List[str] = []
    excluded_by_reason: Dict[str, int] = {}
    excluded: List[Dict[str, Any]] = []

    for row in sets:
        set_id = str(row.get("set_id") or row.get("id") or "")
        if not set_id:
            continue
        status = public_analytics_status(row)
        if status == ANALYTICS_READY:
            eligible.append(set_id)
            continue
        excluded_by_reason[status] = excluded_by_reason.get(status, 0) + 1
        excluded.append(
            {
                "setId": set_id,
                "setName": row.get("name") or row.get("set_name"),
                "status": status,
                "reason": STATUS_REASONS.get(status),
            }
        )

    return {
        "version": PUBLIC_ANALYTICS_POLICY_VERSION,
        "eligibleSetIds": sorted(eligible),
        "eligibleSetCount": len(eligible),
        "status": ANALYTICS_READY if eligible else "empty_cohort",
        "excludedCountsByReason": excluded_by_reason,
        "excluded": sorted(excluded, key=lambda row: str(row["setName"] or row["setId"])),
    }


# Overall-ranked cohort status codes. The Overall RIP ranking is a stricter
# population than the eligible cohort: it needs a valid CA7 under ONE version.
OVERALL_RANKED_OK = "overall_ranked_ok"
OVERALL_RANKED_INCOMPLETE_MISSING_CA7 = "overall_ranked_incomplete_missing_ca7"
OVERALL_RANKED_CA7_VERSION_MISMATCH = "overall_ranked_ca7_version_mismatch"


def audit_overall_ranked_cohort(
    eligible_set_ids: Iterable[str],
    overall_available_by_set: Mapping[str, bool],
    ca7_version_by_set: Mapping[str, Optional[str]],
) -> Dict[str, Any]:
    """Which eligible sets may enter the Overall RIP ranking, and is it coherent?

    Overall RIP = 0.90 Financial + 0.10 CA7, so a set joins the Overall ranking
    only with a valid CA7 (``overall_available_by_set[set_id]`` True). A set
    without CA7 is FLAGGED, never dropped silently and never given a fabricated
    Overall RIP: it keeps its Financial RIP and Universal Set Desirability on the
    page but is not counted in the Overall denominator.

    Mixed CA7 versions among ranked sets FAIL CLOSED
    (``OVERALL_RANKED_CA7_VERSION_MISMATCH``): two Overall RIPs computed under
    different CA7 formulas are not comparable, so a leaderboard mixing them is
    self-inconsistent. This is the fail-closed condition a publication guard must
    refuse on.
    """
    ranked: List[str] = []
    missing_ca7: List[str] = []
    versions: Dict[str, int] = {}
    for set_id in eligible_set_ids:
        set_id = str(set_id)
        if overall_available_by_set.get(set_id):
            ranked.append(set_id)
            version = ca7_version_by_set.get(set_id)
            if version is not None:
                versions[str(version)] = versions.get(str(version), 0) + 1
        else:
            missing_ca7.append(set_id)

    distinct_versions = sorted(versions)
    if len(distinct_versions) > 1:
        status = OVERALL_RANKED_CA7_VERSION_MISMATCH
    elif missing_ca7:
        status = OVERALL_RANKED_INCOMPLETE_MISSING_CA7
    else:
        status = OVERALL_RANKED_OK

    return {
        "status": status,
        "rankedSetIds": sorted(ranked),
        "rankedSetCount": len(ranked),
        "missingCa7SetIds": sorted(missing_ca7),
        "missingCa7Count": len(missing_ca7),
        "ca7Version": distinct_versions[0] if len(distinct_versions) == 1 else None,
        "ca7Versions": distinct_versions,
        "publishable": status != OVERALL_RANKED_CA7_VERSION_MISMATCH,
    }


class PublicCohortIntegrityError(RuntimeError):
    """An analytics_ready set has no Collector Appeal.

    Raised rather than handled. The two ways to "handle" it are both wrong:
    dropping the set silently shrinks the denominator every other rank is
    quoted against, and renormalizing the financial pillars publishes a
    canonical-looking RIP that is not comparable to the others. Both make the
    payload self-consistent and false. See ``weighted_rip``'s missing-pillar
    policy, which refuses the same trade for the same reason.
    """


def assert_cohort_integrity(
    cohort: Mapping[str, Any],
    desirability_by_set: Mapping[str, Any],
) -> None:
    """Every eligible set must carry Universal Set Desirability.

    Checked against the UNIVERSAL score, not CA7. CA7 is no longer a required
    pillar - it is an optional Simulation Opening Experience diagnostic that
    exists only where a pull model loads - so an absent CA7 is now an expected
    state and asserting on it would raise on every set whose pack model is
    unavailable. Universal Set Desirability is the authoritative score and needs
    no simulation, so an analytics_ready set without one is still a genuine
    contradiction worth failing on.
    """
    missing = [
        set_id for set_id in cohort.get("eligibleSetIds") or []
        if desirability_by_set.get(set_id) is None
    ]
    if missing:
        raise PublicCohortIntegrityError(
            f"{len(missing)} analytics_ready set(s) have no Universal Set Desirability "
            f"and cannot be ranked in a public cohort: {sorted(missing)}. "
            "Either the set is not actually analytics_ready or its desirability "
            "coverage regressed; neither is resolvable by dropping it from the cohort."
        )
