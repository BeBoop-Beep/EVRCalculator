"""The ONE definition of "is this published RIP leaderboard still current?".

WHY THIS MODULE EXISTS
----------------------
Production evidence: the newest published leaderboard reported

    overall_rip_v4_90_financial_10_ca7
    financial_rip_v2_60_25_15

while 22 fresh Financial RIP V3 simulations already existed underneath it. Three
independent defects produced that, and each of them was individually invisible:

1. **The publisher published the wrong objects.** ``publication_contract`` in
   ``pokemon_explore_rankings_publisher`` built its rows from ``target['rip']``
   (Overall RIP v4, off the V2 pillars and legacy CA7) and ``target['ripCore']``
   (Financial RIP V2). It was never repointed at the V3/V5/V6 objects when those
   cutovers landed, so the leaderboard kept publishing the legacy models.

2. **The version metadata was a stale literal.** The ranking payload's
   ``meta.ripWeightsConfig`` hardcoded ``FINANCIAL_RIP_V2_VERSION`` and
   ``OVERALL_RIP_V4_VERSION``, and the publisher copies those strings into the
   snapshot row. So the row's version columns were TRUE about what was published
   and, precisely because both halves were consistently wrong, nothing could
   detect the discrepancy.

3. **Freshness never looked at versions at all.**
   ``refresh_stale_public_snapshots._global_snapshot_staleness`` compared
   dependency TIMESTAMPS against the snapshot timestamp and checked structural
   markers. A scoring-version change moves no timestamp: the snapshot stays
   "fresh" forever, under an obsolete contract, and a matching market date reads
   as proof of currency.

The root cause common to all three is that "current" was defined per call site.
This module defines it once. A snapshot is stale when ANY of the conditions in
:func:`evaluate_leaderboard_staleness` holds, and a matching market date alone
never establishes freshness.

NO SCHEMA CHANGE
----------------
Everything below is expressed against columns that already exist.
``pokemon_public_rip_leaderboard_snapshots.ca7_version`` is a HISTORICAL column
name from when the appeal input was legacy CA7; it carries the canonical
Collector Appeal version, whichever that currently is. The two identifiers with
no column of their own - the public contract version and the supported-cohort
fingerprint - live in the existing free-form ``diagnostics_json``, which is what
:func:`build_publication_diagnostics` writes and
:func:`read_published_identity` reads back.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V4_VERSION
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    canonical_public_rip_contract_version,
)

logger = logging.getLogger(__name__)

# The identifiers under which the leaderboard is published, and the
# diagnostics_json keys that carry the two with no dedicated column.
DIAGNOSTICS_CONTRACT_VERSION_KEY = "public_rip_contract_version"
DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY = "collector_appeal_version"
DIAGNOSTICS_COHORT_FINGERPRINT_KEY = "supported_cohort_fingerprint"
DIAGNOSTICS_COHORT_KEYS_KEY = "supported_cohort_keys"
DIAGNOSTICS_SOURCE_RUN_IDS_KEY = "source_calculation_run_ids"

# Staleness reason codes. Branch on these, not on prose.
REASON_SNAPSHOT_MISSING = "snapshot_missing"
REASON_FINANCIAL_VERSION = "financial_rip_version_not_canonical"
REASON_COLLECTOR_APPEAL_VERSION = "collector_appeal_version_not_canonical"
REASON_OVERALL_VERSION = "overall_rip_version_not_canonical"
REASON_CONTRACT_VERSION = "public_rip_contract_version_not_canonical"
REASON_SOURCE_RUN_SUPERSEDED = "source_simulation_run_superseded"
REASON_COHORT_FINGERPRINT = "supported_cohort_fingerprint_changed"
REASON_ROW_COUNT = "ranked_row_count_does_not_match_supported_cohort"
REASON_NOT_COMPLETE = "publication_status_not_complete"
REASON_NOT_PUBLISHED = "published_at_missing"

SUPPORTED_COHORT_FINGERPRINT_VERSION = "supported_opening_cohort_fingerprint_v1"

# --- Canonical checklist Set Value publication contract ----------------------
#
# WHY THIS IS PART OF THE PUBLICATION CONTRACT
# --------------------------------------------
# The public targets reader used to call
# `_enrich_rankings_payload_with_checklist_set_values` on EVERY healthy request:
# a second DB round trip against `pokemon_set_market_dashboard_snapshot_latest`
# whose only job is to fill a checklist Set Value that is MISSING. Measured
# against the live publication it filled 0 of 34 targets and cost ~403 ms - 58%
# of the response - because the rankings builder already writes the canonical
# value from `pokemon_set_value_daily_history`.
#
# It could not simply be deleted: nothing on the publish path REQUIRED the value,
# so a future builder change could have dropped it silently and turned a
# redundant read into missing public data. The fix is contract-first - make the
# value a published guarantee, then let the reader trust the guarantee.
#
# THE SMALLEST CONTRACT THAT PROVES THE GUARANTEE
# ------------------------------------------------
# Exactly the fields the compatibility layer could have written, and nothing
# else. Requiring less would leave a field the reader stops filling and the
# publisher never checks; requiring more would pin aliases the one builder
# assignment already derives from the same variable.
PUBLIC_SET_VALUE_CONTRACT_VERSION = "public_rip_set_value_contract_v1"

CANONICAL_SET_VALUE_FIELD = "checklistSetValue"
SET_VALUE_VALUE_FIELDS = (
    CANONICAL_SET_VALUE_FIELD,
    "checklist_set_value",
    "currentChecklistSetValue",
    "current_checklist_set_value",
)
SET_VALUE_AS_OF_FIELDS = ("checklistSetValueAsOf", "checklist_set_value_as_of")

SET_VALUE_COVERAGE_COMPLETE = "complete"
SET_VALUE_COVERAGE_PARTIAL = "partial"


def _positive_float(value: Any) -> Optional[float]:
    """A strictly positive number, or None. Strings are NOT coerced.

    A Set Value that arrives as ``"561.26"`` is a serialization defect, not a
    value: it compares wrong, sorts wrong and formats wrong downstream. The
    contract must fail on it rather than quietly accept a shape the builder
    never produces.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number <= 0:  # NaN or non-positive
        return None
    return number


def set_value_contract_problems(
    target: Mapping[str, Any], *, market_date: Optional[str] = None
) -> List[str]:
    """Every way ONE target fails the canonical checklist Set Value contract.

    A LIST, for the same reason every other check in this module returns one: a
    target missing the value and a target whose as-of drifted off the market date
    are different defects, and reporting only the first sends an operator back
    for a second publication run to discover the rest.

    ``market_date`` is the publication's own market date. The as-of is required
    to equal it because the builder resolves the value from
    ``pokemon_set_value_daily_history`` AT the current published snapshot date -
    a value carrying any other date was not built for this publication.
    """
    label = str(
        target.get("canonical_key") or target.get("set_id") or target.get("target_id") or "target"
    )
    problems: List[str] = []
    canonical = _positive_float(target.get(CANONICAL_SET_VALUE_FIELD))
    if canonical is None:
        problems.append(f"{label}: {CANONICAL_SET_VALUE_FIELD} is missing or not a positive number")
    else:
        for field in SET_VALUE_VALUE_FIELDS[1:]:
            if _positive_float(target.get(field)) != canonical:
                problems.append(f"{label}: {field} does not match {CANONICAL_SET_VALUE_FIELD}")
    expected_as_of = str(market_date)[:10] if market_date else None
    for field in SET_VALUE_AS_OF_FIELDS:
        observed = _text(target.get(field))
        if observed is None:
            problems.append(f"{label}: {field} is missing")
        elif expected_as_of and observed[:10] != expected_as_of:
            problems.append(
                f"{label}: {field} is {observed!r}; the publication market date is {expected_as_of!r}"
            )
    return problems


def evaluate_set_value_coverage(
    targets: Sequence[Mapping[str, Any]], *, market_date: Optional[str] = None
) -> Dict[str, Any]:
    """The Set Value capability marker a publication carries in its metadata.

    Computed over EVERY target in the payload, not just the ranked cohort, because
    the reader serves every target and the marker is what lets it skip the
    compatibility fill for all of them.

    Coverage is ``complete`` only when every target satisfies the contract.
    A discovery-only target that is not yet ranked - a newly onboarded set whose
    daily set-value history has not started - legitimately has no canonical value;
    that publishes normally and reports ``partial``, and the reader keeps filling
    it. Publication is refused only for RANKED targets, which the publisher gates
    separately. Encoding the exception is what keeps the guarantee honest instead
    of making a normal onboarding fail to publish.
    """
    resolved = [target for target in targets if isinstance(target, Mapping)]
    covered = [
        target
        for target in resolved
        if not set_value_contract_problems(target, market_date=market_date)
    ]
    return {
        "version": PUBLIC_SET_VALUE_CONTRACT_VERSION,
        "coverage": (
            SET_VALUE_COVERAGE_COMPLETE
            if resolved and len(covered) == len(resolved)
            else SET_VALUE_COVERAGE_PARTIAL
        ),
        "targetCount": len(resolved),
        "coveredTargetCount": len(covered),
        "asOf": str(market_date)[:10] if market_date else None,
    }


def payload_guarantees_canonical_set_value(payload: Mapping[str, Any]) -> bool:
    """Was this persisted payload published under the Set Value guarantee?

    THE READER'S ONE QUESTION. "The field happens to be present" is deliberately
    not the test: that is a property of the row the reader is holding, not proof
    of the contract it was published under, and it cannot distinguish a payload
    published before the guarantee existed from one published after it.

    Fails CLOSED, exactly like `evaluate_leaderboard_staleness`: an absent or
    unrecognised marker means the compatibility fill still runs. A legacy payload
    therefore keeps its existing behaviour without knowing anything about this.
    """
    if not isinstance(payload, Mapping):
        return False
    meta = payload.get("meta")
    meta = meta if isinstance(meta, Mapping) else {}
    snapshot = meta.get("snapshot")
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    marker = snapshot.get("setValueContract")
    marker = marker if isinstance(marker, Mapping) else {}
    return (
        _text(marker.get("version")) == PUBLIC_SET_VALUE_CONTRACT_VERSION
        and _text(marker.get("coverage")) == SET_VALUE_COVERAGE_COMPLETE
    )


def canonical_publication_identity() -> Dict[str, str]:
    """The four version identifiers a current publication must carry.

    Read from the ONE canonical selection in ``scoring_config`` (and, for the
    appeal, from ``collector_appeal``). Nothing here restates a version literal -
    a second copy of a cutover switch is a second cutover, and the defect this
    module exists to fix was exactly that.
    """
    return {
        "financialRipVersion": CANONICAL_FINANCIAL_RIP_VERSION,
        "collectorAppealVersion": COLLECTOR_APPEAL_V4_VERSION,
        "overallRipVersion": CANONICAL_OVERALL_RIP_VERSION,
        "publicRipContractVersion": canonical_public_rip_contract_version(),
    }


def supported_cohort_fingerprint(keys: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """A stable fingerprint of the AUTHORITATIVE supported opening cohort.

    ``keys`` defaults to ``opening_simulation_gate.supported_opening_set_keys()``
    - the single definition of "simulation-supported", shared with the metadata
    sync, the freshness gate and the publication audit. Support is deliberately
    NOT inferred from whether a V3 score happens to exist: a set whose simulation
    failed would then silently leave the cohort and shrink every denominator
    without anything recording that the population changed.

    Sorted before hashing, so the fingerprint describes the SET of supported keys
    and not the order a registry happened to enumerate them in.
    """
    if keys is None:
        from backend.db.services.opening_simulation_gate import supported_opening_set_keys

        keys = supported_opening_set_keys()
    normalized = sorted({str(key).strip() for key in keys if str(key).strip()})
    digest = hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()
    return {
        "version": SUPPORTED_COHORT_FINGERPRINT_VERSION,
        "fingerprint": digest,
        "keys": normalized,
        "count": len(normalized),
    }


def build_publication_diagnostics(
    *,
    set_ids: Sequence[str],
    cohort: Optional[Mapping[str, Any]] = None,
    source_run_ids: Optional[Mapping[str, Optional[str]]] = None,
) -> Dict[str, Any]:
    """The ``diagnostics_json`` block a publication must carry.

    Holds the two identifiers with no dedicated column (the public contract
    version and the supported-cohort fingerprint) plus the per-set source run
    IDs, so a later audit can ask "was every row built from the latest eligible
    simulation?" without re-deriving the answer from a different table than the
    publisher used.
    """
    resolved = dict(cohort) if cohort else supported_cohort_fingerprint()
    identity = canonical_publication_identity()
    return {
        "set_ids": sorted(str(set_id) for set_id in set_ids),
        DIAGNOSTICS_CONTRACT_VERSION_KEY: identity["publicRipContractVersion"],
        DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY: identity["collectorAppealVersion"],
        DIAGNOSTICS_COHORT_FINGERPRINT_KEY: resolved.get("fingerprint"),
        DIAGNOSTICS_COHORT_KEYS_KEY: list(resolved.get("keys") or []),
        "supported_cohort_count": resolved.get("count"),
        "supported_cohort_fingerprint_version": resolved.get("version"),
        DIAGNOSTICS_SOURCE_RUN_IDS_KEY: {
            str(key): (str(value) if value else None)
            for key, value in dict(source_run_ids or {}).items()
        },
    }


def read_published_identity(row: Mapping[str, Any]) -> Dict[str, Optional[str]]:
    """The four version identifiers a published snapshot row actually carries.

    ``ca7_version`` is the historical column name for the canonical Collector
    Appeal version - see the module docstring. The diagnostics copy is preferred
    when present because it is written under an unambiguous key; the column is
    the fallback so rows published before this module still read.
    """
    diagnostics = row.get("diagnostics_json")
    diagnostics = dict(diagnostics) if isinstance(diagnostics, Mapping) else {}
    appeal = diagnostics.get(DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY) or row.get("ca7_version")
    return {
        "financialRipVersion": _text(row.get("financial_rip_version")),
        "collectorAppealVersion": _text(appeal),
        "overallRipVersion": _text(row.get("overall_rip_version")),
        "publicRipContractVersion": _text(
            diagnostics.get(DIAGNOSTICS_CONTRACT_VERSION_KEY)
        ),
        "supportedCohortFingerprint": _text(
            diagnostics.get(DIAGNOSTICS_COHORT_FINGERPRINT_KEY)
        ),
    }


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def evaluate_leaderboard_staleness(
    row: Optional[Mapping[str, Any]],
    *,
    ranked_row_count: Optional[int] = None,
    latest_eligible_run_id_by_set: Optional[Mapping[str, Optional[str]]] = None,
    published_run_id_by_set: Optional[Mapping[str, Optional[str]]] = None,
    cohort: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Every reason this published leaderboard is NOT current. Empty means current.

    A LIST, not a boolean. "Stale" is one word for several different situations -
    an obsolete scoring version, a superseded simulation, a cohort that changed
    size - and collapsing them sends an operator to the wrong fix. Every reason is
    reported, not just the first, so one rebuild resolves all of them.

    A MATCHING MARKET DATE IS NOT CHECKED HERE AND NEVER ESTABLISHES FRESHNESS.
    The market date says when the prices were promoted; it says nothing about
    which formula scored them. Freshness by market date is precisely how an
    obsolete contract stayed published across a scoring cutover.

    Fails CLOSED on absent evidence: a snapshot with no contract version recorded
    is stale, because "we cannot tell which contract built this" and "it was built
    under the current contract" are not the same fact.
    """
    if not row:
        return [_reason(REASON_SNAPSHOT_MISSING, "No published leaderboard snapshot row exists.")]

    reasons: List[Dict[str, Any]] = []
    expected = canonical_publication_identity()
    observed = read_published_identity(row)

    for reason_code, key, label in (
        (REASON_FINANCIAL_VERSION, "financialRipVersion", "Financial RIP"),
        (REASON_COLLECTOR_APPEAL_VERSION, "collectorAppealVersion", "Collector Appeal"),
        (REASON_OVERALL_VERSION, "overallRipVersion", "Overall RIP"),
        (REASON_CONTRACT_VERSION, "publicRipContractVersion", "public RIP contract"),
    ):
        if observed.get(key) != expected[key]:
            reasons.append(
                _reason(
                    reason_code,
                    f"Published {label} version is {observed.get(key)!r}; canonical is "
                    f"{expected[key]!r}.",
                    observed=observed.get(key),
                    expected=expected[key],
                )
            )

    resolved_cohort = dict(cohort) if cohort else supported_cohort_fingerprint()
    expected_fingerprint = resolved_cohort.get("fingerprint")
    if observed.get("supportedCohortFingerprint") != expected_fingerprint:
        reasons.append(
            _reason(
                REASON_COHORT_FINGERPRINT,
                "Published supported-cohort fingerprint "
                f"{observed.get('supportedCohortFingerprint')!r} does not match the current "
                f"authoritative cohort ({resolved_cohort.get('count')} sets).",
                observed=observed.get("supportedCohortFingerprint"),
                expected=expected_fingerprint,
            )
        )

    expected_count = resolved_cohort.get("count")
    actual_count = ranked_row_count
    if actual_count is None:
        actual_count = row.get("eligible_cohort_count")
    if expected_count is not None and actual_count is not None and int(actual_count) != int(expected_count):
        reasons.append(
            _reason(
                REASON_ROW_COUNT,
                f"Published leaderboard has {int(actual_count)} ranked rows; the authoritative "
                f"supported cohort has {int(expected_count)}.",
                observed=int(actual_count),
                expected=int(expected_count),
            )
        )

    if str(row.get("publication_status") or "") != "complete":
        reasons.append(
            _reason(
                REASON_NOT_COMPLETE,
                f"publication_status is {row.get('publication_status')!r}, not 'complete'.",
            )
        )
    if not row.get("published_at"):
        reasons.append(_reason(REASON_NOT_PUBLISHED, "published_at is null."))

    superseded = _superseded_source_runs(
        published_run_id_by_set or {}, latest_eligible_run_id_by_set or {}
    )
    for set_key, published_run, latest_run in superseded:
        reasons.append(
            _reason(
                REASON_SOURCE_RUN_SUPERSEDED,
                f"{set_key} was published from simulation run {published_run!r}, but the latest "
                f"eligible ready/rankable run is {latest_run!r}.",
                set_key=set_key,
                observed=published_run,
                expected=latest_run,
            )
        )
    return reasons


def _superseded_source_runs(
    published: Mapping[str, Optional[str]],
    latest: Mapping[str, Optional[str]],
) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """Sets whose published row was built from a run that is no longer the latest.

    Compared by run IDENTITY rather than by timestamp. Two runs on the same day
    have the same date and are different runs, and it is the second one - the
    re-run after a fix - whose absence from the leaderboard matters.

    A set present in ``latest`` but absent from ``published`` is reported with a
    null published run: it is a supported set the leaderboard does not carry,
    which is a staleness fact and not an absence of one.
    """
    out: List[Tuple[str, Optional[str], Optional[str]]] = []
    for set_key in sorted(latest):
        latest_run = _text(latest.get(set_key))
        if latest_run is None:
            continue
        published_run = _text(published.get(set_key))
        if published_run != latest_run:
            out.append((str(set_key), published_run, latest_run))
    return out


def _reason(code: str, detail: str, **extra: Any) -> Dict[str, Any]:
    return {"code": code, "detail": detail, **extra}


def format_staleness_lines(reasons: Iterable[Mapping[str, Any]], *, tag: str) -> List[str]:
    """Greppable log lines, one per reason."""
    return [f"{tag} stale reason={reason.get('code')} detail={reason.get('detail')}" for reason in reasons]
