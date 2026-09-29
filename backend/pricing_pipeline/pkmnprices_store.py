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


def _same_transaction(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Economic transaction identity; enrichment may legitimately be revised."""
    for field in ("provider_listing_id", "provider_card_id", "canonical_card_id"):
        if str(a.get(field)) != str(b.get(field)):
            return False
    try:
        if Decimal(str(a.get("price"))) != Decimal(str(b.get("price"))):
            return False
    except Exception:
        return False
    return (
        a.get("currency") == b.get("currency")
        and str(a.get("sold_at") or "") == str(b.get("sold_at") or "")
    )


def _same_evidence(a: dict[str, Any], b: dict[str, Any]) -> bool:
    # Evidence rows are append-only provider observations. Derived identity
    # classification may legitimately become stricter in a later matcher version,
    # so replay equality is based only on immutable provider/raw identity fields.
    fields = (
        "provider_listing_id", "provider_card_id", "canonical_card_id",
        "title", "price", "currency", "grader", "grade", "graded",
        "provider_variant", "attribution", "sold_at", "ingested_at", "listing_url",
    )
    for field in fields:
        av, bv = a.get(field), b.get(field)
        if field == "price":
            try:
                if Decimal(str(av)) != Decimal(str(bv)):
                    return False
            except Exception:
                return False
        elif field == "ingested_at":
            def _utc(value: Any) -> datetime | None:
                if value in (None, ""):
                    return None
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            try:
                if _utc(av) != _utc(bv):
                    return False
            except (TypeError, ValueError):
                return False
        elif str(av) != str(bv) if field in {"provider_listing_id", "provider_card_id", "canonical_card_id"} else av != bv:
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

    def insert_evidence(self, rows: list[dict[str, Any]]) -> tuple[int, int, int]:
        if not rows:
            return 0, 0, 0
        by_provider: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            by_provider.setdefault(int(row["provider_card_id"]), []).append(dict(row))

        inserted = 0
        skipped = 0
        metadata_drifts = 0
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
                if _same_evidence(old, row):
                    skipped += 1
                    continue
                if _same_transaction(old, row):
                    # Freeze first-seen enrichment in the append-only evidence row.
                    # Provider-side title/attribution/grading enrichment can evolve;
                    # surface that drift in the run receipt without rewriting history.
                    skipped += 1
                    metadata_drifts += 1
                    continue
                raise PkmnPricesStoreError(
                    f"sold transaction conflict provider_card_id={provider_id} "
                    f"listing_id={row['provider_listing_id']}"
                )
            for chunk in _chunks(fresh, 100):
                self.c.table("pkmnprices_ebay_sold_evidence_v1").insert(chunk).execute()
                inserted += len(chunk)
        return inserted, skipped, metadata_drifts
