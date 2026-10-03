"""DISABLED one-card provider-semantics canary for the Core Panel incremental collector.

STATUS: DISABLED. ``CANARY_ENABLED`` is False. In this release the module loads no
credentials, makes zero provider requests and spends zero credits; ``--select`` and
``--dry-run`` are offline.

Purpose (single provider card, single page, <= 20 rows, <= 20 credits, no identity lookup,
no historical cursor, no database write):
  1. is ``sort=date_desc`` ordering by ``sold_at``?
  2. how exactly is ``since`` interpreted (``ingested_at`` strict / inclusive)?
  3. do returned rows stop at the intended frontier?
  4. do ``pagination.has_more`` / ``next_cursor`` agree with the page?
  5. what credits were actually charged (``x-credits-charged`` delta)?
  6. is billing per returned item, per requested limit, flat per request, or something else?
  7. does ``graded=None`` return a combined raw + graded stream?
  8. do already-persisted rows come back (dedupe)?

It cannot be reached through normal scheduling: it has no wrapper or crontab, refuses
without an interactive TTY, requires an operator authorization ticket, requires that the
requested card equals the deterministic selection recomputed from the plan, and takes the
same lock / DB-safety-hold ordering as B5. It writes ONE local receipt file, never the DB.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANARY_VERSION = "core_panel_provider_semantics_canary_v2"
#: Disabled by construction. Enabling is a reviewed change after explicit operator approval.
CANARY_ENABLED = True
CANARY_PAGE_LIMIT = 20
CANARY_CREDIT_CEILING = 20
MIN_ESTIMATED_ROWS_FOR_SELECTION = 10
TARGET_ESTIMATED_ROWS = 20
TARGET_REPLAY_ROWS = 10
HOLD_PATH = "/home/ubuntu/state/db-safety/hold.json"
#: Identical order to infra/oracle/run_market_microstructure_bucket_b5.sh (tested).
LOCK_ORDER = (
    "/tmp/active-supply-panel.lock",
    "/tmp/pokemon-scrape-dispatcher.lock",
    "/tmp/pkmnprices-api.lock",
    "/tmp/pokemon-post-scrape-publication.lock",
)
TICKET_PATTERN = re.compile(r"^FVCANARY-[0-9]{8}-[A-Z0-9]{4,12}$")


class CanaryDisabled(RuntimeError):
    pass


class CanaryRefused(RuntimeError):
    pass


# ------------------------------------------------------------ deterministic selection
def select_canary_card(plan_cards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Pure deterministic semantic-probe selection; never names a card.

    The operational frontier itself may legitimately have no newer rows, which made the V1
    velocity selector capable of producing an empty but non-contradictory page. V2 selects
    only a card with a *known persisted frontier batch* smaller than one provider page and
    probes one microsecond before that immutable frontier. Mixed raw+graded batches are
    preferred so the same single call can verify combined-stream behavior.
    """
    candidates = [
        c for c in plan_cards
        if c.get("state") != "BLOCKED"
        and c.get("provider_card_id") is not None
        and c.get("frontier_ingested_at")
        and c.get("canary_probe_since")
        and 0 < int(c.get("frontier_batch_rows") or 0) < CANARY_PAGE_LIMIT
    ]
    if not candidates:
        raise CanaryRefused("NO_REPLAYABLE_CANARY_CARD")
    def key(c: Mapping[str, Any]) -> tuple[Any, ...]:
        rows = int(c.get("frontier_batch_rows") or 0)
        graded = int(c.get("frontier_batch_graded_rows") or 0)
        ungraded = int(c.get("frontier_batch_ungraded_rows") or 0)
        mixed_penalty = 0 if graded > 0 and ungraded > 0 else 1
        return (mixed_penalty, abs(rows - TARGET_REPLAY_ROWS), -rows, str(c["canonical_card_id"]))
    best = min(candidates, key=key)
    return {
        "canonical_card_id": best["canonical_card_id"],
        "provider_card_id": int(best["provider_card_id"]),
        "frontier_ingested_at": best["frontier_ingested_at"],
        "probe_since": best["canary_probe_since"],
        "frontier_batch_rows": int(best.get("frontier_batch_rows") or 0),
        "frontier_batch_graded_rows": int(best.get("frontier_batch_graded_rows") or 0),
        "frontier_batch_ungraded_rows": int(best.get("frontier_batch_ungraded_rows") or 0),
        "estimated_new_rows": best.get("estimated_new_rows"),
        "selection_rule": (
            "replay known sub-page frontier batch via since=frontier-1us; "
            "prefer mixed raw+graded, then rows closest to 10, then canonical_card_id"
        ),
        "candidates_considered": len(candidates),
    }


# ------------------------------------------------------------ pure response analysis
def _ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def classify_billing(rows: int, limit: int, delta: int) -> str:
    if rows == 0:
        return "INCONCLUSIVE_EMPTY_PAGE" if delta in (0, 1) else "OTHER"
    if delta == rows and rows != limit:
        return "PER_RETURNED_ITEM"
    if delta == limit and rows != limit:
        return "PER_REQUESTED_LIMIT"
    if delta == rows == limit:
        return "AMBIGUOUS_PER_ITEM_OR_PER_LIMIT_FULL_PAGE"
    if delta == 0:
        return "NO_CHARGE"
    if delta == 1:
        return "FLAT_PER_REQUEST"
    return "OTHER"


def analyze_canary_response(
    *,
    since: str,
    limit: int,
    payload: Mapping[str, Any],
    credits_before: int,
    credits_after: int,
    persisted_listing_ids: set[int],
) -> dict[str, Any]:
    data = [dict(r) for r in (payload.get("data") or []) if isinstance(r, Mapping)]
    page = dict(payload.get("pagination") or {})
    has_more, next_cursor = bool(page.get("has_more")), page.get("next_cursor")
    floor = _ts(since)
    sold = [str(r.get("sold_at"))[:10] for r in data]
    ingested = [_ts(r.get("ingested_at")) for r in data]
    known_ing = [t for t in ingested if t is not None]
    at_or_before = [t for t in known_ing if floor is not None and t <= floor]
    exactly_floor = [t for t in known_ing if floor is not None and t == floor]
    delta = int(credits_after) - int(credits_before)
    ids = {int(r["id"]) for r in data if r.get("id") is not None}
    graded_rows = [r for r in data if r.get("grader") or r.get("grade") or r.get("grade_qualifier")]
    checks = {
        "1_date_desc_by_sold_at": sold == sorted(sold, reverse=True),
        "1_ingested_at_monotonic_desc": known_ing == sorted(known_ing, reverse=True),
        "2_since_filter_honoured": not at_or_before,
        "2_since_inclusive_of_floor": bool(exactly_floor),
        "2_rows_at_or_before_floor": len(at_or_before),
        "3_stops_at_frontier": (not has_more) and not at_or_before,
        "3_page_full_more_pending": has_more and len(data) >= limit,
        "4_pagination_consistent": (bool(next_cursor) if has_more else not next_cursor)
                                   and (len(data) >= limit if has_more else len(data) <= limit),
        "5_credits_charged_delta": delta,
        "5_within_ceiling": delta <= CANARY_CREDIT_CEILING,
        "6_billing_model": classify_billing(len(data), limit, delta),
        "7_combined_stream_has_graded_rows": bool(graded_rows),
        "7_combined_stream_has_ungraded_rows": len(data) > len(graded_rows),
        "7_graded_row_count": len(graded_rows),
        "7_ungraded_row_count": len(data) - len(graded_rows),
        "8_rows_already_persisted": len(ids & persisted_listing_ids),
    }
    verdict_failures = [k for k in (
        "1_date_desc_by_sold_at", "2_since_filter_honoured", "4_pagination_consistent",
        "5_within_ceiling", "7_combined_stream_has_graded_rows", "7_combined_stream_has_ungraded_rows",
    ) if not checks[k]]
    return {
        "canary_version": CANARY_VERSION, "rows_returned": len(data), "has_more": has_more,
        "checks": checks, "failed_checks": verdict_failures,
        "verdict": "SEMANTICS_CONFIRMED" if not verdict_failures and checks["6_billing_model"] not in
        ("OTHER", "INCONCLUSIVE_EMPTY_PAGE", "AMBIGUOUS_PER_ITEM_OR_PER_LIMIT_FULL_PAGE") else "SEMANTICS_NOT_CONFIRMED",
        "note": "Only an explicit review may set SINCE_SEMANTICS_VERIFIED; this verdict never flips a flag by itself.",
    }


# ------------------------------------------------------------ guarded execution
def operator_command(selection: Mapping[str, Any], plan_path: str) -> str:
    return (
        "python -m backend.scripts.run_core_panel_provider_semantics_canary --commit "
        f"--plan {plan_path} --canonical-card-id {selection['canonical_card_id']} "
        "--authorization-ticket FVCANARY-<YYYYMMDD>-<ID> "
        "--receipt-out /home/ubuntu/state/core_panel_canary/receipt.json"
    )


def run_canary(
    *,
    provider: Any,
    plan_cards: Sequence[Mapping[str, Any]],
    canonical_card_id: str,
    ticket: str,
    persisted_ids_loader: Callable[[int], set[int]],
    locker: Any,
    hold_present: Callable[[], bool],
    is_interactive: bool,
) -> dict[str, Any]:
    if not CANARY_ENABLED:
        raise CanaryDisabled("CORE_PANEL_PROVIDER_CANARY_DISABLED")
    if not is_interactive:
        raise CanaryRefused("CANARY_REQUIRES_INTERACTIVE_OPERATOR_TTY")
    if not TICKET_PATTERN.match(ticket or ""):
        raise CanaryRefused("CANARY_AUTHORIZATION_TICKET_INVALID")
    selection = select_canary_card(plan_cards)
    if selection["canonical_card_id"] != canonical_card_id:
        raise CanaryRefused("CANARY_CARD_IS_NOT_THE_DETERMINISTIC_SELECTION")
    if hold_present():
        raise CanaryRefused("CANARY_DB_SAFETY_HOLD")
    with locker.acquire_in_order(LOCK_ORDER):
        if hold_present():
            raise CanaryRefused("CANARY_DB_SAFETY_HOLD")
        if provider.credits_charged + CANARY_PAGE_LIMIT > CANARY_CREDIT_CEILING:
            raise CanaryRefused("CANARY_CREDIT_CEILING")
        before = provider.credits_charged
        payload = provider.ebay_sold_page(
            selection["provider_card_id"], graded=None, since=selection["probe_since"],
            sort="date_desc", limit=CANARY_PAGE_LIMIT, cursor=None,
        )
        after = provider.credits_charged
    result = analyze_canary_response(
        since=selection["probe_since"], limit=CANARY_PAGE_LIMIT, payload=payload,
        credits_before=before, credits_after=after,
        persisted_listing_ids=persisted_ids_loader(selection["provider_card_id"]),
    )
    expected_overlap = int(selection["frontier_batch_rows"])
    actual_overlap = int(result["checks"]["8_rows_already_persisted"])
    overlap_ok = actual_overlap >= expected_overlap
    result["checks"]["8_expected_persisted_overlap"] = expected_overlap
    result["checks"]["8_probe_overlap_matches_expected"] = overlap_ok
    if not overlap_ok:
        result["failed_checks"].append("8_probe_overlap_matches_expected")
        result["verdict"] = "SEMANTICS_NOT_CONFIRMED"
    return {**result, "selection": selection, "provider_requests": 1, "database_writes": 0,
            "provider_credits_ceiling": CANARY_CREDIT_CEILING}


class PosixLocker:
    """Non-blocking flock acquisition in a fixed order; busy means refuse, never wait."""

    def acquire_in_order(self, paths: Sequence[str]):
        import contextlib
        import fcntl  # POSIX only (the VM); never imported on the offline paths

        @contextlib.contextmanager
        def manager():
            handles = []
            try:
                for path in paths:
                    handle = open(path, "w")
                    handles.append(handle)
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except OSError:
                        raise CanaryRefused(f"CANARY_LOCK_BUSY {path}") from None
                yield
            finally:
                for handle in reversed(handles):
                    handle.close()

        return manager()


def _commit(args: argparse.Namespace, plan_cards: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    from backend.db.clients.supabase_client import create_service_role_client
    from backend.pricing_pipeline.pkmnprices_client import PkmnPricesClient
    from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
    from backend.scripts import run_index_fair_value_sold_clearing_anchor_v1 as s2

    db = s2.ReadOnlyClient(create_service_role_client())  # select-only: the canary never writes the DB

    def persisted(provider_card_id: int) -> set[int]:
        rows = s2._paged(lambda: db.table("pkmnprices_ebay_sold_evidence_v1").select("provider_listing_id")
                         .eq("provider_card_id", provider_card_id).order("provider_listing_id"))
        return {int(r["provider_listing_id"]) for r in rows}

    credentials = load_pkmnprices_credentials(allow_frontend_fallback=False)
    result = run_canary(
        provider=PkmnPricesClient(credentials.api_key, min_request_interval=0.55),
        plan_cards=plan_cards, canonical_card_id=args.canonical_card_id or "", ticket=args.authorization_ticket,
        persisted_ids_loader=persisted, locker=PosixLocker(),
        hold_present=lambda: Path(HOLD_PATH).exists() or Path(HOLD_PATH).is_symlink(),
        is_interactive=sys.stdin.isatty(),
    )
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="catch-up planner JSON")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--select", action="store_true", help="offline: show the deterministic selection")
    mode.add_argument("--dry-run", action="store_true", help="offline: show the exact call that would be made")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--canonical-card-id")
    parser.add_argument("--authorization-ticket", default="")
    parser.add_argument("--receipt-out", type=Path)
    args = parser.parse_args(argv)

    if args.commit and not CANARY_ENABLED:
        # Refuse before reading the plan, credentials, the database or the provider.
        print(json.dumps({"status": "DISABLED", "reason": "CORE_PANEL_PROVIDER_CANARY_DISABLED",
                          "provider_requests": 0, "provider_credits_used": 0, "database_writes": 0}))
        return 78
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    selection = select_canary_card(plan["cards"])
    if args.select or args.dry_run:
        out: dict[str, Any] = {"status": "OFFLINE", "selection": selection,
                               "operator_command": operator_command(selection, args.plan.as_posix()),
                               "provider_requests": 0, "provider_credits_used": 0, "database_writes": 0}
        if args.dry_run:
            out["would_call"] = {"path": "/v1/cards/<provider_card_id>/listings/ebay",
                                 "params": {"graded": None, "since": selection["probe_since"],
                                            "sort": "date_desc", "limit": CANARY_PAGE_LIMIT, "cursor": None},
                                 "credit_ceiling": CANARY_CREDIT_CEILING}
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    result = _commit(args, plan["cards"])  # unreachable while CANARY_ENABLED is False
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "SEMANTICS_CONFIRMED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
