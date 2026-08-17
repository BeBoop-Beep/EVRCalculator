"""Build, validate and atomically publish the canonical Explore RIP leaderboard.

WHAT THIS PUBLISHES, AND WHAT IT USED TO
----------------------------------------
It publishes the CANONICAL models:

    overall_rip_score  <- target['overallRipV8']  (0.90 V3 + 0.10 Collector Appeal V4)
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
import json
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


# Superseded public contracts that are BUILT canonically but not PERSISTED into the
# `_latest` Rankings row.
#
# WHY THEY ARE DROPPED HERE AND NOWHERE ELSE
# ------------------------------------------
# GET /explore/rip-statistics/targets was measured at ~861 ms HTTP / ~714 ms
# PostgREST, of which ~600 ms is purely moving a 2.8 MB JSON document across the DB
# boundary (a metadata-only query on the same row, index and connection is 67.5 ms).
# SQL is 0.117 ms planned / ~48 ms with a forced detoast, and the lookup already uses
# its UNIQUE (tcg, scope) primary key, so the document itself is the cost. These three
# blocks are 982,110 bytes - 37.47% of all target bytes.
#
# Dropping them is safe because nothing that reads the persisted row consumes them:
#   * the set page keeps them - `_merge_canonical_rip_contract_into_set_payload`
#     lifts V4/V5/V6 from `get_rip_statistics_targets_payload()`, the LIVE builder,
#     so set Insights is unaffected by what this artifact stores;
#   * `_score_contract_problems` validates `publicRipContractV8` only;
#   * `attach_daily_rip_rank_movements` reads ids plus `overallRipV8.rank` /
#     `financialRipV3.rank`;
#   * `canonicalRipV7.mjs` has "deliberately no third step" and never falls back to
#     V5/V6 - they are different models, not shape variants;
#   * no `getRipStatisticsTargets` consumer reads them.
#
# The builders in backend/desirability/public_rip_contract_v{4,5,6}.py are deliberately
# untouched: other endpoints still need them.
LEGACY_CONTRACT_KEYS_NOT_PERSISTED_IN_LATEST = (
    "publicRipContractV4",
    "publicRipContractV5",
    "publicRipContractV6",
)


# The RAW Financial RIP V3 calculation-run document, dropped from `_latest` for a
# different reason than the superseded contracts above.
#
# IT IS NOT A snake_case ALIAS OF `financialRipV3`. It is the JSONB document stored
# on the `calculation_runs` row, and it is the INPUT that produces the camel object:
#
#     calculation_runs.financial_rip_v3_payload      raw simulation document
#       -> _build_financial_rip_v3(target)           score / status / components
#         -> target["financialRipV3"]
#           -> _rank_financial_rip_v3                rank / tier / relativeScore / cohortSize
#             -> publicRipContractV8.financialRip    public packaging
#
# That lineage is also the 34-vs-22 coverage answer: 22 targets have a V3 run, and
# the remaining 12 carry `financialRipV3.status == "unavailable"` with
# `statusReason == "no_financial_rip_v3_payload_on_latest_run"`. The camel object is
# the computed verdict (all 34); the raw document exists only where a run does (22).
#
# Byte anatomy of the pair on the live payload, over the 22 populated targets:
#   audit                    184,080 B in BOTH, byte-identical 22/22  <- 62% of the pair
#   distributionDisclosures   16,898 B in both AND in V7, identical
#   depthAndRobustness        12,605 B in both AND in V7, identical
#   components                55,748 camel / 68,932 snake  (different shapes)
#   snake-only  estimationDiagnostics 4,782, tailContractVersion 660,
#               configVersion 616, packCost 97
# The two objects were never byte-identical at the top level only because their key
# SETS differ - which is why "0/34 identical pairs" was not evidence of independence.
#
# Nothing reads the raw document from THIS artifact:
#   * the frontend has ZERO references to `financial_rip_v3_payload`;
#   * `_merge_canonical_rip_contract_into_set_payload` lifts `financialRipV3` into
#     the set page payload but NOT the raw document;
#   * the publisher, publication contract, `attach_daily_rip_rank_movements` and the
#     snapshot reader never reference it;
#   * `audit_financial_rip_v3_inputs.py` / `compare_financial_rip_v2_v3.py` read the
#     `explore_rip_statistics_latest` VIEW, not this table.
#
# The live builder still produces and consumes it, so only persistence changes.
RAW_CALCULATION_DOCUMENT_KEYS_NOT_PERSISTED_IN_LATEST = ("financial_rip_v3_payload",)

# The complete removal set applied to each target of the persisted `_latest` payload.
TARGET_KEYS_NOT_PERSISTED_IN_LATEST = (
    LEGACY_CONTRACT_KEYS_NOT_PERSISTED_IN_LATEST
    + RAW_CALCULATION_DOCUMENT_KEYS_NOT_PERSISTED_IN_LATEST
)


def project_latest_rankings_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the payload to persist in `_latest`, minus the superseded contracts.

    NON-DESTRUCTIVE BY CONSTRUCTION. The caller's payload is the object publication
    validation and the historical leaderboard rows were built from, so this copies
    rather than mutating: the complete canonical document must remain exactly what
    was validated and what history stores.
    """
    if not isinstance(payload, dict):
        return payload

    targets = payload.get("targets")
    if not isinstance(targets, list):
        return payload

    projected_targets = []
    for target in targets:
        if not isinstance(target, dict):
            projected_targets.append(target)
            continue
        projected_targets.append(
            {key: value for key, value in target.items() if key not in TARGET_KEYS_NOT_PERSISTED_IN_LATEST}
        )

    return {**payload, "targets": projected_targets}


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
    contract = target.get("publicRipContractV9") or {}
    problems = []
    if not contract:
        return [f"{label}: publicRipContractV9 is missing"]
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
    collector_components = (contract.get("collectorAppeal") or {}).get("components") or {}
    for name in ("rosterDesirability", "desirableOutcomeFrequency"):
        component = collector_components.get(name) or {}
        for field in ("rank", "tier", "rankedSetCount", "relativeScore"):
            if component.get(field) is None:
                problems.append(f"{label}: collectorAppeal.components.{name}.{field} is missing")
    modeled_pokemon = (collector_components.get("rosterDesirability") or {}).get("modeledPokemon")
    if not isinstance(modeled_pokemon, list) or not modeled_pokemon:
        problems.append(
            f"{label}: collectorAppeal.components.rosterDesirability.modeledPokemon is missing"
        )
    else:
        for index, pokemon in enumerate(modeled_pokemon):
            if not isinstance(pokemon, dict):
                problems.append(
                    f"{label}: collectorAppeal.components.rosterDesirability."
                    f"modeledPokemon[{index}] is malformed"
                )
                continue
            for field in ("name", "desirabilityScore"):
                if pokemon.get(field) is None:
                    problems.append(
                        f"{label}: collectorAppeal.components.rosterDesirability."
                        f"modeledPokemon[{index}].{field} is missing"
                    )
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
    # The canonical ranked cohort: targets carrying an Overall RIP V8 rank.
    targets = [target for target in all_targets if _ranked(target, "overallRipV9")]
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
            f"incomplete Overall RIP V8 cohort expected={ranked_count} actual={len(targets)}"
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
    # Overall RIP v4 ranked cohort to match the canonical one, because migration
    # 054's RPC counted ranked targets by `rip.rank` and would otherwise have
    # thrown an opaque exception from inside the transaction.
    #
    # Migration 061 repointed the RPC at `overallRipV7.rank` and made it check
    # `publicRipContractV7.contractVersion` itself; migration 062 moves both to
    # `overallRipV8` and `publicRipContractV8` for the Collector Appeal V4
    # cutover. The database is authoritative about the canonical cohort, so this
    # check no longer guards anything - it only kept a retired model
    # load-bearing for a publication that does not consult it.
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
        "overall_rip_score": (target.get("overallRipV9") or {}).get("score"),
        "overall_rip_rank": (target.get("overallRipV9") or {}).get("rank"),
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
        if isinstance(target, dict) and (target.get("overallRipV9") or {}).get("rank") is not None
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

    # ORDER MATTERS. The projection runs AFTER validation and AFTER movement, so the
    # publication contract, the Set Value coverage check and the 1D rank movement all
    # still see the complete canonical payload. Only the `_latest` row - the single
    # artifact GET /explore/rip-statistics/targets reads, and the one whose size was
    # measured as the bottleneck - is slimmed. `snapshot`/`history_rows` are passed
    # through untouched, so the historical leaderboard keeps the full document and
    # tomorrow's `previous_calendar_day_payload` comparison is byte-for-byte unchanged.
    latest_row = {
        **row,
        "ranking_payload_json": project_latest_rankings_payload(row["ranking_payload_json"]),
    }
    full_bytes = len(json.dumps(row["ranking_payload_json"], default=str))
    slim_bytes = len(json.dumps(latest_row["ranking_payload_json"], default=str))
    logger.info(
        "[rankings-publish] _latest payload projection: %s -> %s bytes (-%s, -%.1f%%) removed=%s",
        full_bytes,
        slim_bytes,
        full_bytes - slim_bytes,
        (100.0 * (full_bytes - slim_bytes) / full_bytes) if full_bytes else 0.0,
        ",".join(TARGET_KEYS_NOT_PERSISTED_IN_LATEST),
    )

    if not commit:
        logger.info("[dry-run] validated complete RIP publication market_date=%s rows=%s",
                    snapshot["market_date"], len(history_rows))
        return row
    client.rpc("publish_pokemon_public_rip_leaderboard", {
        "p_snapshot": snapshot, "p_rows": history_rows, "p_latest": latest_row,
    }).execute()
    return row
