"""Persistence boundary for provider-agnostic active-supply snapshots."""
from __future__ import annotations

from typing import Any


class ActiveSupplyStore:
    def __init__(self, client: Any) -> None:
        self.c = client

    def create_run(self, row: dict[str, Any]) -> None:
        self.c.table("market_active_supply_snapshot_runs_v1").insert(row).execute()

    def finish_run(self, run_id: str, values: dict[str, Any]) -> None:
        self.c.table("market_active_supply_snapshot_runs_v1").update(values).eq("run_id", run_id).execute()

    def run_for_date(
        self, *, panel_fingerprint: str, source_provider: str, expected_date: str
    ) -> dict[str, Any] | None:
        rows = (
            self.c.table("market_active_supply_snapshot_runs_v1")
            .select(
                "run_id,status,target_count,observed_target_count,"
                "provider_request_count,provider_credits_used,metadata"
            )
            .eq("panel_fingerprint", panel_fingerprint)
            .eq("source_provider", source_provider)
            .eq("expected_observation_date", expected_date)
            .limit(1)
            .execute()
            .data
            or []
        )
        return dict(rows[0]) if rows else None

    def snapshot_states(self, run_id: str) -> dict[str, dict[str, Any]]:
        rows = (
            self.c.table("market_active_supply_snapshots_v1")
            .select("id,card_variant_id,observation_state")
            .eq("run_id", run_id)
            .execute()
            .data
            or []
        )
        return {str(row["card_variant_id"]): dict(row) for row in rows}

    def provider_identity(self, canonical_card_id: str) -> dict[str, Any] | None:
        rows = (
            self.c.table("pkmnprices_card_identity_v1")
            .select("provider_card_id,canonical_card_id,tcgplayer_product_id,language")
            .eq("canonical_card_id", canonical_card_id)
            .eq("language", "English")
            .limit(1)
            .execute()
            .data
            or []
        )
        return dict(rows[0]) if rows else None

    def _insert_snapshot_compat(
        self, row: dict[str, Any], listings: list[dict[str, Any]]
    ) -> str:
        try:
            result = (
                self.c.table("market_active_supply_snapshots_v1")
                .insert(row)
                .execute()
                .data
                or []
            )
        except Exception as exc:
            if "does not exist" not in str(exc) and "schema cache" not in str(exc):
                raise
            enriched = dict(row)
            payload = dict(enriched.get("source_payload") or {})
            for key in (
                "seller_concentration_hhi",
                "lowest_landed_ask",
                "median_landed_ask",
                "landed_ask_q1",
                "landed_ask_q3",
                "landed_ask_mad",
                "price_depth_bands",
            ):
                if key in enriched:
                    payload[key] = enriched.pop(key)
            payload["schema_compatibility"] = "bucket_a_jsonb"
            enriched["source_payload"] = payload
            result = (
                self.c.table("market_active_supply_snapshots_v1")
                .insert(enriched)
                .execute()
                .data
                or []
            )
        if len(result) != 1:
            raise RuntimeError("snapshot insert did not return exactly one row")
        snapshot_id = str(result[0]["id"])
        self._insert_listings(snapshot_id, listings)
        return snapshot_id

    def _insert_listings(self, snapshot_id: str, listings: list[dict[str, Any]]) -> None:
        if not listings:
            return
        payload = [dict(item, snapshot_id=snapshot_id) for item in listings]
        try:
            self.c.table("market_active_supply_listing_observations_v1").insert(payload).execute()
        except Exception as exc:
            if "does not exist" not in str(exc) and "schema cache" not in str(exc):
                raise
            legacy = []
            for item in payload:
                compatible = dict(item)
                safe = dict(compatible.get("source_payload") or {})
                for key in (
                    "landed_price",
                    "listing_updated_at",
                    "provider_snapshot_at",
                    "seller_rating",
                    "seller_sales_count",
                ):
                    safe[key] = compatible.pop(key, None)
                safe["schema_compatibility"] = "bucket_a_jsonb"
                compatible["source_payload"] = {
                    key: value for key, value in safe.items() if value is not None
                }
                legacy.append(compatible)
            self.c.table("market_active_supply_listing_observations_v1").insert(legacy).execute()

    def insert_snapshot(self, row: dict[str, Any], listings: list[dict[str, Any]]) -> None:
        self._insert_snapshot_compat(row, listings)

    def replace_retryable_snapshot(
        self, row: dict[str, Any], listings: list[dict[str, Any]]
    ) -> None:
        """Replace a same-run failure placeholder after a bounded retry.

        OBSERVED rows are immutable. TARGET_FAILED placeholders may be upgraded to
        OBSERVED (or refreshed with another failure) inside the same expected-date
        run. They never have child listing rows before successful replacement.
        """
        existing = (
            self.c.table("market_active_supply_snapshots_v1")
            .select("id,observation_state")
            .eq("run_id", row["run_id"])
            .eq("card_variant_id", row["card_variant_id"])
            .limit(1)
            .execute()
            .data
            or []
        )
        if not existing:
            self._insert_snapshot_compat(row, listings)
            return
        current = existing[0]
        if current.get("observation_state") == "OBSERVED":
            raise RuntimeError("observed snapshot is immutable")
        snapshot_id = str(current["id"])
        values = {key: value for key, value in row.items() if key not in {"run_id", "card_variant_id"}}
        updated = (
            self.c.table("market_active_supply_snapshots_v1")
            .update(values)
            .eq("id", snapshot_id)
            .execute()
            .data
            or []
        )
        if len(updated) != 1:
            raise RuntimeError("retryable snapshot update did not return exactly one row")
        self._insert_listings(snapshot_id, listings)
