from datetime import datetime, timezone

from backend.scripts.plan_collector_appeal_refresh import freshness_plan


def _run(source, timeframe, captured="2026-09-10T00:00:00+00:00"):
    return {"id":source+str(timeframe),"source_name":source,"status":"success","captured_at":captured,"raw_payload_json":{"timeframe":timeframe}}


def test_freshness_plan_uses_weekly_and_monthly_horizons_without_daily_scraping():
    rows=[_run("google_trends_pokemon_v2",None),_run("google_trends_trainer","today 12-m"),_run("google_trends_trainer","today 5-y","2026-08-20T00:00:00+00:00"),_run("google_trends_artist","today 12-m"),_run("google_trends_artist","today 5-y","2026-08-20T00:00:00+00:00")]
    plan=freshness_plan(rows,datetime(2026,9,11,tzinfo=timezone.utc))
    assert plan["allFresh"] is True
    assert not any(x["due"] for x in plan["sources"])


def test_failed_or_stale_run_never_satisfies_refresh_contract():
    rows=[_run("google_trends_artist","today 12-m","2026-08-01T00:00:00+00:00")]
    plan=freshness_plan(rows,datetime(2026,9,11,tzinfo=timezone.utc))
    assert plan["allFresh"] is False
    assert next(x for x in plan["sources"] if x["key"]=="artist_12m")["due"] is True
