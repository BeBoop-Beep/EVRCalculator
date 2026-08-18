from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.services.chase_economics_service import build_chase_economics_snapshot_row
from backend.db.services.publication_gate import add_publication_gate_args, enforce_cli_publication_gate
from backend.scripts.pokemon_snapshot_builders import (
    add_target_set_args,
    get_client,
    resolve_target_sets,
    should_commit,
    upsert_row,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build dedicated Pokemon chase-economics snapshots")
    add_target_set_args(parser, include_current_authorities=True)
    add_publication_gate_args(parser)
    return parser


def _current_run_id(client, set_id: str):
    rows = (
        client.table("pokemon_set_page_snapshot_latest")
        .select("payload_json")
        .eq("set_id", set_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    payload = rows[0].get("payload_json") if rows else None
    rip_decision = payload.get("ripDecision") if isinstance(payload, dict) else None
    return rip_decision.get("sourceCalculationRunId") if isinstance(rip_decision, dict) else None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = build_parser().parse_args()
    client = get_client()
    commit = should_commit(args)
    gate = enforce_cli_publication_gate(
        client,
        commit=commit,
        market_date=args.market_date,
        override=args.force_publish,
        entry_point="chase economics snapshots",
    )
    if not gate.proceed:
        return gate.exit_code

    built = 0
    failed = 0
    for set_row in resolve_target_sets(client, args):
        set_id = str(set_row["id"])
        try:
            row = build_chase_economics_snapshot_row(
                set_id=set_id,
                run_id=_current_run_id(client, set_id),
                client=client,
            )
            upsert_row(
                client,
                "pokemon_set_chase_economics_snapshot_latest",
                row,
                on_conflict="set_id",
                commit=commit,
            )
            built += 1
        except Exception:
            failed += 1
            logging.exception("failed chase snapshot set_id=%s", set_id)

    summary = f"chase economics snapshot summary built={built} failed={failed}"
    logging.info(summary)
    print(summary)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
