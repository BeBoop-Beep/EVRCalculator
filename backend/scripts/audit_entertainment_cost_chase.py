"""Read-only validation of Entertainment Cost and chase economics on real sets.

DRY RUN ONLY. There is deliberately no `--commit` flag and no write path: this
script exists to let a human check the numbers against reality before anything
is published, and a script that can also write is a script someone will
eventually run with the wrong flag.

Usage:
    python -m backend.scripts.audit_entertainment_cost_chase --set-slug <slug> [...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _print_products(contract: Dict[str, Any]) -> None:
    print("\n  SCORED PRODUCTS")
    print(f"  {'Product':<38} {'Price':>9} {'EV':>9} {'EntCost':>9} {'/pack':>8} {'ratio':>7}")
    for product in contract.get("sealedProducts", {}).get("products", []):
        block = product.get("entertainmentCost") or {}

        def _fmt(value, width=9, places=2):
            return f"{value:>{width}.{places}f}" if isinstance(value, (int, float)) else f"{'--':>{width}}"

        print(
            f"  {str(product.get('productName'))[:38]:<38}"
            f"{_fmt(block.get('purchasePrice'))}"
            f"{_fmt(block.get('expectedValue'))}"
            f"{_fmt(block.get('entertainmentCost'))}"
            f"{_fmt(block.get('entertainmentCostPerPackEquivalent'), 8)}"
            f"{_fmt(block.get('entertainmentCostRatio'), 7, 3)}"
        )

    unsupported = contract.get("unsupportedProducts", {}).get("products", [])
    print(f"\n  UNSUPPORTED PRODUCTS ({len(unsupported)})")
    for product in unsupported:
        reason = (product.get("entertainmentCost") or {}).get("reason")
        print(f"  {str(product.get('productName'))[:48]:<48} {reason}")


def _print_chase(payload: Dict[str, Any], top_n: int) -> None:
    cards = payload.get("cards") or []
    print(
        f"\n  CHASE ECONOMICS  ({len(cards)} published of "
        f"{payload.get('eligibleCardCount')} eligible)"
    )
    deltas: List[float] = []
    # Track every published card's delta for the drift summary, not just the
    # ones printed in detail below.
    for card in cards:
        delta = card.get("targetPriceBasisDelta")
        if isinstance(delta, (int, float)):
            deltas.append(delta)

    for card in cards[:top_n]:
        delta = card.get("targetPriceBasisDelta")
        print(
            f"\n  {card.get('cardName')}  "
            f"current=${card.get('currentTargetMarketPrice')}  "
            f"evBasis=${card.get('targetValueUsedInEV')}  "
            f"delta={delta}"
        )
        print(
            f"    1 in {card.get('impliedOddsOneInN')} packs | "
            f"50%: {card.get('packsFor50PercentChance')} packs | "
            f"95%: {card.get('packsFor95PercentChance')} packs"
        )
        for product in card.get("products") or []:
            if not product.get("available"):
                print(f"    {product.get('productFamily'):<32} unavailable: {product.get('reason')}")
                continue
            print(
                f"    {str(product.get('productFamily')):<32}"
                f" spend=${product.get('grossSpend', 0) or 0:.0f}"
                f" recovery=${product.get('incidentalRecovery', 0) or 0:.0f}"
                f" acquire=${product.get('ripAcquisitionCost', 0) or 0:.0f}"
                f" premium=${product.get('entertainmentPremium', 0) or 0:.0f}"
            )

    print(
        f"\n  PRICE BASIS DRIFT summary across all {len(deltas)} published cards "
        f"with both bases present:"
    )
    print("  (current minus EV basis; positive = card appreciated since the run was priced)")
    if not deltas:
        print("  No card in this set has both price bases populated - drift cannot be assessed.")
        return

    min_delta = min(deltas)
    max_delta = max(deltas)
    mean_delta = sum(deltas) / len(deltas)
    print(f"  min={min_delta:.2f} max={max_delta:.2f} mean={mean_delta:.2f}")

    if all(delta == 0 for delta in deltas):
        print(
            "  *** WARNING: every observed delta is exactly 0.00. This is the "
            "signature of price_used not actually being read - the current-price "
            "basis and the EV-price basis have silently collapsed into one. "
            "Do not trust this set's chase economics without investigating "
            "price_used on simulation_input_cards for this run. ***"
        )


def _resolve_set_and_run(client: Any, slug: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a set slug to (set_id, current calculation_run_id).

    Reuses the repository's existing resolvers rather than writing a second
    one: ``resolve_set_row`` (the canonical slug/id lookup already used by
    every snapshot builder) for the set, and ``_current_run_id`` (already
    used by ``build_pokemon_set_chase_economics_snapshots.py``, which reads
    ``ripDecision.sourceCalculationRunId`` off the set page snapshot) for the
    run. A second run-resolution query could disagree with the page it is
    meant to describe, which is exactly the failure mode this whole decision
    layer exists to prevent.
    """
    from backend.scripts.pokemon_snapshot_builders import resolve_set_row
    from backend.scripts.build_pokemon_set_chase_economics_snapshots import _current_run_id

    try:
        set_row = resolve_set_row(client, slug)
    except ValueError:
        return None, None
    set_id = set_row.get("id")
    if set_id is None:
        return None, None
    set_id = str(set_id)
    run_id = _current_run_id(client, set_id)
    return set_id, run_id


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set-slug", action="append", required=True,
                        help="canonical set key; repeatable")
    parser.add_argument("--top", type=int, default=3,
                        help="how many chase cards to print per set")
    parser.add_argument("--json", action="store_true",
                        help="dump raw contracts instead of tables")
    args = parser.parse_args(argv)

    from backend.db.clients.supabase_client import supabase
    from backend.db.services.rip_decision_service import build_rip_decision_contract
    from backend.db.services.chase_economics_service import build_chase_economics_snapshot_row

    for slug in args.set_slug:
        print(f"\n{'=' * 78}\nSET: {slug}\n{'=' * 78}")
        set_id, run_id = _resolve_set_and_run(supabase, slug)
        if set_id is None:
            print("  set not found")
            continue
        print(f"  set_id={set_id}  calculation_run_id={run_id}")
        if run_id is None:
            print("  WARNING: no current calculation_run_id resolved for this set "
                  "(ripDecision.sourceCalculationRunId was absent). Chase economics "
                  "will publish an explicitly empty payload.")

        contract = build_rip_decision_contract(set_id=set_id, run_id=run_id, client=supabase)

        # build_chase_economics_snapshot_row returns a ROW dict whose
        # payload_json key holds the published contract - not the contract
        # itself.
        snapshot_row = build_chase_economics_snapshot_row(
            set_id=set_id, run_id=run_id, client=supabase
        )
        payload = snapshot_row["payload_json"]

        if snapshot_row.get("calculation_run_id") != payload.get("sourceCalculationRunId"):
            print(
                "  *** WARNING: snapshot row calculation_run_id "
                f"({snapshot_row.get('calculation_run_id')!r}) disagrees with "
                f"payload sourceCalculationRunId ({payload.get('sourceCalculationRunId')!r}) ***"
            )

        if args.json:
            print(json.dumps({"ripDecision": contract, "chaseEconomics": payload},
                             indent=2, allow_nan=False))
            continue

        _print_products(contract)
        _print_chase(payload, args.top)

        # The contract must be publishable as JSON, on real data, not just in
        # fixtures. This is the check that catches a real NaN.
        json.dumps(contract, allow_nan=False)
        json.dumps(payload, allow_nan=False)
        print("\n  JSON safety: OK")

    return 0


if __name__ == "__main__":
    sys.exit(main())
