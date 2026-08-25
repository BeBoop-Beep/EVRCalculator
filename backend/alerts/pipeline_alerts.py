"""Stable, deduplicated alert events for Pokémon publication pipeline stages."""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional, Sequence

from backend.alerts.scrape_alerts import queue_alert


def _success_enabled() -> bool:
    return os.getenv("PIPELINE_SUCCESS_ALERTS", "true").strip().lower() in {"1", "true", "yes"}


def _queue(alert_type: str, title: str, message: str, *, severity: str,
           dedupe_key: str, payload: Mapping[str, Any], success: bool = False):
    if success and not _success_enabled():
        return None
    return queue_alert(alert_type, title, message, severity=severity,
                       dedupe_key=dedupe_key, payload=dict(payload))


def alert_daily_batch_created(*, market_date: str, batch_id: Any,
                              expected_set_count: int, queued_set_count: int,
                              trigger_source: str, runtime_git_sha: Optional[str],
                              runtime_registry_hash: Optional[str] = None):
    payload = locals()
    return _queue("pokemon_daily_batch_created", f"✅ Pokémon daily batch created — {market_date}",
                  f"{queued_set_count} sets queued. Runtime: {(runtime_git_sha or 'unknown')[:12]}. Trigger: {trigger_source}.",
                  severity="info", dedupe_key=f"market_batch_created:{market_date}",
                  payload=payload, success=True)


def alert_set_scrape_failed(*, market_date: str, batch_id: Any, queue_job_id: Any,
                            canonical_key: str, attempts: int, max_attempts: int,
                            error_code: Optional[str], retryable: bool,
                            error_summary: Optional[str]):
    action = "retrying automatically" if retryable and attempts < max_attempts else "manual action required"
    payload = {**locals(), "status": "failed", "stage": "scrape", "error_summary": (error_summary or "")[:500]}
    return _queue("pokemon_set_scrape_failed", f"❌ Pokémon set scrape failed — {canonical_key}",
                  f"{market_date}: attempt {attempts}/{max_attempts}; {action}. Error: {error_code or 'unknown'}.",
                  severity="error" if retryable else "critical",
                  dedupe_key=f"set_scrape_failed:{market_date}:{canonical_key}:{error_code or 'unknown'}:terminal",
                  payload=payload)


def alert_scrape_batch_complete(*, market_date: str, batch_id: Any,
                                succeeded_set_count: int, expected_set_count: int,
                                failed_queue_rows: int = 0, duration: Optional[str] = None):
    payload = locals()
    return _queue("pokemon_scrape_batch_complete", f"✅ Pokémon scrape complete — {market_date}",
                  f"Market cohort observations: {succeeded_set_count}/{expected_set_count}. Promotion gate OPEN.",
                  severity="info", dedupe_key=f"market_batch_complete:{market_date}", payload=payload, success=True)


def alert_market_quality(*, market_date: str, status: str, qualifying_set_count: int,
                         cohort_set_count: int, missing_canonical_keys: Sequence[str] = (),
                         missing_valuation_sets: Sequence[str] = (),
                         missing_run_evidence: Sequence[str] = (),
                         previous_accepted_market_date: Optional[str] = None):
    ready = status.upper() == "READY"
    alert_type = "pokemon_market_quality_ready" if ready else "pokemon_market_quality_blocked"
    missing = ", ".join(missing_canonical_keys) or "none"
    message = f"{qualifying_set_count}/{cohort_set_count} Market sets qualified."
    if not ready:
        message += f" Missing: {missing}. Global /Market remains {previous_accepted_market_date or 'unknown'}."
    return _queue(alert_type, f"{'✅' if ready else '❌'} Market Quality {status} — {market_date}", message,
                  severity="info" if ready else "error",
                  dedupe_key=f"market_quality:{market_date}:{status.upper()}", payload=locals(), success=ready)


def alert_market_index(*, market_date: str, raw_latest_date: Optional[str],
                       top10_latest_date: Optional[str], raw_card_count: Optional[int] = None,
                       chase_card_count: Optional[int] = None, eligible_set_count: Optional[int] = None):
    published = raw_latest_date == market_date and top10_latest_date == market_date
    return _queue("pokemon_market_index_published" if published else "pokemon_market_index_failed",
                  f"{'✅ Pokémon Market Index' if published else '❌ Market Index blocked'} — {market_date}",
                  f"Raw: {raw_latest_date or 'missing'}. Top 10: {top10_latest_date or 'missing'}.",
                  severity="info" if published else "error",
                  dedupe_key=f"market_index:{market_date}:{'published' if published else 'failed'}",
                  payload=locals(), success=published)


def alert_global_market(*, market_date: str, row_market_date: Optional[str],
                        payload_market_date: Optional[str], overview_market_date: Optional[str],
                        set_count: Optional[int] = None, fingerprint: Optional[str] = None):
    published = row_market_date == payload_market_date == overview_market_date == market_date
    return _queue("pokemon_global_market_published" if published else "pokemon_global_market_failed",
                  f"{'✅ Global Pokémon Market published' if published else '❌ Global Pokémon Market blocked'} — {market_date}",
                  f"Market Overview: {overview_market_date or 'missing'}. Set Market: {row_market_date or 'missing'}. Sets: {set_count or 0}.",
                  severity="info" if published else "error",
                  dedupe_key=f"global_market:{market_date}:{'published' if published else 'failed'}",
                  payload=locals(), success=published)


def alert_market_audit(*, market_date: str, passed: bool, failing_surfaces: Sequence[str] = (),
                       expected_date: Optional[str] = None, actual_dates: Optional[Mapping[str, Any]] = None,
                       error: Optional[str] = None):
    detail = "All required Market surfaces are current." if passed else f"Stale: {', '.join(failing_surfaces) or 'unknown'}."
    return _queue("pokemon_market_audit_passed" if passed else "pokemon_market_audit_failed",
                  f"{'✅' if passed else '❌'} Post-scrape Market audit {'PASS' if passed else 'FAIL'} — {market_date}", detail,
                  severity="info" if passed else "critical",
                  dedupe_key=f"market_audit:{market_date}:{'passed' if passed else 'failed'}",
                  payload={**locals(), "error": (error or "")[:500]}, success=passed)


def alert_market_pipeline_complete(*, market_date: str, scrape_progress: str,
                                   quality_progress: str, raw_index_date: str,
                                   top10_index_date: str, global_market_date: str):
    message = (f"Scrape: {scrape_progress}\nMarket Quality: {quality_progress} READY\n"
               f"Raw Index: {raw_index_date}\nTop 10 Index: {top10_index_date}\n"
               f"Global Market: {global_market_date}\nAudit: PASS\n\nPublic Market is current.")
    return _queue("pokemon_market_pipeline_complete", f"✅ Pokémon Market Pipeline COMPLETE — {market_date}", message,
                  severity="info", dedupe_key=f"market_pipeline:{market_date}:complete",
                  payload={**locals(), "stage": "daily_market", "status": "complete"}, success=True)


def alert_market_pipeline_complete_if_ready(client: Any, *, market_date: str,
                                            audit_passed: bool):
    """Re-read every authority and alert only when the full morning contract holds."""
    if not audit_passed:
        return None
    batch_rows = list((client.table("pokemon_scrape_batches")
                       .select("status,promoted_at,missing_set_count,expected_set_count,succeeded_set_count")
                       .eq("market_date", market_date).limit(1).execute()).data or [])
    quality_rows = list((client.table("pokemon_market_date_quality")
                         .select("status,qualifying_set_count,cohort_set_count")
                         .eq("market_date", market_date).limit(1).execute()).data or [])
    index_rows = list((client.table("pokemon_market_index_daily_history")
                       .select("index_key,market_date").eq("tcg", "pokemon")
                       .eq("market_date", market_date).execute()).data or [])
    global_rows = list((client.table("pokemon_explore_set_value_snapshot_latest")
                        .select("market_date,payload_json").eq("tcg", "pokemon")
                        .eq("scope", "market").limit(1).execute()).data or [])
    if not batch_rows or not quality_rows or not global_rows:
        return None
    batch, quality, global_row = batch_rows[0], quality_rows[0], global_rows[0]
    payload = global_row.get("payload_json") or {}
    index_keys = {row.get("index_key") for row in index_rows
                  if str(row.get("market_date"))[:10] == market_date}
    global_dates = (str(global_row.get("market_date"))[:10],
                    str((((payload.get("meta") or {}).get("snapshot") or {}).get("marketDate") or ""))[:10],
                    str(((payload.get("marketOverview") or {}).get("marketDate") or ""))[:10])
    ready = (batch.get("status") == "complete" and batch.get("promoted_at")
             and int(batch.get("missing_set_count") or 0) == 0
             and quality.get("status") == "READY"
             and {"raw", "top10"}.issubset(index_keys)
             and all(day == market_date for day in global_dates))
    if not ready:
        return None
    expected = int(batch.get("expected_set_count") or 0)
    succeeded = int(batch.get("succeeded_set_count") or expected)
    qualifying = int(quality.get("qualifying_set_count") or 0)
    cohort = int(quality.get("cohort_set_count") or 0)
    return alert_market_pipeline_complete(
        market_date=market_date, scrape_progress=f"{succeeded}/{expected}",
        quality_progress=f"{qualifying}/{cohort}", raw_index_date=market_date,
        top10_index_date=market_date, global_market_date=market_date)


def alert_simulation_stage(*, market_date: str, state: str, **details: Any):
    types = {"started": "pokemon_simulation_pipeline_started", "failed": "pokemon_simulation_pipeline_failed",
             "complete": "pokemon_full_publication_complete", "publication_failed": "pokemon_full_publication_failed"}
    alert_type = types[state]
    success = state in {"started", "complete"}
    return _queue(alert_type, f"{'✅' if success else '❌'} Pokémon simulation/full publication {state} — {market_date}",
                  "Simulation publication is a separate phase from morning Market publication.",
                  severity="info" if success else "critical",
                  dedupe_key=f"simulation_pipeline:{market_date}:{state}",
                  payload={"market_date": market_date, "stage": "simulation", "status": state, **details}, success=success)
