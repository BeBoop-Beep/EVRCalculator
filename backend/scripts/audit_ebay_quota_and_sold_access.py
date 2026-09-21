"""P6.5: audit the production eBay keyset: real quotas, Browse pool mapping and Marketplace Insights (sold) access.

Tiny, bounded probes only (a handful of calls in total; no sold-data crawl, no HTML scraping). Nothing secret is
printed or written: tokens are never stored, and only status codes, error ids and quota numbers are recorded.
A provider usage response of HTTP 204 (a known eBay issue for getRateLimits) is recorded as UNRESOLVED and is never
interpreted as zero or as unlimited quota.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend/artifacts/pricing/ebay_quota_and_sold_access_audit.json"
API = "https://api.ebay.com"
TOKEN_URL = f"{API}/identity/v1/oauth2/token"
BASE_SCOPE = "https://api.ebay.com/oauth/api_scope"
INSIGHTS_SCOPE = "https://api.ebay.com/oauth/api_scope/buy.marketplace.insights"
ANALYTICS_URL = f"{API}/developer/analytics/v1_beta/rate_limit/"
INSIGHTS_URL = f"{API}/buy/marketplace_insights/v1_beta/item_sales/search"
BROWSE_SEARCH = f"{API}/buy/browse/v1/item_summary/search"
BROWSE_ITEM = f"{API}/buy/browse/v1/item/"


def _clean_errors(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    return [{k: e.get(k) for k in ("errorId", "domain", "category", "message", "longMessage")}
            for e in (body.get("errors") or []) if isinstance(e, dict)]


def http(method: str, url: str, token: str | None = None, data: bytes | None = None, headers: dict[str, str] | None = None,
         timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read()
            body = json.loads(raw) if raw else None
            return {"status": resp.status, "body": body, "empty": not raw}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = {"non_json_body_length": len(raw)}
        return {"status": exc.code, "body": body, "empty": not raw}
    except Exception as exc:  # noqa: BLE001
        return {"status": None, "body": None, "error_type": type(exc).__name__}


def fetch_token(creds: Any, scope: str) -> dict[str, Any]:
    basic = base64.b64encode(f"{creds.client_id}:{creds.client_secret}".encode()).decode()
    payload = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": scope}).encode()
    result = http("POST", TOKEN_URL, data=payload, headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    body = result.get("body") or {}
    out = {"scope": scope, "http_status": result["status"], "granted": bool(body.get("access_token"))}
    if out["granted"]:
        out.update(token_type=body.get("token_type"), expires_in=body.get("expires_in"))
        out["_token"] = body["access_token"]  # kept in memory only; stripped before anything is written
    else:
        out.update(error=body.get("error"), error_description=body.get("error_description"))
    return out


def summarize_rate_limits(response: dict[str, Any]) -> dict[str, Any]:
    """Normalize getRateLimits. 204/empty is UNRESOLVED (never zero, never unlimited)."""
    status, body = response["status"], response.get("body")
    if status == 204 or (status == 200 and not body):
        return {"http_status": status, "state": "PROVIDER_USAGE_UNRESOLVED_NO_CONTENT", "interpretation": "unknown; not zero, not unlimited", "limits": []}
    if status != 200 or not isinstance(body, dict):
        return {"http_status": status, "state": "PROVIDER_USAGE_ERROR", "errors": _clean_errors(body), "limits": []}
    limits = []
    for api in body.get("rateLimits") or []:
        for resource in api.get("resources") or []:
            for rate in resource.get("rates") or []:
                limits.append({"api_context": api.get("apiContext"), "api_name": api.get("apiName"), "api_version": api.get("apiVersion"),
                               "resource": resource.get("name"), "limit": rate.get("limit"), "count": rate.get("count"),
                               "remaining": rate.get("remaining"), "reset": rate.get("reset"),
                               "time_window_seconds": rate.get("timeWindow"), "time_unit": rate.get("timeUnit")})
    return {"http_status": status, "state": "PROVIDER_USAGE_OK" if limits else "PROVIDER_USAGE_EMPTY_LIST", "limits": limits}


def usage_snapshot(token: str, query: str = "") -> dict[str, Any]:
    return summarize_rate_limits(http("GET", ANALYTICS_URL + query, token))


def find(limits: list[dict[str, Any]], name_contains: str) -> list[dict[str, Any]]:
    return [x for x in limits if name_contains.lower() in f"{x.get('api_context')} {x.get('api_name')} {x.get('resource')}".lower()]


def run(args: argparse.Namespace) -> dict[str, Any]:
    from backend.pricing_pipeline.ebay_credentials import credential_presence, load_ebay_credentials

    audit: dict[str, Any] = {"audited_at": datetime.now(timezone.utc).isoformat(), "calls": {"token": 0, "analytics": 0, "browse": 0, "insights": 0}}
    creds = load_ebay_credentials()
    audit["credentials"] = {"source": creds.source, "environment": creds.environment, "client_id_length": len(creds.client_id),
                            "presence_by_source": credential_presence()}
    base = fetch_token(creds, BASE_SCOPE)
    audit["calls"]["token"] += 1
    audit["oauth"] = {"grant_type": "client_credentials (application token)", "base_scope": {k: v for k, v in base.items() if k != "_token"}}
    if not base["granted"]:
        audit["verdict_inputs"] = {"error": "base_token_unavailable"}
        return audit
    token = base["_token"]

    insights_token = fetch_token(creds, INSIGHTS_SCOPE)
    audit["calls"]["token"] += 1
    audit["oauth"]["insights_scope"] = {k: v for k, v in insights_token.items() if k != "_token"}

    # -- provider usage authority
    all_limits = usage_snapshot(token)
    audit["calls"]["analytics"] += 1
    browse_limits = usage_snapshot(token, "?api_context=buy&api_name=Browse")
    audit["calls"]["analytics"] += 1
    audit["provider_usage"] = {"all_apis": all_limits, "buy_browse": browse_limits}

    # -- which resource does search / getItem debit? sandwich two tiny Browse calls between usage snapshots
    mapping: dict[str, Any] = {"method": "usage snapshot before/after one search and one getItem", "steps": []}
    if not args.no_browse_probe:
        from dotenv import load_dotenv

        from backend.db.clients.supabase_client import create_service_role_client
        from backend.pricing_pipeline.budget import DbBudgetLedger

        load_dotenv(ROOT / "backend/.env", override=False)
        ledger = DbBudgetLedger(create_service_role_client())  # diagnostic Browse calls count against the shared cap
        headers = {"X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
        before = usage_snapshot(token, "?api_context=buy&api_name=Browse")
        audit["calls"]["analytics"] += 1
        ledger.reserve()
        query = urllib.parse.urlencode({"q": "pikachu 25/165 pokemon card", "category_ids": "183454", "limit": 1})
        search = http("GET", f"{BROWSE_SEARCH}?{query}", token, headers=headers)
        audit["calls"]["browse"] += 1
        item_id = ((search.get("body") or {}).get("itemSummaries") or [{}])[0].get("itemId")
        time.sleep(args.settle_seconds)
        after_search = usage_snapshot(token, "?api_context=buy&api_name=Browse")
        audit["calls"]["analytics"] += 1
        after_item = None
        item_status = None
        if item_id:
            ledger.reserve()
            item = http("GET", BROWSE_ITEM + urllib.parse.quote(item_id, safe=""), token, headers=headers)
            audit["calls"]["browse"] += 1
            item_status = item["status"]
            time.sleep(args.settle_seconds)
            after_item = usage_snapshot(token, "?api_context=buy&api_name=Browse")
            audit["calls"]["analytics"] += 1
        mapping["steps"] = [{"step": "before", **before}, {"step": "after_search", "http_status_of_call": search["status"], **after_search},
                            {"step": "after_getItem", "http_status_of_call": item_status, **(after_item or {"state": "not_run"})}]
        mapping["settle_seconds"] = args.settle_seconds
        deltas = {}
        for label, snap in (("search", after_search), ("getItem", after_item)):
            prev = before if label == "search" else after_search
            if snap and snap.get("state") == "PROVIDER_USAGE_OK" and prev.get("state") == "PROVIDER_USAGE_OK":
                deltas[label] = [{"resource": a["resource"], "count_delta": (b["count"] or 0) - (a["count"] or 0)}
                                 for a, b in zip(prev["limits"], snap["limits"]) if (b["count"] or 0) != (a["count"] or 0)]
        mapping["observed_count_deltas"] = deltas or "UNRESOLVED: provider usage unavailable or unchanged after settle window"
    audit["browse_bucket_mapping"] = mapping

    # -- Marketplace Insights entitlement: one tiny request per available token, no crawl
    insights: dict[str, Any] = {"endpoint": "GET /buy/marketplace_insights/v1_beta/item_sales/search", "attempts": []}
    attempts = [("base_scope_token", token)]
    if insights_token["granted"]:
        attempts.append(("insights_scope_token", insights_token["_token"]))
    for label, tok in attempts:
        response = http("GET", f"{INSIGHTS_URL}?{urllib.parse.urlencode({'q': 'pokemon card', 'limit': 1})}", tok,
                        headers={"X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})
        audit["calls"]["insights"] += 1
        body = response.get("body")
        insights["attempts"].append({"token": label, "http_status": response["status"], "errors": _clean_errors(body),
                                     "returned_item_sales": isinstance(body, dict) and "itemSales" in body,
                                     "top_level_fields": sorted(body.keys()) if isinstance(body, dict) and response["status"] == 200 else None})
    audit["marketplace_insights"] = insights
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browse-probe", action="store_true", help="skip the two diagnostic Browse calls")
    parser.add_argument("--settle-seconds", type=int, default=20, help="wait before re-reading provider usage")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args(argv)
    audit = run(args)
    args.output.write_text(json.dumps(audit, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"credentials": audit.get("credentials"), "oauth": audit.get("oauth"), "calls": audit["calls"],
                      "usage_states": {k: v.get("state") for k, v in (audit.get("provider_usage") or {}).items()},
                      "insights": [(a["token"], a["http_status"], [e.get("errorId") for e in a["errors"]]) for a in (audit.get("marketplace_insights") or {}).get("attempts", [])]},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
