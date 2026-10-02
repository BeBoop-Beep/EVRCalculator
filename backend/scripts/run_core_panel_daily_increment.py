"""ACTIVE bounded daily sold-increment collector for the frozen 207-card Core Panel.

STATUS: ACTIVE FOR THE RESEARCH-ONLY FAIR VALUE SHADOW FEED. ``--preflight`` remains
zero-provider / zero-write. Committed runs are bounded by the frozen daily credit budget,
reuse cached identities only, preserve B4/B5 historical state, and never mutate canonical
pricing or any public Fair Value surface. Production execution is SHA-pinned by the managed
VM installer and wrapper.

Why it exists
-------------
B4 stops fetching a Core Panel card once ``phase1_ready`` and B5 excludes the completed
Core Panel, so after historical backfill nothing guarantees the newest sold transactions
for these 207 cards arrive daily. Fair Value shadow validation needs them.

Contract (all enforced in code, tested without any provider call)
-----------------------------------------------------------------
* Never restarts or touches historical backfill. Cards whose B4 phase-1 (180-day) walk is not
  ready, or that have no recorded frontier, are skipped; a PARTIAL lifetime cursor is left alone. Existing ``core_panel_backfill_*`` cursors and every pre-existing sync
  field are preserved byte-for-byte; this module writes ONLY the namespaced metadata key
  ``core_panel_daily_increment``.
* Reuses cached exact PkmnPrices identities. It NEVER performs an identity lookup; a card
  with no cached identity is reported, not fetched.
* Fetches newest ``date_desc`` combined (raw + graded) pages with ``since=<frontier>``.
  Per ``PKMNPRICES_SOLD_HISTORY_PERSISTENCE_20260929.md`` ``since`` filters on
  ``ingested_at``; a sale collected today can have an old ``sold_at``. Completeness is
  therefore "the provider reports the ``since`` set exhausted", never "a page looked old".
* Appends/dedupes through ``PkmnPricesStore.insert_evidence``. Original evidence is
  immutable; later provider enrichment drift is counted, never rewritten.
* A card whose newest page is entirely newer than the frontier and still has more pages is
  an OVERFLOW card. Overflow continues only inside the bounded policy; if the bound is hit
  an ``open_gap`` (floor + resume cursor) is persisted and the frontier does NOT advance,
  so the missing transactions cannot be silently skipped. Open gaps are served first.
* If the provider returns rows at/older than the frontier despite ``since`` (filter not
  honoured) the card fails closed (gap stays open).

Budget (derived from current contracts, see ``budget_contract``)
----------------------------------------------------------------
Provider ceiling 75,000 credits per UTC day. Existing reserved consumers: B5 55,000,
active-supply C 4,500 (hard cap; ~4,140 projected), daily vintage-gap collector 600.
This collector: hard cap 8,000 = one mandatory 207x20 = 4,140 page pass plus 3,860 of
bounded overflow. Total commitments 68,100; unallocated headroom 6,900.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesAPIError, PkmnPricesClient  # noqa: E402
from backend.pricing_pipeline.pkmnprices_store import PkmnPricesStore  # noqa: E402
from backend.scripts.run_market_active_supply_snapshot import (  # noqa: E402
    FULL_PANEL_CREDIT_CAP as ACTIVE_SUPPLY_DAILY_CREDIT_CAP,
)
from backend.scripts.run_market_microstructure_bucket_b import (  # noqa: E402
    COLLECTOR_VERSION,
    PANEL_FINGERPRINT,
    _normalize,
)
from backend.scripts.run_market_microstructure_bucket_b4 import (  # noqa: E402
    DAILY_B_CREDIT_CAP as B4_DAILY_CREDIT_CAP,
    operational_pause_reason,
    panel_states,
    phoenix_date,
    provider_credit_day_utc,
)
from backend.scripts.run_market_microstructure_bucket_b5 import (  # noqa: E402
    ACCOUNT_DAILY_CREDIT_LIMIT,
    DAILY_B5_CREDIT_CAP,
)

MODE = "core_panel_daily_increment_v1"
SELECTOR_VERSION = "core_panel_daily_increment_selector_v1"
STATE_KEY = "core_panel_daily_increment"
PROVIDER_DAILY_CREDIT_HALT = "PROVIDER_DAILY_CREDIT_LIMIT_EXCEEDED"

#: Reviewed activation for the research-only prospective Fair Value shadow evidence feed.
ACTIVATION_ENABLED = True

EXPECTED_PANEL_COUNT = 207
PAGE_SIZE = 20
MAX_PAGES_PER_CARD_DAY = 4
ONE_PAGE_PASS_CREDITS = EXPECTED_PANEL_COUNT * PAGE_SIZE  # 4,140
DAILY_INCREMENT_CREDIT_CAP = 8000
#: .github/workflows/pkmnprices-sold-evidence-daily.yml passes --item-credit-cap 600.
VINTAGE_GAP_DAILY_CREDIT_CAP = 600
#: One-time provider-semantics canary ceiling (run_core_panel_provider_semantics_canary); not daily.
CANARY_ONE_TIME_CREDIT_CEILING = 20
#: Scheduled / schedulable PkmnPrices consumers audited against current develop. The test suite
#: scans .github/workflows and infra/oracle crontabs and fails if a new one appears unaccounted.
AUDITED_SCHEDULED_PROVIDER_CONSUMERS = {
    "b4_phase1_breadth": "infra/oracle/market-microstructure-b4.crontab (cap 55,000; inert once 207/207 phase1_ready)",
    "b5_targeted_expansion": "infra/oracle/market-microstructure-b5.crontab (cap 55,000)",
    "active_supply_c": "infra/oracle/active-supply-panel.crontab (hard cap 4,500)",
    "vintage_gap_daily": ".github/workflows/pkmnprices-sold-evidence-daily.yml (cap 600)",
    "core_panel_increment": "infra/oracle/core-panel-daily-increment.crontab (cap 8,000 shared across retries)",
}
RUNTIME_SAFETY_MARGIN = 2000
MIN_UNALLOCATED_HEADROOM = 5000


class IncrementDormant(RuntimeError):
    pass


def _ts(value: Any) -> datetime | None:
    """Parse an ISO timestamp to aware UTC; string comparison of mixed formats is unsafe."""
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _max_ts(*values: Any) -> str | None:
    parsed = [(t, v) for v in values if (t := _ts(v)) is not None]
    return max(parsed, key=lambda pair: pair[0])[1] if parsed else None


def budget_contract() -> dict[str, Any]:
    """Derive and validate the daily credit budget from the other consumers' contracts."""
    committed = {
        "b5_daily_cap": DAILY_B5_CREDIT_CAP,
        "active_supply_c_daily_cap": ACTIVE_SUPPLY_DAILY_CREDIT_CAP,
        "vintage_gap_daily_cap": VINTAGE_GAP_DAILY_CREDIT_CAP,
        "core_panel_increment_daily_cap": DAILY_INCREMENT_CREDIT_CAP,
    }
    total = sum(committed.values())
    headroom = ACCOUNT_DAILY_CREDIT_LIMIT - total
    absolute_worst_case = EXPECTED_PANEL_COUNT * MAX_PAGES_PER_CARD_DAY * PAGE_SIZE
    contract = {
        "account_daily_credit_limit": ACCOUNT_DAILY_CREDIT_LIMIT,
        **committed,
        "total_committed": total,
        "scheduled_committed_total": total,
        "unallocated_headroom": headroom,
        "scheduled_unallocated_headroom": headroom,
        "headroom_scope": "AUDITED_SCHEDULED_CONSUMERS_ONLY",
        "account_wide_remaining_credits_known": False,
        "unscheduled_research_consumers_may_share_account": True,
        "provider_exhaustion_authority": "HTTP_429_credit_limit_exceeded",
        "one_page_pass_credits": ONE_PAGE_PASS_CREDITS,
        "overflow_budget_credits": DAILY_INCREMENT_CREDIT_CAP - ONE_PAGE_PASS_CREDITS,
        "uncapped_worst_case_credits": absolute_worst_case,
        "worst_case_credits_enforced": DAILY_INCREMENT_CREDIT_CAP,
        "max_pages_per_card_day": MAX_PAGES_PER_CARD_DAY,
        "page_size": PAGE_SIZE,
        "b4_daily_cap_informational": B4_DAILY_CREDIT_CAP,
        "b4_note": "B4 carries its own 55,000 cap but is inert at 207/207 phase1_ready; if it ever spends, the "
                   "runtime other-consumer accounting in invocation_budget() shrinks this collector's room.",
        "canary_one_time_credit_ceiling": CANARY_ONE_TIME_CREDIT_CEILING,
        "audited_scheduled_provider_consumers": AUDITED_SCHEDULED_PROVIDER_CONSUMERS,
        "runtime_safety_margin": RUNTIME_SAFETY_MARGIN,
    }
    if DAILY_INCREMENT_CREDIT_CAP < ONE_PAGE_PASS_CREDITS:
        raise RuntimeError("INCREMENT_CAP_BELOW_ONE_PAGE_PASS")
    if headroom < MIN_UNALLOCATED_HEADROOM:
        raise RuntimeError(f"INCREMENT_BUDGET_BREAKS_ACCOUNT_HEADROOM headroom={headroom}")
    if total > ACCOUNT_DAILY_CREDIT_LIMIT:
        raise RuntimeError("INCREMENT_BUDGET_EXCEEDS_ACCOUNT_LIMIT")
    return contract


# ------------------------------------------------------------------ state helpers
def increment_state(sync: dict[str, Any] | None) -> dict[str, Any]:
    return dict(((sync or {}).get("metadata") or {}).get(STATE_KEY) or {})


def frontier_of(sync: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Return (frontier_ingested_at, source). Never invents one."""
    inc = increment_state(sync)
    if inc.get("frontier_ingested_at"):
        return str(inc["frontier_ingested_at"]), "increment_state"
    meta = dict((sync or {}).get("metadata") or {})
    if meta.get("core_panel_incremental_watermark"):
        return str(meta["core_panel_incremental_watermark"]), "b4_incremental_watermark"
    if (sync or {}).get("last_ingested_at"):
        return str(sync["last_ingested_at"]), "sync_last_ingested_at"
    return None, None


def card_eligibility(state: dict[str, Any]) -> tuple[bool, str]:
    identity, sync = state.get("identity"), state.get("sync")
    if not identity:
        return False, "NO_CACHED_IDENTITY"  # never looked up here
    if not sync:
        return False, "NO_SYNC_STATE"
    # B4 only walks each card back to its 180-day horizon (`phase1_ready`) and may leave the
    # lifetime cursor PARTIAL. What incremental collection needs is that the newest-first walk
    # started from a recorded watermark, not that history is drained; the historical cursor is
    # never read, resumed or modified here.
    if not state.get("phase1_ready"):
        return False, "PHASE1_NOT_READY"
    frontier, _ = frontier_of(sync)
    if not frontier:
        return False, "NO_FRONTIER"
    return True, "ELIGIBLE"


def order_cards(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Open gaps first (oldest opened), then stalest frontier, then panel order."""
    def key(state: dict[str, Any]) -> tuple[Any, ...]:
        inc = increment_state(state["sync"])
        gap = inc.get("open_gap")
        frontier, _ = frontier_of(state["sync"])
        return (
            0 if gap else 1,
            str((gap or {}).get("opened_on") or ""),
            str(frontier or ""),
            int(state.get("panel_index", 0)),
        )
    return sorted(states, key=key)


# ------------------------------------------------------------------ preflight
def _credits_used_today_by_mode(db: Any, credit_day: str) -> dict[str, int]:
    start = datetime.fromisoformat(credit_day + "T00:00:00+00:00")
    rows = (
        db.table("pkmnprices_sold_runs_v1").select("credits_used,metadata,started_at")
        .gte("started_at", start.isoformat())
        .lt("started_at", (start + timedelta(days=1)).isoformat())
        .execute().data or []
    )
    out: Counter[str] = Counter()
    for row in rows:
        out[str(dict(row.get("metadata") or {}).get("mode") or "unknown")] += int(row.get("credits_used") or 0)
    return dict(out)


def _provider_daily_credit_exhausted_today(db: Any, credit_day: str) -> bool:
    """Remember an account-wide provider daily-credit 429 for this UTC day.

    PkmnPrices credits are account-wide, so manual/research consumers can spend credits
    outside the sold-run ledger. Once any sold run observes credit_limit_exceeded, later
    increment retries must make zero provider calls until the next UTC credit day.
    """
    start = datetime.fromisoformat(credit_day + "T00:00:00+00:00")
    rows = (
        db.table("pkmnprices_sold_runs_v1").select("error_code,metadata,started_at")
        .gte("started_at", start.isoformat())
        .lt("started_at", (start + timedelta(days=1)).isoformat())
        .execute().data or []
    )
    for row in rows:
        meta = dict(row.get("metadata") or {})
        if meta.get("halted_reason") == PROVIDER_DAILY_CREDIT_HALT:
            return True
        for failure in list(meta.get("failures") or []):
            if "code=credit_limit_exceeded" in str((failure or {}).get("message") or ""):
                return True
    return False

def invocation_budget(used_by_mode: dict[str, int], requested_cap: int) -> dict[str, int]:
    if not 1 <= requested_cap <= DAILY_INCREMENT_CREDIT_CAP:
        raise ValueError(f"credit cap must be 1..{DAILY_INCREMENT_CREDIT_CAP}")
    prior_increment = int(used_by_mode.get(MODE, 0))
    other = sum(v for k, v in used_by_mode.items() if k != MODE)
    account_room = (
        ACCOUNT_DAILY_CREDIT_LIMIT - RUNTIME_SAFETY_MARGIN - ACTIVE_SUPPLY_DAILY_CREDIT_CAP - other - prior_increment
    )
    remaining = max(0, min(requested_cap - prior_increment, account_room))
    return {
        "prior_increment_credits_today": prior_increment,
        "other_sold_run_credits_today": other,
        "account_room_credits": account_room,
        "local_ledger_room_upper_bound_credits": account_room,
        "account_room_scope": "LOCAL_PERSISTED_SOLD_RUNS_PLUS_RESERVED_ACTIVE_SUPPLY_ONLY",
        "account_wide_remaining_credits_known": False,
        "invocation_credit_cap": remaining,
    }


def preflight(db: Any, *, expected_date: str, credit_cap: int = DAILY_INCREMENT_CREDIT_CAP) -> dict[str, Any]:
    contract = budget_contract()
    credit_day = provider_credit_day_utc()
    provider_daily_credit_exhausted = _provider_daily_credit_exhausted_today(db, credit_day)
    budget = invocation_budget(_credits_used_today_by_mode(db, credit_day), credit_cap)
    if provider_daily_credit_exhausted:
        budget["invocation_credit_cap"] = 0
    states = panel_states(db)
    reasons: Counter[str] = Counter()
    eligible, gaps, due, current_today = [], 0, 0, 0
    for state in states:
        ok, reason = card_eligibility(state)
        reasons[reason] += 1
        if ok:
            eligible.append(state)
            state_inc = increment_state(state["sync"])
            has_gap = bool(state_inc.get("open_gap"))
            gaps += has_gap
            if state_inc.get("last_run_date") == expected_date and not has_gap:
                current_today += 1
            else:
                due += 1
    return {
        "status": "PREFLIGHT_OK",
        "mode": MODE,
        "activation_enabled": ACTIVATION_ENABLED,
        "dormant": not ACTIVATION_ENABLED,
        "panel_fingerprint": PANEL_FINGERPRINT,
        "panel_count": len(states),
        "expected_date": expected_date,
        "provider_credit_day_utc": credit_day,
        "budget_contract": contract,
        "invocation_budget": budget,
        "provider_daily_credit_exhausted": provider_daily_credit_exhausted,
        "provider_account_balance_authority": (
            "EXHAUSTED_FROM_AUTHORITATIVE_429_RECEIPT"
            if provider_daily_credit_exhausted
            else "UNKNOWN_UNTIL_PROVIDER_RESPONSE"
        ),
        "eligibility": dict(sorted(reasons.items())),
        "eligible_cards": len(eligible),
        "due_cards": due,
        "already_current_today": current_today,
        "open_gap_cards": gaps,
        "operational_pause": operational_pause_reason(db),
        "provider_requests": 0,
        "provider_credits_used": 0,
        "database_writes": 0,
    }


# ------------------------------------------------------------------ collection
def _save_state(
    store: Any, state: dict[str, Any], inc: dict[str, Any]
) -> None:
    """Write ONLY the namespaced key; every other field is passed through unchanged."""
    sync = dict(state["sync"])
    sync.pop("updated_at", None)
    meta = dict(sync.get("metadata") or {})
    meta[STATE_KEY] = inc
    sync["metadata"] = meta
    store.upsert_sync_state(sync)
    state["sync"] = {**state["sync"], "metadata": meta}


def _fetch_page(
    provider: Any, provider_id: int, *, floor: str, cursor: str | None
) -> tuple[list[dict[str, Any]], bool, str | None]:
    payload = provider.ebay_sold_page(
        provider_id, graded=None, since=floor, sort="date_desc", limit=PAGE_SIZE, cursor=cursor
    )
    data = payload.get("data") or []
    if not isinstance(data, list):
        raise PkmnPricesAPIError(200, "invalid_payload", "sold data is not an array")
    page = payload.get("pagination") or {}
    has_more = bool(page.get("has_more"))
    next_value = page.get("next_cursor")
    next_cursor = str(next_value) if next_value else None
    if has_more and (not next_cursor or next_cursor == cursor):
        raise PkmnPricesAPIError(200, "invalid_pagination", "sold pagination cursor did not advance")
    return [dict(row) for row in data if isinstance(row, dict)], has_more, next_cursor


def _run_card_page(
    *, provider: Any, store: Any, ctx: dict[str, Any], run_id: str, totals: Counter[str]
) -> None:
    """Fetch and persist exactly one page for a card; update ctx['status']."""
    state, target = ctx["state"], ctx["state"]["target"]
    provider_id = int(state["identity"]["provider_card_id"])
    before = provider.credits_charged
    raw_rows, has_more, next_cursor = _fetch_page(
        provider, provider_id, floor=ctx["floor"], cursor=ctx["cursor"]
    )
    collected_at = datetime.now(timezone.utc).isoformat()
    normalized = [_normalize(raw, target, provider_id, run_id, collected_at) for raw in raw_rows]
    inserted, duplicates, drifts = store.insert_evidence(normalized)
    ingested = [str(r["ingested_at"]) for r in normalized if r.get("ingested_at")]
    ctx["head"] = _max_ts(ctx["head"], *ingested)
    floor_ts = _ts(ctx["floor"])
    ctx["pages"] += 1
    ctx["rows"] += len(normalized)
    ctx["inserted"] += inserted
    ctx["credits"] += provider.credits_charged - before
    ctx["has_more"] = has_more
    ctx["cursor"] = next_cursor if has_more else None
    totals.update({"rows_seen": len(normalized), "rows_inserted": inserted,
                   "duplicates": duplicates, "provider_metadata_drifts": drifts})
    ctx["drifts"] += drifts
    ctx["full_page_all_newer"] = bool(
        has_more and len(raw_rows) >= PAGE_SIZE
        and len(ingested) == len(raw_rows)
        and all((t := _ts(i)) is not None and floor_ts is not None and t > floor_ts for i in ingested)
    )
    # Provider honoured `since` iff nothing at/older than the floor comes back.
    if floor_ts is None or any((t := _ts(i)) is None or t <= floor_ts for i in ingested):
        ctx["since_not_honoured"] = True


def _finish_card(store: Any, ctx: dict[str, Any], run_id: str, today: str) -> dict[str, Any]:
    state = ctx["state"]
    inc = increment_state(state["sync"])
    exhausted = (not ctx["has_more"]) and not ctx.get("since_not_honoured")
    base = {
        "last_run_id": run_id,
        "last_run_date": today,
        "last_pages": ctx["pages"],
        "last_rows_seen": ctx["rows"],
        "last_rows_inserted": ctx["inserted"],
    }
    if exhausted:
        new_frontier = _max_ts(ctx["floor"], ctx["head"])
        inc.update({**base, "frontier_ingested_at": new_frontier, "open_gap": None})
        outcome = "FRONTIER_REACHED"
    else:
        inc.update({
            **base,
            # Frontier deliberately unchanged: the unfetched span stays addressable.
            "frontier_ingested_at": inc.get("frontier_ingested_at") or ctx["origin_frontier"],
            "open_gap": {
                "floor_ingested_at": ctx["floor"],
                "head_ingested_at": ctx["head"],
                "resume_cursor": ctx["cursor"],
                "opened_on": (ctx["gap_opened_on"] or today),
                "reason": (
                    ctx.get("forced_gap_reason")
                    or ("SINCE_FILTER_NOT_HONOURED" if ctx.get("since_not_honoured") else "BOUNDED_OVERFLOW")
                ),
            },
        })
        outcome = "GAP_OPEN_" + inc["open_gap"]["reason"]
    _save_state(store, state, inc)
    return {
        "canonical_card_id": state["target"]["canonical_card_id"],
        "provider_card_id": int(state["identity"]["provider_card_id"]),
        "outcome": outcome, "pages": ctx["pages"], "rows_seen": ctx["rows"],
        "rows_inserted": ctx["inserted"], "credits": ctx["credits"],
        "metadata_drifts": ctx["drifts"], "overflow": ctx["pages"] > 1,
        "frontier_before": ctx["origin_frontier"], "frontier_after": inc["frontier_ingested_at"],
    }


def run_increment(
    *,
    db: Any,
    provider: Any,
    store: Any | None = None,
    expected_date: str,
    credit_cap: int = DAILY_INCREMENT_CREDIT_CAP,
    states: list[dict[str, Any]] | None = None,
    pause_check: Any = None,
) -> dict[str, Any]:
    if not ACTIVATION_ENABLED:
        raise IncrementDormant("CORE_PANEL_DAILY_INCREMENT_DORMANT: activation is not enabled in this release")
    contract = budget_contract()
    credit_day = provider_credit_day_utc()
    provider_daily_credit_exhausted = _provider_daily_credit_exhausted_today(db, credit_day)
    budget = invocation_budget(_credits_used_today_by_mode(db, credit_day), credit_cap)
    if provider_daily_credit_exhausted:
        budget["invocation_credit_cap"] = 0
    cap = budget["invocation_credit_cap"]
    pause_check = pause_check or operational_pause_reason
    pause = pause_check(db)
    if pause or cap <= 0:
        reason = (
            (pause or {}).get("reason")
            or (PROVIDER_DAILY_CREDIT_HALT if provider_daily_credit_exhausted else "INCREMENT_DAILY_BUDGET_EXHAUSTED")
        )
        return {"status": "BLOCKED", "reason": reason,
                "invocation_budget": budget, "provider_daily_credit_exhausted": provider_daily_credit_exhausted,
                "provider_credits_used": 0, "database_writes": 0}

    store = store or PkmnPricesStore(db)
    states = states if states is not None else panel_states(db)
    skipped: Counter[str] = Counter()
    contexts: list[dict[str, Any]] = []
    for state in order_cards(states):
        ok, reason = card_eligibility(state)
        if not ok:
            skipped[reason] += 1
            continue
        inc = increment_state(state["sync"])
        gap = inc.get("open_gap") or {}
        if inc.get("last_run_date") == expected_date and not gap:
            skipped["ALREADY_CURRENT_TODAY"] += 1
            continue
        origin, _ = frontier_of(state["sync"])
        contexts.append({
            "state": state, "origin_frontier": origin,
            "floor": str(gap.get("floor_ingested_at") or origin),
            "head": gap.get("head_ingested_at"), "cursor": gap.get("resume_cursor"),
            "gap_opened_on": gap.get("opened_on"),
            "pages": 0, "rows": 0, "inserted": 0, "credits": 0, "drifts": 0,
            "has_more": True, "needs_more": True, "done": False,
        })

    run_id = str(uuid.uuid4())
    store.create_run({
        "run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
        "status": "RUNNING", "selector_version": SELECTOR_VERSION, "collector_version": COLLECTOR_VERSION,
        "target_count": len(contexts), "item_credit_cap": cap, "api_request_count": 0, "credits_used": 0,
        "provider_card_lookup_count": 0, "sold_item_count": 0, "exact_attribution_count": 0,
        "fair_value_signal_eligible_count": 0, "set_value_nm_eligible_count": 0,
        "manifest_fingerprint": PANEL_FINGERPRINT,
        "metadata": {"mode": MODE, "panel_fingerprint": PANEL_FINGERPRINT, "expected_date": expected_date,
                     "budget_contract": contract, "invocation_budget": budget,
                     "provider_credit_day_utc": credit_day, "identity_lookups_allowed": False},
    })

    totals: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    receipts: dict[str, dict[str, Any]] = {}
    halted = ""

    def can_spend() -> bool:
        return provider.credits_charged + PAGE_SIZE <= cap

    def step(ctx: dict[str, Any]) -> bool:
        """One page for one card. Returns False when the run must stop."""
        nonlocal halted
        if not can_spend():
            halted = "BUDGET_EXHAUSTED"
            return False
        if pause_check(db):
            halted = "OPERATIONAL_PAUSE"
            return False
        if provider.credits_limit not in (None, ACCOUNT_DAILY_CREDIT_LIMIT):
            halted = "ACCOUNT_CREDIT_LIMIT_MISMATCH"
            return False
        try:
            _run_card_page(provider=provider, store=store, ctx=ctx, run_id=run_id, totals=totals)
        except Exception as exc:  # fail closed: preserve already-fetched spans; never skip silently
            failures.append({"canonical_card_id": ctx["state"]["target"]["canonical_card_id"],
                             "code": type(exc).__name__, "message": str(exc)[:300]})
            ctx["has_more"] = True
            ctx["since_not_honoured"] = ctx.get("since_not_honoured", False)
            ctx["failed"] = True
            ctx["done"] = True
            if (
                isinstance(exc, PkmnPricesAPIError)
                and exc.status == 429
                and exc.code == "credit_limit_exceeded"
            ):
                halted = PROVIDER_DAILY_CREDIT_HALT
                ctx["forced_gap_reason"] = PROVIDER_DAILY_CREDIT_HALT
                return False
        return True

    # Pass 1: one mandatory page per card (open gaps first by ordering).
    for ctx in contexts:
        if not step(ctx):
            break
    # Pass 2: bounded overflow for cards whose newest page was entirely newer.
    if not halted:
        while True:
            pending = [c for c in contexts if not c["done"] and c["has_more"]
                       and c["pages"] < MAX_PAGES_PER_CARD_DAY and not c.get("since_not_honoured")]
            if not pending:
                break
            progressed = False
            for ctx in pending:
                if not step(ctx):
                    break
                progressed = True
            if halted or not progressed:
                break

    for ctx in contexts:
        if ctx["pages"] == 0:
            continue  # never fetched (budget/pause) -> state untouched, gap logic unaffected
        receipt = _finish_card(store, ctx, run_id, expected_date)
        receipts[receipt["canonical_card_id"]] = receipt
    unvisited = [c["state"]["target"]["canonical_card_id"] for c in contexts if c["pages"] == 0]

    outcomes = Counter(r["outcome"] for r in receipts.values())
    status = "PARTIAL" if failures or halted or unvisited else "COMPLETE"
    store.update_run(run_id, {
        "finished_at": datetime.now(timezone.utc).isoformat(), "status": status,
        "api_request_count": provider.request_attempt_count, "credits_used": provider.credits_charged,
        "provider_card_lookup_count": 0, "sold_item_count": totals["rows_seen"],
        "exact_attribution_count": 0, "fair_value_signal_eligible_count": 0,
        "set_value_nm_eligible_count": 0, "error_code": failures[0]["code"] if failures else None,
        "metadata": {"mode": MODE, "panel_fingerprint": PANEL_FINGERPRINT, "expected_date": expected_date,
                     "budget_contract": contract, "invocation_budget": budget, "halted_reason": halted or None,
                     "provider_daily_credit_exhausted": halted == PROVIDER_DAILY_CREDIT_HALT,
                     "provider_credit_day_utc": credit_day, "identity_lookups_allowed": False,
                     "outcomes": dict(outcomes), "skipped": dict(skipped), "unvisited_cards": unvisited,
                     "overflow_cards": sum(r["overflow"] for r in receipts.values()),
                     "open_gap_cards": sum(o.startswith("GAP_OPEN") for o in outcomes.elements()),
                     "provider_metadata_drifts": totals["provider_metadata_drifts"],
                     "provider_credits_limit": provider.credits_limit,
                     "receipts": list(receipts.values()), "failures": failures},
    })
    return {"status": status, "run_id": run_id, "credits_used": provider.credits_charged,
            "invocation_credit_cap": cap, "halted_reason": halted or None, "outcomes": dict(outcomes),
            "unvisited_cards": len(unvisited), "skipped": dict(skipped), "failures": failures,
            "provider_metadata_drifts": totals["provider_metadata_drifts"],
            "rows_inserted": totals["rows_inserted"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-date", default=phoenix_date())
    parser.add_argument("--credit-cap", type=int, default=DAILY_INCREMENT_CREDIT_CAP)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    if args.commit and not ACTIVATION_ENABLED:
        # Refuse BEFORE touching credentials, the database, or the provider.
        print(json.dumps({"status": "DORMANT", "reason": "CORE_PANEL_DAILY_INCREMENT_DORMANT",
                          "provider_requests": 0, "provider_credits_used": 0, "database_writes": 0}))
        return 78

    from backend.db.clients.supabase_client import create_service_role_client

    db = create_service_role_client()
    if args.preflight:
        result = preflight(db, expected_date=args.expected_date, credit_cap=args.credit_cap)
    else:
        from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials

        credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
        result = run_increment(
            db=db, provider=PkmnPricesClient(credentials.api_key, min_request_interval=0.55),
            expected_date=args.expected_date, credit_cap=args.credit_cap,
        )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] in {"PREFLIGHT_OK", "COMPLETE"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
