import json
from typing import Any, Dict

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
