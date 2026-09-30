"""Deterministic FMA-1 projection builder with no provider dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from backend.domain.pokemon.market_activity import (
    CONTRACT_VERSION, DEFAULT_POLICY, DOMAIN_VERSION, WINDOW_DAYS,
    aggregate_group_activity, assemble_instrument_detail, fingerprint,
    instrument_key, classify_grading, validate_members,
)

FIXTURE_MANIFEST_SHA256 = "e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007"


class ProjectionSource(Protocol):
    """Read-only snapshot adapter. Implementations must apply ``cutoff``."""
    def pin_roster(self, market_key: str) -> Mapping[str, Any]: ...
    def load_instrument(self, card_variant_id: str, *, cutoff: str) -> Mapping[str, Any]: ...


class ProjectionSink(Protocol):
    def load_generation(self, generation_id: str) -> Mapping[str, Any] | None: ...
    def validate_resume(self, generation_id: str, market_key: str, resume_after_rank: int) -> Sequence[str]: ...
    def create_generation(self, row: Mapping[str, Any]) -> None: ...
    def write_batch(self, table: str, rows: Sequence[Mapping[str, Any]]) -> None: ...
    def reconcile_generation(self, generation_id: str, market_key: str, denominator: int) -> Mapping[str, Any]: ...
    def finish_generation(self, generation_id: str, state: str, diagnostics: Mapping[str, Any]) -> None: ...


@dataclass
class BuildMetrics:
    query_count: int = 0
    rows_read: int = 0
    rows_written: int = 0
    batches: int = 0
    elapsed_seconds: float = 0.0
    resumed_after_rank: int = 0
    errors: list[str] = field(default_factory=list)


class MarketActivityProjectionBuilder:
    """Build one immutable generation from a logically pinned source view.

    ``evidence_cutoff`` is captured before any evidence read. Source adapters
    must include only committed runs and immutable evidence first seen at or
    before it. Partial completed runs remain observations but cannot fabricate
    receipt proof; in-progress supply runs are excluded. Roster publication is
    pinned before the cutoff and custom revisions are immutable IDs.
    """
    def __init__(self, source: ProjectionSource, sink: ProjectionSink, *, batch_size: int = 50):
        if not 1 <= batch_size <= 500:
            raise ValueError("batch_size must be between 1 and 500")
        self.source, self.sink, self.batch_size = source, sink, batch_size

    def build(self, market_key: str, *, as_of: str, evidence_cutoff: str | None = None,
              generation_id: str | None = None, resume_after_rank: int = 0,
              dry_run: bool = False) -> dict[str, Any]:
        started = perf_counter()
        cutoff = evidence_cutoff or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        generation_id = generation_id or str(uuid4())
        metrics = BuildMetrics(resumed_after_rank=resume_after_rank)
        roster = dict(self.source.pin_roster(market_key)); metrics.query_count += 1
        members, roster_errors = validate_members(roster.get("members"), roster.get("denominator"))
        if roster_errors:
            return self._reject(generation_id, metrics, roster_errors, dry_run, started)
        generation = {
            "activity_generation_id": generation_id, "as_of": as_of,
            "surface_generation_id": roster.get("surfaceGenerationId"),
            "query_revision_id": roster.get("queryRevisionId"), "roster_ref": roster["revision"],
            "contract_version": CONTRACT_VERSION, "domain_version": DOMAIN_VERSION,
            "policy_version": DEFAULT_POLICY.version, "policy": DEFAULT_POLICY.as_contract(),
            "fixture_manifest_sha256": FIXTURE_MANIFEST_SHA256, "evidence_cutoff": cutoff,
            "evidence_provenance": {"snapshotRule": "committed-and-first-seen-at-or-before-cutoff-v1"},
            "state": "BUILDING", "serving_state": "RETAINED",
        }
        if resume_after_rank and dry_run:
            return self._reject(generation_id, metrics, ["dry-run cannot resume persisted state"], dry_run, started)
        if resume_after_rank:
            existing = self.sink.load_generation(generation_id)
            resume_errors = []
            if not existing:
                resume_errors.append("resume requires an existing generation")
            else:
                if existing.get("state") != "BUILDING": resume_errors.append("resume generation is not BUILDING")
                if str(existing.get("evidence_cutoff")) != cutoff: resume_errors.append("resume evidence cutoff mismatch")
                if existing.get("roster_ref") != roster["revision"]: resume_errors.append("resume roster ref mismatch")
                resume_errors.extend(self.sink.validate_resume(generation_id, market_key, resume_after_rank))
            if resume_errors:
                return self._reject(generation_id, metrics, resume_errors, True, started)
        elif not dry_run:
            self.sink.create_generation(generation); metrics.rows_written += 1
            self.sink.write_batch("market_activity_rosters_v1", [{
                "activity_generation_id": generation_id, "market_key": market_key,
                "roster_type": roster["revision"]["kind"], "roster_revision": roster["revision"],
                "roster_as_of": roster["asOf"], "roster_denominator": len(members)}])
            metrics.rows_written += 1
        detail_inputs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        try:
            for start in range(0, len(members), self.batch_size):
                batch = members[start:start + self.batch_size]
                roster_rows, payload_rows = [], []
                for member in batch:
                    source_input = dict(self.source.load_instrument(member["cardVariantId"], cutoff=cutoff))
                    metrics.query_count += 1; metrics.rows_read += int(source_input.pop("_rowsRead", 0))
                    raw_key = member["instrumentKey"]
                    request = {"marketKey": market_key, "activityGenerationId": generation_id,
                               "rosterRef": roster["revision"], "instrumentKey": raw_key,
                               "asOf": as_of, "windowDays": 30, "chartRange": None}
                    inputs = {**source_input, "request": request, "evaluatedAt": cutoff,
                              "servedGenerationId": roster.get("surfaceGenerationId"),
                              "activityGeneration": {"activityGenerationId": generation_id,
                                                     "state": "RETAINED", "rosterRef": roster["revision"]},
                              "roster": {"asOf": roster["asOf"], "denominator": len(members),
                                         "memberVariantIds": [m["cardVariantId"] for m in members]}}
                    detail = assemble_instrument_detail(inputs)
                    detail_inputs.append((member, source_input))
                    roster_rows.append({"activity_generation_id": generation_id, "market_key": market_key, **{
                        "rank": member["rank"], "instrument_key": raw_key, "card_variant_id": member["cardVariantId"]}})
                    payload_rows.append({"activity_generation_id": generation_id, "instrument_key": raw_key, "payload": detail})
                pending_roster = [row for row in roster_rows if row["rank"] > resume_after_rank]
                pending_keys = {row["instrument_key"] for row in pending_roster}
                pending_payloads = [row for row in payload_rows if row["instrument_key"] in pending_keys]
                if not dry_run and pending_roster:
                    self.sink.write_batch("market_activity_roster_members_v1", pending_roster)
                    self.sink.write_batch("market_activity_instrument_payloads_v1", pending_payloads)
                    metrics.rows_written += len(pending_roster) + len(pending_payloads)
                    facts = self._fact_rows(generation_id, [
                        (member, next(row["payload"] for row in pending_payloads
                                      if row["instrument_key"] == member["instrumentKey"]))
                        for member in batch if member["rank"] > resume_after_rank])
                    for table, rows in facts.items():
                        if rows:
                            self.sink.write_batch(table, rows); metrics.rows_written += len(rows)
                metrics.batches += 1
            group_inputs = {"asset": "cards", "request": {"marketKey": market_key, "activityGenerationId": generation_id,
                            "rosterRef": roster["revision"], "asOf": as_of, "windowDays": 30, "chartRange": None},
                            "evaluatedAt": cutoff, "servedGenerationId": roster.get("surfaceGenerationId"),
                            "activityGeneration": {"activityGenerationId": generation_id,
                                                   "state": "RETAINED", "rosterRef": roster["revision"]},
                            "roster": {"asOf": roster["asOf"], "denominator": len(members)},
                            "members": [{**member, "detailInputs": source_input}
                                        for member, source_input in detail_inputs]}
            for days in WINDOW_DAYS:
                group_inputs["request"]["windowDays"] = days
                payload = aggregate_group_activity(group_inputs)
                if not dry_run:
                    self.sink.write_batch("market_activity_group_payloads_v1", [{
                        "activity_generation_id": generation_id, "market_key": market_key,
                        "window_days": days, "payload": payload}]); metrics.rows_written += 1
        except Exception as exc:
            return self._reject(generation_id, metrics, [f"{type(exc).__name__}: {exc}"], dry_run, started)
        metrics.elapsed_seconds = round(perf_counter() - started, 6)
        reconciliation = ({"dryRun": True} if dry_run else
                          dict(self.sink.reconcile_generation(generation_id, market_key, len(members))))
        if not dry_run and not reconciliation.get("valid"):
            return self._reject(generation_id, metrics, reconciliation.get("errors") or ["persisted reconciliation failed"], False, started)
        diagnostics = {**metrics.__dict__, "rosterFingerprint": fingerprint(members),
                       "reconciliation": reconciliation, "dryRun": dry_run}
        if not dry_run:
            self.sink.finish_generation(generation_id, "VALIDATED", diagnostics)
        return {"generationId": generation_id, "state": "VALIDATED", "diagnostics": diagnostics}

    @staticmethod
    def _fact_rows(generation_id: str, items: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
        out = {name: [] for name in ("market_activity_instrument_windows_v1", "market_activity_instrument_asks_v1",
                                     "market_activity_peer_ranks_v1", "market_activity_daily_v1",
                                     "market_activity_supply_daily_v1", "market_activity_instrument_series_meta_v1")}
        for member, detail in items:
            instrument_key_value = member["instrumentKey"]; variant = member["cardVariantId"]
            sales = detail.get("sales") or {}; observation = sales.get("observation") or {}
            for window in sales.get("windows") or []:
                ready = window["readiness"]; summary = window.get("priceSummary") or {}
                amount = lambda name: ((summary.get(name) or {}).get("amount"))
                out["market_activity_instrument_windows_v1"].append({
                    "activity_generation_id": generation_id, "instrument_key": instrument_key_value,
                    "window_days": window["days"], "card_variant_id": variant,
                    "tier": sales.get("tier") or "RAW", "start_date": window["startDate"], "end_date": window["endDate"],
                    "observation_state": observation.get("state") or "NOT_COLLECTED", "observation_basis": observation.get("basis"),
                    "readiness_state": ready["state"], "readiness_reasons": ready.get("reasons") or [],
                    "proven_lower_bound_date": ready.get("provenLowerBoundDate"), "exhausted": bool(ready.get("exhausted")),
                    "reconciled_through": ready.get("reconciledThrough"), "observed_count": window.get("observedCount"),
                    "proven_count": window.get("provenCount"), "summary_state": summary.get("state"),
                    "summary_basis": summary.get("basis"), "price_record_count": summary.get("recordCount"),
                    "median_price": amount("median"), "low_price": amount("low"), "high_price": amount("high"),
                    "excluded_record_counts": sales.get("excludedRecordCounts") or {},
                    "evidence_fingerprint": detail["evidenceFingerprint"]})
            asks = detail.get("asks")
            if asks:
                out["market_activity_instrument_asks_v1"].append({
                    "activity_generation_id": generation_id, "card_variant_id": variant, "ask_state": asks["state"],
                    "ask_reasons": asks.get("reasons") or [], "provider_confirmed_at": asks.get("providerConfirmedAt"),
                    "collected_at": asks.get("collectedAt"), "current_until": asks.get("currentUntil"),
                    "offer_qualification": asks.get("offerQualification") or "NOT_CURRENT",
                    "captured_listing_count": asks.get("capturedListingCount"),
                    "captured_quantity": (asks.get("capturedQuantity") or {}).get("value"),
                    "quantity_provenance": (asks.get("capturedQuantity") or {}).get("provenance"),
                    "depth": asks.get("depth"), "lowest_ask_basis": (asks.get("lowestAsk") or {}).get("basis"),
                    "lowest_ask_amount": (((asks.get("lowestAsk") or {}).get("price") or {}).get("amount")),
                    "unconfirmed_offers": asks.get("unconfirmedOffers")})
            peers = detail.get("peers")
            if peers:
                scope = peers.get("scope") or {}
                out["market_activity_peer_ranks_v1"].append({
                    "activity_generation_id": generation_id, "instrument_key": instrument_key_value,
                    "window_days": int(detail["request"].get("windowDays") or 30),
                    "population_key": peers.get("populationKey") or fingerprint(peers),
                    "scope_kind": scope.get("kind") or "MARKET_ROSTER", "scope_id": scope.get("scopeId") or detail["request"]["marketKey"],
                    "cohort_revision": scope.get("cohortRevision") or generation_id, "state": peers.get("state") or "UNAVAILABLE",
                    "eligible_other_peer_count": peers.get("eligibleOtherPeerCount") or 0,
                    "quarantined_peer_count": peers.get("quarantinedPeerCount") or 0,
                    "duplicate_peer_row_count": peers.get("duplicatePeerRowCount") or 0,
                    "activity_percentile": peers.get("activityPercentile"), "strict_below_pct": peers.get("strictBelowPct"),
                    "tie_count": peers.get("tieCount")})
            series = detail.get("series") or {}; sale_series = series.get("sales") or {}
            prices = {p["date"]: p for p in (sale_series.get("prices") or {}).get("points") or []}
            for point in (sale_series.get("counts") or {}).get("points") or []:
                price = prices[point["date"]]
                out["market_activity_daily_v1"].append({
                    "activity_generation_id": generation_id, "instrument_key": instrument_key_value,
                    "activity_date": point["date"], "observed_count": point["observedCount"], "proof_state": point["proofState"],
                    "first_ingested_at": point.get("firstIngestedAt"), "last_ingested_at": point.get("lastIngestedAt"),
                    "ingested_after_reconciliation": bool(point.get("ingestedAfterReconciliation")),
                    "record_count": price["recordCount"], "low_price": price["low"]["amount"],
                    "median_price": price["median"]["amount"], "high_price": price["high"]["amount"]})
            span = sale_series.get("provenSpan") or {}
            supply_series = series.get("supply") or {}
            quantities = {p["date"]: p for p in (supply_series.get("quantity") or {}).get("points") or []}
            lowest = {p["date"]: p for p in (supply_series.get("lowestAsk") or {}).get("points") or []}
            for point in (supply_series.get("listings") or {}).get("points") or []:
                quantity = quantities.get(point["date"], {}); ask = lowest.get(point["date"], {})
                out["market_activity_supply_daily_v1"].append({
                    "activity_generation_id": generation_id, "card_variant_id": variant,
                    "activity_date": point["date"], "provider_confirmed_at": point["providerConfirmedAt"],
                    "first_collected_at": point["firstCollectedAt"], "last_collected_at": point["lastCollectedAt"],
                    "collection_count": point["collectionCount"], "confirmations_on_date": point["confirmationsOnDate"],
                    "state_at_collection": point["stateAtCollection"], "depth": point.get("depth"),
                    "listing_count": point["value"], "listed_quantity": quantity.get("value", 0),
                    "quantity_provenance": quantity.get("provenance") or "LEGACY_UNVERIFIED",
                    "lowest_ask_basis": ask.get("basis"), "lowest_ask_amount": (ask.get("price") or {}).get("amount")})
            out["market_activity_instrument_series_meta_v1"].append({
                "activity_generation_id": generation_id, "instrument_key": instrument_key_value,
                "proven_span_start": span.get("startDate"), "proven_span_end": span.get("endDate"),
                "reconciled_through": sale_series.get("reconciledThrough"),
                "excluded_supply_snapshots": (series.get("supply") or {}).get("excludedSnapshots") or {}})
        return out

    def _reject(self, generation_id: str, metrics: BuildMetrics, errors: Sequence[str], dry_run: bool, started: float) -> dict[str, Any]:
        metrics.errors.extend(errors); metrics.elapsed_seconds = round(perf_counter() - started, 6)
        diagnostics = {**metrics.__dict__, "dryRun": dry_run}
        if not dry_run:
            self.sink.finish_generation(generation_id, "REJECTED", diagnostics)
        return {"generationId": generation_id, "state": "REJECTED", "diagnostics": diagnostics}


def raw_instrument_key(card_variant_id: str) -> str:
    return instrument_key(card_variant_id, classify_grading(None, None))
