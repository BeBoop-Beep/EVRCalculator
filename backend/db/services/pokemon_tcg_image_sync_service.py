import re
import sys
import os
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.db.clients.pokemon_tcg_api_client import PokemonTCGAPIClient
from backend.db.repositories.card_variant_repository import (
    get_card_variants_by_card_ids,
    update_card_variant_image_sync_fields_batch,
)
from backend.db.repositories.cards_repository import (
    get_all_cards_for_set,
    update_card_image_sync_fields_batch,
)
from backend.db.repositories.sets_repository import get_set_by_name, get_set_id_by_name


TARGET_SET_API_SEARCH_NAMES = {
    "Prismatic Evolutions": "Prismatic Evolutions",
    "Scarlet and Violet 151": "151",
}

IMAGE_ONLY_SPECIAL_TYPES = {"pokeball", "poke ball", "master ball", "masterball"}


class PokemonTCGImageSyncService:
    """One-way sync of Pokemon TCG image URLs onto existing card_variants rows."""

    def __init__(self, client: Optional[PokemonTCGAPIClient] = None):
        self.client = client or PokemonTCGAPIClient()

    def sync_set(self, set_name: str, dry_run: bool = True) -> Dict[str, object]:
        internal_set_id = get_set_id_by_name(set_name)
        if not internal_set_id:
            raise ValueError(f"Set '{set_name}' was not found in the internal database")

        set_row = get_set_by_name(set_name)
        pokemon_api_set_id = (set_row.data or {}).get("pokemon_api_set_id") if set_row and set_row.data else None

        if pokemon_api_set_id:
            api_set = {"id": pokemon_api_set_id, "name": set_name}
        else:
            api_set_search_name = TARGET_SET_API_SEARCH_NAMES.get(set_name, set_name)
            api_set = self.client.resolve_set(api_set_search_name)
        api_cards = list(self.client.iter_cards_for_set(api_set["id"]))

        internal_cards = get_all_cards_for_set(internal_set_id)
        card_ids = [card["id"] for card in internal_cards]
        variants = get_card_variants_by_card_ids(card_ids)
        variants_by_card_id = defaultdict(list)
        for variant in variants:
            variants_by_card_id[variant["card_id"]].append(variant)

        exact_index = defaultdict(list)
        number_index = defaultdict(list)
        for card in internal_cards:
            normalized_number = self._normalize_card_number(card.get("card_number"))
            normalized_name = self._normalize_card_name(card.get("name"), card.get("card_number"))
            if not normalized_number or not normalized_name:
                continue
            exact_index[(normalized_number, normalized_name)].append(card)
            number_index[normalized_number].append(card)

        api_fetch_summary = {
            "internal_set_name": set_name,
            "internal_set_id": internal_set_id,
            "pokemon_api_set_id": pokemon_api_set_id,
            "api_set_id_used": api_set.get("id"),
            "api_set_name_used": api_set.get("name"),
            "api_cards_fetched": len(api_cards),
            "internal_cards_loaded": len(internal_cards),
            "internal_variants_loaded": len(variants),
        }

        updates_by_card_id: Dict[str, Dict[str, object]] = {}
        updates_by_variant_id: Dict[str, Dict[str, object]] = {}
        unmatched = []
        skipped = []
        image_only_matches = 0
        exact_matches = 0
        fallback_matches = 0
        sync_timestamp = datetime.now(timezone.utc).isoformat()

        card_matching_summary = {
            "api_cards_seen": 0,
            "internal_cards_seen": len(internal_cards),
            "cards_matched_by_number_name": 0,
            "cards_matched_by_number_only_unique": 0,
            "cards_unmatched": 0,
            "cards_ambiguous": 0,
        }
        image_availability_summary = {
            "api_cards_with_small_image": 0,
            "api_cards_with_large_image": 0,
            "matched_cards_with_small_image": 0,
            "matched_cards_with_large_image": 0,
        }
        variant_impact_preview_summary = {
            "variants_seen_for_matched_cards": 0,
            "variants_with_existing_image": 0,
            "variants_that_would_gain_resolved_image_from_card": 0,
            "variants_still_missing_after_card_fallback": 0,
            "matched_cards_with_existing_card_image": 0,
            "matched_cards_missing_card_image": 0,
            "matched_cards_that_would_receive_card_image": 0,
        }

        card_match_preview: List[Dict[str, Any]] = []
        variant_match_preview: List[Dict[str, Any]] = []
        unmatched_examples: List[Dict[str, Any]] = []
        ambiguous_examples: List[Dict[str, Any]] = []
        matched_cards_with_zero_variants_examples: List[Dict[str, Any]] = []
        matched_internal_card_ids: set = set()
        matched_card_ids_with_existing_image: set = set()
        matched_card_ids_missing_image: set = set()
        matched_card_ids_that_would_receive_image: set = set()
        api_exact_key_counts: Dict[str, int] = defaultdict(int)

        for api_card in api_cards:
            card_matching_summary["api_cards_seen"] += 1

            normalized_number = self._normalize_card_number(api_card.get("number"))
            normalized_name = self._normalize_card_name(api_card.get("name"))

            if api_card.get("image_small_url"):
                image_availability_summary["api_cards_with_small_image"] += 1
            if api_card.get("image_large_url"):
                image_availability_summary["api_cards_with_large_image"] += 1

            if normalized_number and normalized_name:
                api_exact_key_counts[f"{normalized_number}::{normalized_name}"] += 1

            preview_record: Dict[str, Any] = {
                "api_card_id": api_card.get("pokemon_tcg_api_id"),
                "api_card_name": api_card.get("name"),
                "api_card_number": api_card.get("number"),
                "api_image_small_url": api_card.get("image_small_url"),
                "api_image_large_url": api_card.get("image_large_url"),
                "normalized_name": normalized_name,
                "normalized_number": normalized_number,
                "matched_card_id": None,
                "matched_card_name": None,
                "matched_card_number": None,
                "match_strategy": None,
                "reason": None,
            }

            if not normalized_number or not normalized_name:
                preview_record["match_strategy"] = "unmatched"
                preview_record["reason"] = "API card is missing a usable name or number"
                card_matching_summary["cards_unmatched"] += 1
                if len(unmatched_examples) < 25:
                    unmatched_examples.append(
                        {
                            "api_card_id": api_card.get("pokemon_tcg_api_id"),
                            "name": api_card.get("name"),
                            "card_number": api_card.get("number"),
                            "normalized_name": normalized_name,
                            "normalized_number": normalized_number,
                            "candidate_count": 0,
                            "reason": "API card is missing a usable name or number",
                        }
                    )

                skipped.append(
                    {
                        "api_card_id": api_card.get("pokemon_tcg_api_id"),
                        "name": api_card.get("name"),
                        "number": api_card.get("number"),
                        "reason": "API card is missing a usable name or number",
                    }
                )
                card_match_preview.append(preview_record)
                continue

            strict_exact_candidates = exact_index.get((normalized_number, normalized_name), [])
            strict_number_candidates = number_index.get(normalized_number, [])
            strict_match_card = None
            strict_match_strategy = None
            strict_reason = None

            if len(strict_exact_candidates) == 1:
                strict_match_card = strict_exact_candidates[0]
                strict_match_strategy = "number_name"
            elif len(strict_exact_candidates) > 1:
                strict_match_strategy = "ambiguous"
                strict_reason = "Multiple internal cards matched normalized number+name"
            elif len(strict_number_candidates) == 1:
                strict_match_card = strict_number_candidates[0]
                strict_match_strategy = "number_only_unique"
            elif len(strict_number_candidates) > 1:
                strict_match_strategy = "ambiguous"
                strict_reason = "Multiple internal cards matched normalized number"
            else:
                strict_match_strategy = "unmatched"
                strict_reason = "No internal cards matched normalized number+name or unique number"

            if strict_match_strategy == "number_name":
                card_matching_summary["cards_matched_by_number_name"] += 1
            elif strict_match_strategy == "number_only_unique":
                card_matching_summary["cards_matched_by_number_only_unique"] += 1
            elif strict_match_strategy == "ambiguous":
                card_matching_summary["cards_ambiguous"] += 1
            else:
                card_matching_summary["cards_unmatched"] += 1

            if strict_match_card:
                preview_record["matched_card_id"] = strict_match_card.get("id")
                preview_record["matched_card_name"] = strict_match_card.get("name")
                preview_record["matched_card_number"] = strict_match_card.get("card_number")
                preview_record["match_strategy"] = strict_match_strategy

                matched_internal_card_ids.add(strict_match_card.get("id"))

                strict_card_has_existing_image = bool(
                    strict_match_card.get("image_small_url") or strict_match_card.get("image_large_url")
                )
                strict_api_has_image = bool(api_card.get("image_small_url") or api_card.get("image_large_url"))
                if strict_card_has_existing_image:
                    matched_card_ids_with_existing_image.add(strict_match_card.get("id"))
                else:
                    matched_card_ids_missing_image.add(strict_match_card.get("id"))
                    if strict_api_has_image:
                        matched_card_ids_that_would_receive_image.add(strict_match_card.get("id"))

                if api_card.get("image_small_url"):
                    image_availability_summary["matched_cards_with_small_image"] += 1
                if api_card.get("image_large_url"):
                    image_availability_summary["matched_cards_with_large_image"] += 1

                preview_variants = variants_by_card_id.get(strict_match_card.get("id"), [])
                variant_impact_preview_summary["variants_seen_for_matched_cards"] += len(preview_variants)

                if not preview_variants and len(matched_cards_with_zero_variants_examples) < 25:
                    matched_cards_with_zero_variants_examples.append(
                        {
                            "api_card_id": api_card.get("pokemon_tcg_api_id"),
                            "api_card_name": api_card.get("name"),
                            "api_card_number": api_card.get("number"),
                            "normalized_name": normalized_name,
                            "normalized_number": normalized_number,
                            "matched_card_id": strict_match_card.get("id"),
                            "matched_card_name": strict_match_card.get("name"),
                            "matched_card_number": strict_match_card.get("card_number"),
                            "candidate_count": 0,
                        }
                    )

                variant_rows = []
                for variant in preview_variants:
                    has_variant_image = bool(variant.get("image_small_url") or variant.get("image_large_url"))
                    has_api_image = bool(api_card.get("image_small_url") or api_card.get("image_large_url"))
                    if has_variant_image:
                        resolution_status = "variant_image"
                        variant_impact_preview_summary["variants_with_existing_image"] += 1
                    elif has_api_image:
                        resolution_status = "future_card_image_fallback"
                        variant_impact_preview_summary["variants_that_would_gain_resolved_image_from_card"] += 1
                    else:
                        resolution_status = "no_image"
                        variant_impact_preview_summary["variants_still_missing_after_card_fallback"] += 1

                    variant_rows.append(
                        {
                            "variant_id": variant.get("id"),
                            "printing_type": variant.get("printing_type"),
                            "special_type": variant.get("special_type"),
                            "edition": variant.get("edition"),
                            "has_image_small": bool(variant.get("image_small_url")),
                            "has_image_large": bool(variant.get("image_large_url")),
                            "would_resolve_image_via": resolution_status,
                        }
                    )

                variant_match_preview.append(
                    {
                        "api_card_id": api_card.get("pokemon_tcg_api_id"),
                        "api_card_name": api_card.get("name"),
                        "api_card_number": api_card.get("number"),
                        "matched_card_id": strict_match_card.get("id"),
                        "matched_card_name": strict_match_card.get("name"),
                        "matched_card_number": strict_match_card.get("card_number"),
                        "variants_count": len(preview_variants),
                        "variants": variant_rows,
                    }
                )
            else:
                preview_record["match_strategy"] = strict_match_strategy
                preview_record["reason"] = strict_reason

                if strict_match_strategy == "ambiguous" and len(ambiguous_examples) < 25:
                    source_candidates = strict_exact_candidates if strict_exact_candidates else strict_number_candidates
                    ambiguous_examples.append(
                        {
                            "api_card_id": api_card.get("pokemon_tcg_api_id"),
                            "name": api_card.get("name"),
                            "card_number": api_card.get("number"),
                            "normalized_name": normalized_name,
                            "normalized_number": normalized_number,
                            "candidate_count": len(source_candidates),
                            "candidate_cards": [
                                {
                                    "card_id": candidate.get("id"),
                                    "card_name": candidate.get("name"),
                                    "card_number": candidate.get("card_number"),
                                }
                                for candidate in source_candidates
                            ],
                            "reason": strict_reason,
                        }
                    )

                if strict_match_strategy == "unmatched" and len(unmatched_examples) < 25:
                    unmatched_examples.append(
                        {
                            "api_card_id": api_card.get("pokemon_tcg_api_id"),
                            "name": api_card.get("name"),
                            "card_number": api_card.get("number"),
                            "normalized_name": normalized_name,
                            "normalized_number": normalized_number,
                            "candidate_count": 0,
                            "reason": strict_reason,
                        }
                    )

            card_match_preview.append(preview_record)

            candidate_cards = exact_index.get((normalized_number, normalized_name), [])
            match_type = "exact"

            if not candidate_cards:
                fallback_candidates = number_index.get(normalized_number, [])
                if len(fallback_candidates) == 1:
                    candidate_cards = fallback_candidates
                    match_type = "number_only"
                else:
                    unmatched.append(
                        {
                            "api_card_id": api_card.get("pokemon_tcg_api_id"),
                            "name": api_card.get("name"),
                            "number": api_card.get("number"),
                            "reason": "No safe internal match found",
                        }
                    )
                    continue

            if match_type == "exact":
                exact_matches += 1
            else:
                fallback_matches += 1

            for card in candidate_cards:
                card_update_payload = {
                    "card_id": card["id"],
                    "image_last_synced_at": sync_timestamp,
                }
                if api_card.get("image_small_url"):
                    card_update_payload["image_small_url"] = api_card["image_small_url"]
                if api_card.get("image_large_url"):
                    card_update_payload["image_large_url"] = api_card["image_large_url"]
                if api_card.get("pokemon_tcg_api_id"):
                    card_update_payload["pokemon_tcg_api_id"] = api_card["pokemon_tcg_api_id"]

                if len(card_update_payload) > 2:
                    updates_by_card_id[card["id"]] = card_update_payload

                card_variants = variants_by_card_id.get(card["id"], [])
                if not card_variants:
                    skipped.append(
                        {
                            "card_id": card["id"],
                            "name": card.get("name"),
                            "number": card.get("card_number"),
                            "reason": "Matched card has no card_variants rows",
                        }
                    )
                    continue

                for variant in card_variants:
                    existing_api_id = variant.get("pokemon_tcg_api_id")
                    can_store_api_id = match_type == "exact" and not self._is_image_only_variant(variant)

                    if existing_api_id and can_store_api_id and existing_api_id != api_card.get("pokemon_tcg_api_id"):
                        skipped.append(
                            {
                                "card_id": variant["id"],
                                "name": card.get("name"),
                                "number": card.get("card_number"),
                                "reason": (
                                    f"Existing pokemon_tcg_api_id '{existing_api_id}' conflicts with "
                                    f"'{api_card.get('pokemon_tcg_api_id')}'"
                                ),
                            }
                        )
                        continue

                    update_payload = {
                        "card_id": variant["id"],
                        "image_last_synced_at": sync_timestamp,
                    }
                    if api_card.get("image_small_url"):
                        update_payload["image_small_url"] = api_card["image_small_url"]
                    if api_card.get("image_large_url"):
                        update_payload["image_large_url"] = api_card["image_large_url"]
                    if can_store_api_id and api_card.get("pokemon_tcg_api_id"):
                        update_payload["pokemon_tcg_api_id"] = api_card["pokemon_tcg_api_id"]
                    elif self._is_image_only_variant(variant):
                        image_only_matches += 1

                    if len(update_payload) == 2:
                        skipped.append(
                            {
                                "card_id": variant["id"],
                                "name": card.get("name"),
                                "number": card.get("card_number"),
                                "reason": "API card did not include image URLs",
                            }
                        )
                        continue

                    updates_by_variant_id[variant["id"]] = update_payload

        internal_cards_with_no_matching_api_examples: List[Dict[str, Any]] = []
        for card in internal_cards:
            card_id = card.get("id")
            normalized_number = self._normalize_card_number(card.get("card_number"))
            normalized_name = self._normalize_card_name(card.get("name"), card.get("card_number"))
            if not normalized_number or not normalized_name:
                continue

            if card_id in matched_internal_card_ids:
                continue

            api_match_count = api_exact_key_counts.get(f"{normalized_number}::{normalized_name}", 0)
            if len(internal_cards_with_no_matching_api_examples) < 25:
                internal_cards_with_no_matching_api_examples.append(
                    {
                        "card_id": card_id,
                        "name": card.get("name"),
                        "card_number": card.get("card_number"),
                        "normalized_name": normalized_name,
                        "normalized_number": normalized_number,
                        "candidate_count": api_match_count,
                    }
                )

        variant_impact_preview_summary["matched_cards_with_existing_card_image"] = len(matched_card_ids_with_existing_image)
        variant_impact_preview_summary["matched_cards_missing_card_image"] = len(matched_card_ids_missing_image)
        variant_impact_preview_summary["matched_cards_that_would_receive_card_image"] = len(
            matched_card_ids_that_would_receive_image
        )

        card_updates = list(updates_by_card_id.values())
        updated_card_count = 0
        if not dry_run and card_updates:
            updated_card_count = update_card_image_sync_fields_batch(card_updates)

        updates = list(updates_by_variant_id.values())
        updated_count = 0
        if not dry_run and updates:
            updated_count = update_card_variant_image_sync_fields_batch(updates)

        existing_write_behavior = {
            "existing_card_updates_planned": len(card_updates),
            "existing_card_updates_written": updated_card_count,
            "existing_variant_updates_planned": len(updates),
            "existing_variant_updates_written": updated_count,
            "dry_run": dry_run,
        }

        preview_examples = {
            "unmatched_api_cards": unmatched_examples,
            "ambiguous_api_cards": ambiguous_examples,
            "matched_api_cards_with_zero_variants": matched_cards_with_zero_variants_examples,
            "internal_cards_with_no_matching_api": internal_cards_with_no_matching_api_examples,
        }

        preview_summary_payload = {
            "api_fetch_summary": api_fetch_summary,
            "card_matching_summary": card_matching_summary,
            "image_availability_summary": image_availability_summary,
            "variant_impact_preview_summary": variant_impact_preview_summary,
            "existing_write_behavior": existing_write_behavior,
            "preview_example_counts": {
                "unmatched_api_cards": len(unmatched_examples),
                "ambiguous_api_cards": len(ambiguous_examples),
                "matched_api_cards_with_zero_variants": len(matched_cards_with_zero_variants_examples),
                "internal_cards_with_no_matching_api": len(internal_cards_with_no_matching_api_examples),
            },
        }

        print("[SYNC PREVIEW]", json.dumps(preview_summary_payload, indent=2))

        return {
            "set_name": set_name,
            "internal_set_id": internal_set_id,
            "pokemon_api_set_id": pokemon_api_set_id,
            "api_set_id": api_set.get("id"),
            "api_set_name": api_set.get("name"),
            "dry_run": dry_run,
            "fetched_api_cards": len(api_cards),
            "exact_matches": exact_matches,
            "fallback_matches": fallback_matches,
            "prepared_card_updates": len(card_updates),
            "updated_card_rows": updated_card_count,
            "prepared_variant_updates": len(updates),
            "updated_variant_rows": updated_count,
            "image_only_variant_matches": image_only_matches,
            "unmatched": unmatched,
            "skipped": skipped,
            "api_fetch_summary": api_fetch_summary,
            "card_matching_summary": card_matching_summary,
            "image_availability_summary": image_availability_summary,
            "variant_impact_preview_summary": variant_impact_preview_summary,
            "existing_write_behavior": existing_write_behavior,
            "preview_examples": preview_examples,
            "card_match_preview": card_match_preview,
            "variant_match_preview": variant_match_preview,
        }

    @staticmethod
    def _normalize_card_name(name: Optional[str], card_number: Optional[str] = None) -> Optional[str]:
        if not name:
            return None

        normalized = " ".join(str(name).strip().split())
        if card_number:
            suffix = f" - {card_number}"
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)].rstrip()
        return normalized.casefold()

    @staticmethod
    def _normalize_card_number(number: Optional[str]) -> Optional[str]:
        if not number:
            return None

        base_number = str(number).split("/", 1)[0].strip().upper()
        if not base_number:
            return None
        return re.sub(r"^0+(?=\d)", "", base_number) or "0"

    @staticmethod
    def _is_image_only_variant(variant: Dict[str, object]) -> bool:
        special_type = str(variant.get("special_type") or "").strip().lower()
        return special_type in IMAGE_ONLY_SPECIAL_TYPES
