import re
import sys
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.db.clients.pokemon_tcg_api_client import PokemonTCGAPIClient
from backend.db.repositories.card_variant_repository import (
    get_card_variants_by_card_ids,
    update_card_variant_image_sync_fields_batch,
)
from backend.db.repositories.cards_repository import get_all_cards_for_set
from backend.db.repositories.sets_repository import get_set_id_by_name


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

        updates_by_variant_id: Dict[str, Dict[str, object]] = {}
        unmatched = []
        skipped = []
        image_only_matches = 0
        exact_matches = 0
        fallback_matches = 0
        sync_timestamp = datetime.now(timezone.utc).isoformat()

        for api_card in api_cards:
            normalized_number = self._normalize_card_number(api_card.get("number"))
            normalized_name = self._normalize_card_name(api_card.get("name"))
            if not normalized_number or not normalized_name:
                skipped.append(
                    {
                        "api_card_id": api_card.get("pokemon_tcg_api_id"),
                        "name": api_card.get("name"),
                        "number": api_card.get("number"),
                        "reason": "API card is missing a usable name or number",
                    }
                )
                continue

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

        updates = list(updates_by_variant_id.values())
        updated_count = 0
        if not dry_run and updates:
            updated_count = update_card_variant_image_sync_fields_batch(updates)

        return {
            "set_name": set_name,
            "internal_set_id": internal_set_id,
            "api_set_id": api_set.get("id"),
            "api_set_name": api_set.get("name"),
            "dry_run": dry_run,
            "fetched_api_cards": len(api_cards),
            "exact_matches": exact_matches,
            "fallback_matches": fallback_matches,
            "prepared_variant_updates": len(updates),
            "updated_variant_rows": updated_count,
            "image_only_variant_matches": image_only_matches,
            "unmatched": unmatched,
            "skipped": skipped,
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
