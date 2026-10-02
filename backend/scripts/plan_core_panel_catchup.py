"""Zero-credit, read-only catch-up debt planner for the 207-card Core Panel.

READ-ONLY. No provider call, no credentials loaded, no database write, no watermark
advanced, no B4/B5 state touched. The only database handle is the harness
``ReadOnlyClient`` (select-only). ``since`` semantics are not live-verified, so this is a
PLANNER: it never asserts a gap is recoverable.

Per card it reports the B4 completion state, the stored frontier, the latest persisted
provider observation and sale date, the potential catch-up interval between B4 completion
and the intended activation date, a velocity-based estimate of how many newer rows may be
waiting, and a state:

  BLOCKED                  not eligible for the dormant collector (identity/backfill/frontier)
  POTENTIAL_OVERFLOW       conservative estimate exceeds one newest page
  NEEDS_CANARY_SEMANTICS   fits in one page on paper, but `since`/billing semantics are unverified
  READY                    only reachable once SINCE_SEMANTICS_VERIFIED is True (a reviewed change
                           after the canary); it is False in this release, so READY is never emitted
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts import run_core_panel_daily_increment as inc  # noqa: E402
from backend.scripts import run_index_fair_value_sold_clearing_anchor_v1 as s2  # noqa: E402

PLANNER_VERSION = "core_panel_catchup_planner_v1"
#: Flipped only by a reviewed change after the live canary verifies `since` and billing.
SINCE_SEMANTICS_VERIFIED = False
VELOCITY_WINDOW_DAYS = 30
OVERFLOW_SAFETY_FACTOR = 2.0
OUT_DIR = ROOT / "backend/artifacts/index_fair_value/shadow_s3"


def _ts(value: Any) -> datetime | None:
    return inc._ts(value)


def plan_card(
    state: Mapping[str, Any],
    persisted: Mapping[str, Any],
    *,
    intended_activation: date,
) -> dict[str, Any]:
    """Pure: one card's plan from already-read facts."""
    sync = state.get("sync")
    meta = dict((sync or {}).get("metadata") or {})
    eligible, reason = inc.card_eligibility(dict(state))
    frontier, frontier_source = inc.frontier_of(sync)
    frontier_ts = _ts(frontier)
    interval_days = (
        max(0.0, (datetime.combine(intended_activation, datetime.min.time(), tzinfo=timezone.utc) - frontier_ts)
            .total_seconds() / 86400.0)
        if frontier_ts else None
    )
    recent = int(persisted.get("rows_ingested_in_velocity_window") or 0)
    per_day = recent / VELOCITY_WINDOW_DAYS
    expected = per_day * interval_days if interval_days is not None else None
    conservative = expected * OVERFLOW_SAFETY_FACTOR if expected is not None else None
    pages = math.ceil(conservative / inc.PAGE_SIZE) if conservative is not None else None
    if not eligible:
        status = "BLOCKED"
    elif conservative is not None and conservative > inc.PAGE_SIZE:
        status = "POTENTIAL_OVERFLOW"
    elif not SINCE_SEMANTICS_VERIFIED:
        status = "NEEDS_CANARY_SEMANTICS"
    else:
        status = "READY"
    return {
        "canonical_card_id": state["target"]["canonical_card_id"],
        "provider_card_id": (state.get("identity") or {}).get("provider_card_id"),
        "state": status,
        "block_reason": None if eligible else reason,
        "b4_sync_status": (sync or {}).get("status"),
        "b4_backfill_complete": meta.get("core_panel_backfill_complete"),
        "b4_phase1_ready": bool(state.get("phase1_ready")),
        "b4_phase1_ready_reason": meta.get("phase1_ready_reason"),
        "frontier_ingested_at": frontier,
        "frontier_source": frontier_source,
        "open_gap": bool(inc.increment_state(sync).get("open_gap")),
        "latest_persisted_ingested_at": persisted.get("latest_ingested_at"),
        "latest_persisted_sold_at": persisted.get("latest_sold_at"),
        "frontier_batch_rows": int(persisted.get("frontier_batch_rows") or 0),
        "frontier_batch_graded_rows": int(persisted.get("frontier_batch_graded_rows") or 0),
        "frontier_batch_ungraded_rows": int(persisted.get("frontier_batch_ungraded_rows") or 0),
        "canary_probe_since": persisted.get("canary_probe_since"),
        "catchup_interval_days": None if interval_days is None else round(interval_days, 3),
        "rows_ingested_in_velocity_window": recent,
        "estimated_new_rows": None if expected is None else round(expected, 2),
        "conservative_new_rows": None if conservative is None else round(conservative, 2),
        "likely_needs_more_than_one_page": bool(conservative is not None and conservative > inc.PAGE_SIZE),
        "estimated_pages_conservative": pages,
        "estimated_days_to_clear_at_page_cap": (
            None if pages is None else math.ceil(pages / inc.MAX_PAGES_PER_CARD_DAY)),
    }


def summarize(cards: list[dict[str, Any]]) -> dict[str, Any]:
    states = Counter(c["state"] for c in cards)
    blocks = Counter(c["block_reason"] for c in cards if c["block_reason"])
    credits = sum(
        min(max(c["estimated_pages_conservative"] or 1, 1), inc.MAX_PAGES_PER_CARD_DAY) * inc.PAGE_SIZE
        for c in cards if c["state"] != "BLOCKED")
    return {
        "cards": len(cards), "states": dict(sorted(states.items())), "block_reasons": dict(sorted(blocks.items())),
        "first_day_credit_ceiling_if_activated": min(credits, inc.DAILY_INCREMENT_CREDIT_CAP),
        "first_day_credit_demand_uncapped": credits,
        "max_days_to_clear_any_card": max((c["estimated_days_to_clear_at_page_cap"] or 0 for c in cards), default=0),
        "since_semantics_verified": SINCE_SEMANTICS_VERIFIED,
        "ready_is_unreachable_until_canary": True,
    }


# ---------------------------------------------------------------- read-only I/O
def fetch_states(db: Any, panel: Mapping[str, Any]) -> list[dict[str, Any]]:
    ids = sorted(str(r["canonical_card_id"]) for r in panel["rows"])
    identities: dict[str, dict[str, Any]] = {}
    for i in range(0, len(ids), 50):
        for row in s2._paged(lambda c=ids[i:i + 50]: db.table("pkmnprices_card_identity_v1")
                             .select("provider_card_id,canonical_card_id,tcgplayer_product_id,language")
                             .in_("canonical_card_id", c).eq("language", "English").order("provider_card_id")):
            identities[str(row["canonical_card_id"])] = row
    provider_ids = sorted(int(v["provider_card_id"]) for v in identities.values())
    sync: dict[int, dict[str, Any]] = {}
    for i in range(0, len(provider_ids), 50):
        for row in s2._paged(lambda c=provider_ids[i:i + 50]: db.table("pkmnprices_sold_sync_state_v1")
                             .select("provider_card_id,canonical_card_id,last_ingested_at,last_sold_at,status,"
                                     "rows_seen,rows_inserted,consecutive_failures,last_error_code,metadata")
                             .in_("provider_card_id", c).order("provider_card_id")):
            sync[int(row["provider_card_id"])] = row
    states = []
    for index, target in enumerate(sorted(panel["rows"], key=lambda r: str(r["canonical_card_id"]))):
        ident = identities.get(str(target["canonical_card_id"]))
        row = sync.get(int(ident["provider_card_id"])) if ident else None
        meta = dict((row or {}).get("metadata") or {})
        states.append({"target": target, "identity": ident, "sync": row, "panel_index": index,
                       "phase1_ready": bool(meta.get("phase1_ready"))})
    return states


def fetch_persisted(db: Any, state: Mapping[str, Any]) -> dict[str, Any]:
    ident = state.get("identity")
    if not ident:
        return {}
    pid = int(ident["provider_card_id"])
    latest = (db.table("pkmnprices_ebay_sold_evidence_v1")
              .select("provider_listing_id,ingested_at,sold_at,graded,grader,grade")
              .eq("provider_card_id", pid).order("ingested_at", desc=True).limit(inc.PAGE_SIZE).execute().data or [])
    latest_sold = (db.table("pkmnprices_ebay_sold_evidence_v1").select("sold_at")
                   .eq("provider_card_id", pid).order("sold_at", desc=True).limit(1).execute().data or [])
    frontier, _ = inc.frontier_of(state.get("sync"))
    frontier_ts = _ts(frontier)
    recent = 0
    frontier_batch: list[dict[str, Any]] = []
    if frontier_ts:
        frontier_batch = [dict(row) for row in latest if _ts(row.get("ingested_at")) == frontier_ts]
        start = (frontier_ts - timedelta(days=VELOCITY_WINDOW_DAYS)).isoformat()
        res = (db.table("pkmnprices_ebay_sold_evidence_v1").select("provider_listing_id", count="exact")
               .eq("provider_card_id", pid).gte("ingested_at", start).lte("ingested_at", frontier_ts.isoformat())
               .limit(1).execute())
        recent = int(getattr(res, "count", 0) or 0)
    graded = sum(1 for row in frontier_batch if row.get("graded") is True or row.get("grader") or row.get("grade"))
    ungraded = len(frontier_batch) - graded
    probe_since = None
    if frontier_ts and 0 < len(frontier_batch) < inc.PAGE_SIZE:
        # Semantic probe only: one microsecond before the immutable operational frontier.
        # This should replay the known frontier batch iff provider `since` is ingestion-time based.
        probe_since = (frontier_ts - timedelta(microseconds=1)).isoformat().replace("+00:00", "Z")
    return {
        "latest_ingested_at": (latest[0]["ingested_at"] if latest else None),
        "latest_sold_at": (latest_sold[0]["sold_at"] if latest_sold else None),
        "rows_ingested_in_velocity_window": recent,
        "frontier_batch_rows": len(frontier_batch),
        "frontier_batch_graded_rows": graded,
        "frontier_batch_ungraded_rows": ungraded,
        "canary_probe_since": probe_since,
    }


def build_plan(db: Any, *, intended_activation: date) -> dict[str, Any]:
    panel = s2.load_panel()
    states = fetch_states(db, panel)
    cards = [plan_card(s, fetch_persisted(db, s), intended_activation=intended_activation) for s in states]
    return {
        "planner_version": PLANNER_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "intended_activation_date": intended_activation.isoformat(),
        "panel_fingerprint": panel["panel_fingerprint"],
        "summary": summarize(cards),
        "cards": cards,
        "read_select_requests": len(getattr(db, "read_requests", [])),
        "provider_calls": 0, "provider_credits_used": 0, "database_writes": 0,
        "caveat": "Planner only. `since` semantics are not live-verified; no gap is asserted recoverable.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--intended-activation-date", type=date.fromisoformat, required=True)
    parser.add_argument("--out", type=Path, default=OUT_DIR / "catchup_debt_plan.json")
    args = parser.parse_args(argv)
    plan = build_plan(s2.make_read_only_client(args.env_file), intended_activation=args.intended_activation_date)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({**plan["summary"], "select_requests": plan["read_select_requests"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
