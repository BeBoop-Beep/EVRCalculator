"""Report whether dynamic Collector evidence is fresh enough for a frozen rebuild.

This is deliberately a planner, not a second scheduler. The existing daily
publication job can invoke it after normal publication and run only the source
commands reported as due.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DYNAMIC_CONTRACT = (
    {"key":"pokemon_trends","sourceName":"google_trends_pokemon_v2","timeframe":None,"maxAgeDays":7},
    {"key":"trainer_12m","sourceName":"google_trends_trainer","timeframe":"today 12-m","maxAgeDays":7},
    {"key":"trainer_5y","sourceName":"google_trends_trainer","timeframe":"today 5-y","maxAgeDays":31},
    {"key":"artist_12m","sourceName":"google_trends_artist","timeframe":"today 12-m","maxAgeDays":7},
    {"key":"artist_5y","sourceName":"google_trends_artist","timeframe":"today 5-y","maxAgeDays":31},
)


def parse_captured_at(value):
    """Accept PostgREST timestamps on runtimes requiring 0/3/6 fraction digits."""
    text=str(value).replace("Z","+00:00")
    match=re.match(r"^(.*\.)(\d+)([+-]\d\d:\d\d)$",text)
    if match:
        fraction=(match.group(2)+"000000")[:6]
        text=f"{match.group(1)}{fraction}{match.group(3)}"
    return datetime.fromisoformat(text)


def freshness_plan(runs, now):
    result=[]
    for spec in DYNAMIC_CONTRACT:
        eligible=[r for r in runs if r.get("source_name")==spec["sourceName"] and r.get("status")=="success" and (spec["timeframe"] is None or (r.get("raw_payload_json") or {}).get("timeframe")==spec["timeframe"])]
        eligible.sort(key=lambda r: str(r.get("captured_at") or ""),reverse=True)
        latest=eligible[0] if eligible else None
        captured=parse_captured_at(latest["captured_at"]) if latest else None
        due=captured is None or now-captured>timedelta(days=spec["maxAgeDays"])
        result.append({**spec,"latestSuccessfulRunId":None if latest is None else latest.get("id"),"lastSuccessfulAt":None if captured is None else captured.isoformat(),"due":due})
    return {"allFresh":not any(x["due"] for x in result),"lastSuccessfulCollectorAppealRefreshAt":min((x["lastSuccessfulAt"] for x in result if x["lastSuccessfulAt"]),default=None),"sources":result}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--now");args=parser.parse_args()
    load_dotenv(ROOT/"backend/.env",override=False)
    from backend.db.clients.supabase_client import supabase
    runs=supabase.table("pokemon_collector_source_runs").select("id,source_name,status,captured_at,raw_payload_json").in_("source_name",sorted({x["sourceName"] for x in DYNAMIC_CONTRACT})).execute().data or []
    now=datetime.fromisoformat(args.now.replace("Z","+00:00")) if args.now else datetime.now(timezone.utc)
    print(json.dumps(freshness_plan(runs,now),indent=2));return 0


if __name__=="__main__":raise SystemExit(main())
