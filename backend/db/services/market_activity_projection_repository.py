"""Service-role database source/sink for the FMA-1 projection builder.

Only existing database evidence is read. This module has no provider client and
never advances collector state. Generations remain invisible while BUILDING;
the sink reconciles persisted rows before the final VALIDATED transition.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from backend.pricing_pipeline.market_activity_projection import raw_instrument_key


def _rows(result: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in (getattr(result, "data", result) or [])]


def _page(query_factory: Any, size: int = 500) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []; offset = 0
    while True:
        batch = _rows(query_factory().range(offset, offset + size - 1).execute())
        rows.extend(batch)
        if len(batch) < size: return rows
        offset += len(batch)


def _sold_record_contract(row: Mapping[str, Any]) -> dict[str, Any]:
    """Translate one persisted sold row into the frozen FMA domain shape."""
    return {
        "source": "pkmnprices_ebay_sold",
        "providerCardId": str(row["provider_card_id"]),
        "listingId": str(row["provider_listing_id"]),
        "price": str(row["price"]),
        "currency": row["currency"],
        "soldAt": row["sold_at"],
        "ingestedAt": row.get("ingested_at"),
        "collectedAt": row["collected_at"],
        "providerVariant": row.get("provider_variant"),
        "attribution": row.get("attribution"),
        "grader": row.get("grader"),
        "grade": row.get("grade"),
        "gradeQualifier": row.get("grade_qualifier"),
        "graded": row.get("graded"),
    }


def _candidate_contract(row: Mapping[str, Any]) -> dict[str, Any]:
    """Translate a full sibling variant into fma_exact_identity_v1 fields."""
    return {
        "id": str(row["id"]),
        "edition": row.get("edition"),
        "printingType": row.get("printing_type"),
        "specialType": row.get("special_type"),
    }


def _collection_record_contract(sync: Mapping[str, Any] | None, provider_card_id: Any) -> dict[str, Any] | None:
    """A successful sync is collection evidence, never completeness proof."""
    if not sync or not sync.get("last_success_at") or provider_card_id is None:
        return None
    return {
        "collected": True,
        "providerCardId": str(provider_card_id),
        "lastSuccessAt": sync.get("last_success_at"),
    }


def _offer_contract(row: Mapping[str, Any], observed_at: Any) -> dict[str, Any]:
    return {
        "itemPrice": str(row["item_price"]),
        "shippingPrice": None if row.get("shipping_price") is None else str(row["shipping_price"]),
        "quantity": row.get("quantity"),
        "providerSnapshotAt": row.get("provider_snapshot_at"),
        "listingUpdatedAt": row.get("listing_updated_at"),
        "observedAt": observed_at,
    }


def _snapshot_contract(snapshot: Mapping[str, Any], run_status: Any,
                       offers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Translate persisted supply evidence without inventing provenance."""
    source_payload = snapshot.get("source_payload") or {}
    return {
        "snapshotId": snapshot["id"],
        "runStatus": run_status,
        "observationState": snapshot.get("observation_state"),
        "observedAt": snapshot.get("observed_at"),
        "hasMore": snapshot.get("has_more"),
        "sourceConfirmedAt": source_payload.get("provider_snapshot_at"),
        "offers": [_offer_contract(row, snapshot.get("observed_at")) for row in offers],
    }


class SupabaseMarketActivitySource:
    """Read-only source over a service-role Supabase/PostgREST client."""
    def __init__(self, client: Any, *, custom_revision_id: str | None = None):
        self.c = client
        self.custom_revision_id = custom_revision_id

    def pin_roster(self, market_key: str) -> Mapping[str, Any]:
        if market_key.startswith("custom:"):
            fingerprint = market_key.removeprefix("custom:")
            query = self.c.table("pokemon_market_explorer_query_cache_revisions_v1").select("*").eq(
                "query_fingerprint", fingerprint)
            if self.custom_revision_id:
                query = query.eq("revision_id", self.custom_revision_id)
            revisions = _rows(query.order("published_at", desc=True).limit(1).execute())
            if not revisions: raise RuntimeError("published custom roster revision not found")
            revision = revisions[0]
            members = _page(lambda: self.c.table("pokemon_market_explorer_query_cache_revision_members_v1")
                            .select("rank,card_variant_id,item").eq("revision_id", revision["revision_id"]).order("rank"))
            return {"revision": {"kind": "QUERY_CACHE_PUBLISHED_REVISION", "queryFingerprint": fingerprint,
                                 "revisionId": revision["revision_id"], "computedThrough": revision["computed_through"]},
                    "queryRevisionId": revision["revision_id"], "asOf": revision["computed_through"],
                    "denominator": revision["constituent_count"],
                    "members": [{"rank": r["rank"], "cardVariantId": str(r["card_variant_id"]),
                                 "instrumentKey": raw_instrument_key(str(r["card_variant_id"]))} for r in members]}
        serving = _rows(self.c.table("pokemon_market_explorer_surface_serving_v2").select("generation_id")
                        .eq("singleton", 1).limit(1).execute())
        if not serving or not serving[0].get("generation_id"): raise RuntimeError("no prepared V2 generation serving")
        generation_id = str(serving[0]["generation_id"])
        totals = _rows(self.c.table("pokemon_market_explorer_surface_constituent_totals_v2")
                       .select("total_count,asset").eq("generation_id", generation_id).eq("market_key", market_key).limit(1).execute())
        if not totals or totals[0].get("asset") != "cards": raise RuntimeError("prepared card roster not found")
        members = _page(lambda: self.c.table("pokemon_market_explorer_surface_constituents_v2")
                        .select("rank,instrument_id,item").eq("generation_id", generation_id)
                        .eq("market_key", market_key).eq("asset", "cards").order("rank"))
        generation = _rows(self.c.table("pokemon_market_explorer_surface_generations_v2").select("market_date")
                           .eq("generation_id", generation_id).limit(1).execute())[0]
        return {"revision": {"kind": "SURFACE_V2_GENERATION", "generationId": generation_id, "marketKey": market_key},
                "surfaceGenerationId": generation_id, "asOf": generation["market_date"],
                "denominator": totals[0]["total_count"],
                "members": [{"rank": r["rank"], "cardVariantId": str(r["instrument_id"]),
                             "instrumentKey": raw_instrument_key(str(r["instrument_id"]))} for r in members]}

    def _optional_receipts(self, provider_card_id: Any, cutoff: str) -> list[dict[str, Any]]:
        # Collector receipt tables are intentionally absent today. Once added,
        # this bounded read consumes only committed, cutoff-pinned receipts.
        try:
            headers = _rows(self.c.table("pkmnprices_sold_walk_receipts_v1").select("*")
                            .eq("provider_card_id", provider_card_id).eq("committed", True)
                            .lte("committed_at", cutoff).execute())
        except Exception as exc:
            if "does not exist" in str(exc) or "schema cache" in str(exc): return []
            raise
        walks = []
        for header in headers:
            pages = _rows(self.c.table("pkmnprices_sold_walk_pages_v1").select("*")
                          .eq("walk_id", header["walk_id"]).order("page_index").execute())
            edges = _rows(self.c.table("pkmnprices_sold_right_edge_receipts_v1").select("*")
                          .eq("head_walk_id", header["walk_id"]).lte("reconciled_through", cutoff).execute())
            walks.append({**header, "pages": pages, "rightEdge": edges[0] if edges else None})
        return walks

    def load_instrument(self, card_variant_id: str, *, cutoff: str) -> Mapping[str, Any]:
        target = _rows(self.c.table("card_variants").select("id,card_id,edition,printing_type,special_type")
                       .eq("id", card_variant_id).limit(1).execute())
        if not target: raise RuntimeError(f"card variant {card_variant_id} not found")
        siblings = _rows(self.c.table("card_variants").select("id,edition,printing_type,special_type")
                         .eq("card_id", target[0]["card_id"]).execute())
        metadata = _rows(self.c.table("pokemon_market_explorer_card_current_metadata")
                         .select("canonical_card_id").eq("card_variant_id", card_variant_id).limit(1).execute())
        canonical_id = str(metadata[0]["canonical_card_id"]) if metadata else None
        identity = (_rows(self.c.table("pkmnprices_card_identity_v1").select("provider_card_id")
                          .eq("canonical_card_id", canonical_id).eq("language", "English").limit(1).execute()) if canonical_id else [])
        provider_card_id = identity[0]["provider_card_id"] if identity else None
        sold_rows = []
        sync = None
        if provider_card_id is not None:
            sold_rows = _page(lambda: self.c.table("pkmnprices_ebay_sold_evidence_v1").select("*")
                              .eq("provider_card_id", provider_card_id).lte("collected_at", cutoff)
                              .order("sold_at", desc=True))
            sync_rows = _rows(self.c.table("pkmnprices_sold_sync_state_v1").select("*")
                              .eq("provider_card_id", provider_card_id).lte("last_attempt_at", cutoff).limit(1).execute())
            sync = sync_rows[0] if sync_rows else None
        records = [_sold_record_contract(r) for r in sold_rows]
        snapshots = _page(lambda: self.c.table("market_active_supply_snapshots_v1").select("*")
                          .eq("card_variant_id", card_variant_id).lte("created_at", cutoff).order("created_at", desc=True))
        completed = []
        for snap in snapshots:
            runs = _rows(self.c.table("market_active_supply_snapshot_runs_v1").select("status")
                         .eq("run_id", snap["run_id"]).in_("status", ["COMPLETE", "PARTIAL", "FAILED", "MISSING"]).limit(1).execute())
            if not runs: continue
            offers = _rows(self.c.table("market_active_supply_listing_observations_v1").select("*")
                           .eq("snapshot_id", snap["id"]).lte("created_at", cutoff).order("source_rank").execute())
            completed.append(_snapshot_contract(snap, runs[0]["status"], offers))
        latest = completed[0] if completed else None
        return {"asset": "cards", "canonicalCardId": canonical_id,
                "sold": {"providerCardId": provider_card_id, "records": records,
                         "walks": self._optional_receipts(provider_card_id, cutoff) if provider_card_id else [],
                         "collectionRecord": _collection_record_contract(sync, provider_card_id),
                         "candidates": [_candidate_contract(v) for v in siblings],
                         "candidateScope": "FULL_CARD_VARIANT_SET"},
                "asks": latest, "askHistory": completed[1:], "peers": None,
                "_rowsRead": len(sold_rows) + len(snapshots) + sum(len(s.get("offers") or []) for s in completed)}


class SupabaseMarketActivitySink:
    """Staging sink with persisted-prefix and final-state reconciliation."""
    def __init__(self, client: Any): self.c = client

    def load_generation(self, generation_id: str) -> Mapping[str, Any] | None:
        rows = _rows(self.c.table("market_activity_generations_v1").select("*")
                     .eq("activity_generation_id", generation_id).limit(1).execute())
        return rows[0] if rows else None

    def create_generation(self, row: Mapping[str, Any]) -> None:
        self.c.table("market_activity_generations_v1").insert(dict(row)).execute()

    def write_batch(self, table: str, rows: Sequence[Mapping[str, Any]]) -> None:
        if rows: self.c.table(table).insert([dict(row) for row in rows]).execute()

    def validate_resume(self, generation_id: str, market_key: str, resume_after_rank: int) -> Sequence[str]:
        roster = _rows(self.c.table("market_activity_rosters_v1").select("market_key")
                       .eq("activity_generation_id", generation_id).eq("market_key", market_key).limit(1).execute())
        if not roster: return ["resume market/roster header mismatch"]
        members = _page(lambda: self.c.table("market_activity_roster_members_v1").select("rank,instrument_key,card_variant_id")
                        .eq("activity_generation_id", generation_id).eq("market_key", market_key)
                        .lte("rank", resume_after_rank).order("rank"))
        if [r["rank"] for r in members] != list(range(1, resume_after_rank + 1)):
            return ["resume prefix ranks are not contiguous"]
        keys = [r["instrument_key"] for r in members]
        payloads = (_page(lambda: self.c.table("market_activity_instrument_payloads_v1").select("instrument_key")
                          .eq("activity_generation_id", generation_id).in_("instrument_key", keys)) if keys else [])
        windows = (_page(lambda: self.c.table("market_activity_instrument_windows_v1").select("instrument_key,window_days")
                         .eq("activity_generation_id", generation_id).in_("instrument_key", keys)) if keys else [])
        meta = (_page(lambda: self.c.table("market_activity_instrument_series_meta_v1").select("instrument_key")
                      .eq("activity_generation_id", generation_id).in_("instrument_key", keys)) if keys else [])
        errors = []
        if len({r["instrument_key"] for r in payloads}) != resume_after_rank: errors.append("resume prefix payloads incomplete")
        if len(windows) != resume_after_rank * 4: errors.append("resume prefix windows incomplete")
        if len({r["instrument_key"] for r in meta}) != resume_after_rank: errors.append("resume prefix series metadata incomplete")
        return errors

    def reconcile_generation(self, generation_id: str, market_key: str, denominator: int) -> Mapping[str, Any]:
        members = _page(lambda: self.c.table("market_activity_roster_members_v1").select("rank,instrument_key,card_variant_id")
                        .eq("activity_generation_id", generation_id).eq("market_key", market_key).order("rank"))
        keys = [r["instrument_key"] for r in members]
        payloads = (_page(lambda: self.c.table("market_activity_instrument_payloads_v1").select("instrument_key")
                          .eq("activity_generation_id", generation_id).in_("instrument_key", keys)) if keys else [])
        windows = (_page(lambda: self.c.table("market_activity_instrument_windows_v1").select("instrument_key,window_days")
                         .eq("activity_generation_id", generation_id).in_("instrument_key", keys)) if keys else [])
        meta = (_page(lambda: self.c.table("market_activity_instrument_series_meta_v1").select("instrument_key")
                      .eq("activity_generation_id", generation_id).in_("instrument_key", keys)) if keys else [])
        errors = []
        if len(members) != denominator or [r["rank"] for r in members] != list(range(1, denominator + 1)):
            errors.append("persisted roster denominator/ranks mismatch")
        if len({r["instrument_key"] for r in members}) != denominator or len({str(r["card_variant_id"]) for r in members}) != denominator:
            errors.append("persisted roster contains duplicate instrument/card")
        if len({r["instrument_key"] for r in payloads}) != denominator: errors.append("member payload reconciliation failed")
        if len(windows) != denominator * 4: errors.append("window fact reconciliation failed")
        if len({r["instrument_key"] for r in meta}) != denominator: errors.append("series metadata reconciliation failed")
        return {"valid": not errors, "errors": errors, "memberCount": len(members),
                "payloadCount": len(payloads), "windowCount": len(windows), "seriesMetaCount": len(meta)}

    def finish_generation(self, generation_id: str, state: str, diagnostics: Mapping[str, Any]) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        values = {"state": state, "diagnostics": dict(diagnostics), "built_at": now}
        if state == "VALIDATED": values["validated_at"] = now
        self.c.table("market_activity_generations_v1").update(values).eq(
            "activity_generation_id", generation_id).eq("state", "BUILDING").execute()
