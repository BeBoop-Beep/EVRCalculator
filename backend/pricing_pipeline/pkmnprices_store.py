"""Persistence boundary for PkmnPrices sold-evidence collection."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable


class PkmnPricesStoreError(RuntimeError):
    pass


def _chunks(values: list[Any], size: int = 100) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _same_evidence(a: dict[str, Any], b: dict[str, Any]) -> bool:
    fields = (
        "provider_listing_id", "provider_card_id", "canonical_card_id",
        "card_variant_id", "price", "currency", "grader", "grade", "graded",
        "provider_variant", "attribution", "sold_at", "ingested_at",
        "identity_state", "fair_value_signal_eligible", "set_value_nm_eligible",
        "condition_state", "exclusion_reason",
    )
    for field in fields:
        av, bv = a.get(field), b.get(field)
        if field == "price":
            try:
                if Decimal(str(av)) != Decimal(str(bv)):
                    return False
            except Exception:
                return False
        elif av != bv:
            return False
    return True


class PkmnPricesStore:
    def __init__(self, client: Any) -> None:
        self.c = client

    def create_run(self, row: dict[str, Any]) -> dict[str, Any]:
        rows = self.c.table("pkmnprices_sold_runs_v1").insert(row).execute().data or []
        if len(rows) != 1:
            raise PkmnPricesStoreError("run insert did not return exactly one row")
        return dict(rows[0])

    def update_run(self, run_id: str, fields: dict[str, Any]) -> None:
        rows = (
            self.c.table("pkmnprices_sold_runs_v1")
            .update(dict(fields))
            .eq("run_id", run_id)
            .execute().data
            or []
        )
        if len(rows) != 1:
            raise PkmnPricesStoreError(f"run update affected {len(rows)} rows")

    def get_identity_by_canonical(self, canonical_card_id: str, language: str = "English") -> dict[str, Any] | None:
        rows = (
            self.c.table("pkmnprices_card_identity_v1")
            .select("*")
            .eq("canonical_card_id", canonical_card_id)
            .eq("language", language)
            .limit(1)
            .execute().data
            or []
        )
        return dict(rows[0]) if rows else None

    def get_identity_by_provider(self, provider_card_id: int) -> dict[str, Any] | None:
        rows = (
            self.c.table("pkmnprices_card_identity_v1")
            .select("*")
            .eq("provider_card_id", provider_card_id)
            .limit(1)
            .execute().data
            or []
        )
        return dict(rows[0]) if rows else None

    def upsert_identity(self, row: dict[str, Any]) -> None:
        canonical_old = self.get_identity_by_canonical(str(row["canonical_card_id"]), str(row["language"]))
        provider_old = self.get_identity_by_provider(int(row["provider_card_id"]))
        for old in (canonical_old, provider_old):
            if not old:
                continue
            if (
                str(old["canonical_card_id"]) != str(row["canonical_card_id"])
                or str(old["tcgplayer_product_id"]) != str(row["tcgplayer_product_id"])
                or str(old["language"]) != str(row["language"])
            ):
                raise PkmnPricesStoreError("provider identity conflict")
        payload = dict(row)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.c.table("pkmnprices_card_identity_v1").upsert(
            payload, on_conflict="provider_card_id"
        ).execute()

    def get_sync_state(self, provider_card_id: int) -> dict[str, Any] | None:
        rows = (
            self.c.table("pkmnprices_sold_sync_state_v1")
            .select("*")
            .eq("provider_card_id", provider_card_id)
            .limit(1)
            .execute().data
            or []
        )
        return dict(rows[0]) if rows else None

    def upsert_sync_state(self, row: dict[str, Any]) -> None:
        payload = dict(row)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.c.table("pkmnprices_sold_sync_state_v1").upsert(
            payload, on_conflict="provider_card_id"
        ).execute()

    def existing_evidence(self, provider_card_id: int, listing_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not listing_ids:
            return {}
        result: dict[int, dict[str, Any]] = {}
        for chunk in _chunks(sorted(set(int(x) for x in listing_ids)), 100):
            rows = (
                self.c.table("pkmnprices_ebay_sold_evidence_v1")
                .select("*")
                .eq("provider_card_id", provider_card_id)
                .in_("provider_listing_id", chunk)
                .execute().data
                or []
            )
            for row in rows:
                result[int(row["provider_listing_id"])] = dict(row)
        return result

    def insert_evidence(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        if not rows:
            return 0, 0
        by_provider: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            by_provider.setdefault(int(row["provider_card_id"]), []).append(dict(row))

        inserted = 0
        skipped = 0
        for provider_id, provider_rows in by_provider.items():
            existing = self.existing_evidence(
                provider_id, [int(row["provider_listing_id"]) for row in provider_rows]
            )
            fresh = []
            for row in provider_rows:
                old = existing.get(int(row["provider_listing_id"]))
                if old is None:
                    fresh.append(row)
                    continue
                if not _same_evidence(old, row):
                    raise PkmnPricesStoreError(
                        f"sold evidence conflict provider_card_id={provider_id} "
                        f"listing_id={row['provider_listing_id']}"
                    )
                skipped += 1
            for chunk in _chunks(fresh, 100):
                self.c.table("pkmnprices_ebay_sold_evidence_v1").insert(chunk).execute()
                inserted += len(chunk)
        return inserted, skipped
