"""Persistence boundary for the pipeline. `SupabaseStore` is production; `MemoryStore` backs the test suite.

Both enforce the same idempotency contract: identical replays are skipped, a changed replay of an existing key
fails closed with `PipelineError`.
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from backend.pricing_pipeline.contracts import PipelineError, PIPELINE_VERSION
from backend.scripts.pokemon_multi_source_card_price_v1 import POLICY_VERSION


def _chunks(rows: list, size: int = 100) -> Iterable[list]:
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


class MemoryStore:
    """In-memory double with the production constraints that the pipeline relies on."""

    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.pricing_runs: dict[str, dict[str, Any]] = {}
        self.evidence: dict[tuple, dict[str, Any]] = {}
        self.summaries: dict[tuple, dict[str, Any]] = {}
        self.estimates: dict[tuple, dict[str, Any]] = {}
        self.shadow: dict[tuple, dict[str, Any]] = {}
        self.catalog: tuple = ([], [], [], [])
        self.identity_inputs: dict[str, Any] = {"links": [], "cards": [], "variants": []}
        self.events: list[dict[str, Any]] = []
        self.batches: dict[str, str] = {}
        self.non_tcg_current = 0
        self.schema_ok = True
        self.writes: list[str] = []

    # ---- run state
    def schema_ready(self) -> bool:
        return self.schema_ok

    def get_run(self, market_date: str) -> dict[str, Any] | None:
        for row in self.runs.values():
            if row["market_date"] == market_date and row["policy_version"] == POLICY_VERSION:
                return copy.deepcopy(row)
        return None

    def create_run(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.get_run(row["market_date"]):
            raise PipelineError("RUN_EXISTS", row["market_date"])
        self.runs[row["run_id"]] = dict(row)
        self.writes.append("create_run")
        return copy.deepcopy(row)

    def update_run(self, run_id: str, fields: dict[str, Any]) -> None:
        self.runs[run_id].update(fields)
        self.writes.append("update_run")

    # ---- TCG authority / catalog
    def fetch_catalog(self):
        return self.catalog

    def tcg_batch_complete(self, market_date: str) -> bool:
        return self.batches.get(market_date) == "complete"

    def fetch_tcg_prices(self, canonical_ids: list[str]) -> dict[str, dict[str, Any]]:
        wanted = set(canonical_ids)
        return {str(p["canonical_card_id"]): p for p in self.catalog[3] if str(p["canonical_card_id"]) in wanted}

    def fetch_identity_inputs(self, canonical_cards: list[dict[str, Any]]) -> dict[str, Any]:
        return self.identity_inputs

    def recent_price_events(self, start: str, end: str) -> list[dict[str, Any]]:
        return list(self.events)

    def previous_disagreements(self, before: str) -> set[str]:
        latest: dict[str, tuple] = {}
        for key, row in self.shadow.items():
            if row["market_date"] < before and row["source_agreement_state"] in ("MODERATE_DISAGREEMENT", "SEVERE_DISAGREEMENT"):
                latest[row["canonical_card_id"]] = (row["market_date"],)
        return set(latest)

    def count_non_tcg_current(self) -> int:
        return self.non_tcg_current

    def completed_run_history(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.runs.values() if r["status"] == "COMPLETE"]

    # ---- eBay evidence (P3 tables)
    def get_pricing_run(self, run_id: str) -> dict[str, Any] | None:
        return copy.deepcopy(self.pricing_runs.get(run_id))

    def upsert_pricing_run(self, row: dict[str, Any]) -> None:
        old = self.pricing_runs.get(row["run_id"])
        if old and old["run_fingerprint"] != row["run_fingerprint"]:
            raise PipelineError("EVIDENCE_RUN_CONTRACT_CHANGED", row["run_id"])
        self.pricing_runs[row["run_id"]] = dict(row)
        self.writes.append("upsert_pricing_run")

    def insert_evidence(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        inserted = skipped = 0
        for row in rows:
            key = (row["run_id"], row["canonical_card_id"], row["listing_item_id"])
            if key in self.evidence:
                if self.evidence[key]["landed_ask_usd"] != row["landed_ask_usd"]:
                    raise PipelineError("EVIDENCE_CHANGED", str(key))
                skipped += 1
            else:
                self.evidence[key] = dict(row)
                inserted += 1
        self.writes.append("insert_evidence")
        return inserted, skipped

    def upsert_summaries(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            key = (row["run_id"], row["canonical_card_id"])
            old = self.summaries.get(key)
            if old and old["evidence_fingerprint"] != row["evidence_fingerprint"]:
                raise PipelineError("SUMMARY_CHANGED", str(key))
            self.summaries[key] = dict(row)
        self.writes.append("upsert_summaries")

    def get_evidence(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(r) for k, r in sorted(self.evidence.items()) if k[0] == run_id]

    def get_summaries(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(r) for k, r in sorted(self.summaries.items()) if k[0] == run_id]

    # ---- estimates (P4C table, append-only)
    def get_estimates(self, market_date: str, estimator_version: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.estimates.values()
                if r["market_date"] == market_date and r["estimator_version"] == estimator_version]

    def insert_estimates(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        inserted = skipped = 0
        for row in rows:
            key = (row["card_variant_id"], row["condition_id"], row["market_date"], row["estimator_version"])
            old = self.estimates.get(key)
            if old:
                if old["estimator_fingerprint"] != row["estimator_fingerprint"]:
                    raise PipelineError("ESTIMATE_CONFLICT", str(key))
                skipped += 1
            else:
                self.estimates[key] = dict(row, id=row.get("id") or f"est-{len(self.estimates)}")
                inserted += 1
        self.writes.append("insert_estimates")
        return inserted, skipped

    # ---- shadow authority
    def get_shadow_rows(self, market_date: str) -> list[dict[str, Any]]:
        return [dict(r) for r in self.shadow.values() if r["market_date"] == market_date]

    def insert_shadow_rows(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        inserted = skipped = 0
        for row in rows:
            key = (row["card_variant_id"], row["condition_id"], row["market_date"], row["policy_version"])
            old = self.shadow.get(key)
            if old:
                if old["decision_fingerprint"] != row["decision_fingerprint"]:
                    raise PipelineError("SHADOW_ROW_CONFLICT", str(key))
                skipped += 1
            else:
                self.shadow[key] = dict(row)
                inserted += 1
        self.writes.append("insert_shadow_rows")
        return inserted, skipped


class SupabaseStore:
    def __init__(self, client: Any) -> None:
        self.c = client

    @staticmethod
    def _retry(call, attempts: int = 4, base_delay: float = 3.0, sleep=None):
        """Read-only PostgREST calls are retried on transient timeouts (57014) and gateway errors; writes never use this."""
        import time

        sleep = sleep or time.sleep
        for attempt in range(attempts):
            try:
                return call()
            except Exception as exc:  # noqa: BLE001
                text = str(exc)
                transient = "57014" in text or "statement timeout" in text or "502" in text or "503" in text or "504" in text
                if not transient or attempt == attempts - 1:
                    raise
                sleep(base_delay * (attempt + 1))

    def _paged(self, factory):
        rows, start = [], 0
        while True:
            page = list(self._retry(lambda: factory().range(start, start + 999).execute().data or []))
            rows.extend(page)
            if len(page) < 1000:
                return rows
            start += 1000

    def schema_ready(self) -> bool:
        # Only a genuinely absent relation means "migration missing". Timeouts/gateway errors are transient: they are
        # retried and, if they persist, propagate as errors instead of being misreported as a missing migration.
        for table in ("pokemon_multi_source_pricing_runs_v1", "pokemon_multi_source_card_prices_v1",
                      "ebay_active_ask_price_estimates_v1", "ebay_pricing_runs_v1", "ebay_browse_request_ledger_v1",
                      "ebay_api_request_budget_v2"):
            try:
                self._retry(lambda table=table: self.c.table(table).select("*").limit(0).execute())
            except Exception as exc:  # noqa: BLE001
                text = str(exc)
                if "42P01" in text or "PGRST205" in text or "does not exist" in text or "Could not find the table" in text:
                    return False
                raise
        return True

    def get_run(self, market_date: str) -> dict[str, Any] | None:
        rows = self.c.table("pokemon_multi_source_pricing_runs_v1").select("*").eq("market_date", market_date).eq(
            "policy_version", POLICY_VERSION).limit(1).execute().data or []
        return rows[0] if rows else None

    def create_run(self, row: dict[str, Any]) -> dict[str, Any]:
        return self.c.table("pokemon_multi_source_pricing_runs_v1").insert(row).execute().data[0]

    def update_run(self, run_id: str, fields: dict[str, Any]) -> None:
        self.c.table("pokemon_multi_source_pricing_runs_v1").update(
            dict(fields, updated_at=datetime.now(timezone.utc).isoformat())).eq("run_id", run_id).execute()

    def fetch_catalog(self):
        cards = self._paged(lambda: self.c.table("pokemon_canonical_cards").select(
            "id,set_id,name,number,printed_number,rarity,catalog_role,opening_eligible,set_value_eligible,canonical_review_status,pokemon_tcg_api_card_id").order("id"))
        sets = self._paged(lambda: self.c.table("sets").select("id,name,era_id").order("id"))
        eras = self._paged(lambda: self.c.table("eras").select("id,name,sort_order").order("id"))
        prices = self._paged(lambda: self.c.table("pokemon_canonical_card_market_prices_latest").select(
            "canonical_card_id,card_variant_id,market_price,captured_at,source").order("canonical_card_id"))
        if any(row.get("source") != "TCGPlayer" for row in prices):
            raise PipelineError("SOURCE_LOCK_AUTHORITY_MISMATCH", "canonical price authority is no longer exclusively TCGPlayer")
        return cards, sets, eras, prices

    def fetch_tcg_prices(self, canonical_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Explicit TCGplayer authority read for specific cards (no full-catalog download); fails closed on another source."""
        out: dict[str, dict[str, Any]] = {}
        for chunk in _chunks(sorted(set(canonical_ids)), 100):
            rows = self._retry(lambda chunk=chunk: self.c.table("pokemon_canonical_card_market_prices_latest").select(
                "canonical_card_id,card_variant_id,market_price,captured_at,source").in_("canonical_card_id", chunk).execute().data or [])
            for row in rows:
                if row.get("source") != "TCGPlayer":
                    raise PipelineError("SOURCE_LOCK_AUTHORITY_MISMATCH", "canonical price authority is no longer exclusively TCGPlayer")
                out[str(row["canonical_card_id"])] = row
        return out

    def tcg_batch_complete(self, market_date: str) -> bool:
        rows = self.c.table("pokemon_scrape_batches").select("status").eq("market_date", market_date).limit(1).execute().data or []
        return bool(rows) and rows[0]["status"] == "complete"

    def fetch_identity_inputs(self, canonical_cards: list[dict[str, Any]]) -> dict[str, Any]:
        set_ids = sorted({str(c["set_id"]) for c in canonical_cards})
        canon_ids = [str(c["id"]) for c in canonical_cards]
        links = []
        for chunk in _chunks(canon_ids, 200):
            links += self.c.table("pokemon_canonical_card_legacy_identity_links").select("canonical_card_id,legacy_card_id").in_(
                "canonical_card_id", chunk).execute().data or []
        cards = []
        for chunk in _chunks(set_ids, 20):
            cards += self._paged(lambda chunk=chunk: self.c.table("cards").select(
                "id,set_id,name,card_number,pokemon_tcg_api_id").in_("set_id", chunk).order("id"))
        variants = []
        card_ids = [str(c["id"]) for c in cards]
        for chunk in _chunks(card_ids, 200):
            variants += self.c.table("card_variants").select("id,card_id,printing_type,special_type,pokemon_tcg_api_id").in_(
                "card_id", chunk).execute().data or []
        return {"links": links, "cards": cards, "variants": variants}

    def recent_price_events(self, start: str, end: str) -> list[dict[str, Any]]:
        return list(self.c.table("card_variant_price_events_v2").select("id,card_variant_id,effective_date,market_price,source").gte(
            "effective_date", start).lte("effective_date", end).eq("source", "TCGPlayer").order("effective_date", desc=True).order(
            "id", desc=True).range(0, 999).execute().data or [])

    def previous_disagreements(self, before: str) -> set[str]:
        rows = self.c.table("pokemon_multi_source_card_prices_v1").select("canonical_card_id,market_date").in_(
            "source_agreement_state", ["MODERATE_DISAGREEMENT", "SEVERE_DISAGREEMENT"]).lt("market_date", before).order(
            "market_date", desc=True).limit(500).execute().data or []
        return {r["canonical_card_id"] for r in rows}

    def completed_run_history(self) -> list[dict[str, Any]]:
        return list(self.c.table("pokemon_multi_source_pricing_runs_v1").select("requests_attempted,target_count").eq(
            "status", "COMPLETE").order("market_date", desc=True).limit(14).execute().data or [])

    def count_non_tcg_current(self) -> int | None:
        """0 = verified TCGPlayer-only; >0 = contamination; None = could not be verified (transient timeout on a full scan)."""
        try:
            rows = self._retry(lambda: self.c.table("card_variant_price_current_v2").select("source").neq("source", "TCGPlayer").limit(1).execute().data or [],
                               attempts=2, base_delay=2.0)
        except Exception as exc:  # noqa: BLE001
            if "57014" in str(exc) or "statement timeout" in str(exc):
                return None
            raise
        return len(rows)

    def get_pricing_run(self, run_id: str) -> dict[str, Any] | None:
        rows = self.c.table("ebay_pricing_runs_v1").select("*").eq("run_id", run_id).limit(1).execute().data or []
        return rows[0] if rows else None

    def upsert_pricing_run(self, row: dict[str, Any]) -> None:
        old = self.get_pricing_run(row["run_id"])
        if old and old["run_fingerprint"] != row["run_fingerprint"]:
            raise PipelineError("EVIDENCE_RUN_CONTRACT_CHANGED", row["run_id"])
        self.c.table("ebay_pricing_runs_v1").upsert(row, on_conflict="run_id").execute()

    def insert_evidence(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        existing = {(r["canonical_card_id"], r["listing_item_id"]): r for r in self.get_evidence(rows[0]["run_id"])} if rows else {}
        fresh = []
        for row in rows:
            old = existing.get((row["canonical_card_id"], row["listing_item_id"]))
            if old is None:
                fresh.append(row)
            elif Decimal_eq(old["landed_ask_usd"], row["landed_ask_usd"]) is False:
                raise PipelineError("EVIDENCE_CHANGED", row["listing_item_id"])
        for chunk in _chunks(fresh):
            self.c.table("ebay_card_listing_evidence_v1").insert(chunk).execute()
        return len(fresh), len(rows) - len(fresh)

    def upsert_summaries(self, rows: list[dict[str, Any]]) -> None:
        for chunk in _chunks(rows):
            self.c.table("ebay_card_pricing_run_summary_v1").upsert(chunk, on_conflict="run_id,canonical_card_id").execute()

    def get_evidence(self, run_id: str) -> list[dict[str, Any]]:
        return self._paged(lambda: self.c.table("ebay_card_listing_evidence_v1").select("*").eq("run_id", run_id).order("id"))

    def get_summaries(self, run_id: str) -> list[dict[str, Any]]:
        return self._paged(lambda: self.c.table("ebay_card_pricing_run_summary_v1").select("*").eq("run_id", run_id).order("canonical_card_id"))

    def get_estimates(self, market_date: str, estimator_version: str) -> list[dict[str, Any]]:
        return self._paged(lambda: self.c.table("ebay_active_ask_price_estimates_v1").select("*").eq(
            "market_date", market_date).eq("estimator_version", estimator_version).order("id"))

    def insert_estimates(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        if not rows:
            return 0, 0
        existing = {(r["card_variant_id"], r["condition_id"]): r for r in self.get_estimates(rows[0]["market_date"], rows[0]["estimator_version"])}
        fresh = []
        for row in rows:
            old = existing.get((row["card_variant_id"], row["condition_id"]))
            if old is None:
                fresh.append(row)
            elif old["estimator_fingerprint"] != row["estimator_fingerprint"]:
                raise PipelineError("ESTIMATE_CONFLICT", row["card_variant_id"])
        for chunk in _chunks(fresh):
            self.c.table("ebay_active_ask_price_estimates_v1").insert(chunk).execute()
        return len(fresh), len(rows) - len(fresh)

    def get_shadow_rows(self, market_date: str) -> list[dict[str, Any]]:
        return self._paged(lambda: self.c.table("pokemon_multi_source_card_prices_v1").select("*").eq(
            "market_date", market_date).eq("policy_version", POLICY_VERSION).order("id"))

    def insert_shadow_rows(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        if not rows:
            return 0, 0
        existing = {(r["card_variant_id"], r["condition_id"]): r for r in self.get_shadow_rows(rows[0]["market_date"])}
        fresh = []
        for row in rows:
            old = existing.get((row["card_variant_id"], row["condition_id"]))
            if old is None:
                fresh.append(row)
            elif old["decision_fingerprint"] != row["decision_fingerprint"]:
                raise PipelineError("SHADOW_ROW_CONFLICT", row["card_variant_id"])
        for chunk in _chunks(fresh):
            self.c.table("pokemon_multi_source_card_prices_v1").insert(chunk).execute()
        return len(fresh), len(rows) - len(fresh)


def Decimal_eq(a: Any, b: Any) -> bool:
    from decimal import Decimal
    return Decimal(str(a)) == Decimal(str(b))
