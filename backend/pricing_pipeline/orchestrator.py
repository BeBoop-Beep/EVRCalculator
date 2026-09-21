"""One daily entrypoint: targets -> collection -> evidence -> estimates -> multi-source shadow -> validation -> receipt.

State lives in `pokemon_multi_source_pricing_runs_v1` (one run per market date). Every stage is idempotent and gated:
an upstream contract failure stops the pipeline with a stable failure code, and `resume` continues from the first
incomplete stage without repeating completed network work or duplicating writes.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from backend.pricing_pipeline import builder, collector, estimates, evidence, targets
from backend.pricing_pipeline.contracts import (
    DAILY_REQUEST_LIMIT, MAX_FAILED_REQUEST_SHARE, MIN_ATTEMPTED_SHARE, NM_CONDITION_ID, PIPELINE_VERSION, STAGES,
    PipelineError, assert_policy_contract, digest,
)
from backend.pricing_pipeline.variants import resolve_default_variants
from backend.scripts import p5b_cohort_builder as cb
from backend.scripts import pokemon_multi_source_card_price_v1 as policy
from backend.scripts.freeze_ebay_active_ask_v1 import VERSION as ESTIMATOR_VERSION


class Orchestrator:
    def __init__(self, store: Any, ledger: Any, state_dir: Path, *, http_factory: Callable[[Any], Any] | None = None,
                 max_requests: int = DAILY_REQUEST_LIMIT, require_tcg_ready: bool = True, log: Callable[[str], None] = lambda m: None) -> None:
        self.store, self.ledger, self.state_dir = store, ledger, Path(state_dir)
        self.http_factory, self.max_requests = http_factory, min(max_requests, DAILY_REQUEST_LIMIT)
        self.require_tcg_ready, self.log = require_tcg_ready, log
        self._t0 = time.monotonic()

    # ------------------------------------------------------------------ helpers
    def _dir(self, market_date: str) -> Path:
        return self.state_dir / market_date

    def _set(self, run: dict[str, Any], **fields: Any) -> None:
        self.store.update_run(run["run_id"], fields)
        run.update(fields)

    def _fail(self, run: dict[str, Any] | None, exc: PipelineError) -> None:
        if run:
            self._set(run, status=exc.status, failure_code=exc.code, failure_detail=(exc.detail or "")[:500])

    def _stage(self, run: dict[str, Any], stage: str, **fields: Any) -> None:
        self._set(run, stage=stage, status="RUNNING", failure_code=None, failure_detail=None, **fields)
        self.log(f"stage {stage}")

    # ------------------------------------------------------------------ public
    def preview_targets(self, market_date: date) -> dict[str, Any]:
        """--dry-run: build the manifest only. No network to eBay, no database writes, no budget reservation."""
        assert_policy_contract()
        return self._build_manifest(market_date, remaining=self.ledger.remaining())["manifest"]

    def run(self, market_date: date, *, resume: bool = True) -> dict[str, Any]:
        assert_policy_contract()
        md = market_date.isoformat()
        if not self.store.schema_ready():
            raise PipelineError("MIGRATION_MISSING", "pricing pipeline tables/RPC are not deployed")
        run = self.store.get_run(md)
        if run and run["status"] == "COMPLETE":
            return self._replay(run)
        if run and not resume:
            raise PipelineError("RUN_EXISTS", f"{md} already has a {run['status']} run; use --resume")
        if not run:
            run = self.store.create_run({
                "run_id": str(uuid.uuid4()), "market_date": md, "policy_version": policy.POLICY_VERSION,
                "pipeline_version": PIPELINE_VERSION, "status": "RUNNING", "stage": "INIT",
                "request_cap": max(1, self.max_requests), "started_at": datetime.now(timezone.utc).isoformat()})
        try:
            while run["stage"] != "COMPLETE":
                handler = getattr(self, "_" + run["stage"].lower())
                handler(run, md)
            return run["receipt"] if isinstance(run.get("receipt"), dict) else json.loads(run["receipt"])
        except PipelineError as exc:
            self._fail(run, exc)
            raise
        except Exception as exc:  # noqa: BLE001 - unexpected failures are recorded and stay resumable
            self._fail(run, PipelineError("UNEXPECTED_ERROR", f"{type(exc).__name__}: {exc}"))
            raise

    # ------------------------------------------------------------------ stages (named by the stage they START from)
    def _build_manifest(self, market_date: date, remaining: int) -> dict[str, Any]:
        cards, sets, eras, prices = self.store.fetch_catalog()
        universe = cb.build_universe(cards, sets, eras, prices, market_date)
        missing_ids = {u["canonical_card_id"] for u in universe if u["tcg_status"] == "missing" and cb.eligible_for_cohort(u)}
        missing_cards = [c for c in cards if str(c["id"]) in missing_ids]
        resolved = resolve_default_variants(missing_cards, self.store.fetch_identity_inputs(missing_cards)) if missing_cards else {}
        events = self.store.recent_price_events((market_date - timedelta_days(30)).isoformat(), market_date.isoformat())
        manifest = targets.plan_targets(
            universe, market_date, remaining_requests=remaining,
            cost_per_target=targets.measured_requests_per_target(self.store.completed_run_history()),
            resolved_variants=resolved, disagreements=self.store.previous_disagreements(market_date.isoformat()), events=events)
        return {"manifest": manifest, "prices": {str(p["canonical_card_id"]): p for p in prices}}

    def _init(self, run: dict[str, Any], md: str) -> None:
        if self.require_tcg_ready and not self.store.tcg_batch_complete(md):
            raise PipelineError("TCG_BATCH_NOT_COMPLETE", f"no completed TCGplayer scrape batch for {md}", status="WAITING")
        remaining = self.ledger.remaining()
        if remaining <= 0:
            raise PipelineError("BUDGET_EXHAUSTED", "no eBay Browse requests remain today")
        manifest = self._build_manifest(date.fromisoformat(md), remaining)["manifest"]
        if manifest["target_count"] == 0:
            raise PipelineError("NO_TARGETS", "selector produced no targets within the remaining budget")
        self._stage(run, "TARGETS_BUILT", manifest=manifest, target_count=manifest["target_count"],
                    target_fingerprint=manifest["selector_fingerprint"], request_cap=max(1, min(self.max_requests, remaining)))

    def _targets_built(self, run: dict[str, Any], md: str) -> None:
        self._verify_manifest(run)
        self._stage(run, "COLLECTION_RUNNING")

    def _verify_manifest(self, run: dict[str, Any]) -> Mapping[str, Any]:
        manifest = run["manifest"] if isinstance(run["manifest"], dict) else json.loads(run["manifest"])
        if not targets.verify_manifest(manifest) or manifest["selector_fingerprint"] != run["target_fingerprint"]:
            raise PipelineError("TARGET_FINGERPRINT_MISMATCH", run["run_id"])
        return manifest

    def _collection_running(self, run: dict[str, Any], md: str) -> None:
        manifest = self._verify_manifest(run)
        if self.http_factory is None:
            raise PipelineError("COLLECTOR_UNAVAILABLE", "no eBay HTTP client configured")
        checkpoint = collector.CollectionCheckpoint(self._dir(md))
        progress = {"n": 0}

        def on_target(record: Mapping[str, Any]) -> None:
            progress["n"] += 1
            if progress["n"] % 10 == 0:
                self.store.update_run(run["run_id"], {"metrics": {"targets_collected": progress["n"]}})

        summary = collector.collect(manifest, checkpoint, self.http_factory(self.ledger),
                                    max_requests=min(run["request_cap"], self.ledger.remaining() + sum(
                                        r["requests_attempted"] for r in checkpoint.completed().values())),
                                    on_target=on_target)
        attempted = summary["targets_completed"] / max(1, summary["targets_total"])
        failed_share = summary["requests_failed"] / max(1, summary["requests_attempted"])
        metrics = dict(run.get("metrics") or {}, collection=summary)
        if attempted < MIN_ATTEMPTED_SHARE or failed_share > MAX_FAILED_REQUEST_SHARE:
            self._set(run, metrics=metrics, requests_attempted=summary["requests_attempted"],
                      requests_failed=summary["requests_failed"], retries=summary["retries"])
            raise PipelineError("COLLECTOR_PARTIAL_BEYOND_POLICY",
                                f"attempted {attempted:.0%} (min {MIN_ATTEMPTED_SHARE:.0%}), failed requests {failed_share:.1%}", status="PARTIAL")
        self._stage(run, "COLLECTION_COMPLETE", metrics=metrics, requests_attempted=summary["requests_attempted"],
                    requests_failed=summary["requests_failed"], retries=summary["retries"])

    def _collection_complete(self, run: dict[str, Any], md: str) -> None:
        manifest = self._verify_manifest(run)
        prepared = self._prepare_evidence(run, manifest, md)
        evidence.persist(self.store, prepared)
        evidence.verify(self.store, prepared)
        self._stage(run, "EVIDENCE_PERSISTED", ebay_pricing_run_id=prepared["run"]["run_id"],
                    metrics=dict(run.get("metrics") or {}, evidence={
                        "listing_rows": len(prepared["evidence"]), "cards_summarized": len(prepared["summaries"]),
                        "decision_states": prepared["state_counts"], "raw_listings": prepared["run"]["raw_listing_count"],
                        "identity_qualified": prepared["run"]["identity_qualified_count"]}))

    def _prepare_evidence(self, run: dict[str, Any], manifest: Mapping[str, Any], md: str) -> dict[str, Any]:
        records = collector.CollectionCheckpoint(self._dir(md)).completed()
        c = (run.get("metrics") or {}).get("collection") or {}
        return evidence.prepare(manifest, records, market_date=md, state_path=str(self._dir(md)),
                                started_at=str(run["started_at"]),
                                requests={"attempted": run["requests_attempted"], "failed": run["requests_failed"], "retries": run["retries"]},
                                planned_requests=round(manifest["target_count"] * manifest["cost_per_target"]))

    def _evidence_persisted(self, run: dict[str, Any], md: str) -> None:
        manifest = self._verify_manifest(run)
        prepared = self._prepare_evidence(run, manifest, md)
        pricing_run = run["ebay_pricing_run_id"]
        if pricing_run != prepared["run"]["run_id"]:
            raise PipelineError("EVIDENCE_RUN_MISMATCH", f"{pricing_run} != {prepared['run']['run_id']}")
        built = estimates.build(self.store.get_evidence(pricing_run), self.store.get_summaries(pricing_run), manifest,
                                pricing_run_id=pricing_run, market_date=md, evidence_digest=prepared["evidence_digest"])
        if any(r["estimator_version"] != ESTIMATOR_VERSION for r in built["rows"]):
            raise PipelineError("ESTIMATOR_VERSION_MISMATCH", "estimator version drift")
        inserted, skipped = self.store.insert_estimates(built["rows"])
        stored = {r["canonical_card_id"]: r for r in self.store.get_estimates(md, ESTIMATOR_VERSION)}
        if {r["canonical_card_id"] for r in built["rows"]} - set(stored):
            raise PipelineError("ESTIMATE_PERSISTENCE_MISMATCH", "estimate rows missing after insert")
        depth = {"SUFFICIENT": 0, "THIN": 0, "INSUFFICIENT": 0}
        for d in built["diagnostics"].values():
            depth[d["depth_state"]] += 1
        self._stage(run, "ESTIMATES_BUILT", metrics=dict(run.get("metrics") or {}, estimates={
            "depth_counts": depth, "rows_inserted": inserted, "rows_skipped": skipped}))

    def _estimates_built(self, run: dict[str, Any], md: str) -> None:
        manifest = self._verify_manifest(run)
        pricing_run = run["ebay_pricing_run_id"]
        catalog_prices = {str(p["canonical_card_id"]): p for p in self.store.fetch_catalog()[3]}
        rows = builder.build(manifest, self.store.get_summaries(pricing_run), self.store.get_estimates(md, ESTIMATOR_VERSION),
                             catalog_prices, market_date=md, pipeline_run_id=run["run_id"])
        inserted, skipped = self.store.insert_shadow_rows(rows)
        if len(self.store.get_shadow_rows(md)) < len(rows):
            raise PipelineError("SHADOW_PERSISTENCE_MISMATCH", "shadow rows missing after insert")
        self._stage(run, "MULTI_SOURCE_BUILT", metrics=dict(run.get("metrics") or {}, multi_source={
            "decision_counts": builder.decision_counts(rows), "rows_inserted": inserted, "rows_skipped": skipped, "rows": len(rows)}))

    def _multi_source_built(self, run: dict[str, Any], md: str) -> None:
        manifest = self._verify_manifest(run)
        pricing_run = run["ebay_pricing_run_id"]
        catalog_prices = {str(p["canonical_card_id"]): p for p in self.store.fetch_catalog()[3]}
        estimate_rows = self.store.get_estimates(md, ESTIMATOR_VERSION)
        expected = builder.build(manifest, self.store.get_summaries(pricing_run), estimate_rows, catalog_prices,
                                 market_date=md, pipeline_run_id=run["run_id"])
        stored = {r["canonical_card_id"]: r for r in self.store.get_shadow_rows(md)}
        for row in expected:
            got = stored.get(row["canonical_card_id"])
            if got is None or got["decision_fingerprint"] != row["decision_fingerprint"]:
                raise PipelineError("SHADOW_VALIDATION_MISMATCH", row["canonical_card_id"])
        evidence_rows = self.store.get_evidence(pricing_run)
        if not all(estimates.verify_replay(r, evidence_rows) for r in estimate_rows):
            raise PipelineError("ESTIMATE_REPLAY_MISMATCH", "estimator fingerprint not reproducible from persisted evidence")
        if any(r["policy_version"] != policy.POLICY_VERSION for r in stored.values()):
            raise PipelineError("POLICY_VERSION_MISMATCH", "stored row policy drift")
        if self.store.count_non_tcg_current() != 0:
            raise PipelineError("SOURCE_LOCK_AUTHORITY_MISMATCH", "non-TCGPlayer rows in generic current pricing")
        self._stage(run, "VALIDATED")

    def _validated(self, run: dict[str, Any], md: str) -> None:
        metrics = dict(run.get("metrics") or {})
        manifest = self._verify_manifest(run)
        receipt = {
            "market_date": md, "pipeline_run_id": run["run_id"], "pipeline_version": PIPELINE_VERSION, "policy_version": policy.POLICY_VERSION,
            "policy_fingerprint": policy.POLICY_FINGERPRINT, "target_count": manifest["target_count"], "tier_counts": manifest["tier_counts"],
            "target_fingerprint": run["target_fingerprint"], "ebay_pricing_run_id": run["ebay_pricing_run_id"],
            "requests_attempted": run["requests_attempted"], "requests_failed": run["requests_failed"], "retries": run["retries"],
            "request_cap": run["request_cap"], "remaining_budget_today": self.ledger.remaining(),
            "collection": metrics.get("collection"), "evidence": metrics.get("evidence"), "estimates": metrics.get("estimates"),
            "multi_source": metrics.get("multi_source"),
            "gap_fills": (metrics.get("multi_source") or {}).get("decision_counts", {}).get("EBAY_ACTIVE_ASK_FALLBACK", 0),
            "runtime_seconds": round(time.monotonic() - self._t0, 1), "last_successful_stage": "VALIDATED",
            "completed_at": datetime.now(timezone.utc).isoformat()}
        receipt["receipt_fingerprint"] = digest({k: v for k, v in receipt.items() if k not in ("completed_at", "runtime_seconds", "remaining_budget_today")})
        path = self._dir(md)
        path.mkdir(parents=True, exist_ok=True)
        (path / "receipt.json").write_text(json.dumps(receipt, indent=2, default=str) + "\n", encoding="utf-8")
        self._set(run, stage="COMPLETE", status="COMPLETE", failure_code=None, failure_detail=None, receipt=receipt,
                  finished_at=receipt["completed_at"])

    def _replay(self, run: dict[str, Any]) -> dict[str, Any]:
        """A COMPLETE market date is never re-collected or re-written; the stored receipt is returned."""
        receipt = run["receipt"] if isinstance(run["receipt"], dict) else json.loads(run["receipt"])
        return dict(receipt, idempotent_replay=True)


def timedelta_days(n: int):
    from datetime import timedelta
    return timedelta(days=n)
