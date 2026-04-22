import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from backend.calculations.utils.rarity_classification import normalize_rarity_key
from backend.calculations.utils.special_type_normalization import derive_pattern_key, normalize_special_type_key
from backend.db.services.evr_input_repository import EVRInputRepository
from backend.db.services.evr_input_transformer import EVRInputTransformer


class EVRInputPreparationService:
    """Service boundary for DB-backed EVR input preparation and diagnostics."""

    REQUIRED_REVERSE_PRICE_COLUMN = "Reverse Variant Price ($)"

    def __init__(self, repository: EVRInputRepository | None = None, transformer: EVRInputTransformer | None = None):
        self.repository = repository or EVRInputRepository()
        self.transformer = transformer or EVRInputTransformer()

    def prepare_for_set(self, config: Any, canonical_key: str, set_name: str) -> Dict[str, Any]:
        set_identity = {
            "canonical_key": canonical_key,
            "set_id": getattr(config, "SET_ID", None),
            "set_name": getattr(config, "SET_NAME", None) or set_name,
        }

        repository_payload = self.repository.load_inputs(set_identity)
        internal_payload = self.transformer.transform(repository_payload, config)
        compatibility_payload = self.transformer.to_legacy_calculator_payload(internal_payload)
        diagnostics_summary = self._emit_diagnostics(repository_payload, compatibility_payload)
        row_audit_summary = self._emit_row_population_audit(compatibility_payload, config, set_name)
        self._maybe_write_debug_json_dump(
            config=config,
            set_name=set_name,
            diagnostics_summary=diagnostics_summary,
            row_audit_summary=row_audit_summary,
            internal_payload=internal_payload,
        )
        self._validate_required_inputs(compatibility_payload, set_name)
        return compatibility_payload

    def _emit_diagnostics(self, repository_payload: Dict[str, Any], transformed_payload: Dict[str, Any]) -> Dict[str, Any]:
        repo_diag = (repository_payload or {}).get("diagnostics") or {}
        transform_diag = (transformed_payload or {}).get("diagnostics") or {}

        diagnostics = {
            "total_cards_loaded": repo_diag.get("total_cards_loaded", 0),
            "cards_missing_prices": repo_diag.get("cards_missing_prices", 0),
            "duplicate_card_mappings": repo_diag.get("duplicate_card_mappings", 0),
            "pack_price_resolution": {
                "status": repo_diag.get("pack_price_resolution_status", "unknown"),
                "missing": bool(transform_diag.get("pack_price_missing", False)),
            },
            "etb_price_resolution": {
                "status": repo_diag.get("etb_price_resolution_status", "unknown"),
                "missing": bool(transform_diag.get("etb_price_missing", False)),
            },
            "promo_price_resolution": {
                "status": repo_diag.get("promo_price_resolution_status", "unknown"),
                "missing": bool(transform_diag.get("etb_promo_card_price_missing", False)),
            },
            "rows_emitted": transform_diag.get("rows_emitted"),
            "rows_dropped": transform_diag.get("rows_dropped"),
        }

        print(f"[DB_INPUT_DIAGNOSTICS] {json.dumps(diagnostics, sort_keys=True)}")
        return diagnostics

    def _emit_row_population_audit(self, transformed_payload: Dict[str, Any], config: Any, set_name: str) -> Dict[str, Any]:
        dataframe = transformed_payload.get("dataframe")
        if not isinstance(dataframe, pd.DataFrame):
            return {}

        rarity_keys = (
            dataframe.get("Rarity", pd.Series("", index=dataframe.index, dtype="object"))
            .fillna("")
            .astype(str)
            .map(normalize_rarity_key)
        )
        pattern_keys = (
            dataframe.get("Special Type", pd.Series("", index=dataframe.index, dtype="object"))
            .fillna("")
            .astype(str)
            .map(normalize_special_type_key)
            .map(derive_pattern_key)
        )

        identity_series = self._build_identity_series(dataframe)
        non_pattern_counts = {
            rarity: int((rarity_keys.eq(rarity) & pattern_keys.eq("")).sum())
            for rarity in ("common", "uncommon", "rare")
        }

        diagnostics = {
            "set_name": getattr(config, "SET_NAME", None) or set_name,
            "total_rows": int(len(dataframe)),
            "counts_by_rarity_key": {str(key or "<blank>"): int(value) for key, value in rarity_keys.value_counts(dropna=False).items()},
            "counts_by_pattern_key": {str(key or "<blank>"): int(value) for key, value in pattern_keys.value_counts(dropna=False).items()},
            "non_pattern_common": non_pattern_counts["common"],
            "non_pattern_uncommon": non_pattern_counts["uncommon"],
            "non_pattern_rare": non_pattern_counts["rare"],
            "duplicate_identity_only_rows": int(identity_series.duplicated(keep=False).sum()),
            "duplicate_identity_plus_pattern_rows": int(
                pd.DataFrame({"identity": identity_series, "pattern_key": pattern_keys})
                .duplicated(subset=["identity", "pattern_key"], keep=False)
                .sum()
            ),
        }
        print(f"[DB_INPUT_ROW_AUDIT] {json.dumps(diagnostics, sort_keys=True)}")

        if self._is_prismatic_set(config, set_name) and any(count <= 0 for count in non_pattern_counts.values()):
            raise ValueError(
                "Prismatic Evolutions input contract violated: expected non-empty non-pattern base pools for "
                f"common/uncommon/rare, got {non_pattern_counts}."
            )

        return diagnostics

    def _maybe_write_debug_json_dump(
        self,
        *,
        config: Any,
        set_name: str,
        diagnostics_summary: Dict[str, Any],
        row_audit_summary: Dict[str, Any],
        internal_payload: Dict[str, Any],
    ) -> None:
        if not self._is_debug_json_dump_enabled():
            return

        try:
            generated_at = datetime.now(timezone.utc).isoformat()
            resolved_set_name = getattr(config, "SET_NAME", None) or set_name
            resolved_set_id = getattr(config, "SET_ID", None)

            final_rows = [
                self._to_debug_row(row)
                for row in (internal_payload or {}).get("card_rows") or []
            ]
            pricing_summary = self._build_pricing_summary(final_rows)
            suspicious_rows = self._build_suspicious_rows(final_rows)
            suspicious_counts = self._build_suspicious_counts(suspicious_rows)

            payload = {
                "set_name": resolved_set_name,
                "set_id": resolved_set_id,
                "generated_at": generated_at,
                "diagnostics_summary": diagnostics_summary,
                "row_audit_summary": row_audit_summary,
                "pricing_summary": pricing_summary,
                "suspicious_rows": suspicious_rows,
                "final_shaped_card_rows": final_rows,
            }

            output_dir = Path(__file__).resolve().parents[2] / "logs" / "debug_json"
            output_dir.mkdir(parents=True, exist_ok=True)

            safe_set_id = str(resolved_set_id or "unknown_set").strip() or "unknown_set"
            run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            output_path = output_dir / f"{safe_set_id}_{run_stamp}.json"
            output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

            print(f"[DEBUG_JSON_DUMP] wrote={output_path.as_posix()}")
            print(
                "[DEBUG_SUSPICIOUS_ROWS] "
                f"total={len(suspicious_rows)} "
                f"common={suspicious_counts['common']} "
                f"uncommon={suspicious_counts['uncommon']} "
                f"rare={suspicious_counts['rare']}"
            )
        except Exception as exc:
            print(f"[DEBUG_JSON_DUMP] skipped=write_error:{type(exc).__name__}:{str(exc)}")

    def _is_debug_json_dump_enabled(self) -> bool:
        return str(os.getenv("DEBUG_JSON_DUMP_ENABLED", "")).strip().lower() == "true"

    def _to_debug_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "card_id": row.get("card_id"),
            "card_name": row.get("card_name"),
            "card_number": row.get("card_number"),
            "card_variant_id": row.get("card_variant_id"),
            "condition_id": row.get("condition_id"),
            "price_source": row.get("price_source"),
            "captured_at": row.get("captured_at"),
            "rarity": row.get("rarity"),
            "rarity_key": row.get("rarity_key"),
            "aggregation_key": row.get("aggregation_key"),
            "classification_key": row.get("classification_key"),
            "base_rarity_key": row.get("base_rarity_key"),
            "pattern_key": row.get("pattern_key"),
            "printing_type": row.get("printing_type"),
            "special_type": row.get("special_type"),
            "edition": row.get("edition"),
            "base_variant_id": row.get("base_variant_id"),
            "reverse_variant_id": row.get("reverse_variant_id"),
            "base_price": row.get("base_price"),
            "reverse_price": row.get("reverse_price"),
            "candidate_count": row.get("candidate_count"),
            "selected_base_candidate_rank": row.get("selected_base_candidate_rank"),
            "selected_reverse_candidate_rank": row.get("selected_reverse_candidate_rank"),
            "selected_base_reason": row.get("selected_base_reason"),
            "selected_reverse_reason": row.get("selected_reverse_reason"),
            "cheapest_non_reverse_variant_id": row.get("cheapest_non_reverse_variant_id"),
            "cheapest_non_reverse_price": row.get("cheapest_non_reverse_price"),
            "cheapest_non_reverse_candidate_rank": row.get("cheapest_non_reverse_candidate_rank"),
            "highest_non_reverse_variant_id": row.get("highest_non_reverse_variant_id"),
            "highest_non_reverse_price": row.get("highest_non_reverse_price"),
            "highest_non_reverse_candidate_rank": row.get("highest_non_reverse_candidate_rank"),
            "selected_base_matches_cheapest_non_reverse": row.get("selected_base_matches_cheapest_non_reverse"),
            "selected_base_matches_highest_non_reverse": row.get("selected_base_matches_highest_non_reverse"),
            "selected_base_price_delta_vs_cheapest_non_reverse": row.get("selected_base_price_delta_vs_cheapest_non_reverse"),
            "selected_base_price_delta_vs_highest_non_reverse": row.get("selected_base_price_delta_vs_highest_non_reverse"),
            "suspicious_flags": row.get("suspicious_flags") or [],
            "candidate_variants": row.get("candidate_variants") or [],
        }

    def _build_pricing_summary(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        rarity_values = [str((row.get("rarity_key") or "")).strip() for row in rows]
        aggregation_values = [str((row.get("aggregation_key") or "")).strip() for row in rows]
        pattern_values = [str((row.get("pattern_key") or "")).strip() for row in rows]

        return {
            "counts_by_rarity_key": self._count_values(rarity_values),
            "counts_by_aggregation_key": self._count_values(aggregation_values),
            "counts_by_pattern_key": self._count_values(pattern_values),
            "base_price_stats_by_bucket": {
                "common": self._price_stats([row.get("base_price") for row in rows if str(row.get("rarity_key") or "") == "common"]),
                "uncommon": self._price_stats([row.get("base_price") for row in rows if str(row.get("rarity_key") or "") == "uncommon"]),
                "rare": self._price_stats([row.get("base_price") for row in rows if str(row.get("rarity_key") or "") == "rare"]),
            },
            "reverse_price_stats": self._price_stats([row.get("reverse_price") for row in rows]),
        }

    def _build_suspicious_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        suspicious: List[Dict[str, Any]] = []

        for row in rows:
            rarity_key = str(row.get("rarity_key") or "").strip()
            base_price = self._coerce_float(row.get("base_price"))
            reverse_price = self._coerce_float(row.get("reverse_price"))
            candidate_count = int(row.get("candidate_count") or 0)
            pattern_key = str(row.get("pattern_key") or "").strip()
            suspicious_flags = list(row.get("suspicious_flags") or [])

            threshold_hit = (
                (rarity_key == "common" and (base_price or 0.0) >= 0.75)
                or (rarity_key == "uncommon" and (base_price or 0.0) >= 1.25)
                or (rarity_key == "rare" and (base_price or 0.0) >= 3.0)
            )
            multi_candidate = candidate_count > 1
            equal_base_reverse = (base_price is not None and reverse_price is not None and abs(base_price - reverse_price) < 1e-9)
            maybe_non_plain = pattern_key == "" and self._suggests_non_plain_base(row)
            selected_base_not_cheapest = row.get("selected_base_matches_cheapest_non_reverse") is False

            if not (selected_base_not_cheapest or threshold_hit or multi_candidate or equal_base_reverse or maybe_non_plain):
                continue

            candidates = list(row.get("candidate_variants") or [])
            top_by_price = sorted(
                candidates,
                key=lambda candidate: (
                    -(self._coerce_float(candidate.get("price")) or 0.0),
                    str(candidate.get("variant_id") or ""),
                ),
            )[:3]
            top_by_rank = sorted(
                candidates,
                key=lambda candidate: int(candidate.get("candidate_rank") or 10**9),
            )[:3]

            suspicious.append(
                {
                    "card_name": row.get("card_name"),
                    "card_number": row.get("card_number"),
                    "rarity_key": rarity_key,
                    "base_price": base_price,
                    "reverse_price": reverse_price,
                    "candidate_count": candidate_count,
                    "base_variant_id": row.get("base_variant_id"),
                    "reverse_variant_id": row.get("reverse_variant_id"),
                    "printing_type": row.get("printing_type"),
                    "special_type": row.get("special_type"),
                    "edition": row.get("edition"),
                    "pattern_key": pattern_key,
                    "selected_base_reason": row.get("selected_base_reason"),
                    "suspicious_flags": suspicious_flags,
                    "cheapest_non_reverse_price": row.get("cheapest_non_reverse_price"),
                    "highest_non_reverse_price": row.get("highest_non_reverse_price"),
                    "selected_base_price_delta_vs_cheapest_non_reverse": row.get("selected_base_price_delta_vs_cheapest_non_reverse"),
                    "selected_base_matches_cheapest_non_reverse": row.get("selected_base_matches_cheapest_non_reverse"),
                    "selected_base_matches_highest_non_reverse": row.get("selected_base_matches_highest_non_reverse"),
                    "top_3_candidates_by_price": top_by_price,
                    "top_3_candidates_by_rank": top_by_rank,
                }
            )

        return suspicious

    def _build_suspicious_counts(self, suspicious_rows: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {"common": 0, "uncommon": 0, "rare": 0}
        for row in suspicious_rows:
            rarity_key = str(row.get("rarity_key") or "").strip()
            if rarity_key in counts:
                counts[rarity_key] += 1
        return counts

    def _count_values(self, values: List[str]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for value in values:
            key = value or "<blank>"
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _price_stats(self, values: List[Any]) -> Dict[str, float | int | None]:
        numeric_values = [float(v) for v in [self._coerce_float(value) for value in values] if v is not None]
        if not numeric_values:
            return {"count": 0, "min": None, "max": None, "mean": None}

        return {
            "count": len(numeric_values),
            "min": float(min(numeric_values)),
            "max": float(max(numeric_values)),
            "mean": float(sum(numeric_values) / len(numeric_values)),
        }

    def _suggests_non_plain_base(self, row: Dict[str, Any]) -> bool:
        special_type = str(row.get("special_type") or "").strip().lower()
        edition = str(row.get("edition") or "").strip().lower()
        printing_type = str(row.get("printing_type") or "").strip().lower()

        if special_type != "":
            return True
        if edition != "":
            return True

        suspicious_tokens = ("reverse", "holo", "foil", "stamped", "parallel", "promo")
        return any(token in printing_type for token in suspicious_tokens)

    def _coerce_float(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_identity_series(self, dataframe: pd.DataFrame) -> pd.Series:
        if "card_id" in dataframe.columns:
            identity = dataframe["card_id"].fillna("").astype(str).str.strip()
            if identity.ne("").any():
                return identity

        if "Card Number" in dataframe.columns:
            identity = dataframe["Card Number"].fillna("").astype(str).str.strip()
            if identity.ne("").any():
                return identity

        return dataframe.get("Card Name", pd.Series("", index=dataframe.index, dtype="object")).fillna("").astype(str).str.strip()

    def _is_prismatic_set(self, config: Any, set_name: str) -> bool:
        normalized_name = str(getattr(config, "SET_NAME", None) or set_name or "").strip().lower()
        normalized_set_id = str(getattr(config, "SET_ID", "")).strip().lower()
        return normalized_name == "prismatic evolutions" or normalized_set_id == "sv8pt5"

    def _validate_required_inputs(self, transformed_payload: Dict[str, Any], set_name: str) -> None:
        dataframe = transformed_payload["dataframe"]

        if self.REQUIRED_REVERSE_PRICE_COLUMN not in dataframe.columns:
            raise ValueError(
                f"DB input missing required reverse price column '{self.REQUIRED_REVERSE_PRICE_COLUMN}' "
                f"for set '{set_name}'."
            )

        if transformed_payload.get("pack_price") is None:
            raise ValueError(
                f"DB input missing pack price for set '{set_name}' "
                "(pack price resolution is required for EVR calculations)."
            )

        if dataframe.empty:
            raise ValueError(f"No EVR input rows available from DB for set '{set_name}'.")
