from collections.abc import Mapping
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


class EVRInputTransformer:
    """Transform DB EVR payloads into internal contract and legacy calculator shape."""

    INTERNAL_CARD_FIELDS = [
        "card_name",
        "card_number",
        "rarity",
        "special_type",
        "market_price",
        "pull_rate_one_in_x",
        "reverse_market_price",
    ]

    REQUIRED_COLUMNS = [
        "Card Name",
        "Card Number",
        "Rarity",
        "Price ($)",
        "Pull Rate (1/X)",
        "Reverse Variant Price ($)",
        "Pack Price",
    ]

    OPTIONAL_COMPAT_COLUMNS = [
        "Special Type",
        "ETB Price",
        "ETB Promo Card Price",
    ]

    PERSISTENCE_COMPAT_COLUMNS = [
        "card_id",
        "card_variant_id",
        "condition_id",
        "price_source",
        "captured_at",
    ]

    GENERIC_RARITY_KEYS = {"common", "uncommon", "rare"}

    def transform(self, payload: Dict[str, Any], config: Any) -> Dict[str, Any]:
        cards = payload.get("cards") or []
        pull_rate_mapping = self._normalized_mapping(getattr(config, "PULL_RATE_MAPPING", {}))
        rarity_mapping = self._normalized_mapping(getattr(config, "RARITY_MAPPING", {}))

        sealed_payload = payload.get("sealed") or {}
        sealed_variants = payload.get("sealed_variants") or {}

        pack_price = self._extract_sealed_price(sealed_payload.get("pack"))
        etb_price = self._extract_sealed_price(sealed_payload.get("etb"))
        etb_promo_card_price = self._extract_sealed_price(sealed_payload.get("promo"))
        booster_box_price = self._extract_sealed_price(sealed_payload.get("booster_box"))

        etb_variants = self._extract_etb_variants(sealed_variants)
        booster_box_variants = self._extract_booster_box_variants(sealed_variants)

        if "standard" in etb_variants:
            etb_price = self._coerce_float(etb_variants["standard"].get("etb_price"))
            etb_promo_card_price = self._coerce_float(etb_variants["standard"].get("etb_promo_card_price"))

        if "standard" in booster_box_variants:
            booster_box_price = self._coerce_float(booster_box_variants["standard"].get("booster_box_price"))

        card_rows: List[Dict[str, Any]] = []
        missing_pull_rate_rows = 0
        missing_price_rows = 0

        for card in cards:
            card_name = str(card.get("name") or "").strip()
            rarity_raw = self._normalize_text(card.get("rarity"))
            normalized_rarity = self._normalize_rarity(rarity_raw, rarity_mapping)

            (
                selected_price,
                selected_reverse_price,
                selected_special_type,
                selected_variant_id,
                selected_condition_id,
                selected_price_source,
                selected_captured_at,
            ) = self._select_card_prices(card.get("variants") or [])
            pull_rate = self._resolve_pull_rate(
                card_name=card_name,
                rarity_text=normalized_rarity,
                pull_rate_mapping=pull_rate_mapping,
            )

            if selected_price is None:
                missing_price_rows += 1
                continue

            if pull_rate is None:
                missing_pull_rate_rows += 1
                continue

            card_rows.append(
                {
                    "card_id": card.get("card_id"),
                    "card_name": card_name,
                    "card_number": str(card.get("card_number") or "").strip(),
                    "card_variant_id": selected_variant_id,
                    "condition_id": selected_condition_id,
                    "rarity": normalized_rarity,
                    "special_type": self._normalize_text(selected_special_type),
                    "market_price": selected_price,
                    "price_source": selected_price_source,
                    "captured_at": selected_captured_at,
                    "pull_rate_one_in_x": pull_rate,
                    "reverse_market_price": (
                        selected_reverse_price if selected_reverse_price is not None else selected_price
                    ),
                }
            )

        rows_dropped = len(cards) - len(card_rows)
        diagnostics = {
            "source_card_rows": len(cards),
            "rows_emitted": len(card_rows),
            "rows_dropped": rows_dropped,
            "missing_pull_rates": missing_pull_rate_rows,
            "missing_price_rows": missing_price_rows,
            "pack_price_missing": pack_price is None,
            "etb_price_missing": etb_price is None,
            "etb_promo_card_price_missing": etb_promo_card_price is None,
            "price_selection_rule": (
                "base_price=max(non-reverse near-mint); fallback=max(any near-mint); "
                "reverse_price=max(reverse-tagged near-mint) fallback=base_price"
            ),
        }

        return {
            "card_rows": card_rows,
            "sealed_prices": {
                "pack_price": pack_price,
                "etb_price": etb_price,
                "etb_promo_card_price": etb_promo_card_price,
                "booster_box_price": booster_box_price,
                "etb_variants": etb_variants,
                "booster_box_variants": booster_box_variants,
            },
            "diagnostics": diagnostics,
        }

    def to_legacy_calculator_payload(self, internal_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Map internal DB-native contract to legacy dataframe/column calculator input."""
        rows = (internal_payload or {}).get("card_rows") or []
        sealed_prices = (internal_payload or {}).get("sealed_prices") or {}

        pack_price = self._coerce_float(sealed_prices.get("pack_price"))
        etb_price = self._coerce_float(sealed_prices.get("etb_price"))
        etb_promo_card_price = self._coerce_float(sealed_prices.get("etb_promo_card_price"))
        booster_box_price = self._coerce_float(sealed_prices.get("booster_box_price"))
        etb_variants = self._sanitize_etb_variants(sealed_prices.get("etb_variants"))
        booster_box_variants = self._sanitize_booster_box_variants(sealed_prices.get("booster_box_variants"))

        legacy_rows: List[Dict[str, Any]] = []
        for row in rows:
            legacy_rows.append(
                {
                    "card_id": row.get("card_id"),
                    "Card Name": row.get("card_name"),
                    "Card Number": row.get("card_number", ""),
                    "Rarity": row.get("rarity"),
                    "Special Type": row.get("special_type") or "",
                    "Price ($)": row.get("market_price"),
                    "Pull Rate (1/X)": row.get("pull_rate_one_in_x"),
                    "Reverse Variant Price ($)": row.get("reverse_market_price"),
                    "Pack Price": pack_price,
                    "ETB Price": etb_price,
                    "ETB Promo Card Price": etb_promo_card_price,
                    "card_variant_id": row.get("card_variant_id"),
                    "condition_id": row.get("condition_id"),
                    "price_source": row.get("price_source"),
                    "captured_at": row.get("captured_at"),
                }
            )

        dataframe = pd.DataFrame(legacy_rows)
        for col in [*self.REQUIRED_COLUMNS, *self.OPTIONAL_COMPAT_COLUMNS, *self.PERSISTENCE_COMPAT_COLUMNS]:
            if col not in dataframe.columns:
                dataframe[col] = pd.Series(dtype="float64" if "Price" in col or "Rate" in col else "object")

        dataframe = dataframe[[*self.REQUIRED_COLUMNS, *self.OPTIONAL_COMPAT_COLUMNS, *self.PERSISTENCE_COMPAT_COLUMNS]]

        return {
            "dataframe": dataframe,
            "pack_price": pack_price,
            "etb_price": etb_price,
            "etb_promo_card_price": etb_promo_card_price,
            "booster_box_price": booster_box_price,
            "etb_variants": etb_variants,
            "booster_box_variants": booster_box_variants,
            "diagnostics": (internal_payload or {}).get("diagnostics") or {},
        }

    def _extract_etb_variants(self, sealed_variants_payload: Dict[str, Any]) -> Dict[str, Dict[str, Optional[float]]]:
        etb_variants_payload = sealed_variants_payload.get("etb") or {}
        promo_variants_payload = sealed_variants_payload.get("promo") or {}
        variants: Dict[str, Dict[str, Optional[float]]] = {}

        variant_keys = set(etb_variants_payload.keys()) | set(promo_variants_payload.keys())
        for variant_key in variant_keys:
            etb_price = self._extract_sealed_price(etb_variants_payload.get(variant_key))
            promo_price = self._extract_sealed_price(promo_variants_payload.get(variant_key))
            if etb_price is None and promo_price is None:
                continue
            variants[str(variant_key)] = {
                "etb_price": etb_price,
                "etb_promo_card_price": promo_price,
            }

        return variants

    def _extract_booster_box_variants(
        self,
        sealed_variants_payload: Dict[str, Any],
    ) -> Dict[str, Dict[str, Optional[float]]]:
        booster_variants_payload = sealed_variants_payload.get("booster_box") or {}
        variants: Dict[str, Dict[str, Optional[float]]] = {}

        for variant_key, variant_payload in booster_variants_payload.items():
            booster_box_price = self._extract_sealed_price(variant_payload)
            if booster_box_price is None:
                continue
            variants[str(variant_key)] = {
                "booster_box_price": booster_box_price,
                "booster_box_promo_card_price": None,
            }

        return variants

    def _sanitize_etb_variants(self, raw_variants: Any) -> Dict[str, Dict[str, Optional[float]]]:
        if not isinstance(raw_variants, Mapping):
            return {}

        sanitized: Dict[str, Dict[str, Optional[float]]] = {}
        for variant_key, variant_payload in raw_variants.items():
            if not isinstance(variant_payload, Mapping):
                continue
            etb_price = self._coerce_float(variant_payload.get("etb_price"))
            promo_price = self._coerce_float(variant_payload.get("etb_promo_card_price"))
            if etb_price is None and promo_price is None:
                continue
            sanitized[str(variant_key)] = {
                "etb_price": etb_price,
                "etb_promo_card_price": promo_price,
            }

        return sanitized

    def _sanitize_booster_box_variants(self, raw_variants: Any) -> Dict[str, Dict[str, Optional[float]]]:
        if not isinstance(raw_variants, Mapping):
            return {}

        sanitized: Dict[str, Dict[str, Optional[float]]] = {}
        for variant_key, variant_payload in raw_variants.items():
            if not isinstance(variant_payload, Mapping):
                continue
            booster_box_price = self._coerce_float(variant_payload.get("booster_box_price"))
            booster_box_promo = self._coerce_float(variant_payload.get("booster_box_promo_card_price"))
            if booster_box_price is None and booster_box_promo is None:
                continue
            sanitized[str(variant_key)] = {
                "booster_box_price": booster_box_price,
                "booster_box_promo_card_price": booster_box_promo,
            }

        return sanitized

    def _select_card_prices(
        self,
        variants: Iterable[Dict[str, Any]],
    ) -> Tuple[Optional[float], Optional[float], str, Optional[int], Optional[int], str, Optional[str]]:
        all_priced: List[Tuple[float, bool, int, str, Optional[int], str, Optional[str]]] = []

        for variant in variants:
            price = self._extract_market_price(variant)
            if price is None:
                continue

            is_reverse = self._is_reverse_variant(variant)
            variant_id = variant.get("variant_id")
            special_type = self._normalize_text(variant.get("special_type"))
            latest_price = variant.get("near_mint_latest") or {}
            condition_id = latest_price.get("condition_id") if isinstance(latest_price, Mapping) else None
            source = latest_price.get("source") if isinstance(latest_price, Mapping) else None
            captured_at = latest_price.get("captured_at") if isinstance(latest_price, Mapping) else None
            all_priced.append(
                (
                    price,
                    is_reverse,
                    variant_id,
                    special_type,
                    condition_id,
                    self._normalize_text(source) or "unknown",
                    captured_at,
                )
            )

        if not all_priced:
            return None, None, "", None, None, "unknown", None

        non_reverse = [row for row in all_priced if not row[1]]
        reverse = [row for row in all_priced if row[1]]

        # Deterministic selection: choose highest price, then lowest variant id tie-break.
        base_pool = non_reverse or all_priced
        selected_base = sorted(base_pool, key=lambda row: (-row[0], row[2]))[0]
        base_price = selected_base[0]
        base_special_type = selected_base[3]

        reverse_pool = reverse or [selected_base]
        reverse_price = sorted(reverse_pool, key=lambda row: (-row[0], row[2]))[0][0]

        return (
            float(base_price),
            float(reverse_price),
            base_special_type,
            selected_base[2],
            selected_base[4],
            selected_base[5],
            selected_base[6],
        )

    def _resolve_pull_rate(
        self,
        card_name: str,
        rarity_text: str,
        pull_rate_mapping: Dict[str, Any],
    ) -> Optional[float]:
        card_name_normalized = self._normalize_text(card_name)

        if "master ball pattern" in card_name_normalized:
            return self._coerce_float(pull_rate_mapping.get("master ball pattern"))
        if "poke ball pattern" in card_name_normalized:
            return self._coerce_float(pull_rate_mapping.get("poke ball pattern"))

        exact = self._coerce_float(pull_rate_mapping.get(rarity_text))
        if exact is not None:
            return exact

        for rarity_key, pull_rate in pull_rate_mapping.items():
            if rarity_key in self.GENERIC_RARITY_KEYS:
                continue
            if rarity_key and rarity_key in rarity_text:
                parsed = self._coerce_float(pull_rate)
                if parsed is not None:
                    return parsed

        return None

    def _normalize_rarity(self, rarity_text: str, rarity_mapping: Dict[str, Any]) -> str:
        if rarity_text in rarity_mapping:
            return rarity_text

        for mapping_key in rarity_mapping:
            if mapping_key in self.GENERIC_RARITY_KEYS:
                continue
            if mapping_key and mapping_key in rarity_text:
                return mapping_key

        return rarity_text

    def _extract_market_price(self, variant: Dict[str, Any]) -> Optional[float]:
        near_mint_latest = variant.get("near_mint_latest")

        if isinstance(near_mint_latest, dict):
            return self._coerce_float(near_mint_latest.get("market_price"))

        if isinstance(near_mint_latest, (float, int, str)):
            return self._coerce_float(near_mint_latest)

        return self._coerce_float(variant.get("market_price"))

    def _extract_sealed_price(self, sealed_payload: Optional[Dict[str, Any]]) -> Optional[float]:
        if not sealed_payload:
            return None

        latest_price = sealed_payload.get("latest_price")
        if isinstance(latest_price, dict):
            return self._coerce_float(latest_price.get("market_price"))

        if isinstance(latest_price, (int, float, str)):
            return self._coerce_float(latest_price)

        return self._coerce_float(sealed_payload.get("market_price"))

    def _is_reverse_variant(self, variant: Dict[str, Any]) -> bool:
        candidate_fields = [
            variant.get("printing"),
            variant.get("printing_type"),
            variant.get("variant"),
            variant.get("name"),
            variant.get("pokemon_tcg_api_id"),
        ]
        text_blob = " ".join(self._normalize_text(value) for value in candidate_fields if value)
        return "reverse" in text_blob

    def _normalized_mapping(self, value: Any) -> Dict[str, Any]:
        if not isinstance(value, Mapping):
            return {}
        return {self._normalize_text(key): mapped for key, mapped in value.items()}

    def _coerce_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _normalize_text(self, value: Any) -> str:
        return str(value or "").strip().lower()
