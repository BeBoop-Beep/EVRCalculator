"""Best-effort Pokemon card metadata enrichment after a targeted scrape.

This is deliberately scoped to initial/manual single-set scrapes.  Daily price
refreshes already have complete card identity for established sets and must not
pay an extra Pokemon TCG API round-trip per set.

The enrichment preserves canonical-card UUIDs.  A TCGplayer-first set may have
fallback pokemon_canonical_cards rows that are already referenced by price,
desirability, and publication tables.  When Pokemon TCG API identity becomes
available we UPDATE those rows in place; we never replace their UUIDs and never
insert API-only cards that were absent from the scraped local roster.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from backend.db.clients.pokemon_tcg_api_client import PokemonTCGAPIClient, PokemonTCGAPIError
from backend.db.clients.supabase_client import create_service_role_client
from backend.db.services.pokemon_tcg_image_sync_service import PokemonTCGImageSyncService
from backend.scripts.ingest_pokemon_canonical_cards import (
    build_canonical_row,
    fetch_api_set,
    fetch_cards_for_api_set,
    to_optional_int,
)

FALLBACK_CANONICAL_SOURCE = "tcgplayer_cards_fallback"
_API_PREFIX_RE = re.compile(r"^(?:ME(?:\d+)?\s*:\s*)", re.IGNORECASE)


def _candidate_api_names(set_name: str) -> List[str]:
    """Return bounded exact-name candidates without fuzzy identity guessing."""
    raw = " ".join(str(set_name or "").split()).strip()
    if not raw:
        return []
    candidates = [raw]
    stripped = _API_PREFIX_RE.sub("", raw).strip()
    if stripped and stripped not in candidates:
        candidates.append(stripped)
    if stripped.lower().endswith(" classic collection"):
        colon = stripped[: -len(" classic collection")].rstrip() + ": Classic Collection"
        if colon not in candidates:
            candidates.append(colon)
    return candidates


def _resolve_api_set_id(set_name: str, expected_api_set_id: Optional[str]) -> Dict[str, Any]:
    expected = str(expected_api_set_id or "").strip()
    if expected:
        return {"id": expected, "name": None, "resolution": "configured"}

    client = PokemonTCGAPIClient()
    failures: List[str] = []
    for candidate in _candidate_api_names(set_name):
        try:
            row = client.resolve_set(candidate)
        except PokemonTCGAPIError as exc:
            failures.append(f"{candidate}: {exc}")
            continue
        api_id = str(row.get("id") or "").strip()
        if api_id:
            return {
                "id": api_id,
                "name": row.get("name"),
                "resolution": "exact_name",
                "candidate": candidate,
            }
    raise PokemonTCGAPIError(
        "Pokemon TCG API set identity could not be resolved from bounded exact-name candidates: "
        + "; ".join(failures[-3:])
    )


def _load_canonical_rows(client: Any, set_id: str) -> List[Dict[str, Any]]:
    result = (
        client.table("pokemon_canonical_cards")
        .select(
            "id,set_id,pokemon_tcg_api_card_id,name,number,printed_number,"
            "image_small_url,image_large_url,source,source_payload"
        )
        .eq("set_id", set_id)
        .limit(1000)
        .execute()
    )
    return list(result.data or [])


def _canonical_metadata_complete(rows: Iterable[Dict[str, Any]]) -> bool:
    rows = list(rows)
    if not rows:
        return False
    for row in rows:
        api_id = str(row.get("pokemon_tcg_api_card_id") or "")
        if (
            str(row.get("source") or "") == FALLBACK_CANONICAL_SOURCE
            or not api_id
            or api_id.startswith("fallback:")
            or not row.get("image_small_url")
            or not row.get("image_large_url")
        ):
            return False
    return True


def _load_legacy_cards(client: Any, set_id: str) -> Dict[str, Dict[str, Any]]:
    result = (
        client.table("cards")
        .select("id,set_id,name,card_number,pokemon_tcg_api_id,image_small_url,image_large_url")
        .eq("set_id", set_id)
        .limit(1000)
        .execute()
    )
    return {str(row["id"]): row for row in (result.data or []) if row.get("id")}


def _api_owners(client: Any, api_ids: List[str]) -> Dict[str, str]:
    owners: Dict[str, str] = {}
    clean = sorted({str(value) for value in api_ids if str(value or "").strip()})
    for start in range(0, len(clean), 100):
        result = (
            client.table("pokemon_canonical_cards")
            .select("id,pokemon_tcg_api_card_id")
            .in_("pokemon_tcg_api_card_id", clean[start : start + 100])
            .execute()
        )
        for row in result.data or []:
            api_id = str(row.get("pokemon_tcg_api_card_id") or "")
            canonical_id = str(row.get("id") or "")
            if api_id and canonical_id:
                owners[api_id] = canonical_id
    return owners


def _hydrate_existing_canonical_rows(
    *,
    client: Any,
    set_id: str,
    api_set_id: str,
    api_set: Dict[str, Any],
    api_cards: List[Dict[str, Any]],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Upgrade only canonical rows already owned by the local scraped roster."""
    canonical_rows = _load_canonical_rows(client, set_id)
    if not canonical_rows:
        return {
            "status": "no_canonical_rows_yet",
            "canonical_rows": 0,
            "updated": 0,
            "unmatched": 0,
            "conflicts": [],
        }

    legacy_by_id = _load_legacy_cards(client, set_id)
    api_by_id = {
        str(card.get("id")): card
        for card in api_cards
        if isinstance(card, dict) and card.get("id")
    }

    intended: List[tuple[Dict[str, Any], str, Dict[str, Any]]] = []
    unmatched: List[Dict[str, Any]] = []
    for canonical in canonical_rows:
        current_api_id = str(canonical.get("pokemon_tcg_api_card_id") or "").strip()
        source_payload = canonical.get("source_payload")
        source_payload = source_payload if isinstance(source_payload, dict) else {}
        legacy_id = str(source_payload.get("source_card_id") or "").strip()
        legacy = legacy_by_id.get(legacy_id) if legacy_id else None
        resolved_api_id = str((legacy or {}).get("pokemon_tcg_api_id") or "").strip()
        if not resolved_api_id and current_api_id and not current_api_id.startswith("fallback:"):
            resolved_api_id = current_api_id
        api_card = api_by_id.get(resolved_api_id)
        if not resolved_api_id or api_card is None:
            unmatched.append(
                {
                    "canonical_card_id": canonical.get("id"),
                    "name": canonical.get("name"),
                    "number": canonical.get("printed_number") or canonical.get("number"),
                    "legacy_card_id": legacy_id or None,
                }
            )
            continue
        intended.append((canonical, resolved_api_id, api_card))

    owners = _api_owners(client, [api_id for _, api_id, _ in intended])
    printed_total = to_optional_int(api_set.get("printedTotal"))
    conflicts: List[Dict[str, Any]] = []
    updated = 0
    for canonical, api_id, api_card in intended:
        canonical_id = str(canonical.get("id") or "")
        owner = owners.get(api_id)
        if owner and owner != canonical_id:
            conflicts.append(
                {
                    "canonical_card_id": canonical_id,
                    "pokemon_tcg_api_card_id": api_id,
                    "owned_by": owner,
                }
            )
            continue

        authoritative = build_canonical_row(
            local_set_id=set_id,
            api_set_id=api_set_id,
            api_printed_total=printed_total,
            card=api_card,
        )
        payload = {
            key: value
            for key, value in authoritative.items()
            if key != "set_id"
        }
        if dry_run:
            updated += 1
            continue
        result = (
            client.table("pokemon_canonical_cards")
            .update(payload)
            .eq("id", canonical_id)
            .execute()
        )
        if result is not None:
            updated += 1

    return {
        "status": "hydrated" if not conflicts else "hydrated_with_conflicts",
        "canonical_rows": len(canonical_rows),
        "updated": updated,
        "unmatched": len(unmatched),
        "unmatched_examples": unmatched[:20],
        "conflicts": conflicts,
        "api_returned_cards": len(api_cards),
        "dry_run": bool(dry_run),
    }


def enrich_scraped_set_card_metadata(
    *,
    set_id: str,
    set_name: str,
    canonical_key: str,
    cards_scraped: int,
    expected_api_set_id: Optional[str] = None,
    client: Any = None,
    image_sync_service: Optional[PokemonTCGImageSyncService] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Enrich one successfully scraped set without changing scrape success."""
    if int(cards_scraped or 0) <= 0:
        return {"status": "skipped_no_cards", "cards_scraped": int(cards_scraped or 0)}

    active = client or create_service_role_client()
    canonical_before = _load_canonical_rows(active, set_id)
    if _canonical_metadata_complete(canonical_before):
        return {
            "status": "already_complete",
            "canonical_rows": len(canonical_before),
            "cards_scraped": int(cards_scraped),
        }

    resolved = _resolve_api_set_id(set_name, expected_api_set_id)
    api_set_id = str(resolved["id"])
    api_set = fetch_api_set(api_set_id)
    set_images = api_set.get("images") if isinstance(api_set.get("images"), dict) else {}

    # Persist the verified set identity so later onboarding/publication stages
    # and future image refreshes do not need to rediscover it.
    set_payload: Dict[str, Any] = {"pokemon_api_set_id": api_set_id}
    if set_images.get("symbol"):
        set_payload["symbol_image_url"] = set_images["symbol"]
    if set_images.get("logo"):
        set_payload["logo_image_url"] = set_images["logo"]
    if not dry_run:
        active.table("sets").update(set_payload).eq("id", set_id).execute()

    # Reuse the established card/variant matcher for the legacy compatibility
    # layer.  This is intentionally before canonical hydration: fallback
    # canonical rows remember source_card_id, and the sync writes the exact
    # Pokemon API card id onto that legacy card.
    sync = image_sync_service or PokemonTCGImageSyncService()
    legacy_report = sync.sync_set(set_name, dry_run=dry_run)

    # Fetch the full provider card payload once for canonical metadata.  Unlike
    # the legacy image synchronizer, this includes rarity/supertype/subtypes/
    # artist/Pokedex metadata through the canonical ingestion adapter.
    api_cards = fetch_cards_for_api_set(api_set_id)
    canonical_report = _hydrate_existing_canonical_rows(
        client=active,
        set_id=set_id,
        api_set_id=api_set_id,
        api_set=api_set,
        api_cards=api_cards,
        dry_run=dry_run,
    )

    return {
        "status": (
            "dry_run"
            if dry_run
            else "enriched"
            if canonical_report.get("status") in {"hydrated", "no_canonical_rows_yet"}
            else "partial"
        ),
        "set_id": set_id,
        "canonical_key": canonical_key,
        "pokemon_api_set_id": api_set_id,
        "api_set_name": api_set.get("name"),
        "api_resolution": resolved,
        "legacy_image_sync": {
            "fetched_api_cards": legacy_report.get("fetched_api_cards"),
            "updated_card_rows": legacy_report.get("updated_card_rows"),
            "updated_variant_rows": legacy_report.get("updated_variant_rows"),
            "exact_matches": legacy_report.get("exact_matches"),
            "fallback_matches": legacy_report.get("fallback_matches"),
            "unmatched_count": len(legacy_report.get("unmatched") or []),
            "skipped_count": len(legacy_report.get("skipped") or []),
        },
        "canonical_hydration": canonical_report,
        "provider_count_difference": {
            "cards_scraped": int(cards_scraped),
            "api_returned_cards": len(api_cards),
            "delta": len(api_cards) - int(cards_scraped),
        },
    }
