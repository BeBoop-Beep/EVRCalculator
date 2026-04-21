import json
from typing import Any, Dict

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
        self._emit_diagnostics(repository_payload, compatibility_payload)
        self._emit_row_population_audit(compatibility_payload, config, set_name)
        self._validate_required_inputs(compatibility_payload, set_name)
        return compatibility_payload

    def _emit_diagnostics(self, repository_payload: Dict[str, Any], transformed_payload: Dict[str, Any]) -> None:
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

    def _emit_row_population_audit(self, transformed_payload: Dict[str, Any], config: Any, set_name: str) -> None:
        dataframe = transformed_payload.get("dataframe")
        if not isinstance(dataframe, pd.DataFrame):
            return

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
