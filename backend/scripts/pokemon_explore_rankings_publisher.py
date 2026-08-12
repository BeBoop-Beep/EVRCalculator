"""Build, validate and atomically publish the canonical Explore RIP leaderboard.

WHAT THIS PUBLISHES, AND WHAT IT USED TO
----------------------------------------
It publishes the CANONICAL models:

    overall_rip_score  <- target['overallRipV7']  (0.90 V3 + 0.10 Collector Appeal V3)
    financial_rip_score<- target['financialRipV3'] (six-component, fixed anchors)

It previously read ``target['rip']`` (Overall RIP v4, off the Financial RIP V2
pillars and legacy CA7) and ``target['ripCore']`` (Financial RIP V2), and was
never repointed when the V3, V5, V6 or V7 cutovers landed. That is why the newest
published leaderboard reported ``overall_rip_v4_90_financial_10_ca7`` and
``financial_rip_v2_60_25_15`` while 22 fresh Financial RIP V3 simulations sat
underneath it - the publisher was faithfully publishing the legacy objects, and
the version strings it copied alongside them were accurate about that, so nothing
downstream contradicted it.

THE VERSIONS ARE VERIFIED, NOT JUST COPIED
------------------------------------------
``meta.ripWeightsConfig`` is still the source of the version strings written into
the snapshot row, but they are now CHECKED against the one canonical selection in
``scoring_config`` before anything is written. A payload built by an older worker,
or a metadata block left behind by the next cutover, refuses to publish instead of
quietly minting a snapshot under a superseded contract.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from backend.db.services.public_rip_publication_contract import (
    PUBLIC_SET_VALUE_CONTRACT_VERSION,
    build_publication_diagnostics,
    canonical_publication_identity,
    evaluate_set_value_coverage,
    set_value_contract_problems,
    supported_cohort_fingerprint,
)
from backend.scripts.pokemon_snapshot_builders import (
    DEFAULT_RANKINGS_LIMIT,
    attach_daily_rip_rank_movements,
    build_explore_rankings_snapshot_row,
)

logger = logging.getLogger(__name__)


def _ranked(target: Dict[str, Any], key: str) -> bool:
    return (target.get(key) or {}).get("rank") is not None


# The canonical score contract every ranked target must satisfy. Both layers are
# required, on every pillar and every weighted component:
#
#   ABSOLUTE - the formula output. Cohort independent; what the blend consumes
#              and what historical comparisons are made against.
#   RELATIVE - min-max position within the ranked cohort. The primary public
#              display score, and never an input to any formula.
#
# A supported set missing either layer FAILS publication rather than being
# dropped from the cohort. Dropping it would shrink every denominator and change
# every relative score without anything recording that the population moved -
# which is indistinguishable, downstream, from the set genuinely not existing.
REQUIRED_SCORE_FIELDS = (
    "score", "absoluteScore", "relativeScore", "rank", "tier", "rankedSetCount",
)
REQUIRED_PILLAR_FIELDS = REQUIRED_SCORE_FIELDS + ("cohortFingerprint",)
CANONICAL_PILLARS = ("overallRip", "financialRip", "collectorAppeal")


def _score_contract_problems(target: Dict[str, Any]) -> list:
    """Every missing canonical absolute/relative value on ONE ranked target.

    A LIST, not a boolean, and never the first failure only: a set missing four
    component relative scores and a set missing one are different situations, and
    reporting one of them sends an operator back for a second run to discover the
    rest.
    """
    label = target.get("canonical_key") or target.get("set_id") or target.get("target_id")
    contract = target.get("publicRipContractV7") or {}
    problems = []
    if not contract:
        return [f"{label}: publicRipContractV7 is missing"]
    for pillar in CANONICAL_PILLARS:
        block = contract.get(pillar) or {}
        for field in REQUIRED_PILLAR_FIELDS:
            if block.get(field) is None:
                problems.append(f"{label}: {pillar}.{field} is missing")
    components = (contract.get("financialRip") or {}).get("components") or {}
    for name, component in sorted(components.items()):
        if not isinstance(component, dict):
            problems.append(f"{label}: financialRip.components.{name} is malformed")
            continue
        for field in REQUIRED_SCORE_FIELDS:
            if component.get(field) is None:
                problems.append(f"{label}: financialRip.components.{name}.{field} is missing")
    return problems


def publication_contract(row):
    payload = row["ranking_payload_json"]
    meta = payload.get("meta") or {}
    cohort = meta.get("publicAnalyticsCohort") or {}
    versions = meta.get("ripWeightsConfig") or {}
    canonical = canonical_publication_identity()
    market_date = str((meta.get("comparisonSnapshots") or {}).get("currentMarketDate") or "")[:10]
    overall_ranked = cohort.get("overallRanked") or {}
    ranked_count = int(overall_ranked.get("rankedSetCount") or 0)
    financial_count = int(cohort.get("eligibleSetCount") or 0)

    all_targets = list(payload.get("targets") or [])
    # The canonical ranked cohort: targets carrying an Overall RIP V7 rank.
    targets = [target for target in all_targets if _ranked(target, "overallRipV7")]
    appeal_versions = sorted({
        str(((target.get("openingExperience") or {}).get("collectorAppeal") or {}).get("version"))
        for target in targets
        if ((target.get("openingExperience") or {}).get("collectorAppeal") or {}).get("version")
    })
    overall_version = (versions.get("overallRip") or {}).get("version")
    financial_version = (versions.get("financialRip") or {}).get("version")
    contract_version = (versions.get("publicContract") or {}).get("version")
    cohort_version = cohort.get("version")
    built_at = (meta.get("snapshot") or {}).get("builtAt")
    supported = supported_cohort_fingerprint()

    problems = []
    if not market_date:
        problems.append("missing market date")
    if not built_at:
        problems.append("missing built timestamp")
    if ranked_count <= 0 or len(targets) != ranked_count:
        problems.append(
            f"incomplete Overall RIP V7 cohort expected={ranked_count} actual={len(targets)}"
        )
    if financial_count <= 0:
        problems.append("missing Financial RIP cohort count")
    if len(appeal_versions) != 1:
        problems.append(f"incompatible Collector Appeal versions={appeal_versions}")
    elif appeal_versions[0] != canonical["collectorAppealVersion"]:
        problems.append(
            f"Collector Appeal version {appeal_versions[0]!r} is not the canonical "
            f"{canonical['collectorAppealVersion']!r}"
        )
    if any(not _ranked(target, "financialRipV3") for target in targets):
        problems.append("missing Financial RIP V3 rank")
    # Versions are VERIFIED against the canonical selection, never merely copied.
    for label, observed, expected in (
        ("Overall RIP", overall_version, canonical["overallRipVersion"]),
        ("Financial RIP", financial_version, canonical["financialRipVersion"]),
        ("public RIP contract", contract_version, canonical["publicRipContractVersion"]),
    ):
        if not observed:
            problems.append(f"missing {label} version")
        elif observed != expected:
            problems.append(f"{label} version {observed!r} is not the canonical {expected!r}")
    if not cohort_version:
        problems.append("missing cohort version")
    if supported["count"] and len(targets) != supported["count"]:
        problems.append(
            f"ranked cohort size {len(targets)} does not match the authoritative supported "
            f"cohort of {supported['count']} sets"
        )
    # The transitional legacy-cohort precondition stood here. It required the
    # Overall RIP v4 ranked cohort to match the canonical V7 one, because
    # migration 054's RPC counted ranked targets by `rip.rank` and would
    # otherwise have thrown an opaque exception from inside the transaction.
    #
    # Migration 061 repointed the RPC at `overallRipV7.rank` and made it check
    # `publicRipContractV7.contractVersion` itself; it is applied in production
    # (the live function body reads `overallRipV7` and no longer contains
    # `{rip,rank}`). The database is now authoritative about the canonical
    # cohort, so this check no longer guards anything - it only kept a retired
    # model load-bearing for a publication that does not consult it.
    #
    # Both score layers, on every pillar and every weighted component, for every
    # supported set. Reported in full rather than as a count so one rerun fixes
    # everything that is wrong.
    score_problems = [
        problem for target in targets for problem in _score_contract_problems(target)
    ]
    # THE CANONICAL CHECKLIST SET VALUE IS PART OF THE PUBLICATION, NOT A
    # DECORATION. The public targets reader previously re-read
    # `pokemon_set_market_dashboard_snapshot_latest` on every healthy request to
    # fill this value if it was absent - 58% of the response time to change
    # nothing. That fill can only be retired if the value is guaranteed here, so
    # a ranked target without it now fails publication for the same reason a
    # ranked target without a relative score does: publishing it would put an
    # incomplete public record in front of visitors.
    #
    # RANKED targets only. An unranked discovery target may legitimately predate
    # its own set-value history (a newly onboarded set does), and that case is
    # reported through the coverage marker instead of breaking publication.
    score_problems.extend(
        problem
        for target in targets
        for problem in set_value_contract_problems(target, market_date=market_date)
    )
    problems.extend(score_problems[:40])
    if len(score_problems) > 40:
        problems.append(f"...and {len(score_problems) - 40} further missing canonical score values")
    if problems:
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: " + "; ".join(problems))

    ids = sorted(str(target.get("set_id") or target.get("target_id")) for target in targets)
    source_run_ids = {
        str(target.get("canonical_key") or target.get("set_id") or target.get("target_id")):
            target.get("calculation_run_id")
        for target in targets
    }
    snapshot = {
        "id": str(uuid4()), "market_date": market_date,
        "built_at": built_at,
        "eligible_cohort_count": ranked_count, "cohort_version": cohort_version,
        "cohort_fingerprint": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
        "overall_rip_version": overall_version, "financial_rip_version": financial_version,
        # HISTORICAL COLUMN NAME. `ca7_version` dates from when the appeal input
        # was legacy CA7; it carries the canonical Collector Appeal version. The
        # column is part of the snapshot table's uniqueness key, so renaming it
        # would be a migration for no behavioural gain - the diagnostics block
        # below records the same value under an unambiguous key.
        "ca7_version": appeal_versions[0],
        "diagnostics": build_publication_diagnostics(
            set_ids=ids, cohort=supported, source_run_ids=source_run_ids
        ),
    }
    rows = [{
        "set_id": target.get("set_id") or target.get("target_id"),
        "set_canonical_key": target.get("canonical_key") or target.get("slug"),
        "overall_rip_score": (target.get("overallRipV7") or {}).get("score"),
        "overall_rip_rank": (target.get("overallRipV7") or {}).get("rank"),
        "financial_rip_score": (target.get("financialRipV3") or {}).get("score"),
        "financial_rip_rank": (target.get("financialRipV3") or {}).get("rank"),
        "overall_ranked_cohort_count": ranked_count,
        "financial_ranked_cohort_count": financial_count,
        "simulation_calculation_run_id": target.get("calculation_run_id"),
        "source_market_date": market_date, "pack_price": target.get("pack_cost"),
    } for target in targets]
    return snapshot, rows


def attach_publication_metadata(row: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Write the publication metadata the reader is entitled to trust.

    `publicationId` and `marketDate` identify the publication. `setValueContract`
    is the CAPABILITY marker: it records that this payload was built under the
    canonical checklist Set Value contract and whether every served target
    satisfies it. The reader skips its compatibility fill on that marker rather
    than on "the field happens to be present", because presence is a property of
    the row in hand and says nothing about the contract it was published under -
    which is exactly what distinguishes a payload published before this guarantee
    from one published after it.

    Coverage is measured over EVERY target in the payload, ranked or not, because
    the reader serves them all.
    """
    payload = row["ranking_payload_json"]
    payload.setdefault("meta", {}).setdefault("snapshot", {}).update({
        "publicationId": snapshot["id"],
        "marketDate": snapshot["market_date"],
        "setValueContract": evaluate_set_value_coverage(
            payload.get("targets") or [], market_date=snapshot["market_date"]
        ),
    })
    return row


def previous_calendar_day_payload(client: Any, market_date: str) -> Optional[Dict[str, Any]]:
    previous_date = (date.fromisoformat(market_date) - timedelta(days=1)).isoformat()
    result = (client.table("pokemon_public_rip_leaderboard_snapshots").select("payload_json")
              .eq("market_date", previous_date).eq("publication_status", "complete")
              .limit(1).execute())
    rows = list(result.data or [])
    return rows[0].get("payload_json") if rows else None


def _reuse_publication_id(client: Any, snapshot: Dict[str, Any]) -> None:
    query = client.table("pokemon_public_rip_leaderboard_snapshots").select("id")
    for field in ("market_date", "cohort_version", "overall_rip_version", "financial_rip_version", "ca7_version"):
        query = query.eq(field, snapshot[field])
    rows = list(query.limit(1).execute().data or [])
    if rows and rows[0].get("id"):
        snapshot["id"] = str(rows[0]["id"])


def _stable_uuid(value: Any, *, label: str) -> str:
    if not value:
        raise RuntimeError(f"Refusing to publish Explore RIP leaderboard: {label} is missing")
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError(
            f"Refusing to publish Explore RIP leaderboard: {label} is not a valid UUID"
        ) from exc


def validate_publication_payload(
    row: Dict[str, Any], snapshot: Dict[str, Any], history_rows: list[Dict[str, Any]]
) -> None:
    """Catch malformed publication parameters before invoking the authoritative RPC."""
    payload = row.get("ranking_payload_json")
    targets = payload.get("targets") if isinstance(payload, dict) else None
    if not isinstance(targets, list):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: latest targets must be an array")
    expected = int(snapshot.get("eligible_cohort_count") or 0)
    ranked_targets = [
        target for target in targets
        if isinstance(target, dict) and (target.get("overallRipV7") or {}).get("rank") is not None
    ]
    if expected <= 0 or len(ranked_targets) != expected:
        raise RuntimeError(
            "Refusing to publish Explore RIP leaderboard: ranked target count "
            f"expected={expected} actual={len(ranked_targets)}"
        )
    if len(history_rows) != expected:
        raise RuntimeError(
            "Refusing to publish Explore RIP leaderboard: history row count "
            f"expected={expected} actual={len(history_rows)}"
        )
    ranked_ids = [
        _stable_uuid(target.get("set_id") or target.get("target_id"), label="ranked target set ID")
        for target in ranked_targets
    ]
    history_ids = [
        _stable_uuid(history.get("set_id"), label="history row set ID")
        for history in history_rows
    ]
    if len(set(ranked_ids)) != len(ranked_ids):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: duplicate ranked target set IDs")
    if len(set(history_ids)) != len(history_ids):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: duplicate history row set IDs")
    if set(ranked_ids) != set(history_ids):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: ranked target/history set IDs differ")
    snapshot_meta = ((payload.get("meta") or {}).get("snapshot") or {})
    publication_id = snapshot_meta.get("publicationId")
    if not publication_id:
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: publicationId is missing")
    if str(publication_id) != str(snapshot.get("id")):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: publicationId does not match snapshot")
    market_date = snapshot_meta.get("marketDate")
    if not market_date:
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: marketDate is missing")
    if str(market_date) != str(snapshot.get("market_date")):
        raise RuntimeError("Refusing to publish Explore RIP leaderboard: marketDate does not match snapshot")
    marker = snapshot_meta.get("setValueContract") or {}
    if marker.get("version") != PUBLIC_SET_VALUE_CONTRACT_VERSION:
        raise RuntimeError(
            "Refusing to publish Explore RIP leaderboard: set value contract marker is missing "
            f"or not {PUBLIC_SET_VALUE_CONTRACT_VERSION!r}"
        )
    if str(marker.get("asOf") or "") != str(snapshot.get("market_date")):
        raise RuntimeError(
            "Refusing to publish Explore RIP leaderboard: set value contract marker as-of does not "
            "match snapshot"
        )


def publish_explore_rip_rankings_snapshot(
    client: Any, *, limit: int = DEFAULT_RANKINGS_LIMIT,
    market_date: Optional[str] = None, commit: bool = True,
) -> Dict[str, Any]:
    """Build, validate, enrich, and atomically publish the canonical RIP leaderboard."""
    row = build_explore_rankings_snapshot_row(limit=limit)
    snapshot, history_rows = publication_contract(row)
    if market_date and snapshot["market_date"] != market_date:
        raise RuntimeError(
            f"Refusing to backdate Explore RIP leaderboard: built market date "
            f"{snapshot['market_date']} does not match requested {market_date}"
        )
    previous = previous_calendar_day_payload(client, snapshot["market_date"])
    row["ranking_payload_json"] = attach_daily_rip_rank_movements(row["ranking_payload_json"], previous)
    if commit:
        _reuse_publication_id(client, snapshot)
    attach_publication_metadata(row, snapshot)
    validate_publication_payload(row, snapshot, history_rows)
    if not commit:
        logger.info("[dry-run] validated complete RIP publication market_date=%s rows=%s",
                    snapshot["market_date"], len(history_rows))
        return row
    client.rpc("publish_pokemon_public_rip_leaderboard", {
        "p_snapshot": snapshot, "p_rows": history_rows, "p_latest": row,
    }).execute()
    return row
