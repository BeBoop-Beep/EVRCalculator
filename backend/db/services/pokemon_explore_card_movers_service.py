from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.db.clients.supabase_client import service_read_client
from backend.desirability.public_analytics_policy import is_public_analytics_eligible
from backend.db.services.pokemon_card_market_delta_contract import (
    MOVEMENT_CONTRACT_VERSION,
    WINDOW_CONVENTION,
)
from backend.db.services.pokemon_set_market_service import canonical_card_movement_sort_key

TABLE = "pokemon_explore_card_movers_snapshot_latest"
logger = logging.getLogger("market.performance")
LIMIT = 30
class ExploreCardMoversUnavailable(Exception):
    def __init__(self, message: str, *, diagnostics: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def _text(value: Any) -> Optional[str]:
    value = str(value or "").strip()
    return value or None


def movement_identity(row: Mapping[str, Any]) -> tuple[str, str, str]:
    card_id = _text(row.get("canonicalCardId") or row.get("canonical_card_id") or row.get("cardId"))
    if not card_id:
        raise ValueError("movement is missing canonical card identity")
    return (
        card_id.lower(),
        (_text(row.get("cardVariantId") or row.get("card_variant_id")) or "").lower(),
        (_text(row.get("conditionId") or row.get("condition_id")) or "").lower(),
    )


def _source_entry(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = snapshot.get("payload_json") or {}
    by_window = payload.get("marketMoversByWindow") or payload.get("market_movers_by_window") or {}
    return by_window.get("7D") or by_window.get("7d") or {}


def _top_chase_cards(snapshot: Mapping[str, Any]) -> Optional[List[Mapping[str, Any]]]:
    payload = snapshot.get("payload_json") or {}
    cards = payload.get("topChaseCards")
    if cards is None:
        cards = payload.get("top_chase_cards")
    if not isinstance(cards, list):
        return None
    return [card for card in cards if isinstance(card, Mapping)]


def build_global_card_movers_row(
    sets: Iterable[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
    *,
    target_market_date: str,
    limit: int = LIMIT,
    built_at: Optional[str] = None,
) -> Dict[str, Any]:
    eligible = [dict(row) for row in sets if is_public_analytics_eligible(row)]
    by_set = {str(row.get("set_id")): row for row in snapshots}
    missing, stale, malformed, generation_parts, candidates = [], [], [], [], []
    top_chase_candidate_count = 0
    participating_set_count = 0
    contract_versions, conventions = set(), set()
    generation_paths = set()

    for pokemon_set in eligible:
        set_id = str(pokemon_set.get("id") or pokemon_set.get("set_id") or "")
        source = by_set.get(set_id)
        if not source:
            missing.append({"setId": set_id, "canonicalKey": pokemon_set.get("canonical_key")})
            continue
        source_date = str(source.get("latest_market_date") or "")[:10]
        if source_date != target_market_date:
            stale.append({"setId": set_id, "canonicalKey": pokemon_set.get("canonical_key"),
                          "sourceDate": source_date or None})
            continue
        payload = source.get("payload_json") or {}
        entry = _source_entry(source)
        movements = entry.get("all") if isinstance(entry, Mapping) else None
        top_chase_cards = _top_chase_cards(source)
        meta = payload.get("meta") or {}
        snapshot_meta = meta.get("snapshot") or {}
        version = (meta.get("movementContractVersion") or snapshot_meta.get("movementContractVersion")
                   or payload.get("movementContractVersion"))
        convention = (meta.get("windowConvention") or snapshot_meta.get("windowConvention")
                      or payload.get("windowConvention"))
        generation_candidates = (
            ("meta.movementGenerationId", meta.get("movementGenerationId")),
            ("meta.snapshot.generationId", snapshot_meta.get("generationId")),
            ("meta.completeness.movementGenerationId", (meta.get("completeness") or {}).get("movementGenerationId")),
            ("movementGenerationId", payload.get("movementGenerationId")),
        )
        generation_path, generation = next(((path, value) for path, value in generation_candidates if value), (None, None))
        missing_fields = []
        if not isinstance(movements, list):
            missing_fields.append("marketMoversByWindow.7D.all")
        if top_chase_cards is None:
            missing_fields.append("topChaseCards")
        if not version:
            missing_fields.append("movementContractVersion")
        if not convention:
            missing_fields.append("windowConvention")
        if not generation:
            missing_fields.append("movementGenerationId")
        if missing_fields:
            malformed.append({"setId": set_id, "canonicalKey": pokemon_set.get("canonical_key"),
                              "missingFields": missing_fields})
            continue
        generation_paths.add(str(generation_path))
        contract_versions.add(str(version))
        conventions.add(str(convention))
        generation_parts.append(f"{set_id}|{generation}")
        set_identity = {
            "setId": set_id,
            "setCanonicalKey": pokemon_set.get("canonical_key"),
            "setName": pokemon_set.get("name"),
        }
        top_chase_identities = set()
        for card in (top_chase_cards or [])[:10]:
            try:
                top_chase_identities.add(movement_identity(card)[0])
            except ValueError:
                continue
        top_chase_candidate_count += len(top_chase_identities)
        set_candidate_count = 0
        for movement in movements:
            if not isinstance(movement, Mapping):
                malformed.append({"setId": set_id, "canonicalKey": pokemon_set.get("canonical_key"),
                                  "missingFields": ["valid movement object"]})
                break
            normalized = {**movement, **set_identity, "sourceMovementGenerationId": generation}
            try:
                identity = movement_identity(normalized)
            except ValueError:
                malformed.append({"setId": set_id, "canonicalKey": pokemon_set.get("canonical_key"),
                                  "missingFields": ["canonical card identity"]})
                break
            if identity[0] not in top_chase_identities:
                continue
            candidates.append(normalized)
            set_candidate_count += 1
        if set_candidate_count:
            participating_set_count += 1

    diagnostics = {
        "requestedTargetMarketDate": target_market_date,
        "eligiblePokemonSetCount": len(eligible),
        "snapshotRowsFound": len(snapshots),
        "includedSetCount": len(eligible) - len(missing) - len(stale) - len(malformed),
        "participatingSetCount": participating_set_count,
        "missingSets": missing,
        "staleSets": stale,
        "malformedSets": malformed,
        "topChaseCandidateCardCount": top_chase_candidate_count,
        "candidateCardCount": len(candidates),
        "candidatesWithValidSevenDayHistoryCount": len(candidates),
        "movementContractVersionsEncountered": sorted(contract_versions),
        "windowConventionsEncountered": sorted(conventions),
        "generationMetadataPathsUsed": sorted(generation_paths),
    }
    if missing or stale or malformed:
        raise ExploreCardMoversUnavailable(
            "eligible source snapshots are incomplete", diagnostics=diagnostics
        )
    if contract_versions != {MOVEMENT_CONTRACT_VERSION} or conventions != {WINDOW_CONVENTION}:
        raise ExploreCardMoversUnavailable(
            "incompatible movement contract or window convention", diagnostics=diagnostics
        )

    deduped: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    for movement in candidates:
        identity = movement_identity(movement)
        current = deduped.get(identity)
        if current is None or canonical_card_movement_sort_key(movement) < canonical_card_movement_sort_key(current):
            deduped[identity] = movement
    ordered = sorted(deduped.values(), key=canonical_card_movement_sort_key)
    published = ordered[: min(max(1, limit), LIMIT)]
    generation_input = "\n".join(
        [target_market_date, MOVEMENT_CONTRACT_VERSION, WINDOW_CONVENTION, *sorted(generation_parts)]
    )
    fingerprint = hashlib.sha256(generation_input.encode("utf-8")).hexdigest()
    built_at = built_at or datetime.now(timezone.utc).isoformat()
    payload = {
        "marketMovers": {"window": "7D", "all": published},
        "meta": {
            "snapshot": {"builtAt": built_at, "marketDate": target_market_date, "window": "7D", "limit": LIMIT},
            "coverage": {
                "expectedEligibleSetCount": len(eligible), "includedSetCount": len(eligible),
                "participatingSetCount": participating_set_count,
                "excludedSetCount": 0,
                "topChaseCandidateCardCount": top_chase_candidate_count,
                "candidateCardCount": len(candidates),
                "candidatesWithValidSevenDayHistoryCount": len(candidates),
                "deduplicatedCardCount": len(deduped), "publishedCardCount": len(published),
            },
            "movementContractVersion": MOVEMENT_CONTRACT_VERSION,
            "windowConvention": WINDOW_CONVENTION,
            "sourceGenerationFingerprint": fingerprint,
            "builder": "pokemon_explore_top_chase_seven_day_movers",
            "warnings": [],
        },
    }
    diagnostics.update({
        "deduplicatedCardCount": len(deduped),
        "publishedCardCount": len(published),
    })
    newest = max((str(row.get("updated_at") or "") for row in snapshots), default=built_at)
    return {
        "tcg": "pokemon", "scope": "explore", "window_key": "7D", "payload_json": payload,
        "market_date": target_market_date, "card_count": len(published),
        "eligible_set_count": len(eligible), "source_updated_at": newest,
        "source_generation_fingerprint": fingerprint,
        "_diagnostics": diagnostics,
    }


def read_explore_card_movers_snapshot(*, limit: Any = LIMIT, client: Any = None) -> Dict[str, Any]:
    active = client or service_read_client
    started = time.perf_counter()
    rows = list((active.table(TABLE).select("payload_json,market_date,updated_at,card_count").eq("tcg", "pokemon").eq("scope", "explore")
                 .eq("window_key", "7D").limit(1).execute()).data or [])
    db_ms = round((time.perf_counter() - started) * 1000, 2)
    if not rows:
        raise ExploreCardMoversUnavailable("global Explore card movers snapshot is unavailable")
    payload = dict(rows[0].get("payload_json") or {})
    entry = dict(payload.get("marketMovers") or {})
    try:
        sanitized = max(1, min(int(limit), LIMIT))
    except (TypeError, ValueError):
        sanitized = LIMIT
    entry["all"] = list(entry.get("all") or [])[:sanitized]
    payload["marketMovers"] = entry
    payload["meta"] = {**(payload.get("meta") or {}), "source": TABLE}
    logger.info("market_read route=/explore/card-market-movers dbDurationMs=%s majorReads=1 cardCount=%s", db_ms, rows[0].get("card_count"))
    return payload


def upsert_explore_card_movers_snapshot(row: Mapping[str, Any], *, client: Any) -> None:
    persisted = {key: value for key, value in row.items() if not str(key).startswith("_")}
    client.table(TABLE).upsert(persisted, on_conflict="tcg,scope,window_key").execute()
