from collections.abc import Mapping
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from backend.calculations.utils.special_type_normalization import derive_pattern_key, normalize_special_type_key


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

            variant_candidates = self._collect_priced_variant_candidates(card.get("variants") or [])
            if not variant_candidates:
                missing_price_rows += 1
                continue

            emitted_rows = self._build_card_rows_for_variants(
                card_id=card.get("card_id"),
                card_name=card_name,
                card_number=str(card.get("card_number") or "").strip(),
                normalized_rarity=normalized_rarity,
                variant_candidates=variant_candidates,
                pull_rate_mapping=pull_rate_mapping,
            )
            if not emitted_rows:
                missing_pull_rate_rows += 1
                continue

            card_rows.extend(emitted_rows)

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

    def _build_card_rows_for_variants(
        self,
        *,
        card_id: Any,
        card_name: str,
        card_number: str,
        normalized_rarity: str,
        variant_candidates: List[Dict[str, Any]],
        pull_rate_mapping: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        generic_rarity = normalized_rarity in self.GENERIC_RARITY_KEYS
        pattern_candidates = [candidate for candidate in variant_candidates if candidate["pattern_key"]]

        if generic_rarity and pattern_candidates:
            emitted_rows: List[Dict[str, Any]] = []
            base_candidates = [candidate for candidate in variant_candidates if not candidate["pattern_key"]]
            selected_base = self._select_base_candidate(base_candidates or pattern_candidates)
            reverse_price = self._select_reverse_price(base_candidates or [selected_base])

            base_row = self._build_card_row(
                card_id=card_id,
                card_name=card_name,
                card_number=card_number,
                rarity=normalized_rarity,
                candidate=selected_base,
                special_type_override="",
                reverse_price_override=reverse_price,
                pull_rate_mapping=pull_rate_mapping,
            )
            if base_row is not None:
                emitted_rows.append(base_row)

            seen_pattern_keys: set[str] = set()
            for pattern_candidate in pattern_candidates:
                pattern_key = str(pattern_candidate["pattern_key"])
                if not pattern_key or pattern_key in seen_pattern_keys:
                    continue
                selected_pattern = self._select_primary_candidate(
                    [candidate for candidate in pattern_candidates if candidate["pattern_key"] == pattern_key]
                )
                pattern_row = self._build_card_row(
                    card_id=card_id,
                    card_name=card_name,
                    card_number=card_number,
                    rarity=normalized_rarity,
                    candidate=selected_pattern,
                    special_type_override=str(selected_pattern["special_type"]),
                    reverse_price_override=float(selected_pattern["price"]),
                    pull_rate_mapping=pull_rate_mapping,
                )
                if pattern_row is not None:
                    emitted_rows.append(pattern_row)
                    seen_pattern_keys.add(pattern_key)

            return emitted_rows

        selected_candidate = self._select_primary_candidate(variant_candidates)
        selected_base = self._select_base_candidate(variant_candidates)
        reverse_price = self._select_reverse_price(variant_candidates)
        base_row = self._build_card_row(
            card_id=card_id,
            card_name=card_name,
            card_number=card_number,
            rarity=normalized_rarity,
            candidate=selected_base,
            special_type_override=str(selected_base["special_type"]),
            reverse_price_override=reverse_price,
            pull_rate_mapping=pull_rate_mapping,
        )
        return [base_row] if base_row is not None else []

    def _build_card_row(
        self,
        *,
        card_id: Any,
        card_name: str,
        card_number: str,
        rarity: str,
        candidate: Dict[str, Any],
        special_type_override: str,
        reverse_price_override: Optional[float],
        pull_rate_mapping: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        special_type = self._normalize_text(special_type_override)
        pull_rate = self._resolve_pull_rate(
            card_name=card_name,
            rarity_text=rarity,
            special_type=special_type,
            pull_rate_mapping=pull_rate_mapping,
        )
        if pull_rate is None:
            return None

        return {
            "card_id": card_id,
            "card_name": card_name,
            "card_number": card_number,
            "card_variant_id": candidate.get("variant_id"),
            "condition_id": candidate.get("condition_id"),
            "rarity": rarity,
            "special_type": special_type,
            "market_price": float(candidate["price"]),
            "price_source": candidate.get("price_source") or "unknown",
            "captured_at": candidate.get("captured_at"),
            "pull_rate_one_in_x": pull_rate,
            "reverse_market_price": float(reverse_price_override if reverse_price_override is not None else candidate["price"]),
        }

    def _collect_priced_variant_candidates(self, variants: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        for variant in variants:
            price = self._extract_market_price(variant)
            if price is None:
                continue

            special_type = self._normalize_text(variant.get("special_type"))
            special_type_key = normalize_special_type_key(special_type)
            pattern_key = derive_pattern_key(special_type_key)
            latest_price = variant.get("near_mint_latest") or {}
            condition_id = latest_price.get("condition_id") if isinstance(latest_price, Mapping) else None
            source = latest_price.get("source") if isinstance(latest_price, Mapping) else None
            captured_at = latest_price.get("captured_at") if isinstance(latest_price, Mapping) else None
            candidates.append(
                {
                    "price": float(price),
                    "reverse_price": float(price),
                    "variant_id": variant.get("variant_id"),
                    "special_type": special_type,
                    "special_type_key": special_type_key,
                    "pattern_key": pattern_key,
                    "is_reverse": self._is_reverse_variant(variant),
                    "condition_id": condition_id,
                    "price_source": self._normalize_text(source) or "unknown",
                    "captured_at": captured_at,
                }
            )

        return candidates

    def _select_primary_candidate(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        return sorted(
            candidates,
            key=lambda row: (
                -float(row["price"]),
                row.get("variant_id") if row.get("variant_id") is not None else float("inf"),
            ),
        )[0]

    def _select_base_candidate(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        non_reverse_candidates = [candidate for candidate in candidates if not candidate.get("is_reverse", False)]
        return self._select_primary_candidate(non_reverse_candidates or candidates)

    def _select_reverse_price(self, candidates: List[Dict[str, Any]]) -> Optional[float]:
        reverse_candidates = [candidate for candidate in candidates if candidate.get("is_reverse", False)]
        selected = self._select_primary_candidate(reverse_candidates or candidates)
        return float(selected["price"]) if selected else None

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

    def _resolve_pull_rate(
        self,
        card_name: str,
        rarity_text: str,
        special_type: str,
        pull_rate_mapping: Dict[str, Any],
    ) -> Optional[float]:
        card_name_normalized = self._normalize_text(card_name)
        special_type_key = normalize_special_type_key(special_type)
        pattern_key = derive_pattern_key(special_type_key)

        if pattern_key == "master_ball_pattern":
            return self._coerce_float(pull_rate_mapping.get("master ball pattern"))
        if pattern_key == "pokeball_pattern":
            return self._coerce_float(pull_rate_mapping.get("poke ball pattern"))

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
