"""Append exact current RIP authorities after the existing daily publication.

This command is deliberately not a scheduler.  The Windows daily publication
owns cadence; this is its final, idempotent history step.  It refreshes only
due sources, rebuilds frozen V7 from explicit run IDs, and fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.plan_collector_appeal_refresh import freshness_plan

V7 = "pokemon_collector_appeal_v7_expanded_price_blind_v1"
FROZEN_FORMULA_FINGERPRINT = "06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b"
PLAYABILITY_KEY = "playability"
CONTROL_PLAYABILITY_RUN = "9947aaf7-8647-484f-8c9c-2cec59792cdb"


@dataclass
class RefreshHooks:
    refresh_source: Any
    build_model: Any
    persist_model: Any
    build_set_pages: Any


def _paged(query_factory):
    rows, start = [], 0
    while True:
        part = query_factory().range(start, start + 999).execute().data or []
        rows.extend(part)
        if len(part) < 1000:
            return rows
        start += 1000


def build_plan(client: Any, *, as_of: date, now: datetime) -> dict[str, Any]:
    runs = _paged(lambda: client.table("pokemon_collector_source_runs").select(
        "id,source_name,status,captured_at,raw_payload_json"
    ))
    freshness = freshness_plan(runs, now)
    current = (client.table("pokemon_collector_appeal_current")
               .select("model_run_id,model_version,as_of_date")
               .eq("scope", "pokemon").single().execute().data)
    if not current or current.get("model_version") != V7:
        raise RuntimeError("current Collector authority is not frozen V7")
    model = (client.table("pokemon_collector_appeal_model_runs")
             .select("id,input_fingerprint,source_run_ids,scoring_config_json")
             .eq("id", current["model_run_id"]).single().execute().data)
    scores = _paged(lambda: client.table("pokemon_set_collector_appeal_scores").select(
        "set_id,collector_appeal_score,score_status"
    ).eq("model_run_id", current["model_run_id"]))
    set_ids = sorted(str(row["set_id"]) for row in scores)
    existing = (client.table("pokemon_rip_temporal_history").select("entity_id", count="exact")
                .eq("domain", "collector").eq("as_of_date", as_of.isoformat())
                .eq("model_version", V7).limit(0).execute().count or 0)
    return {
        "asOfDate": as_of.isoformat(), "freshness": freshness,
        "providerCallsPlanned": 0, "modelRunId": current["model_run_id"],
        "modelFingerprint": model["input_fingerprint"],
        "cohortFingerprint": hashlib.sha256(json.dumps(set_ids, separators=(",", ":")).encode()).hexdigest(),
        "rowsPlanned": len(scores),
        "scoredRows": sum(row.get("score_status") == "scored" for row in scores),
        "unavailableRows": sum(row.get("score_status") != "scored" for row in scores),
        "existingRows": existing,
        "rowsToAppend": max(0, len(scores) - existing),
        "sourceRunIds": model["source_run_ids"],
        "sourceAuthority": _authority_from_model(model),
    }


def _authority_from_model(model: Mapping[str, Any]) -> dict[str, str]:
    manifest = model.get("scoring_config_json") or {}
    explicit = manifest.get("sourceAuthority")
    if explicit:
        return {str(k):str(v) for k,v in explicit.items()}
    ids = list(model.get("source_run_ids") or [])
    if len(ids) != 6:
        raise RuntimeError("Collector model lacks six-source reproducible authority")
    return dict(zip(("pokemonTrends","trainer12m","trainer5y","playability","artist12m","artist5y"),map(str,ids)))


def validate_source_run(client: Any, source_id: str, expected_key: str) -> dict[str, Any]:
    rows = (client.table("pokemon_collector_source_run_health_v").select("*")
            .eq("source_run_id", source_id).limit(1).execute().data or [])
    if not rows or rows[0].get("usable_for_model") is not True:
        raise RuntimeError(f"{expected_key} refreshed run is not usable for model")
    row = rows[0]
    if not row.get("source_fingerprint") or not row.get("captured_at"):
        raise RuntimeError(f"{expected_key} refreshed run lacks fingerprint/observation date")
    source=(client.table("pokemon_collector_source_runs").select(
        "id,source_name,capture_version,status,captured_at,raw_payload_json")
        .eq("id",source_id).single().execute().data)
    expected={"pokemon_trends":("google_trends_pokemon_v2","capture_pokemon_trends_anchor_ladder_v2_r1",None),
        "trainer_12m":("google_trends_trainer","collector_trends_anchor_v1","today 12-m"),
        "trainer_5y":("google_trends_trainer","collector_trends_anchor_v1","today 5-y"),
        "artist_12m":("google_trends_artist","collector_trends_anchor_v1","today 12-m"),
        "artist_5y":("google_trends_artist","collector_trends_anchor_v1","today 5-y")}[expected_key]
    payload=source.get("raw_payload_json") or {}
    if (source.get("source_name"),source.get("capture_version")) != expected[:2] or (
            expected[2] is not None and payload.get("timeframe") != expected[2]):
        raise RuntimeError(f"{expected_key} refreshed run violates query/version contract")
    if any(key in json.dumps(payload).casefold() for key in ('"price"','"market_price"')):
        raise RuntimeError(f"{expected_key} source unexpectedly contains price input")
    return row


def delta_report(previous: Sequence[Mapping[str,Any]], built: Mapping[str,Any],
                 previous_cards: Sequence[Mapping[str,Any]] = ()) -> dict[str,Any]:
    old={str(x["set_id"]):x for x in previous}; new={str(x["set_id"]):x for x in built["sets"]}
    if set(old) != set(new): raise RuntimeError("Collector V7 set membership changed")
    changes=[abs(float(new[k].get("collector_appeal") or 0)-float(old[k].get("collector_appeal_score") or 0)) for k in new]
    old_available={k for k,v in old.items() if v.get("score_status")=="scored"}
    new_available={k for k,v in new.items() if v.get("collector_appeal") is not None}
    if len(new_available) < max(1,int(len(old_available)*.75)):
        raise RuntimeError("Collector V7 massive availability collapse")
    old_cards={str(x.get("pokemon_canonical_card_id")):x for x in previous_cards}
    card_changes=[abs(float(x["card_collector_appeal_v7"])-float(old_cards[str(x["canonical_card_id"])]["collector_card_appeal_score"]))
                  for x in built["cards"] if str(x["canonical_card_id"]) in old_cards]
    old_rank={k:i for i,(k,_) in enumerate(sorted(((k,float(v.get("collector_appeal_score") or -1)) for k,v in old.items()),key=lambda x:(-x[1],x[0])),1)}
    new_rank={k:i for i,(k,_) in enumerate(sorted(((k,float(v.get("collector_appeal") or -1)) for k,v in new.items()),key=lambda x:(-x[1],x[0])),1)}
    f_deltas=[abs(float(x["F_delta"])) for x in new.values() if x.get("F_delta") is not None]
    return {"setCount":len(new),"cardCount":len(built["cards"]),
            "maxAbsoluteCardScoreDelta":max(card_changes,default=0),
            "maxAbsoluteSetScoreDelta":max(changes,default=0),
            "maxAbsoluteRankDelta":max((abs(new_rank[k]-old_rank[k]) for k in new),default=0),
            "maxAbsoluteFDelta":max(f_deltas,default=0),
            "availabilityAdded":sorted(new_available-old_available),
            "availabilityRemoved":sorted(old_available-new_available),
            "fMembershipChanges":sum(bool(x.get("entering_cards") or x.get("leaving_cards")) for x in new.values()),
            "artistCoverage":built["manifest"]["analysis"].get("cardArtistStatusCounts"),
            "trainerCardCount":sum(x.get("subject_type")=="trainer" for x in built["cards"]),
            "pokemonCardCount":sum(x.get("subject_type")=="pokemon" for x in built["cards"])}


def _default_build(client, authority):
    from backend.scripts.build_pokemon_collector_appeal_v7_expanded import build
    return build(client,pokemon_trends_source_run_id=authority["pokemonTrends"],
        trainer_12m_source_run_id=authority["trainer12m"],trainer_5y_source_run_id=authority["trainer5y"],
        playability_source_run_id=authority["playability"],artist_12m_source_run_id=authority["artist12m"],
        artist_5y_source_run_id=authority["artist5y"])


def _default_persist(client,built,as_of):
    from backend.scripts.build_pokemon_collector_appeal_v7_expanded import persist_built_model
    return persist_built_model(client,built,as_of_date=as_of)


def _run_json(command):
    completed=subprocess.run(command,cwd=str(ROOT),text=True,capture_output=True,check=True)
    decoder=json.JSONDecoder(); parsed=None
    for index,char in enumerate(completed.stdout):
        if char != "{": continue
        try: parsed,_=decoder.raw_decode(completed.stdout[index:])
        except json.JSONDecodeError: continue
    if parsed is None: raise RuntimeError(f"command emitted no JSON: {command[1]}")
    return parsed


def _default_refresh(client, key, _old_id, as_of):
    before=datetime.now(timezone.utc).isoformat(); python=sys.executable
    if key == "pokemon_trends":
        capture_dir=ROOT/"backend/artifacts/collector_v7_refresh"/f"pokemon_{as_of.isoformat()}"
        _run_json([python,str(ROOT/"backend/scripts/capture_pokemon_trends_anchor_ladder_v2.py"),"--checkpoint-dir",str(capture_dir)])
        result=_run_json([python,str(ROOT/"backend/scripts/ingest_pokemon_trends_v2_source_run.py"),
            "--checkpoint",str(capture_dir/"checkpoint_rows.jsonl"),"--header",str(capture_dir/"checkpoint_header.json"),
            "--commit","--i-understand-this-writes-to-production"])
        return str(result["sourceRunId"])
    entity,timeframe=("trainer","today 12-m") if key=="trainer_12m" else (("trainer","today 5-y") if key=="trainer_5y" else (("artist","today 12-m") if key=="artist_12m" else ("artist","today 5-y")))
    command=[python,str(ROOT/"backend/scripts/ingest_collector_google_trends.py"),entity,"--commit","--limit","10000","--timeframe",timeframe]
    if entity=="trainer": command += ["--query-overrides",str(ROOT/"backend/config/pokemon_collector_trainer_query_overrides_v1.json")]
    result=_run_json(command)
    if not result.get("sourceRunId"): raise RuntimeError(f"{key} refresh did not create a source run after {before}")
    return str(result["sourceRunId"])


def _default_set_pages(_client, model_run_id, commit):
    if not commit:return {"status":"validated_dry_run"}
    result=_run_json([sys.executable,str(ROOT/"backend/scripts/build_atomic_set_page_snapshot_generation.py"),
        "--write-stage","--collector-authority","model-run","--collector-model-run-id",model_run_id])
    return {"status":"validated","generationId":result["generationId"]}


def default_hooks():
    return RefreshHooks(_default_refresh,_default_build,_default_persist,_default_set_pages)


def execute(client: Any, *, as_of: date, now: datetime, commit: bool,
            hooks: RefreshHooks | None = None) -> dict[str, Any]:
    plan = build_plan(client, as_of=as_of, now=now)
    due = [x["key"] for x in plan["freshness"]["sources"] if x["due"]]
    if due and not commit:
        plan.update(status="COLLECTOR_SOURCE_REFRESH_PLANNED", dueSources=due,
                    providerCallsPlanned=len(due), mutationsPerformed=0)
        return plan
    if due:
        hooks=hooks or default_hooks(); authority=dict(plan["sourceAuthority"]); refreshed={}
        aliases={"pokemon_trends":"pokemonTrends","trainer_12m":"trainer12m","trainer_5y":"trainer5y","artist_12m":"artist12m","artist_5y":"artist5y"}
        try:
            for key in due:
                new_id=hooks.refresh_source(client,key,authority[aliases[key]],as_of)
                validate_source_run(client,new_id,key); authority[aliases[key]]=new_id; refreshed[key]=new_id
            built=hooks.build_model(client,authority)
            if built["manifest"].get("formulaFingerprint") != FROZEN_FORMULA_FINGERPRINT:
                raise RuntimeError("V7_FROZEN_FORMULA_DRIFT_BLOCKER")
            prior=_paged(lambda: client.table("pokemon_set_collector_appeal_scores").select("*").eq("model_run_id",plan["modelRunId"]))
            prior_cards=_paged(lambda: client.table("pokemon_card_collector_appeal_scores").select(
                "pokemon_canonical_card_id,collector_card_appeal_score").eq("model_run_id",plan["modelRunId"]))
            deltas=delta_report(prior,built,prior_cards)
            new_run,validation,created=hooks.persist_model(client,built,as_of)
            pages=hooks.build_set_pages(client,new_run,commit)
            if not pages.get("generationId"):
                raise RuntimeError("validated Set-page generation ID missing")
            client.rpc("promote_pokemon_collector_v7_with_set_page_generation",{
                "p_model_run_id":new_run,"p_generation_id":pages["generationId"]}).execute()
            inserted=client.rpc("append_current_collector_v7_history",{"p_as_of_date":as_of.isoformat()}).execute().data
            plan.update(status="COLLECTOR_HISTORY_APPENDED",dueSources=due,refreshedSourceRuns=refreshed,
                previousModelRunId=plan["modelRunId"],newModelRunId=new_run,modelCreated=created,
                validation=validation,deltaReport=deltas,setPagePublication=pages,
                providerCallsPlanned=len(due),historyResult=int(inserted or 0),
                sourceRunsCreated=len(refreshed),mutationsPerformed=len(refreshed)+int(created)+1+int(inserted or 0))
            return plan
        except Exception as exc:
            plan.update(status="COLLECTOR_SOURCE_REFRESH_BLOCKED",dueSources=due,
                        refreshedSourceRuns=refreshed,error=f"{type(exc).__name__}: {exc}",
                        providerCallsPlanned=len(due),sourceRunsCreated=len(refreshed),
                        mutationsPerformed=len(refreshed))
            return plan
    if not commit:
        plan.update(status="VALIDATED_DRY_RUN", mutationsPerformed=0)
        return plan
    inserted = client.rpc("append_current_collector_v7_history", {
        "p_as_of_date": as_of.isoformat()
    }).execute().data
    plan.update(status="APPENDED" if inserted else "ALREADY_PRESENT",
                mutationsPerformed=int(inserted or 0))
    return plan


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase
    report = execute(supabase, as_of=date.fromisoformat(args.as_of_date),
                     now=datetime.now(timezone.utc), commit=args.commit)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["status"] != "COLLECTOR_SOURCE_REFRESH_BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
