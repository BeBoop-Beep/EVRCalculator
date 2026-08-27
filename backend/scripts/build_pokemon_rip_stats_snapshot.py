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
    m=built["metrics"]; economics=built["payload"]["openingEconomics"]; global_metrics=economics["global"]
    return {"marketDate":market_date,"eligibleSetCount":economics["population"]["setCount"],
        "eligibleProductCount":economics["population"]["productSkuCount"],"productFamilyCount":economics["population"]["productFamilyCount"],
        "exactArtifactSetCount":m["setCount"], "sourceRunFingerprint":built["snapshot"]["source_run_fingerprint"],
        **{key:global_metrics[key] for key in ("averageCostPerPack","averageModelBreakEvenPerPack","modeledReturnOnSpend",
            "meanOutcomeRetention","averageEntertainmentCostPerPack","entertainmentCostShare","typicalOpeningPerPack",
            "typicalRetention","chanceToRecoverCost","valuePerPackPercentiles","normalizedReturnPercentiles")},
        "eraCount":len(economics["eras"]),
        "eras":[{"eraName":era["eraName"],"setCount":era["setCount"],
                 "modeledReturnOnSpend":era["modeledReturnOnSpend"],
                 "productSkuCount":era["productSkuCount"], "typicalOpeningPerPack":era["typicalOpeningPerPack"],
                 "typicalRetention":era["typicalRetention"], "averageEntertainmentCostPerPack":era["averageEntertainmentCostPerPack"],
                 "valuePerPackPercentiles":era["valuePerPackPercentiles"],
                 "normalizedReturnPercentiles":era["normalizedReturnPercentiles"]} for era in economics["eras"]],
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
