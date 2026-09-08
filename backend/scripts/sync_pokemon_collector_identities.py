"""Synchronize Collector Appeal identities from canonical Pokemon card data.

This is the production-facing C1 identity/mapping stage.  It deliberately does
not scrape popularity/playability sources and does not calculate any Collector
Appeal score.

Responsibilities:

* keep artist entities/links aligned with ``pokemon_canonical_cards.artist``;
* link named Supporter cards to already-authoritative Trainer entities using the
  conservative rules in ``backend.desirability.collector_identity``;
* build price/art/rarity-independent functional identities for Pokemon and
  Trainer cards from canonical gameplay payload fields;
* never guess ambiguous Trainer subjects; report them for a future authoritative
  override/source pass instead;
* use bulk reads and batched writes -- never one DB request per card.

Dry-run is the default.  ``--commit`` is required to write.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.desirability.collector_identity import (  # noqa: E402
    COLLECTOR_IDENTITY_MAPPING_VERSION,
    FUNCTIONAL_EXACT_FALLBACK,
    FUNCTIONAL_IDENTITY_VERSION,
    FUNCTIONAL_SIGNATURE,
    build_functional_identity,
    is_supporter,
    match_trainer_subjects,
)

logger = logging.getLogger(__name__)

ENTITY_TABLE = "pokemon_collector_entity_reference"
ENTITY_LINK_TABLE = "pokemon_card_collector_entity_links"
FUNCTION_TABLE = "pokemon_card_functional_reference"
FUNCTION_LINK_TABLE = "pokemon_card_functional_links"
CANONICAL_CARD_TABLE = "pokemon_canonical_cards"

READ_PAGE_SIZE = 250
WRITE_BATCH_SIZE = 500
DEFAULT_OVERRIDES_PATH = REPO_ROOT / "backend" / "config" / "pokemon_collector_trainer_overrides.json"

# Project only gameplay fields out of source_payload.  Pulling the complete raw
# Pokemon TCG API payload for ~20k cards would also transfer images, pricing and
# other irrelevant data into this build.  These aliases keep the working set
# bounded and make the identity stage structurally price-independent.
CANONICAL_CARD_COLUMNS = ",".join(
    (
        "id",
        "set_id",
        "pokemon_tcg_api_card_id",
        "name",
        "supertype",
        "subtypes",
        "artist",
        "rules:source_payload->rules",
        "hp:source_payload->hp",
        "types:source_payload->types",
        "evolvesFrom:source_payload->evolvesFrom",
        "abilities:source_payload->abilities",
        "attacks:source_payload->attacks",
        "weaknesses:source_payload->weaknesses",
        "resistances:source_payload->resistances",
        "retreatCost:source_payload->retreatCost",
        "convertedRetreatCost:source_payload->convertedRetreatCost",
    )
)


class CollectorIdentitySyncError(RuntimeError):
    pass


class CollectorIdentityRepository:
    def __init__(self, client: Optional[Any] = None):
        if client is None:
            from backend.db.clients.supabase_client import supabase

            client = supabase
        self.client = client

    def list_canonical_cards(self, *, set_id: Optional[str] = None) -> List[Dict[str, Any]]:
        def query_factory():
            query = self.client.table(CANONICAL_CARD_TABLE).select(CANONICAL_CARD_COLUMNS)
            if set_id:
                query = query.eq("set_id", set_id)
            return query.order("id")

        rows = _paged_select(query_factory, page_size=READ_PAGE_SIZE)
        for row in rows:
            row["source_payload"] = {
                key: row.get(key)
                for key in (
                    "rules",
                    "hp",
                    "types",
                    "evolvesFrom",
                    "abilities",
                    "attacks",
                    "weaknesses",
                    "resistances",
                    "retreatCost",
                    "convertedRetreatCost",
                )
                if row.get(key) is not None
            }
        return rows

    def list_entities(self) -> List[Dict[str, Any]]:
        return _paged_select(
            lambda: self.client.table(ENTITY_TABLE).select(
                "id,entity_type,canonical_key,display_name,normalized_name,active,identity_metadata_json"
            ),
            page_size=1000,
        )

    def list_entity_links(self) -> List[Dict[str, Any]]:
        return _paged_select(
            lambda: self.client.table(ENTITY_LINK_TABLE).select(
                "id,pokemon_canonical_card_id,collector_entity_id,link_role,link_position,"
                "link_count,contribution_weight,match_method,match_confidence,active,notes"
            ),
            page_size=1000,
        )

    def list_functional_references(self) -> List[Dict[str, Any]]:
        return _paged_select(
            lambda: self.client.table(FUNCTION_TABLE).select(
                "id,functional_key,display_name,normalized_name,supertype,functional_identity_json,active"
            ),
            page_size=1000,
        )

    def list_functional_links(self) -> List[Dict[str, Any]]:
        return _paged_select(
            lambda: self.client.table(FUNCTION_LINK_TABLE).select(
                "id,pokemon_canonical_card_id,functional_reference_id,match_method,match_confidence,active,notes"
            ),
            page_size=1000,
        )

    def upsert_entities(self, rows: Sequence[Dict[str, Any]]) -> None:
        _batched_upsert(
            self.client,
            ENTITY_TABLE,
            rows,
            on_conflict="entity_type,canonical_key",
        )

    def upsert_entity_links(self, rows: Sequence[Dict[str, Any]]) -> None:
        _batched_upsert(
            self.client,
            ENTITY_LINK_TABLE,
            rows,
            on_conflict="pokemon_canonical_card_id,collector_entity_id,link_role",
        )

    def upsert_functional_references(self, rows: Sequence[Dict[str, Any]]) -> None:
        _batched_upsert(
            self.client,
            FUNCTION_TABLE,
            rows,
            on_conflict="functional_key",
        )

    def upsert_functional_links(self, rows: Sequence[Dict[str, Any]]) -> None:
        _batched_upsert(
            self.client,
            FUNCTION_LINK_TABLE,
            rows,
            on_conflict="pokemon_canonical_card_id,functional_reference_id",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only (THE DEFAULT).")
    mode.add_argument("--commit", action="store_true", help="Write identity/link rows.")
    parser.add_argument("--set-id", help="Optional sets.id UUID for a scoped repair/audit; default is all cards.")
    parser.add_argument(
        "--trainer-overrides-path",
        default=str(DEFAULT_OVERRIDES_PATH),
        help="Explicit card-id/API-id -> Trainer name overrides JSON.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def load_backend_env() -> None:
    load_dotenv(REPO_ROOT / "backend" / ".env", override=False)


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    load_backend_env()

    overrides = load_trainer_overrides(Path(args.trainer_overrides_path))
    report = build_identity_sync_report(
        repository=CollectorIdentityRepository(),
        set_id=args.set_id,
        trainer_overrides=overrides,
        dry_run=not args.commit,
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("status") in {"dry_run", "committed"} else 1


def load_trainer_overrides(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        raise CollectorIdentitySyncError(f"Trainer override file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CollectorIdentitySyncError("Trainer override file must contain a JSON object")
    raw = payload.get("cardOverrides") or {}
    if not isinstance(raw, dict):
        raise CollectorIdentitySyncError("cardOverrides must be a JSON object")
    resolved: Dict[str, List[str]] = {}
    for key, value in raw.items():
        card_key = str(key or "").strip()
        names = value if isinstance(value, list) else [value]
        clean = [str(name).strip() for name in names if str(name or "").strip()]
        if card_key and clean:
            resolved[card_key] = clean
    return resolved


def build_identity_sync_report(
    *,
    repository: Any,
    set_id: Optional[str],
    trainer_overrides: Mapping[str, Sequence[str]],
    dry_run: bool,
) -> Dict[str, Any]:
    cards = repository.list_canonical_cards(set_id=set_id)
    entities = repository.list_entities()
    existing_entity_links = repository.list_entity_links()
    existing_function_refs = repository.list_functional_references()
    existing_function_links = repository.list_functional_links()

    artist_plan = build_artist_entity_plan(cards=cards, entities=entities)
    artist_entity_rows = artist_plan["entity_rows"]

    # Artist entities must exist before their FK-backed links can be generated.
    # In commit mode we insert only missing entities, then re-read the registry
    # once; there is never a per-artist or per-card lookup.
    if not dry_run and artist_entity_rows:
        repository.upsert_entities(artist_entity_rows)
        entities = repository.list_entities()

    entity_by_artist_key = {
        str(row.get("canonical_key")): row
        for row in entities
        if row.get("entity_type") == "artist" and row.get("active") is not False
    }
    artist_links = build_artist_link_rows(cards=cards, entities_by_key=entity_by_artist_key)

    trainer_entities = [
        row
        for row in entities
        if row.get("entity_type") == "trainer" and row.get("active") is not False
    ]
    trainer_plan = build_trainer_link_plan(
        cards=cards,
        trainer_entities=trainer_entities,
        trainer_overrides=trainer_overrides,
    )
    trainer_links = trainer_plan["rows"]

    entity_link_rows = [*artist_links, *trainer_links]
    entity_link_delta = changed_entity_links(entity_link_rows, existing_entity_links)
    if not dry_run and entity_link_delta:
        repository.upsert_entity_links(entity_link_delta)

    function_plan = build_functional_reference_plan(cards)
    functional_reference_rows = function_plan["reference_rows"]
    function_ref_delta = changed_functional_references(
        functional_reference_rows,
        existing_function_refs,
    )
    if not dry_run and function_ref_delta:
        repository.upsert_functional_references(function_ref_delta)
        existing_function_refs = repository.list_functional_references()

    function_by_key = {
        str(row.get("functional_key")): row
        for row in existing_function_refs
        if row.get("functional_key") and row.get("active") is not False
    }
    if dry_run:
        # Dry-run has no database IDs for brand-new refs.  A deterministic
        # pseudo-id keeps expected-link accounting meaningful without pretending
        # those UUIDs exist in production.
        for row in functional_reference_rows:
            key = str(row["functional_key"])
            function_by_key.setdefault(key, {**row, "id": f"dry-run:{key}"})

    functional_links = build_functional_link_rows(
        cards=cards,
        identities_by_card=function_plan["identities_by_card"],
        references_by_key=function_by_key,
    )
    function_link_delta = changed_functional_links(functional_links, existing_function_links)
    if not dry_run and function_link_delta:
        repository.upsert_functional_links(function_link_delta)

    diagnostics = {
        "mappingVersion": COLLECTOR_IDENTITY_MAPPING_VERSION,
        "functionalIdentityVersion": FUNCTIONAL_IDENTITY_VERSION,
        "setId": set_id,
        "canonicalCardsLoaded": len(cards),
        "cardsBySupertype": dict(sorted(Counter(str(card.get("supertype") or "<null>") for card in cards).items())),
        "cardsWithArtist": sum(bool(str(card.get("artist") or "").strip()) for card in cards),
        "artistEntitiesExisting": sum(row.get("entity_type") == "artist" for row in entities),
        "artistEntitiesMissing": len(artist_entity_rows),
        "artistLinksExpected": len(artist_links),
        "trainerEntitiesAvailable": len(trainer_entities),
        "supporterCards": trainer_plan["supporter_count"],
        "trainerSubjectLinksExpected": len(trainer_links),
        "trainerSupportersResolved": trainer_plan["resolved_supporter_count"],
        "trainerSupportersUnresolved": trainer_plan["unresolved_supporter_count"],
        "functionalEligibleCards": function_plan["eligible_card_count"],
        "uniqueFunctionalIdentities": len(functional_reference_rows),
        "functionalSignatureCards": function_plan["signature_card_count"],
        "functionalExactFallbackCards": function_plan["fallback_card_count"],
        "functionalLinksExpected": len(functional_links),
        "writesPlanned": {
            "artistEntities": len(artist_entity_rows),
            "collectorEntityLinks": len(entity_link_delta),
            "functionalReferences": len(function_ref_delta),
            "functionalLinks": len(function_link_delta),
        },
        "performanceContract": {
            "readPageSize": READ_PAGE_SIZE,
            "writeBatchSize": WRITE_BATCH_SIZE,
            "canonicalPayloadProjection": "gameplay_fields_only",
            "perCardDatabaseQueries": False,
        },
    }

    return {
        "status": "dry_run" if dry_run else "committed",
        "dryRun": dry_run,
        "diagnostics": diagnostics,
        "unresolvedTrainerSamples": trainer_plan["unresolved_samples"],
        "functionalFallbackSamples": function_plan["fallback_samples"],
    }


def build_artist_entity_plan(
    *,
    cards: Sequence[Mapping[str, Any]],
    entities: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    existing = {
        str(row.get("canonical_key"))
        for row in entities
        if row.get("entity_type") == "artist"
    }
    by_key: Dict[str, str] = {}
    for card in cards:
        display = _clean_whitespace(card.get("artist"))
        if not display:
            continue
        storage_name = _artist_storage_name(display)
        by_key.setdefault(f"artist:{storage_name}", display)

    missing = []
    for key, display in sorted(by_key.items()):
        if key in existing:
            continue
        missing.append(
            {
                "entity_type": "artist",
                "canonical_key": key,
                "display_name": display,
                # Python 3.8 is still supported by the backend runtime.
                "normalized_name": key[len("artist:") :],
                "active": True,
                "identity_metadata_json": {
                    "source": "pokemon_canonical_cards.artist",
                    "mappingVersion": COLLECTOR_IDENTITY_MAPPING_VERSION,
                },
            }
        )
    return {"entity_rows": missing, "distinct_artist_keys": len(by_key)}


def build_artist_link_rows(
    *,
    cards: Sequence[Mapping[str, Any]],
    entities_by_key: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for card in cards:
        card_id = str(card.get("id") or "")
        display = _clean_whitespace(card.get("artist"))
        if not card_id or not display:
            continue
        key = f"artist:{_artist_storage_name(display)}"
        entity = entities_by_key.get(key)
        if not entity or not entity.get("id"):
            continue
        rows.append(
            {
                "pokemon_canonical_card_id": card_id,
                "collector_entity_id": str(entity["id"]),
                "link_role": "artist",
                "link_position": 1,
                "link_count": 1,
                "contribution_weight": 1.0,
                "match_method": "canonical_card_artist_exact_v1",
                "match_confidence": 1.0,
                "active": True,
                "notes": f"collector identity sync {COLLECTOR_IDENTITY_MAPPING_VERSION}",
            }
        )
    return rows


def build_trainer_link_plan(
    *,
    cards: Sequence[Mapping[str, Any]],
    trainer_entities: Sequence[Mapping[str, Any]],
    trainer_overrides: Mapping[str, Sequence[str]],
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    supporter_count = resolved_supporter_count = 0
    unresolved: List[Dict[str, Any]] = []
    for card in cards:
        if not is_supporter(card):
            continue
        supporter_count += 1
        matches = match_trainer_subjects(
            card,
            trainer_entities,
            card_overrides=trainer_overrides,
        )
        if not matches:
            unresolved.append(
                {
                    "pokemonTcgApiCardId": card.get("pokemon_tcg_api_card_id"),
                    "cardId": card.get("id"),
                    "name": card.get("name"),
                    "setId": card.get("set_id"),
                    "reason": "no_deterministic_named_trainer_match",
                }
            )
            continue
        resolved_supporter_count += 1
        for position, match in enumerate(matches, start=1):
            rows.append(
                {
                    "pokemon_canonical_card_id": str(card["id"]),
                    "collector_entity_id": match.entity_id,
                    "link_role": "subject",
                    "link_position": position,
                    "link_count": len(matches),
                    "contribution_weight": match.contribution_weight,
                    "match_method": match.method,
                    "match_confidence": match.confidence,
                    "active": True,
                    "notes": f"collector identity sync {COLLECTOR_IDENTITY_MAPPING_VERSION}",
                }
            )
    return {
        "rows": rows,
        "supporter_count": supporter_count,
        "resolved_supporter_count": resolved_supporter_count,
        "unresolved_supporter_count": len(unresolved),
        "unresolved_samples": unresolved[:50],
    }


def build_functional_reference_plan(cards: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    refs: Dict[str, Dict[str, Any]] = {}
    identities_by_card: Dict[str, Any] = {}
    eligible = signature_count = fallback_count = 0
    fallback_samples: List[Dict[str, Any]] = []
    for card in cards:
        identity = build_functional_identity(card)
        if identity is None:
            continue
        eligible += 1
        card_id = str(card.get("id") or "")
        if not card_id:
            continue
        identities_by_card[card_id] = identity
        if identity.method == FUNCTIONAL_SIGNATURE:
            signature_count += 1
        elif identity.method == FUNCTIONAL_EXACT_FALLBACK:
            fallback_count += 1
            if len(fallback_samples) < 50:
                fallback_samples.append(
                    {
                        "cardId": card_id,
                        "pokemonTcgApiCardId": card.get("pokemon_tcg_api_card_id"),
                        "name": card.get("name"),
                        "supertype": card.get("supertype"),
                    }
                )
        refs.setdefault(
            identity.functional_key,
            {
                "functional_key": identity.functional_key,
                "display_name": identity.display_name,
                "normalized_name": identity.normalized_name,
                "supertype": identity.supertype,
                "functional_identity_json": identity.identity_json,
                "active": True,
            },
        )
    return {
        "reference_rows": [refs[key] for key in sorted(refs)],
        "identities_by_card": identities_by_card,
        "eligible_card_count": eligible,
        "signature_card_count": signature_count,
        "fallback_card_count": fallback_count,
        "fallback_samples": fallback_samples,
    }


def build_functional_link_rows(
    *,
    cards: Sequence[Mapping[str, Any]],
    identities_by_card: Mapping[str, Any],
    references_by_key: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for card in cards:
        card_id = str(card.get("id") or "")
        identity = identities_by_card.get(card_id)
        if identity is None:
            continue
        reference = references_by_key.get(identity.functional_key)
        if not reference or not reference.get("id"):
            continue
        rows.append(
            {
                "pokemon_canonical_card_id": card_id,
                "functional_reference_id": str(reference["id"]),
                "match_method": identity.method,
                "match_confidence": identity.confidence,
                "active": True,
                "notes": f"functional identity sync {FUNCTIONAL_IDENTITY_VERSION}",
            }
        )
    return rows


def changed_entity_links(
    planned: Sequence[Mapping[str, Any]],
    existing: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    index = {
        (
            str(row.get("pokemon_canonical_card_id")),
            str(row.get("collector_entity_id")),
            str(row.get("link_role")),
        ): row
        for row in existing
    }
    return [
        dict(row)
        for row in planned
        if not _rows_equivalent(
            row,
            index.get(
                (
                    str(row.get("pokemon_canonical_card_id")),
                    str(row.get("collector_entity_id")),
                    str(row.get("link_role")),
                )
            ),
            fields=(
                "link_position",
                "link_count",
                "contribution_weight",
                "match_method",
                "match_confidence",
                "active",
                "notes",
            ),
        )
    ]


def changed_functional_references(
    planned: Sequence[Mapping[str, Any]],
    existing: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    index = {str(row.get("functional_key")): row for row in existing}
    return [
        dict(row)
        for row in planned
        if not _rows_equivalent(
            row,
            index.get(str(row.get("functional_key"))),
            fields=(
                "display_name",
                "normalized_name",
                "supertype",
                "functional_identity_json",
                "active",
            ),
        )
    ]


def changed_functional_links(
    planned: Sequence[Mapping[str, Any]],
    existing: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    index = {
        (str(row.get("pokemon_canonical_card_id")), str(row.get("functional_reference_id"))): row
        for row in existing
    }
    return [
        dict(row)
        for row in planned
        if not _rows_equivalent(
            row,
            index.get(
                (str(row.get("pokemon_canonical_card_id")), str(row.get("functional_reference_id")))
            ),
            fields=("match_method", "match_confidence", "active", "notes"),
        )
    ]


def _rows_equivalent(
    planned: Mapping[str, Any],
    existing: Optional[Mapping[str, Any]],
    *,
    fields: Iterable[str],
) -> bool:
    if existing is None:
        return False
    for field in fields:
        left = planned.get(field)
        right = existing.get(field)
        if field in {"contribution_weight", "match_confidence"}:
            try:
                if abs(float(left) - float(right)) > 1e-9:
                    return False
                continue
            except (TypeError, ValueError):
                pass
        if left != right:
            return False
    return True


def _artist_storage_name(value: str) -> str:
    # Match the historical production seed migration exactly: LOWER + trimmed
    # whitespace collapse, with punctuation/accents preserved.
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def _clean_whitespace(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _paged_select(
    query_factory: Callable[[], Any],
    *,
    page_size: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        page = list(
            query_factory()
            .range(start, start + page_size - 1)
            .execute()
            .data
            or []
        )
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return rows


def _batched_upsert(
    client: Any,
    table: str,
    rows: Sequence[Dict[str, Any]],
    *,
    on_conflict: str,
) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    for chunk in _chunked(rows, WRITE_BATCH_SIZE):
        payload = []
        for row in chunk:
            copied = dict(row)
            # Identity/link registries carry updated_at; run-scoped output tables
            # are not touched by this C1 stage.
            if table in {ENTITY_TABLE, ENTITY_LINK_TABLE, FUNCTION_TABLE, FUNCTION_LINK_TABLE}:
                copied["updated_at"] = timestamp
            payload.append(copied)
        client.table(table).upsert(payload, on_conflict=on_conflict).execute()


def _chunked(values: Sequence[Dict[str, Any]], size: int) -> Iterable[Sequence[Dict[str, Any]]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


if __name__ == "__main__":
    raise SystemExit(main())
