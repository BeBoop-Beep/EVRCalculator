from typing import Any, Dict, List, Optional, Tuple

from backend.db.repositories.cards_repository import get_all_cards_for_set
from backend.db.repositories.card_variant_repository import get_card_variants_by_card_ids
from backend.db.repositories.card_variant_prices_repository import get_latest_prices_for_variants
from backend.db.repositories.conditions_repository import get_condition_by_name
from backend.db.repositories.sealed_product_prices_repository import (
    get_latest_prices_for_sealed_product_ids,
)
from backend.db.repositories.sealed_repository import get_sealed_products_for_set
from backend.db.repositories.sets_repository import (
    get_set_by_canonical_key,
    get_set_by_name,
    get_set_by_pokemon_api_set_id,
)


class EVRInputRepository:
    """Load EVR inputs from DB without calculation-layer coupling."""

    PRODUCT_TARGETS = {
        "pack": ("pack", "booster pack", "sleeved booster"),
        "etb": ("etb", "elite trainer box"),
        "promo": ("promo", "etb promo"),
    }

    def load_inputs(self, set_identity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve set, cards, latest Near Mint prices, and key sealed prices.

        Expected identity keys:
        - canonical_key
        - set_id (pokemon api set id from config)
        - set_name
        """
        set_row, set_resolution_path = self._resolve_set_row(set_identity)
        if not set_row:
            return {
                "set": None,
                "cards": [],
                "sealed": {
                    "pack": None,
                    "etb": None,
                    "promo": None,
                },
                "diagnostics": {
                    "set_resolution": "not_found",
                    "total_cards_loaded": 0,
                    "cards_missing_prices": 0,
                    "duplicate_card_mappings": 0,
                    "pack_price_resolution_status": "not_found",
                    "etb_price_resolution_status": "not_found",
                    "promo_price_resolution_status": "not_found",
                },
            }

        near_mint = get_condition_by_name("Near Mint")
        near_mint_condition_id = near_mint["id"] if near_mint else None

        cards = get_all_cards_for_set(set_row["id"])
        card_payload, cards_missing_prices = self._load_card_payload(cards, near_mint_condition_id)
        duplicate_card_mappings = self._count_duplicate_card_keys(cards)

        sealed_resolution = self._resolve_sealed_prices(set_row["id"])

        return {
            "set": {
                "id": set_row.get("id"),
                "name": set_row.get("name"),
                "canonical_key": set_row.get("canonical_key"),
                "pokemon_api_set_id": set_row.get("pokemon_api_set_id"),
                "resolution_path": set_resolution_path,
            },
            "cards": card_payload,
            "sealed": {
                "pack": sealed_resolution["pack"]["resolved"],
                "etb": sealed_resolution["etb"]["resolved"],
                "promo": sealed_resolution["promo"]["resolved"],
            },
            "diagnostics": {
                "set_resolution": set_resolution_path,
                "total_cards_loaded": len(card_payload),
                "cards_missing_prices": cards_missing_prices,
                "duplicate_card_mappings": duplicate_card_mappings,
                "pack_price_resolution_status": sealed_resolution["pack"]["status"],
                "etb_price_resolution_status": sealed_resolution["etb"]["status"],
                "promo_price_resolution_status": sealed_resolution["promo"]["status"],
            },
        }

    def _resolve_set_row(self, set_identity: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        canonical_key = (set_identity.get("canonical_key") or "").strip()
        api_set_id = (set_identity.get("set_id") or "").strip()
        set_name = (set_identity.get("set_name") or "").strip()

        if canonical_key:
            by_canonical = get_set_by_canonical_key(canonical_key)
            if by_canonical:
                return by_canonical, "canonical_key"

        if api_set_id:
            by_api_id = get_set_by_pokemon_api_set_id(api_set_id)
            if by_api_id:
                return by_api_id, "pokemon_api_set_id"

        if set_name:
            try:
                by_name = get_set_by_name(set_name)
                if by_name and by_name.data:
                    return by_name.data, "set_name"
            except Exception:
                return None, "not_found"

        return None, "not_found"

    def _load_card_payload(
        self,
        cards: List[Dict[str, Any]],
        near_mint_condition_id: Optional[int],
    ) -> Tuple[List[Dict[str, Any]], int]:
        if not cards:
            return [], 0

        card_ids = [card["id"] for card in cards if card.get("id") is not None]
        variants = get_card_variants_by_card_ids(card_ids)

        variants_by_card: Dict[int, List[Dict[str, Any]]] = {}
        for variant in variants:
            variants_by_card.setdefault(variant["card_id"], []).append(variant)

        price_by_variant: Dict[int, Dict[str, Any]] = {}
        if near_mint_condition_id is not None:
            variant_ids = [variant["id"] for variant in variants if variant.get("id") is not None]
            latest_prices = get_latest_prices_for_variants(variant_ids, near_mint_condition_id)
            price_by_variant = {
                row["variant_id"]: row
                for row in latest_prices
                if row.get("variant_id") is not None
            }

        payload: List[Dict[str, Any]] = []
        cards_missing_prices = 0

        for card in cards:
            card_variants = variants_by_card.get(card["id"], [])
            variant_rows: List[Dict[str, Any]] = []

            for variant in card_variants:
                variant_rows.append(
                    {
                        "variant_id": variant.get("id"),
                        "pokemon_tcg_api_id": variant.get("pokemon_tcg_api_id"),
                        "special_type": variant.get("special_type"),
                        "near_mint_latest": price_by_variant.get(variant.get("id")),
                    }
                )

            has_price = any(row.get("near_mint_latest") for row in variant_rows)
            if not has_price:
                cards_missing_prices += 1

            payload.append(
                {
                    "card_id": card.get("id"),
                    "name": card.get("name"),
                    "card_number": card.get("card_number"),
                    "rarity": card.get("rarity"),
                    "variants": variant_rows,
                }
            )

        return payload, cards_missing_prices

    def _resolve_sealed_prices(self, set_id: str) -> Dict[str, Dict[str, Any]]:
        sealed_rows = get_sealed_products_for_set(set_id)
        sealed_ids = [row["id"] for row in sealed_rows if row.get("id") is not None]

        latest_prices = get_latest_prices_for_sealed_product_ids(sealed_ids)
        latest_by_sealed_id = {
            row["sealed_product_id"]: row
            for row in latest_prices
            if row.get("sealed_product_id") is not None
        }

        return {
            "pack": self._resolve_single_sealed_target(sealed_rows, latest_by_sealed_id, "pack"),
            "etb": self._resolve_single_sealed_target(sealed_rows, latest_by_sealed_id, "etb"),
            "promo": self._resolve_single_sealed_target(sealed_rows, latest_by_sealed_id, "promo"),
        }

    def _resolve_single_sealed_target(
        self,
        sealed_rows: List[Dict[str, Any]],
        latest_by_sealed_id: Dict[int, Dict[str, Any]],
        target_key: str,
    ) -> Dict[str, Any]:
        tokens = self.PRODUCT_TARGETS[target_key]
        candidates: List[Dict[str, Any]] = []

        for row in sealed_rows:
            product_text = f"{row.get('product_type', '')} {row.get('name', '')}"
            normalized_text = self._normalize_text(product_text)
            if any(token in normalized_text for token in tokens):
                candidates.append(row)

        if not candidates:
            return {"resolved": None, "status": "not_found"}

        chosen = self._choose_candidate(candidates)
        chosen_price = latest_by_sealed_id.get(chosen["id"])

        resolved = {
            "sealed_product": {
                "id": chosen.get("id"),
                "name": chosen.get("name"),
                "product_type": chosen.get("product_type"),
            },
            "latest_price": chosen_price,
        }

        status = "priced" if chosen_price else "missing_price"
        return {"resolved": resolved, "status": status}

    def _choose_candidate(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Deterministic tie-break for stable orchestration behavior.
        sorted_candidates = sorted(
            candidates,
            key=lambda row: (
                0 if row.get("name") else 1,
                self._normalize_text(row.get("product_type", "")),
                self._normalize_text(row.get("name", "")),
            ),
        )
        return sorted_candidates[0]

    def _count_duplicate_card_keys(self, cards: List[Dict[str, Any]]) -> int:
        seen: Dict[Tuple[str, str, str], int] = {}
        duplicates = 0
        for row in cards:
            key = (
                self._normalize_text(row.get("name", "")),
                self._normalize_text(row.get("card_number", "")),
                self._normalize_text(row.get("rarity", "")),
            )
            seen[key] = seen.get(key, 0) + 1

        for count in seen.values():
            if count > 1:
                duplicates += count - 1

        return duplicates

    def _normalize_text(self, value: Any) -> str:
        return str(value or "").strip().lower()
