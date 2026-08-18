from __future__ import annotations
import argparse, json, sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0, str(REPO_ROOT))
from backend.db.services.pokemon_rip_stats_service import build_pokemon_rip_stats_snapshot, publish_pokemon_rip_stats_snapshot
from backend.db.services.publication_gate import add_publication_gate_args, enforce_cli_publication_gate
from backend.scripts.pokemon_snapshot_builders import get_client

def parser():
    p=argparse.ArgumentParser(description="Build exact equal-set Pokemon RIP Stats")
    m=p.add_mutually_exclusive_group(required=True); m.add_argument("--dry-run",action="store_true"); m.add_argument("--commit",action="store_true")
    add_publication_gate_args(p); return p

def build(client, *, market_date, commit):
    built=build_pokemon_rip_stats_snapshot(client,market_date=market_date)
    snapshot_id=publish_pokemon_rip_stats_snapshot(client,built) if commit else None
    m=built["metrics"]
    return {"marketDate":market_date,"eligibleSetCount":m["setCount"],"exactArtifactSetCount":m["setCount"],
        "outcomeCountPerSet":m["outcomeCountPerSet"],"totalSourceOutcomeCount":m["totalSourceOutcomeCount"],
        "sourceRunFingerprint":built["snapshot"]["source_run_fingerprint"],"meanPackCost":m["meanPackCost"],
        "expectedValue":m["expectedValue"],"expectedRetention":m["expectedRetention"],"typicalOpeningValue":m["typicalOpeningValue"],
        "typicalRetention":m["typicalRetention"],"chanceToBeatCost":m["chanceToBeatCost"],"p95Value":m["p95Value"],
        "p99Value":m["p99Value"],"expectedEntertainmentCost":m["expectedEntertainmentCost"],
        "publicationStatus":"published" if commit else "validated","snapshotId":snapshot_id,"errors":[]}

def main():
    args=parser().parse_args(); client=get_client(); gate=enforce_cli_publication_gate(client,commit=args.commit,market_date=args.market_date,override=args.force_publish,entry_point="Pokemon RIP Stats")
    if not gate.proceed: raise SystemExit(gate.exit_code)
    day=str(args.market_date or gate.decision.market_date or "")[:10]
    if not day: raise SystemExit("A promoted --market-date is required")
    try: result=build(client,market_date=day,commit=args.commit)
    except Exception as exc: print(json.dumps({"publicationStatus":"blocked","errors":[str(exc)]},sort_keys=True)); raise SystemExit(1) from exc
    print(json.dumps(result,indent=2,sort_keys=True))
if __name__=="__main__": main()
