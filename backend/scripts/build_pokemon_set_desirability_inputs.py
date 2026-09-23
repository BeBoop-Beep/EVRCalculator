from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.desirability.normalization import (  # noqa: E402
    FORM_SUFFIXES_TO_STRIP,
    normalize_pokemon_name_key,
)
from backend.desirability.composite import COMPOSITE_SCORING_VERSION  # noqa: E402
from backend.desirability.rarity_buckets import HIT_POLICY_VERSION  # noqa: E402
from backend.desirability.set_components import SCORING_VERSION as COMPONENT_SCORING_VERSION  # noqa: E402
from backend.desirability.rip_desirability import SCORING_VERSION as OPENING_SCORING_VERSION  # noqa: E402
from backend.scripts.build_pokemon_card_desirability_links import (  # noqa: E402
    PokemonCardDesirabilityLinksRepository,
    build_links_report,
)
from backend.scripts.build_pokemon_set_desirability_component_scores import (  # noqa: E402
    PokemonSetDesirabilityComponentsRepository,
    build_component_scores_report,
)
from backend.scripts.build_pokemon_set_hit_desirability_summaries import (  # noqa: E402
    DEFAULT_AGGREGATION_VERSION,
    PokemonSetHitDesirabilitySummariesRepository,
    build_set_hit_desirability_summaries_report,
)
from backend.scripts.build_set_rip_desirability_prototype import (  # noqa: E402
    OPENING_DESIRABILITY_TABLE,
    RipDesirabilityPrototypeRepository,
    build_opening_desirability_persistence_rows,
    build_report,
)
from backend.scripts.run_pokemon_set_scrape import (  # noqa: E402
    build_valid_set_key_registry,
    normalize_set_key_filter,
)
from backend.db.clients.tcgdex_pokemon_client import TCGdexPokemonClient, TCGdexError  # noqa: E402
from backend.db.services.supabase_persistence_retry import run_with_transient_retry  # noqa: E402
from backend.scripts.ingest_pokemon_canonical_cards import (  # noqa: E402
    build_canonical_row as build_authoritative_canonical_row,
    fetch_api_set as fetch_authoritative_api_set,
    fetch_cards_for_api_set as fetch_authoritative_cards,
    to_optional_int as canonical_optional_int,
)

logger = logging.getLogger(__name__)

FALLBACK_SOURCE = "tcgplayer_cards_fallback"
TCGDEX_SOURCE = "tcgdex"
FALLBACK_MATCH_METHOD = "name_exact_or_alias"
UPSERT_BATCH_SIZE = 250

# A catalog-only set never supports the opening simulation model, so its canonical
# rows must not silently inherit pokemon_canonical_cards' opening_eligible=true
# default -- that would make them look approved for a simulation this catalog never
# runs. Applied to both the fallback and authoritative-refresh row builders below,
# since catalog_only is a property of the SET, not of the canonical row's source.
CATALOG_ONLY_ELIGIBILITY_REASON = (
    "Catalog/market identity synced from a scraped catalog-only set (card and price "
    "data present); not an approved opening identity because this set does not "
    "support the opening simulation model."
)

CARD_SUFFIX_RE = re.compile(r"\b(ex|gx|vmax|vstar|v|break|lv\.?\s*x|star|prime|legend)\b", flags=re.IGNORECASE)
STANDALONE_EX_RE = re.compile(r"\bex\b", flags=re.IGNORECASE)
TRAINER_LIKE_KEYWORDS = (
    "trainer",
    "supporter",
    "stadium",
    "item",
    "tool",
    "ball",
    "retrieval",
    "net",
    "card",
    "energy",
)

REGIONAL_FORM_PREFIXES = ("alolan", "galarian", "hisuian", "paldean")


class SetDesirabilityInputsError(RuntimeError):
    pass


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    load_dotenv(env_path, override=False)


def get_supabase_client():
    from backend.db.clients.supabase_client import supabase

    return supabase


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build set-level Pokemon desirability inputs from canonical cards through opening desirability snapshots."
    )
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--set", dest="set_key", help="sets.canonical_key to process")
    selector.add_argument("--all", action="store_true", help="Process all sets")

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview changes only (default)")
    mode.add_argument("--commit", action="store_true", help="Write changes to Supabase")

    parser.add_argument("--hit-policy-version", default=HIT_POLICY_VERSION)
    parser.add_argument(
        "--canonical-only", action="store_true",
        help=(
            "Stop after canonical-card synchronization: no desirability links, hit "
            "summaries, component scores, or opening desirability are built. Use for "
            "a narrow catalog-card sync (e.g. right after a catalog-only set's scrape) "
            "without triggering the full desirability/opening pipeline."
        ),
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    load_backend_env()

    dry_run = not args.commit
    if args.dry_run:
        dry_run = True

    report = build_set_desirability_inputs_report(
        set_key=args.set_key,
        process_all=bool(args.all),
        dry_run=dry_run,
        hit_policy_version=args.hit_policy_version,
        canonical_only=bool(args.canonical_only),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    status = str(report.get("status") or "")
    return 0 if status in {"dry_run", "committed"} else 1


def build_set_desirability_inputs_report(
    *,
    set_key: Optional[str],
    process_all: bool,
    dry_run: bool,
    hit_policy_version: str = HIT_POLICY_VERSION,
    canonical_only: bool = False,
) -> Dict[str, Any]:
    client = get_supabase_client()
    registry = build_valid_set_key_registry()
    resolved_set_key = None
    if set_key:
        resolution = normalize_set_key_filter(set_key, registry)
        resolved_set_key = resolution.get("resolved_set_key_filter")
        if not resolved_set_key:
            raise SetDesirabilityInputsError(f"Unknown set key {set_key!r}")

    sets = _list_sets(client, set_key=resolved_set_key, process_all=process_all)
    if not sets:
        return {
            "status": "no_sets_found",
            "dry_run": dry_run,
            "requested_set_key": set_key,
            "resolved_set_key": resolved_set_key,
            "hit_policy_version": hit_policy_version,
        }

    set_reports: List[Dict[str, Any]] = []
    for set_row in sets:
        set_reports.append(_process_single_set(client=client, set_row=set_row, dry_run=dry_run))

    canonical_fallback_summary = {
        "rows_seen_in_cards": sum(int(r.get("cards_rows") or 0) for r in set_reports),
        "rows_preexisting_canonical": sum(int(r.get("preexisting_canonical_rows") or 0) for r in set_reports),
        "rows_missing_before": sum(int(r.get("rows_missing_before") or 0) for r in set_reports),
        "rows_upsert_planned": sum(int(r.get("rows_upsert_planned") or 0) for r in set_reports),
        "rows_upserted": sum(int(r.get("rows_upserted") or 0) for r in set_reports),
        "rows_skipped_missing_required": sum(int(r.get("rows_skipped_missing_required") or 0) for r in set_reports),
    }

    if canonical_only:
        # Narrow path: canonical-card synchronization only. Deliberately never calls
        # _build_links/_build_summaries/_build_components/_build_opening below.
        return {
            "status": "dry_run" if dry_run else "committed",
            "mode": "canonical_only",
            "dry_run": dry_run,
            "requested_set_key": set_key,
            "resolved_set_key": resolved_set_key,
            "hit_policy_version": hit_policy_version,
            "sets_processed": len(set_reports),
            "canonical_fallback": canonical_fallback_summary,
            "set_reports": set_reports,
        }

    selected_set_ids = [str(row.get("id")) for row in sets if row.get("id") is not None]
    selected_set_key = resolved_set_key if resolved_set_key else None

    links_report = _build_links(
        selected_set_key=selected_set_key,
        process_all=process_all,
        hit_policy_version=hit_policy_version,
        dry_run=dry_run,
    )
    summaries_report = _build_summaries(
        selected_set_key=selected_set_key,
        process_all=process_all,
        hit_policy_version=hit_policy_version,
        dry_run=dry_run,
    )
    canonical_identity_changed = any(
        ((row.get("authoritative_refresh") or {}).get("status") == "refreshed")
        for row in set_reports
    )
    components_report = _build_components(
        selected_set_key=selected_set_key,
        process_all=process_all,
        hit_policy_version=hit_policy_version,
        dry_run=dry_run,
        force=canonical_identity_changed,
    )
    opening_report = _build_opening(
        selected_set_ids=selected_set_ids,
        hit_policy_version=hit_policy_version,
        dry_run=dry_run,
    )

    return {
        "status": "dry_run" if dry_run else "committed",
        "dry_run": dry_run,
        "requested_set_key": set_key,
        "resolved_set_key": resolved_set_key,
        "hit_policy_version": hit_policy_version,
        "sets_processed": len(set_reports),
        "canonical_fallback": canonical_fallback_summary,
        "set_reports": set_reports,
        "links_report": links_report,
        "hit_summaries_report": summaries_report,
        "component_scores_report": components_report,
        "opening_desirability_report": opening_report,
    }


def _process_single_set(*, client: Any, set_row: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    set_id = str(set_row.get("id") or "")
    canonical_key = str(set_row.get("canonical_key") or "")
    if not set_id:
        raise SetDesirabilityInputsError("Encountered set row without id")

    canonical_before = _list_canonical_for_set(client, set_id)
    needs_authoritative_refresh = canonical_set_needs_authoritative_refresh(canonical_before)
    authoritative_refresh = (
        _refresh_authoritative_canonical_cards(client=client, set_row=set_row, dry_run=dry_run)
        if needs_authoritative_refresh
        else {"status": "not_needed", "rows_found": len(canonical_before), "rows_upserted": 0}
    )
    cards = _list_cards_for_set(client, set_id)
    canonical_rows = _list_canonical_for_set(client, set_id)
    existing_by_api_id = {
        str(row.get("pokemon_tcg_api_card_id")): row
        for row in canonical_rows
        if row.get("pokemon_tcg_api_card_id") is not None
    }
    existing_by_key = {
        _canonical_identity(str(row.get("number") or ""), str(row.get("name") or "")): row
        for row in canonical_rows
    }

    references = _list_pokemon_reference(client)
    reference_lookup = _build_reference_lookup(references)
    trainer_reference_names = _list_trainer_reference_names(client)
    authoritative_non_pokemon = _list_authoritative_non_pokemon_name_supertypes(
        client,
        [str(card.get("name") or "") for card in cards],
    )

    rows_to_upsert: List[Dict[str, Any]] = []
    skipped_missing_required = 0
    matched_pokemon_cards = 0
    non_pokemon_cards = 0
    unmatched_non_trainer_cards = 0
    sample_unmatched_non_trainer_cards: List[Dict[str, str]] = []

    for card in cards:
        printed_number = str(card.get("card_number") or "").strip()
        number = _canonical_number(printed_number)
        name = str(card.get("name") or "").strip()
        if not number or not name:
            skipped_missing_required += 1
            continue

        api_card_id = str(card.get("pokemon_tcg_api_id") or "").strip() or _fallback_api_card_id(
            set_id=set_id,
            number=printed_number,
            name=name,
        )

        key = _canonical_identity(number, name)
        existing = existing_by_api_id.get(api_card_id) or existing_by_key.get(key)

        if existing and str(existing.get("source") or "") not in {"", FALLBACK_SOURCE}:
            continue

        normalized_name = normalize_pokemon_name_key(name)
        non_pokemon_supertype = _infer_non_pokemon_supertype(name)
        if non_pokemon_supertype is None:
            non_pokemon_supertype = authoritative_non_pokemon.get(normalized_name)
        if non_pokemon_supertype is None and normalized_name in trainer_reference_names:
            non_pokemon_supertype = "Trainer"

        matched_references: List[Dict[str, Any]] = []
        if non_pokemon_supertype is None:
            matched_references = _match_references_for_card_name(
                name=name,
                reference_lookup=reference_lookup,
            )

        if non_pokemon_supertype:
            supertype = non_pokemon_supertype
            non_pokemon_cards += 1
        elif matched_references:
            supertype = "Pokémon"
            matched_pokemon_cards += 1
        else:
            supertype = None
            unmatched_non_trainer_cards += 1
            if len(sample_unmatched_non_trainer_cards) < 10:
                sample_unmatched_non_trainer_cards.append(
                    {
                        "name": name,
                        "card_number": printed_number,
                    }
                )

        subtypes = _infer_subtypes(name) if non_pokemon_supertype is None else []
        pokedex_numbers = [
            int(reference["pokedex_number"])
            for reference in matched_references
            if reference.get("pokedex_number") is not None
        ]

        rows_to_upsert.append(
            {
                "set_id": set_id,
                "pokemon_tcg_api_card_id": api_card_id,
                "name": name,
                "supertype": supertype,
                "subtypes": subtypes,
                "rarity": str(card.get("rarity") or "").strip() or None,
                "number": number,
                "printed_number": printed_number,
                "artist": None,
                "pokemon_tcg_api_set_id": str(set_row.get("pokemon_api_set_id") or "").strip() or None,
                "national_pokedex_numbers": pokedex_numbers,
                "image_small_url": str(card.get("image_small_url") or "").strip() or None,
                "image_large_url": str(card.get("image_large_url") or "").strip() or None,
                "source": FALLBACK_SOURCE,
                "source_payload": {
                    "source_table": "public.cards",
                    "source_card_id": card.get("id"),
                    "match_method": FALLBACK_MATCH_METHOD,
                    "matched_pokedex_number": pokedex_numbers[0] if len(pokedex_numbers) == 1 else None,
                    "matched_pokedex_numbers": pokedex_numbers,
                },
                **catalog_only_eligibility_overrides(set_row),
            }
        )

    rows_upserted = 0
    if not dry_run and rows_to_upsert:
        rows_upserted = _upsert_canonical_rows(client, rows_to_upsert)

    return {
        "set_id": set_id,
        "set_name": set_row.get("name"),
        "set_canonical_key": canonical_key,
        "cards_rows": len(cards),
        "preexisting_canonical_rows": len(canonical_rows),
        "rows_missing_before": max(0, len(cards) - len(canonical_rows)),
        "rows_upsert_planned": len(rows_to_upsert),
        "rows_upserted": rows_upserted,
        "rows_skipped_missing_required": skipped_missing_required,
        "matched_pokemon_cards": matched_pokemon_cards,
        "non_pokemon_cards": non_pokemon_cards,
        "unmatched_non_trainer_cards": unmatched_non_trainer_cards,
        "sample_unmatched_non_trainer_cards": sample_unmatched_non_trainer_cards,
        "authoritative_refresh": authoritative_refresh,
    }


def canonical_row_needs_authoritative_refresh(row: Dict[str, Any]) -> bool:
    """Return whether a canonical row lacks authoritative mapping identity."""
    source = str(row.get("source") or "").strip()
    supertype = str(row.get("supertype") or "").strip()
    represents_pokemon = supertype.casefold() in {"pokemon", "pokémon"}
    return (
        source == FALLBACK_SOURCE
        or not supertype
        or (represents_pokemon and not row.get("national_pokedex_numbers"))
    )


def canonical_set_needs_authoritative_refresh(rows: List[Dict[str, Any]]) -> bool:
    """Preserve refreshes for empty sets and any identity-incomplete row."""
    return not rows or any(canonical_row_needs_authoritative_refresh(row) for row in rows)


def catalog_only_eligibility_overrides(set_row: Dict[str, Any]) -> Dict[str, Any]:
    """Explicit canonical-card eligibility from the set lifecycle contract.

    Historical fallback rows originally relied on table defaults for ordinary sets
    and only overrode catalog-only rows. That is insufficient when a provider-only
    set later graduates into the normal root/subset lifecycle: its already-created
    canonical rows would retain the old catalog-only role/eligibility forever.

    Keep the helper name for compatibility, but make the contract explicit for all
    three structural cases:
      * catalog-only identity -> market-visible, never opening-eligible;
      * contributing subset -> role=subset and inherits parent contribution flags;
      * ordinary root -> normal main/opening-eligible defaults, written explicitly.
    """
    if set_row.get("catalog_only"):
        return {
            "catalog_role": "main",
            "set_value_eligible": True,
            "opening_eligible": False,
            "canonical_review_status": "approved",
            "eligibility_reason": CATALOG_ONLY_ELIGIBILITY_REASON,
        }

    if set_row.get("is_subset"):
        contributes_value = bool(set_row.get("counts_toward_parent_set_value"))
        contributes_opening = bool(set_row.get("counts_toward_parent_opening"))
        return {
            "catalog_role": "subset",
            "set_value_eligible": contributes_value,
            "opening_eligible": contributes_opening,
            "canonical_review_status": "approved",
            "eligibility_reason": (
                "pack_pulled_subset_card"
                if contributes_opening
                else "subset_not_opening_eligible"
            ),
        }

    return {
        "catalog_role": "main",
        "set_value_eligible": True,
        "opening_eligible": True,
        "canonical_review_status": "approved",
        "eligibility_reason": None,
    }



def _tcgdex_provider_name_key(value: Any) -> str:
    """Normalize only provider spelling noise; preserve Top/Bottom distinctions."""
    normalized = normalize_pokemon_name_key(value)
    normalized = re.sub(
        r"\((?:team plasma|delta species|prime)\)",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = _strip_name_tokens(normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.casefold())
    return " ".join(normalized.split())


def _refresh_tcgdex_canonical_cards(
    *, client: Any, set_row: Dict[str, Any], dry_run: bool,
    tcgdex_client: Optional[TCGdexPokemonClient] = None,
) -> Dict[str, Any]:
    """Hydrate canonical metadata from TCGdex without inventing PokemonTCG IDs.

    TCGdex is a free public metadata authority with its own identifiers. Those
    identifiers are retained only in source_payload; the legacy
    pokemon_tcg_api_card_id stays stable so existing canonical/market links do
    not break. Matching prefers exact number+name and then unique normalized
    name, which also supports reprint-style Classic Collection cards whose
    TCGdex local IDs are sequential rather than the original printed numbers.
    """
    set_id = str(set_row.get("id") or "").strip()
    set_name = str(set_row.get("name") or "").strip()
    if not set_id or not set_name:
        return {"status": "unavailable_missing_set_identity", "rows_found": 0, "rows_upserted": 0}

    provider = tcgdex_client or TCGdexPokemonClient()
    try:
        provider_cards = provider.fetch_card_details_for_set_name(set_name)
    except Exception as exc:
        logger.warning(
            "[desirability-inputs] TCGdex metadata unavailable for %s: %s",
            set_row.get("canonical_key") or set_id,
            exc,
        )
        return {
            "status": "unavailable_using_fallback",
            "source": TCGDEX_SOURCE,
            "rows_found": 0,
            "rows_upserted": 0,
            "reason": str(exc),
        }

    internal_cards = _list_cards_for_set(client, set_id)
    canonical_rows = _list_canonical_for_set(client, set_id)
    canonical_by_identity = {
        _canonical_identity(str(row.get("number") or ""), str(row.get("name") or "")): row
        for row in canonical_rows
    }
    provider_by_identity: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    provider_by_name: Dict[str, List[Dict[str, Any]]] = {}
    for row in provider_cards:
        number = _canonical_number(str(row.get("number") or ""))
        name_key = _tcgdex_provider_name_key(row.get("name"))
        if number and name_key:
            provider_by_identity.setdefault((number, name_key), []).append(row)
        if name_key:
            provider_by_name.setdefault(name_key, []).append(row)

    references = _list_pokemon_reference(client)
    reference_lookup = _build_reference_lookup(references)
    overrides = catalog_only_eligibility_overrides(set_row)

    planned: List[Tuple[Optional[str], Dict[str, Any]]] = []
    unmatched: List[Dict[str, Any]] = []
    ambiguous: List[Dict[str, Any]] = []

    for card in internal_cards:
        printed_number = str(card.get("card_number") or "").strip()
        number = _canonical_number(printed_number)
        name = str(card.get("name") or "").strip()
        if not number or not name:
            continue

        name_key = _tcgdex_provider_name_key(name)
        candidates = provider_by_identity.get((number, name_key), [])
        match_method = "number_name"
        if len(candidates) != 1:
            candidates = provider_by_name.get(name_key, [])
            match_method = "unique_name"
        if len(candidates) != 1:
            bucket = ambiguous if len(candidates) > 1 else unmatched
            if len(bucket) < 20:
                bucket.append({
                    "name": name,
                    "printed_number": printed_number,
                    "candidate_count": len(candidates),
                })
            continue

        provider_row = candidates[0]
        existing = canonical_by_identity.get(_canonical_identity(number, name))
        existing_source = str((existing or {}).get("source") or "")
        if existing and existing_source not in {"", FALLBACK_SOURCE, TCGDEX_SOURCE}:
            # Never downgrade an existing authoritative PokemonTCG/Scrydex row.
            continue

        pokedex_numbers = list(provider_row.get("national_pokedex_numbers") or [])
        if not pokedex_numbers and str(provider_row.get("supertype") or "").casefold() in {"pokemon", "pokémon"}:
            pokedex_numbers = [
                int(reference["pokedex_number"])
                for reference in _match_references_for_card_name(
                    name=name,
                    reference_lookup=reference_lookup,
                )
                if reference.get("pokedex_number") is not None
            ]

        stable_external_id = (
            str((existing or {}).get("pokemon_tcg_api_card_id") or "").strip()
            or str(card.get("pokemon_tcg_api_id") or "").strip()
            or _fallback_api_card_id(set_id=set_id, number=printed_number, name=name)
        )
        payload = {
            "set_id": set_id,
            "pokemon_tcg_api_card_id": stable_external_id,
            "name": name,
            "supertype": provider_row.get("supertype"),
            "subtypes": list(provider_row.get("subtypes") or []),
            "rarity": provider_row.get("rarity") or str(card.get("rarity") or "").strip() or None,
            "number": number,
            "printed_number": printed_number,
            "artist": provider_row.get("artist"),
            "national_pokedex_numbers": pokedex_numbers,
            "image_small_url": provider_row.get("image_small_url") or card.get("image_small_url"),
            "image_large_url": provider_row.get("image_large_url") or card.get("image_large_url"),
            "source": TCGDEX_SOURCE,
            "source_payload": {
                "provider": TCGDEX_SOURCE,
                "tcgdex_card_id": provider_row.get("tcgdex_card_id"),
                "match_method": match_method,
                "raw": provider_row.get("source_payload") or {},
            },
            **overrides,
        }
        planned.append((str(existing.get("id")) if existing and existing.get("id") else None, payload))

    written = 0
    if not dry_run:
        inserts: List[Dict[str, Any]] = []
        for existing_id, payload in planned:
            if existing_id:
                update_payload = {**payload, "updated_at": datetime.now(timezone.utc).isoformat()}
                def update_existing(_attempt: int, *, existing_id=existing_id, update_payload=update_payload):
                    return (
                        client.table("pokemon_canonical_cards")
                        .update(update_payload)
                        .eq("id", existing_id)
                        .execute()
                    )

                result = run_with_transient_retry(
                    update_existing,
                    operation_name="refresh_tcgdex_canonical_card",
                )
                written += len(result.data or []) or 1
            else:
                inserts.append(payload)
        if inserts:
            written += _upsert_canonical_rows(client, inserts)

    return {
        "status": "dry_run" if dry_run else "refreshed",
        "source": TCGDEX_SOURCE,
        "provider_rows_found": len(provider_cards),
        "internal_cards_found": len(internal_cards),
        "rows_matched": len(planned),
        "rows_unmatched": len(unmatched),
        "rows_ambiguous": len(ambiguous),
        "unmatched_examples": unmatched,
        "ambiguous_examples": ambiguous,
        "rows_upserted": written,
    }


def _refresh_authoritative_canonical_cards(
    *, client: Any, set_row: Dict[str, Any], dry_run: bool,
) -> Dict[str, Any]:
    """Prefer complete provider metadata before falling back to TCGplayer names.

    Newly announced sets can be present in TCGplayer before the authoritative
    Pokemon card endpoint has populated its checklist. The old pipeline created
    fallback rows at that point but never retried the authoritative source, so
    those rows remained permanently identity-poor. Every normal desirability
    rebuild now retries the configured Pokemon API set and replaces matching
    fallback rows through the canonical table's ordinary upsert contract.
    """
    api_set_id = str(set_row.get("pokemon_api_set_id") or "").strip()
    set_id = str(set_row.get("id") or "").strip()
    if not set_id:
        return {"status": "unavailable_missing_set_identity", "rows_found": 0, "rows_upserted": 0}
    if not api_set_id:
        return _refresh_tcgdex_canonical_cards(
            client=client, set_row=set_row, dry_run=dry_run,
        )
    try:
        api_set = fetch_authoritative_api_set(api_set_id)
        api_cards = fetch_authoritative_cards(api_set_id)
        printed_total = canonical_optional_int(api_set.get("printedTotal"))
        overrides = catalog_only_eligibility_overrides(set_row)
        rows = [
            {
                **build_authoritative_canonical_row(
                    local_set_id=set_id, api_set_id=api_set_id,
                    api_printed_total=printed_total, card=card,
                ),
                **overrides,
            }
            for card in api_cards
        ]
    except Exception as exc:
        logger.warning(
            "[desirability-inputs] PokemonTCG/Scrydex canonical refresh unavailable for %s: %s; "
            "trying free TCGdex metadata",
            set_row.get("canonical_key") or set_id, exc,
        )
        tcgdex = _refresh_tcgdex_canonical_cards(
            client=client, set_row=set_row, dry_run=dry_run,
        )
        tcgdex["upstream_error"] = str(exc)
        return tcgdex
    if not rows:
        return {"status": "unavailable_empty_checklist", "rows_found": 0, "rows_upserted": 0}

    # Promote identity-poor fallback rows IN PLACE before inserting provider
    # rows. Without this reconciliation, a set scraped before provider metadata
    # existed would retain its fallback:* canonical rows and gain a second copy
    # keyed by the authoritative API id when metadata later appeared.
    existing_rows = _list_canonical_for_set(client, set_id)
    fallback_by_identity = {
        _canonical_identity(str(row.get("number") or ""), str(row.get("name") or "")): row
        for row in existing_rows
        if str(row.get("source") or "") == FALLBACK_SOURCE
    }

    # Image sync writes the provider card ID onto the durable TCGplayer card row.
    # For reprint-style subsets, provider metadata may normalize punctuation/name
    # and omit the original-set denominator (e.g. "Buzzwole GX" 57/111 becomes
    # "Buzzwole-GX" 57). Exact canonical identity therefore cannot always promote
    # the pre-provider fallback row. Bridge through the internal card's exact
    # provider ID so one physical checklist card stays one canonical row.
    fallback_by_provider_id: Dict[str, Dict[str, Any]] = {}
    for internal_card in _list_cards_for_set(client, set_id):
        provider_id = str(internal_card.get("pokemon_tcg_api_id") or "").strip()
        if not provider_id:
            continue
        internal_key = _canonical_identity(
            _canonical_number(str(internal_card.get("card_number") or "")),
            str(internal_card.get("name") or ""),
        )
        fallback = fallback_by_identity.get(internal_key)
        if fallback:
            fallback_by_provider_id[provider_id] = fallback

    rows_to_upsert: List[Dict[str, Any]] = []
    promoted = 0
    for row in rows:
        key = _canonical_identity(str(row.get("number") or ""), str(row.get("name") or ""))
        provider_id = str(row.get("pokemon_tcg_api_card_id") or "").strip()
        fallback = fallback_by_identity.get(key) or fallback_by_provider_id.get(provider_id)
        if not fallback or not fallback.get("id"):
            rows_to_upsert.append(row)
            continue
        if dry_run:
            promoted += 1
            continue
        update_payload = dict(row)
        update_payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = (
            client.table("pokemon_canonical_cards")
            .update(update_payload)
            .eq("id", fallback["id"])
            .execute()
        )
        promoted += len(result.data or []) or 1

    inserted_or_updated = 0 if dry_run else _upsert_canonical_rows(client, rows_to_upsert)
    written = promoted + inserted_or_updated
    return {
        "status": "dry_run" if dry_run else "refreshed",
        "source": "pokemon_tcg_api",
        "rows_found": len(rows),
        "rows_promoted_from_fallback": promoted,
        "rows_upserted_by_api_id": inserted_or_updated,
        "rows_upserted": written,
    }


def _build_links(
    *,
    selected_set_key: Optional[str],
    process_all: bool,
    hit_policy_version: str,
    dry_run: bool,
) -> Dict[str, Any]:
    return build_links_report(
        repository=PokemonCardDesirabilityLinksRepository(),
        set_key=selected_set_key,
        process_all=bool(process_all and not selected_set_key),
        hit_policy_version=hit_policy_version,
        dry_run=dry_run,
    )


def _build_summaries(
    *,
    selected_set_key: Optional[str],
    process_all: bool,
    hit_policy_version: str,
    dry_run: bool,
) -> Dict[str, Any]:
    return build_set_hit_desirability_summaries_report(
        repository=PokemonSetHitDesirabilitySummariesRepository(),
        set_key=selected_set_key,
        process_all=bool(process_all and not selected_set_key),
        aggregation_version=DEFAULT_AGGREGATION_VERSION,
        hit_policy_version=hit_policy_version,
        composite_scoring_version=COMPOSITE_SCORING_VERSION,
        min_composite_coverage=0.95,
        dry_run=dry_run,
    )


def _build_components(
    *,
    selected_set_key: Optional[str],
    process_all: bool,
    hit_policy_version: str,
    dry_run: bool,
    force: bool = False,
) -> Dict[str, Any]:
    _ = process_all
    return build_component_scores_report(
        repository=PokemonSetDesirabilityComponentsRepository(),
        set_id=None,
        canonical_key=selected_set_key,
        limit=None,
        force=force,
        scoring_version=COMPONENT_SCORING_VERSION,
        hit_policy_version=hit_policy_version,
        composite_scoring_version=COMPOSITE_SCORING_VERSION,
        min_composite_coverage=0.95,
        dry_run=dry_run,
    )


def _build_opening(
    *,
    selected_set_ids: Sequence[str],
    hit_policy_version: str,
    dry_run: bool,
) -> Dict[str, Any]:
    repository = RipDesirabilityPrototypeRepository()
    report = build_report(
        repository=repository,
        scoring_version=COMPONENT_SCORING_VERSION,
        hit_policy_version=hit_policy_version,
        composite_scoring_version=COMPOSITE_SCORING_VERSION,
        limit=None,
    )
    rows = [
        row
        for row in list(report.get("rows") or [])
        if str(row.get("set_id") or "") in set(selected_set_ids)
    ]

    if dry_run:
        return {
            "committed": False,
            "target_table": OPENING_DESIRABILITY_TABLE,
            "rows_available_in_report": len(report.get("rows") or []),
            "rows_selected": len(rows),
            "rows_to_write": 0,
            "rows_that_would_be_persisted": len(rows),
            "written_rows_returned": 0,
            "scoring_version": OPENING_SCORING_VERSION,
            "hit_policy_version": hit_policy_version,
        }

    payload = build_opening_desirability_persistence_rows(rows, scoring_version=OPENING_SCORING_VERSION)
    deduped_payload = _filter_existing_opening_rows(repository=repository, rows=payload)
    written = _insert_opening_rows(repository=repository, rows=deduped_payload)
    return {
        "committed": True,
        "target_table": OPENING_DESIRABILITY_TABLE,
        "rows_available_in_report": len(report.get("rows") or []),
        "rows_selected": len(rows),
        "rows_to_write": len(deduped_payload),
        "rows_that_would_be_persisted": len(rows),
        "written_rows_returned": written,
        "scoring_version": OPENING_SCORING_VERSION,
        "hit_policy_version": hit_policy_version,
    }


def _insert_opening_rows(*, repository: RipDesirabilityPrototypeRepository, rows: Sequence[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    written = 0
    for chunk in _chunked(list(rows), UPSERT_BATCH_SIZE):
        response = repository.client.table(OPENING_DESIRABILITY_TABLE).insert(list(chunk)).execute()
        written += len(response.data or [])
    return written


def _filter_existing_opening_rows(*, repository: RipDesirabilityPrototypeRepository, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    set_ids = sorted({str(row.get("set_id")) for row in rows if row.get("set_id") is not None})
    if not set_ids:
        return []

    existing_rows: List[Dict[str, Any]] = []
    for chunk in _chunked(set_ids, 200):
        result = (
            repository.client.table(OPENING_DESIRABILITY_TABLE)
            .select("set_id,scoring_version,source_v2_component_row_id,source_rip_calculation_run_id")
            .in_("set_id", list(chunk))
            .eq("scoring_version", OPENING_SCORING_VERSION)
            .execute()
        )
        existing_rows.extend(result.data or [])

    existing_signatures = {
        _opening_signature(
            set_id=row.get("set_id"),
            scoring_version=row.get("scoring_version"),
            source_v2_component_row_id=row.get("source_v2_component_row_id"),
            source_rip_calculation_run_id=row.get("source_rip_calculation_run_id"),
        )
        for row in existing_rows
    }

    filtered: List[Dict[str, Any]] = []
    for row in rows:
        signature = _opening_signature(
            set_id=row.get("set_id"),
            scoring_version=row.get("scoring_version"),
            source_v2_component_row_id=row.get("source_v2_component_row_id"),
            source_rip_calculation_run_id=row.get("source_rip_calculation_run_id"),
        )
        if signature in existing_signatures:
            continue
        filtered.append(row)
    return filtered


def _opening_signature(*, set_id: Any, scoring_version: Any, source_v2_component_row_id: Any, source_rip_calculation_run_id: Any) -> Tuple[str, str, str, str]:
    return (
        str(set_id or ""),
        str(scoring_version or ""),
        str(source_v2_component_row_id or ""),
        str(source_rip_calculation_run_id or ""),
    )


def _list_sets(client: Any, *, set_key: Optional[str], process_all: bool) -> List[Dict[str, Any]]:
    query = client.table("sets").select(
        "id,name,canonical_key,pokemon_api_set_id,catalog_only,is_subset,"
        "counts_toward_parent_set_value,counts_toward_parent_opening"
    ).order("name")
    if set_key:
        query = query.eq("canonical_key", set_key)
    elif not process_all:
        raise SetDesirabilityInputsError("Choose --set or --all")
    result = query.execute()
    return list(result.data or [])


def _list_cards_for_set(client: Any, set_id: str) -> List[Dict[str, Any]]:
    result = (
        client.table("cards")
        .select("id,set_id,name,rarity,card_number,pokemon_tcg_api_id,image_small_url,image_large_url")
        .eq("set_id", set_id)
        .order("card_number")
        .order("name")
        .execute()
    )
    return list(result.data or [])


def _list_canonical_for_set(client: Any, set_id: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        result = (
            client.table("pokemon_canonical_cards")
            .select("id,set_id,pokemon_tcg_api_card_id,name,number,source,supertype,national_pokedex_numbers")
            .eq("set_id", set_id)
            .range(start, start + page_size - 1)
            .execute()
        )
        page = list(result.data or [])
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return rows


def _list_pokemon_reference(client: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        result = (
            client.table("pokemon_reference")
            .select("id,pokedex_number,canonical_name,display_name")
            .range(start, start + page_size - 1)
            .execute()
        )
        page = list(result.data or [])
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return rows


def _list_authoritative_non_pokemon_name_supertypes(
    client: Any,
    names: Sequence[str],
) -> Dict[str, str]:
    """Reuse exact-name supertype evidence from authoritative canonical rows.

    This is intentionally exact-name only. It safely recognizes recurring
    Trainer/Energy cards such as Switch without teaching the fallback path a
    fuzzy non-Pokemon classifier that could swallow owned Pokemon names.
    Conflicting authoritative supertypes are omitted rather than guessed.
    """
    clean_names = sorted({str(name or "").strip() for name in names if str(name or "").strip()})
    observed: Dict[str, set[str]] = {}
    for chunk in _chunked(clean_names, 100):
        result = (
            client.table("pokemon_canonical_cards")
            .select("name,supertype,source")
            .in_("name", list(chunk))
            .neq("source", FALLBACK_SOURCE)
            .execute()
        )
        for row in list(result.data or []):
            supertype = str(row.get("supertype") or "").strip()
            if not supertype or supertype.casefold() in {"pokemon", "pokémon"}:
                continue
            key = normalize_pokemon_name_key(row.get("name"))
            if key:
                observed.setdefault(key, set()).add(supertype)

    return {
        key: next(iter(values))
        for key, values in observed.items()
        if len(values) == 1
    }


def _list_trainer_reference_names(client: Any) -> set[str]:
    """Load reviewed active Trainer identities for exact-name fallback typing.

    Exact matching is deliberate. Prefix matching would misclassify owned
    Pokemon names such as "Erika's Jigglypuff" as Trainer cards.
    """
    rows: List[Dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        result = (
            client.table("pokemon_collector_entity_reference")
            .select("display_name")
            .eq("entity_type", "trainer")
            .eq("active", True)
            .range(start, start + page_size - 1)
            .execute()
        )
        page = list(result.data or [])
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    return {
        key
        for row in rows
        for key in [normalize_pokemon_name_key(row.get("display_name"))]
        if key
    }


def _reference_alias_keys(reference: Dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ("display_name", "canonical_name"):
        key = normalize_pokemon_name_key(reference.get(field))
        if not key:
            continue
        keys.add(key)
        for suffix in FORM_SUFFIXES_TO_STRIP:
            suffix_text = f" {suffix}"
            if key.endswith(suffix_text):
                stripped = key[: -len(suffix_text)].strip()
                if stripped:
                    keys.add(stripped)
    return keys


def _build_reference_lookup(
    references: Sequence[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    lookup: Dict[str, List[Dict[str, Any]]] = {}
    for row in references:
        for key in _reference_alias_keys(row):
            bucket = lookup.setdefault(key, [])
            if not any(str(existing.get("id")) == str(row.get("id")) for existing in bucket):
                bucket.append(row)
    return lookup


def _contains_word_phrase(haystack: str, needle: str) -> bool:
    return f" {needle} " in f" {haystack} "


def _strip_regional_prefix(value: str) -> str:
    tokens = value.split()
    if tokens and tokens[0] in REGIONAL_FORM_PREFIXES:
        return " ".join(tokens[1:]).strip()
    return value


def _match_references_for_card_name(
    *,
    name: str,
    reference_lookup: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Resolve all unambiguous Pokemon subjects represented by a fallback name.

    Provider-only rows do not carry Pokemon TCG API supertype/Pokedex metadata.
    Use the maintained Pokemon reference registry instead of hard-coded set
    exceptions. Whole-word phrase matching supports legacy modifiers/owners and
    explicit multi-Pokemon names while avoiding substring collisions (Mew is not
    matched inside Mewtwo).
    """
    normalized = normalize_pokemon_name_key(name)
    if not normalized:
        return []

    cleaned = _strip_name_tokens(normalized)
    candidates = [cleaned]
    regional = _strip_regional_prefix(cleaned)
    if regional and regional != cleaned:
        candidates.append(regional)

    matched: Dict[str, Dict[str, Any]] = {}

    # Strongest path: exact alias/form-default match.
    for candidate in candidates:
        rows = reference_lookup.get(candidate) or []
        for row in rows:
            if row.get("id") is not None:
                matched[str(row["id"])] = row
    if matched:
        return sorted(
            matched.values(),
            key=lambda row: (int(row.get("pokedex_number") or 10**9), str(row.get("id"))),
        )

    # Provider names frequently retain descriptors that are not part of species
    # identity: "Shining Celebi", "Dark Tyranitar", "Crobat G",
    # "Genesect EX (Team Plasma)", "Erika's Jigglypuff", etc. Match only full
    # word phrases from the maintained reference registry. Multiple distinct
    # matches are intentional for TAG TEAM / LEGEND cards.
    for candidate in candidates:
        for key, rows in reference_lookup.items():
            if not key or len(key) < 3:
                continue
            if not _contains_word_phrase(candidate, key):
                continue
            for row in rows:
                if row.get("id") is not None:
                    matched[str(row["id"])] = row

    return sorted(
        matched.values(),
        key=lambda row: (int(row.get("pokedex_number") or 10**9), str(row.get("id"))),
    )


def _match_reference_for_card_name(
    *,
    name: str,
    reference_lookup: Dict[str, List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """Backward-compatible single-subject wrapper for existing callers/tests."""
    matches = _match_references_for_card_name(name=name, reference_lookup=reference_lookup)
    return matches[0] if len(matches) == 1 else None


def _strip_name_tokens(value: str) -> str:
    cleaned = value
    cleaned = CARD_SUFFIX_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\bmega\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _infer_non_pokemon_supertype(name: str) -> Optional[str]:
    normalized = normalize_pokemon_name_key(name)
    if not normalized:
        return None
    for keyword in TRAINER_LIKE_KEYWORDS:
        if keyword in normalized:
            if keyword == "energy":
                return "Energy"
            return "Trainer"
    return None


def _fallback_api_card_id(*, set_id: str, number: str, name: str) -> str:
    normalized_name = normalize_pokemon_name_key(name) or "unknown"
    return f"fallback:{set_id}:{number}:{normalized_name}"


def _canonical_identity(number: str, name: str) -> Tuple[str, str]:
    return (_canonical_number(number), name.strip().lower())


def _canonical_number(card_number: str) -> str:
    value = str(card_number or "").strip()
    if not value:
        return ""

    left = value.split("/", 1)[0].strip()
    if left.isdigit():
        return str(int(left))
    return left


def _infer_subtypes(name: str) -> List[str]:
    subtypes: List[str] = []
    if "mega" in str(name or "").lower():
        subtypes.append("MEGA")
    if STANDALONE_EX_RE.search(str(name or "")):
        subtypes.append("ex")
    return subtypes


def _upsert_canonical_rows(client: Any, rows: Sequence[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    payload = [dict(row, updated_at=now) for row in rows]
    written = 0
    for chunk in _chunked(payload, UPSERT_BATCH_SIZE):
        chunk_rows = list(chunk)

        def upsert_chunk(_attempt: int, *, chunk_rows=chunk_rows):
            return (
                client.table("pokemon_canonical_cards")
                .upsert(chunk_rows, on_conflict="pokemon_tcg_api_card_id")
                .execute()
            )

        result = run_with_transient_retry(
            upsert_chunk,
            operation_name="upsert_pokemon_canonical_cards",
        )
        written += len(result.data or [])
    return written


def _chunked(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SetDesirabilityInputsError as exc:
        print(f"[pokemon-set-desirability-inputs][ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
