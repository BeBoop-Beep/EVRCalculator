"""Shadow-ingest disambiguated Trainer or artist Google Trends evidence."""
from __future__ import annotations

import argparse, hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from backend.desirability.google_trends import QUERY_TYPE_SEARCH_TERM, make_provider  # noqa: E402
from backend.desirability.collector_source_quality import trends_gate  # noqa: E402

TABLE_RUN = "pokemon_collector_source_runs"
TABLE_OBS = "pokemon_collector_entity_observations"


def query_for(entity_type, name, overrides=None):
    if entity_type == "trainer" and overrides and name in overrides:
        return "%s Pokemon trainer" % name
    return "%s Pokemon" % name if entity_type == "trainer" else "%s Pokemon cards" % name


def collect(provider, entities, entity_type, geo, timeframe, anchor, delay=8.0, lower_anchor=None,
            max_retries=2, retry_backoff=8.0, query_overrides=None):
    rows, telemetry = [], {"networkRequests":0,"retries":0,"rateLimits":0,"batches":0,"zeroRetestRequests":0,"anchorBridgeIntegrity":False}
    for start in range(0, len(entities), 4):
        batch = entities[start:start+4]; terms = [query_for(entity_type, x["display_name"],query_overrides) for x in batch] + [anchor]
        response = provider.fetch_interest(terms=terms, timeframe=timeframe, geo=geo, query_type=QUERY_TYPE_SEARCH_TERM)
        telemetry["networkRequests"] += 1; telemetry["batches"] += 1
        attempt=0
        while response.status == "rate_limited" and attempt < max_retries:
            telemetry["rateLimits"] += 1; telemetry["retries"] += 1; attempt += 1
            time.sleep(retry_backoff * attempt)
            response = provider.fetch_interest(terms=terms, timeframe=timeframe, geo=geo, query_type=QUERY_TYPE_SEARCH_TERM)
            telemetry["networkRequests"] += 1
        if response.status == "rate_limited": telemetry["rateLimits"] += 1
        values = response.interest_by_term or {}; anchor_value = values.get(anchor)
        for entity, term in zip(batch, terms[:-1]):
            raw = values.get(term); status = "genuine_zero" if response.status == "captured" and raw == 0 and anchor_value else "valid" if response.status == "captured" and raw is not None and anchor_value else (
                "anchor_failure" if response.status == "captured" and not anchor_value else "rate_limited" if response.status == "rate_limited" else "provider_unavailable" if getattr(provider,"provider_name","") == "unavailable" else "insufficient" if response.status == "insufficient_data" else "failed")
            rows.append({"collector_entity_id":entity["id"], "dimension_key":"%s_search_interest" % entity_type,
                "raw_entity_name":entity["display_name"], "external_entity_key":term, "raw_value":raw,
                "normalized_observation_score":min(100, raw / anchor_value * 100) if status == "valid" else None,
                "match_status":"matched", "match_confidence":1.0,
                "raw_row_json":{"sourceStatus":status,"queryTerm":term,"geo":geo,"timeframe":timeframe,
                                "anchor":anchor,"anchorValue":anchor_value,"provider":getattr(provider,"provider_name","unknown"),
                                "ambiguity":"pokemon_disambiguated","confidence":1.0 if status == "valid" else 0.0}})
        if start + 4 < len(entities): time.sleep(delay)
    apparent = [row for row in rows if row["raw_row_json"]["sourceStatus"] == "genuine_zero"]
    if lower_anchor and apparent:
        bridge = provider.fetch_interest(terms=[lower_anchor, anchor], timeframe=timeframe, geo=geo, query_type=QUERY_TYPE_SEARCH_TERM)
        telemetry["networkRequests"] += 1; telemetry["batches"] += 1
        attempt=0
        while bridge.status == "rate_limited" and attempt < max_retries:
            telemetry["rateLimits"] += 1; telemetry["retries"] += 1; attempt += 1
            time.sleep(retry_backoff * attempt)
            bridge = provider.fetch_interest(terms=[lower_anchor, anchor], timeframe=timeframe, geo=geo, query_type=QUERY_TYPE_SEARCH_TERM)
            telemetry["networkRequests"] += 1
        if bridge.status == "rate_limited": telemetry["rateLimits"] += 1
        lower_to_main = None
        if bridge.status == "captured" and bridge.interest_by_term.get(anchor):
            lower_to_main = bridge.interest_by_term.get(lower_anchor, 0) / bridge.interest_by_term[anchor]
            telemetry["anchorBridgeIntegrity"] = lower_to_main > 0
        for start in range(0, len(apparent), 4):
            batch=apparent[start:start+4]; terms=[row["external_entity_key"] for row in batch]+[lower_anchor]
            response=provider.fetch_interest(terms=terms,timeframe=timeframe,geo=geo,query_type=QUERY_TYPE_SEARCH_TERM)
            telemetry["networkRequests"] += 1; telemetry["zeroRetestRequests"] += 1; telemetry["batches"] += 1
            attempt=0
            while response.status == "rate_limited" and attempt < max_retries:
                telemetry["rateLimits"] += 1; telemetry["retries"] += 1; attempt += 1
                time.sleep(retry_backoff * attempt)
                response=provider.fetch_interest(terms=terms,timeframe=timeframe,geo=geo,query_type=QUERY_TYPE_SEARCH_TERM)
                telemetry["networkRequests"] += 1
            if response.status == "rate_limited": telemetry["rateLimits"] += 1
            lower_value=(response.interest_by_term or {}).get(lower_anchor)
            for row,term in zip(batch,terms[:-1]):
                value=(response.interest_by_term or {}).get(term)
                raw=row["raw_row_json"]; raw.update({"zeroRetested":True,"lowerAnchor":lower_anchor,"lowerAnchorValue":lower_value,"bridgeRatio":lower_to_main,"lowerTierRawValue":value})
                if response.status == "captured" and value and lower_value and lower_to_main:
                    row["raw_value"]=value; row["normalized_observation_score"]=min(100,value/lower_value*lower_to_main*100); raw["sourceStatus"]="valid"; raw["tier"]="lower_bridge_scaled"
                elif response.status == "captured" and value == 0 and lower_value:
                    raw["sourceStatus"]="genuine_zero"; raw["zeroConfirmed"] = True; raw["tier"]="lower_zero_confirmed"
                else:
                    raw["sourceStatus"]="unscaled_tier"; row["normalized_observation_score"]=None
    return rows, telemetry


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("entity_type",choices=["trainer","artist"]); p.add_argument("--commit",action="store_true")
    p.add_argument("--provider",choices=["auto","pytrends","fixture"],default="auto"); p.add_argument("--limit",type=int,default=8)
    p.add_argument("--entity-name", action="append", help="Repeatable exact entity display name selector")
    p.add_argument("--geo",default="US"); p.add_argument("--timeframe",default="today 12-m"); p.add_argument("--anchor",default="Pikachu Pokemon")
    p.add_argument("--lower-anchor", default=None)
    p.add_argument("--delay-seconds",type=float,default=8.0)
    p.add_argument("--max-retries",type=int,default=2); p.add_argument("--retry-backoff-seconds",type=float,default=8.0)
    p.add_argument("--query-overrides",help="Versioned Trainer query override registry JSON")
    args=p.parse_args(); load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    started=time.perf_counter(); query=supabase.table("pokemon_collector_entity_reference").select("id,entity_type,display_name,canonical_key").eq("entity_type",args.entity_type).eq("active",True)
    if args.entity_name: query=query.in_("display_name",args.entity_name)
    all_entities=query.order("canonical_key").execute().data
    db_read_requests, db_rows_read = 1, len(all_entities)
    artist_card_counts = {}
    if args.entity_type == "artist" and not args.entity_name:
        start = 0
        while True:
            part = (supabase.table("pokemon_card_collector_entity_links")
                    .select("collector_entity_id").eq("link_role", "artist")
                    .range(start, start + 999).execute().data)
            db_read_requests += 1; db_rows_read += len(part)
            for link in part:
                entity_id = link["collector_entity_id"]
                artist_card_counts[entity_id] = artist_card_counts.get(entity_id, 0) + 1
            if len(part) < 1000: break
            start += 1000
        all_entities.sort(key=lambda x: (-artist_card_counts.get(x["id"], 0), x["canonical_key"]))
    entities=all_entities[:args.limit]
    override_payload=json.loads(Path(args.query_overrides).read_text(encoding="utf-8")) if args.query_overrides else {}; query_overrides=override_payload.get("overrides",{})
    provider=make_provider(args.provider,dry_run=not args.commit); lower_anchor=args.lower_anchor or ("Pokemon Trainer" if args.entity_type=="trainer" else "Pokemon illustrator")
    rows,telemetry=collect(provider,entities,args.entity_type,args.geo,args.timeframe,args.anchor,args.delay_seconds,lower_anchor,
                           args.max_retries,args.retry_backoff_seconds,query_overrides)
    payload={"entityType":args.entity_type,"queries":[x["external_entity_key"] for x in rows],"timeframe":args.timeframe,"geo":args.geo,"anchor":args.anchor,
             "queryOverrideRegistryVersion":override_payload.get("registryVersion"),"queryOverrideCount":len(query_overrides)}
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(); run_id=None
    statuses={s:sum(x["raw_row_json"]["sourceStatus"]==s for x in rows) for s in sorted({x["raw_row_json"]["sourceStatus"] for x in rows})}
    represented_cards=sum(artist_card_counts.get(x["collector_entity_id"],0) for x in rows if x["normalized_observation_score"] is not None)
    diagnostics={**telemetry,"eligibleEntities":len(all_entities),"entitiesRead":len(entities),"rows":len(rows),"statuses":statuses,"dbReadRequests":db_read_requests,"dbRowsRead":db_rows_read,
                 "scaled":sum(x["normalized_observation_score"] is not None for x in rows),"zeroConfirmed":sum(x["raw_row_json"].get("zeroConfirmed") is True for x in rows)}
    diagnostics.update({"retrievalCoverage":(diagnostics["scaled"]+diagnostics["zeroConfirmed"])/max(len(rows),1),
                        "observableSignalCoverage":diagnostics["scaled"]/max(len(rows),1),
                        "confirmedZeroShare":diagnostics["zeroConfirmed"]/max(len(rows),1),
                        "missingOrFailedShare":sum(s not in {"valid","genuine_zero"} for s in (x["raw_row_json"]["sourceStatus"] for x in rows))/max(len(rows),1)})
    if args.entity_type == "artist":
        diagnostics.update({"canonicalCardsWithArtist":sum(artist_card_counts.values()),"cardsRepresentedByScaledArtists":represented_cards,
                            "cardWeightedObservableSignalCoverage":represented_cards/max(sum(artist_card_counts.values()),1)})
    gate_metrics={"eligible":len(entities),"scaled":diagnostics["scaled"],"zeroConfirmed":diagnostics["zeroConfirmed"],"unresolved":sum(s not in {"valid","genuine_zero"} for s in (x["raw_row_json"]["sourceStatus"] for x in rows)),
                  "anchorBridgeIntegrity":telemetry["anchorBridgeIntegrity"] or telemetry["zeroRetestRequests"]==0,
                  "apparentZerosRetested":all(x["raw_row_json"]["sourceStatus"]!="genuine_zero" or x["raw_row_json"].get("zeroConfirmed") for x in rows)}
    diagnostics["qualityGate"]=trends_gate(gate_metrics,"%s_trends"%args.entity_type)
    if args.commit:
        now=datetime.now(timezone.utc).isoformat(); source="google_trends_%s"%args.entity_type
        run=supabase.table(TABLE_RUN).insert({"source_name":source,"source_kind":"search_interest","run_key":"%s-%s"%(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),fingerprint[:12]),
            "capture_version":"collector_trends_anchor_v1","status":"running","source_url":"https://trends.google.com/trends/","geo":args.geo,"anchor_term":args.anchor,"raw_payload_json":payload}).execute().data[0]; run_id=run["id"]
        persistable=rows
        for x in persistable: x["source_run_id"]=run_id
        if persistable: supabase.table(TABLE_OBS).insert(persistable).execute()
        usable=sum(x["raw_row_json"]["sourceStatus"] in {"valid","genuine_zero"} for x in rows)
        diagnostics.update({"dbWriteRequests":2+(1 if persistable else 0),"dbRowsInserted":1+len(persistable),"dbWriteBatches":1 if persistable else 0})
        status="success" if usable==len(rows) and rows else "partial_failure" if usable else "failed"
        diagnostics["totalDurationSeconds"]=round(time.perf_counter()-started,3)
        supabase.table(TABLE_RUN).update({"status":status,"completed_at":now,"captured_at":now,"item_count":len(persistable),"source_fingerprint":fingerprint,
            "diagnostics_json":diagnostics}).eq("id",run_id).execute()
    diagnostics["totalDurationSeconds"]=round(time.perf_counter()-started,3)
    print(json.dumps({"status":"committed" if args.commit else "dry_run","sourceRunId":run_id,"diagnostics":diagnostics,"rows":rows},indent=2,default=str)); return 0


if __name__=="__main__": raise SystemExit(main())
