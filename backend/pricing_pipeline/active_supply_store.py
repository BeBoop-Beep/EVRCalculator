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

    def insert_snapshot(self, row: dict[str, Any], listings: list[dict[str, Any]]) -> None:
        try:
            result = self.c.table("market_active_supply_snapshots_v1").insert(row).execute().data or []
        except Exception as exc:
            if "does not exist" not in str(exc) and "schema cache" not in str(exc):
                raise
            # Launch smoke may run after Bucket A but before this PR's additive
            # migration. Preserve every fact in the existing JSONB boundary.
            enriched = dict(row)
            payload = dict(enriched.get("source_payload") or {})
            for key in (
                "seller_concentration_hhi", "lowest_landed_ask", "median_landed_ask",
                "landed_ask_q1", "landed_ask_q3", "landed_ask_mad", "price_depth_bands",
            ):
                if key in enriched:
                    payload[key] = enriched.pop(key)
            payload["schema_compatibility"] = "bucket_a_jsonb"
            enriched["source_payload"] = payload
            result = self.c.table("market_active_supply_snapshots_v1").insert(enriched).execute().data or []
        if len(result) != 1:
            raise RuntimeError("snapshot insert did not return exactly one row")
        snapshot_id = result[0]["id"]
        if listings:
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
                    for key in ("landed_price", "listing_updated_at", "provider_snapshot_at",
                                "seller_rating", "seller_sales_count"):
                        safe[key] = compatible.pop(key, None)
                    safe["schema_compatibility"] = "bucket_a_jsonb"
                    compatible["source_payload"] = {k: v for k, v in safe.items() if v is not None}
                    legacy.append(compatible)
                self.c.table("market_active_supply_listing_observations_v1").insert(legacy).execute()
