"""THE production Collector Appeal service: one place that computes CA7.

WHAT THIS OWNS
--------------
D, P, CA7, Chase Appeal, the specific printings behind each subject's two paths,
and a truthful account of what is unavailable and why - for every set, in one
batch, cached.

WHAT THIS DOES NOT OWN
----------------------
**Ranks, tiers and the public cohort.** They are computed by
``explore_rip_statistics_service``, which is the only component that knows both
the simulated cohort and the eligibility policy. A rank is a property of a
cohort, so computing ranks here - against whatever sets happened to have CA7 -
would produce a second, quietly different denominator from the one the RIP ranks
use. That is the defect this phase exists to remove; reintroducing it one layer
down would not be an improvement.

This service therefore answers "what is this set's Collector Appeal?" and never
"where does it place?".

REUSE, NOT REIMPLEMENTATION
---------------------------
Every number here comes from the module that defines it:

  * D            <- ``universal_set_desirability_service`` (the SAME bundle the
                    public Universal Desirability reader serves, so the two can
                    never disagree about a set's desirability)
  * P            <- ``collector_appeal.compute_dual_path_depth``
  * CA7          <- ``collector_appeal.compute_collector_appeal`` (frozen)
  * Chase Appeal <- ``collector_appeal.compute_chase_appeal``
  * M*           <- ``factorized_opening_appeal.compute_m_star_m1``
  * subjects     <- ``collector_appeal_inputs.build_subject_index``
  * paths        <- ``collector_appeal_inputs.select_subject_paths``

No formula constant and no version string is restated in this file. If a value
appears here that is not read from one of the above, that is a bug.

NO FALLBACK
-----------
When CA7 is unavailable this service reports it unavailable, with a reason. It
never substitutes Universal Desirability. The two are different constructs that
share a product name, and silently serving one as the other is precisely the
confusion ``collector_appeal``'s header documents. A caller that wants D can ask
for D.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Mapping, Optional

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.universal_set_desirability_service import (
    get_universal_desirability_bundle,
)
from backend.desirability.collector_appeal import (
    CHASE_APPEAL_VERSION,
    COLLECTOR_APPEAL_VERSION,
    DUAL_PATH_DEPTH_VERSION,
    compute_chase_appeal,
    compute_collector_appeal,
    compute_dual_path_depth,
)
from backend.desirability.collector_appeal_fingerprint import current_fingerprint
from backend.desirability.collector_appeal_inputs import (
    build_subject_index,
    load_pull_rate_model,
    select_subject_paths,
)
from backend.desirability.factorized_opening_appeal import (
    compute_d1,
    compute_m_star_m1,
    demand_shares,
    desirable_subjects,
)
from backend.desirability.universal_set_desirability import COVERAGE_FULL

logger = logging.getLogger(__name__)

# Matches the Universal Desirability cache. The inputs move when a component
# rebuild or a snapshot rebuild runs - both daily jobs - so a 6h TTL cannot serve
# a score from a superseded formula for a meaningful window.
CACHE_TTL_SECONDS = 6 * 60 * 60

# Unavailable reasons. The same strings the rollout audit reports, so an operator
# reading the API and an operator reading the dry run see one vocabulary.
REASON_UNSUPPORTED = "unsupported_product_type"
REASON_COVERAGE = "desirability_coverage_not_full"
REASON_NO_PULL_MODEL = "dual_path_depth_unavailable_no_pull_model"
REASON_NO_MODELED_SUBJECT = "dual_path_depth_unavailable_no_modeled_subject"

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"

# How many explanatory subjects the contract carries. Three is what the
# "Why this score" block renders; sending the whole roster would be a payload
# cost with no consumer.
TOP_SUBJECT_LIMIT = 3

_cache: Dict[str, Any] = {"bundle": None, "builtAt": 0.0}
_cache_lock = threading.Lock()


def _to_unit(score: Any) -> Optional[float]:
    """A 0-100 desirability onto [0,1] through the canonical rescale."""
    return compute_d1(score)


def _build_subject_explanations(
    subjects: List[Mapping[str, Any]],
    depth: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """The top desirable subjects and the two printings that explain them.

    Ordered by demand SHARE - the same q_s that weights P - so the subjects shown
    are the ones actually driving the score, not merely the most famous Pokemon
    in the set.
    """
    eligible = desirable_subjects(subjects)
    if not eligible:
        return []
    shares = demand_shares(eligible)
    if not shares:
        return []

    contributions = {
        str(row.get("subject_name")): row.get("contribution")
        for row in ((depth or {}).get("top_subjects") or [])
    }

    ranked = sorted(
        eligible,
        key=lambda row: -(shares.get(str(row.get("subject_key"))) or 0.0),
    )[:TOP_SUBJECT_LIMIT]

    explanations: List[Dict[str, Any]] = []
    for row in ranked:
        paths = select_subject_paths(row)
        if paths is None:
            # No modeled printing means no path to name. Emitting the subject
            # with null paths would render a "why" with nothing in it.
            continue
        share = shares.get(str(row.get("subject_key")))
        explanations.append(
            {
                "subjectId": row.get("subject_key"),
                "subjectName": row.get("subject_name"),
                "demandScore": row.get("subject_demand"),
                "demandShare": round(share, 6) if share is not None else None,
                "dualPathContribution": contributions.get(str(row.get("subject_name"))),
                "accessiblePath": paths["accessiblePath"],
                "elitePath": paths["elitePath"],
                "printingCount": paths["printingCount"],
            }
        )
    return explanations


def _build_set_payload(
    *,
    set_id: str,
    universal_row: Mapping[str, Any],
    subjects: Optional[List[Mapping[str, Any]]],
    pull_modeled: bool,
) -> Dict[str, Any]:
    """One set's Collector Appeal, or a truthful account of why there isn't one."""
    coverage = universal_row.get("coverage") or {}
    coverage_full = coverage.get("status") == COVERAGE_FULL

    d_score = universal_row.get("score") if coverage_full else None
    d_unit = _to_unit(d_score)

    depth = compute_dual_path_depth(subjects) if subjects else None
    p_value = (depth or {}).get("value")

    magnetism = compute_m_star_m1(subjects) if subjects else None
    m_value = (magnetism or {}).get("value")

    collector_appeal = compute_collector_appeal(d_unit, p_value)
    chase_appeal = compute_chase_appeal(d_unit, m_value)

    reason: Optional[str] = None
    if d_score is None:
        reason = REASON_COVERAGE
    elif p_value is None:
        # Kept apart because they call for different fixes: "no pack model for
        # this set" is a coverage gap, while "a pack model exists but no
        # desirable subject matched it" is a join failure. Reporting the second
        # as the first sends someone to build a model that already exists.
        reason = REASON_NO_PULL_MODEL if not pull_modeled else REASON_NO_MODELED_SUBJECT

    available = collector_appeal is not None
    if available and reason is not None:  # pragma: no cover - defensive
        logger.error(
            "[collector-appeal] %s: CA7 computed but a reason was recorded (%s)", set_id, reason
        )

    return {
        "setId": set_id,
        "setName": universal_row.get("set_name"),
        "setCanonicalKey": universal_row.get("set_canonical_key"),
        "status": STATUS_AVAILABLE if available else STATUS_UNAVAILABLE,
        "asOf": universal_row.get("as_of"),
        # --- the metrics, all on their honest scales ---------------------
        "rosterDesirability": {
            "score": d_score,
            "version": universal_row.get("version"),
        },
        "dualPathDepth": {
            # P is structurally compressed: it is a coverage share, not a grade
            # out of 100, and a frontend must not rescale it into one.
            "rawValue": p_value,
            "displayPercent": round(p_value * 100.0, 1) if p_value is not None else None,
            "subjectsWithMultiplePaths": (depth or {}).get("multi_printing_subject_count"),
            "modeledSubjectCount": (depth or {}).get("subject_count"),
            "coveredDemandShare": (depth or {}).get("covered_demand_share"),
            "version": DUAL_PATH_DEPTH_VERSION,
        },
        "collectorAppeal": {
            "score": round(collector_appeal * 100.0, 4) if collector_appeal is not None else None,
            "rawValue": collector_appeal,
            "version": COLLECTOR_APPEAL_VERSION,
        },
        "chaseAppeal": {
            "score": round(chase_appeal * 100.0, 4) if chase_appeal is not None else None,
            "rawValue": chase_appeal,
            "eliteScarcity": m_value,
            "version": CHASE_APPEAL_VERSION,
            "note": (
                "Chase Appeal is a separate desirability x scarcity diagnostic. "
                "It is not a RIP pillar and is not added to the RIP score."
            ),
        },
        "topSubjects": _build_subject_explanations(subjects or [], depth),
        "coverage": {
            "status": STATUS_AVAILABLE if available else STATUS_UNAVAILABLE,
            "reasons": [reason] if reason else [],
            "pullModelAvailable": bool(pull_modeled),
            "modeledSubjectCount": (depth or {}).get("subject_count"),
            "desirabilityCoverageStatus": coverage.get("status"),
        },
    }


def _build_bundle() -> Dict[str, Any]:
    """Build every set's Collector Appeal in ONE batch.

    The reads are per-BUNDLE, never per-set: one pull-model read, one card read,
    one link read, and D comes from an already-cached bundle. A per-set build
    would turn a 21-set leaderboard into 21 x (cards + links + pull model), which
    is the N+1 this phase forbids.
    """
    started = time.perf_counter()
    universal = get_universal_desirability_bundle()
    payloads: Mapping[str, Any] = universal.get("payloads") or {}

    set_ids = sorted(payloads)
    pull_model = load_pull_rate_model(public_read_client)
    subjects_by_set = build_subject_index(public_read_client, set_ids, pull_model)

    built: Dict[str, Any] = {}
    for set_id in set_ids:
        built[set_id] = _build_set_payload(
            set_id=set_id,
            universal_row=payloads[set_id],
            subjects=subjects_by_set.get(set_id),
            pull_modeled=set_id in pull_model,
        )

    available = [row for row in built.values() if row["status"] == STATUS_AVAILABLE]
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "[collector-appeal] built %s sets (%s with CA7) in %.0fms",
        len(built), len(available), elapsed_ms,
    )

    return {
        "payloads": built,
        "coverage": {
            "setCount": len(built),
            "availableCount": len(available),
            "unavailableCount": len(built) - len(available),
            "modeledSetCount": len(pull_model),
        },
        # Internal/debug only. The fingerprint is NOT a user-facing field: it
        # answers "under what rules was this computed?", which is an operator's
        # question, and putting a 64-char hash on a product card would be
        # disclosure theatre rather than transparency.
        "identity": {
            "collectorAppealVersion": COLLECTOR_APPEAL_VERSION,
            "dualPathDepthVersion": DUAL_PATH_DEPTH_VERSION,
            "chaseAppealVersion": CHASE_APPEAL_VERSION,
            "formulaFingerprint": current_fingerprint(),
        },
        "buildMs": round(elapsed_ms, 1),
    }


def get_collector_appeal_bundle(*, force_refresh: bool = False) -> Dict[str, Any]:
    """The cached Collector Appeal bundle: ``{payloads, coverage, identity}``.

    Cached in-process for the same reason Universal Desirability is: the inputs
    change on a daily job, not per request, and the pull-model read is expensive
    (production carries ~11 MB of snapshot payload to yield the pack model - see
    ``collector_appeal_inputs`` on why that read is deliberately not optimized).
    Paying it once per TTL is the difference between a cached leaderboard and a
    research dry run on every page view.
    """
    now = time.time()
    with _cache_lock:
        bundle = _cache.get("bundle")
        fresh = bundle is not None and (now - _cache["builtAt"]) < CACHE_TTL_SECONDS
        if fresh and not force_refresh:
            return bundle

    built = _build_bundle()
    with _cache_lock:
        _cache["bundle"] = built
        _cache["builtAt"] = time.time()
    return built


def get_collector_appeal(set_id: str) -> Optional[Dict[str, Any]]:
    """One set's payload, or None when the set has no component row at all.

    None here means "this set is not in the bundle"; a set that IS in the bundle
    but has no CA7 returns a payload with ``status='unavailable'`` and a reason.
    The two are different facts and are not collapsed.
    """
    bundle = get_collector_appeal_bundle()
    return (bundle.get("payloads") or {}).get(str(set_id))


def reset_cache() -> None:
    """Drop the cache. For tests and for the snapshot builder's forced rebuild."""
    with _cache_lock:
        _cache["bundle"] = None
        _cache["builtAt"] = 0.0
