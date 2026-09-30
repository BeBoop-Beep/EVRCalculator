"""Manual FMA-1 projection entry point; imports no provider client.

Production execution requires an explicitly configured repository adapter.
The default and CI-safe mode is dry-run fixture reconciliation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from backend.domain.pokemon.market_activity import (
    aggregate_group_activity, assemble_constituent_page, assemble_instrument_detail,
)
from backend.domain.pokemon.market_activity_contract import SchemaRegistry
from backend.pricing_pipeline.market_activity_projection import MarketActivityProjectionBuilder

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "docs" / "research" / "market_activity_v1" / "fixtures"
CONTRACTS = ROOT / "docs" / "research" / "market_activity_v1" / "contracts"


def reconcile_fixtures() -> dict[str, object]:
    registry = SchemaRegistry(CONTRACTS)
    assemblers = {"instrument_detail": assemble_instrument_detail,
                  "constituent_page": assemble_constituent_page,
                  "group_activity": aggregate_group_activity}
    checked = []
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["fixtures"]:
        fixture = json.loads((FIXTURES / entry["file"]).read_text(encoding="utf-8"))
        actual = assemblers[entry["assembler"]](fixture["inputs"])
        if actual != fixture["expected"]:
            raise RuntimeError(f"fixture drift: {entry['fixtureId']}")
        errors = registry.validate(actual, entry["responseSchema"])
        if errors:
            raise RuntimeError(f"schema drift: {entry['fixtureId']}: {errors[:3]}")
        checked.append(entry["fixtureId"])
    return {"mode": "dry-run", "providerCalls": 0, "productionWrites": 0,
            "fixtureCount": len(checked), "fixtures": checked}


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="reconcile accepted fixtures; no DB access")
    mode.add_argument("--plan", action="store_true", help="read real DB evidence and build an in-memory plan")
    mode.add_argument("--stage", action="store_true", help="stage a real BUILDING generation; never promotes")
    parser.add_argument("--market-key")
    parser.add_argument("--as-of")
    parser.add_argument("--generation-id")
    parser.add_argument("--evidence-cutoff")
    parser.add_argument("--resume-after-rank", type=int, default=0)
    parser.add_argument("--custom-revision-id")
    parser.add_argument("--confirm-stage", help="must equal FMA1_STAGE for --stage")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(reconcile_fixtures(), sort_keys=True)); return 0
    if not args.market_key or not args.as_of:
        parser.error("--market-key and --as-of are required for --plan/--stage")
    if args.stage and args.confirm_stage != "FMA1_STAGE":
        parser.error("--stage requires --confirm-stage FMA1_STAGE")
    # Lazy import prevents fixture dry-run from touching credentials or clients.
    from backend.db.clients.supabase_client import supabase
    from backend.db.services.market_activity_projection_repository import (
        SupabaseMarketActivitySink, SupabaseMarketActivitySource,
    )
    source = SupabaseMarketActivitySource(supabase, custom_revision_id=args.custom_revision_id)
    sink = SupabaseMarketActivitySink(supabase)
    result = MarketActivityProjectionBuilder(source, sink).build(
        args.market_key, as_of=args.as_of, evidence_cutoff=args.evidence_cutoff,
        generation_id=args.generation_id or str(uuid4()), resume_after_rank=args.resume_after_rank,
        dry_run=bool(args.plan))
    result["mode"] = "plan" if args.plan else "stage"
    result["providerCalls"] = 0
    result["promoted"] = False
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
