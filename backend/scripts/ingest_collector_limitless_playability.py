"""Collect bounded Standard playability evidence from the documented Limitless API."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.desirability.collector_identity import normalize_identity_text  # noqa: E402
from backend.desirability.collector_source_quality import limitless_gate  # noqa: E402

API = "https://play.limitlesstcg.com/api"
SOURCE = "limitless_standard_playability"
VERSION = "limitless_standard_playability_v1"
CARD_GROUPS = ("pokemon", "trainer")
WRITE_BATCH = 250


class Telemetry:
    def __init__(self):
        self.data = defaultdict(int)
        self.started = time.perf_counter()

    def duration(self):
        return round(time.perf_counter() - self.started, 3)


class Client:
    def __init__(self, telemetry, delay=.25, retries=3):
        self.telemetry, self.delay, self.retries = telemetry, delay, retries
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "inDex-Collector-Appeal/1.0"

    def get(self, path, params=None):
        for attempt in range(self.retries + 1):
            response = self.session.get(API + path, params=params, timeout=30)
            self.telemetry.data["networkRequests"] += 1
            if response.status_code == 429:
                self.telemetry.data["rateLimits"] += 1
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.retries:
                    self.telemetry.data["retries"] += 1
                    time.sleep(min(8, 2 ** attempt))
                    continue
            response.raise_for_status()
            time.sleep(self.delay)
            return response.json()
        raise RuntimeError("Limitless request retry budget exhausted")


class Repository:
    def __init__(self, client, telemetry):
        self.client, self.telemetry = client, telemetry

    def _all(self, table, columns, size=1000):
        rows, start = [], 0
        while True:
            result = self.client.table(table).select(columns).range(start, start + size - 1).execute().data
            self.telemetry.data["dbReadRequests"] += 1
            self.telemetry.data["dbRowsRead"] += len(result)
            rows.extend(result)
            if len(result) < size:
                return rows
            start += size

    def identity_index(self):
        cards = self._all(
            "pokemon_canonical_cards",
            "id,pokemon_tcg_api_card_id,name,supertype,subtypes,number,printed_number,"
            "ptcgo_code:source_payload->set->>ptcgoCode",
        )
        links = self._all("pokemon_card_functional_links", "pokemon_canonical_card_id,functional_reference_id,active")
        link = {x["pokemon_canonical_card_id"]: x["functional_reference_id"] for x in links if x.get("active") is not False}
        exact, source_card, by_name = defaultdict(set), defaultdict(set), defaultdict(set)
        def number_key(value):
            return str(value or "").split("/", 1)[0].lstrip("0").casefold() or "0"
        for card in cards:
            fid = link.get(card["id"])
            if not fid:
                continue
            api_id = str(card.get("pokemon_tcg_api_card_id") or "").casefold()
            if api_id:
                exact[api_id].add(fid)
            name_key = normalize_identity_text(card.get("name"))
            by_name[name_key].add(fid)
            codes = {str(card.get("ptcgo_code") or "").casefold()}
            if api_id.startswith("sv1-"):
                codes.add("svi")
            for code in codes - {""}:
                for number in {card.get("number"), card.get("printed_number")}:
                    if number is not None:
                        source_card[(code, number_key(number), name_key)].add(fid)
        return exact, source_card, by_name

    def create_run(self, row):
        result = self.client.table("pokemon_collector_source_runs").insert(row).execute().data[0]
        self.telemetry.data["dbWriteRequests"] += 1
        self.telemetry.data["dbRowsInserted"] += 1
        return result["id"]

    def insert_observations(self, rows):
        for start in range(0, len(rows), WRITE_BATCH):
            batch = rows[start:start + WRITE_BATCH]
            self.client.table("pokemon_playability_event_observations").insert(batch).execute()
            self.telemetry.data["dbWriteRequests"] += 1
            self.telemetry.data["dbWriteBatches"] += 1
            self.telemetry.data["dbRowsInserted"] += len(batch)

    def finish_run(self, run_id, status, count, fingerprint, diagnostics, raw):
        self.client.table("pokemon_collector_source_runs").update({
            "status": status, "completed_at": datetime.now(timezone.utc).isoformat(),
            "captured_at": datetime.now(timezone.utc).isoformat(), "item_count": count,
            "source_fingerprint": fingerprint, "diagnostics_json": diagnostics,
            "raw_payload_json": raw,
        }).eq("id", run_id).execute()
        self.telemetry.data["dbWriteRequests"] += 1


def discover(client, today, window_days, pages, page_size, minimum_players):
    rows = []
    for page in range(1, pages + 1):
        part = client.get("/tournaments", {"game":"PTCG", "format":"STANDARD", "limit":page_size, "page":page})
        rows.extend(part)
        if len(part) < page_size:
            break
    cutoff = today - timedelta(days=window_days)
    selected = [r for r in rows if cutoff <= datetime.fromisoformat(r["date"].replace("Z", "+00:00")).date() <= today and int(r.get("players") or 0) >= minimum_players]
    selected.sort(key=lambda r: (-int(r["players"]), r["date"], r["id"]))
    return rows, selected


def collect(client, selected, minimum_coverage, maximum_events):
    accepted, excluded, deck_rows = [], [], []
    for base in selected:
        if len(accepted) >= maximum_events:
            break
        details = client.get("/tournaments/%s/details" % base["id"])
        standings = client.get("/tournaments/%s/standings" % base["id"])
        visible = [s for s in standings if isinstance(s.get("decklist"), dict)]
        coverage = len(visible) / max(int(details.get("players") or 0), 1)
        reasons = []
        if details.get("game") != "PTCG" or details.get("format") != "STANDARD": reasons.append("wrong_game_or_format")
        if not details.get("decklists") or coverage < minimum_coverage: reasons.append("insufficient_decklist_coverage")
        if details.get("specialRules") or details.get("bannedCards"): reasons.append("custom_rules")
        if reasons:
            excluded.append({"id":base["id"], "reasons":reasons, "decklistCoverage":coverage})
            continue
        event = {"id":details["id"], "name":details.get("name"), "date":details.get("date"),
                 "players":details.get("players"), "coverage":coverage, "decklists":len(visible)}
        accepted.append(event)
        for standing in visible:
            deck_id = "%s:%s" % (event["id"], standing.get("player"))
            for group in CARD_GROUPS:
                for card in standing["decklist"].get(group, []) or []:
                    deck_rows.append({"event":event, "deckId":deck_id, "placing":standing.get("placing"),
                                      "group":group, "name":card.get("name"), "set":card.get("set"),
                                      "number":card.get("number"), "copies":int(card.get("count") or 0)})
    return accepted, excluded, deck_rows


def reconcile(deck_rows, exact, source_card, by_name, reference_day):
    grouped = {}
    for row in deck_rows:
        source_set = str(row.get("set") or "").casefold()
        source_number = str(row.get("number") or "").split("/", 1)[0].lstrip("0").casefold() or "0"
        source_name = normalize_identity_text(row.get("name"))
        source_id = "%s-%s" % (source_set, row.get("number"))
        candidates = source_card.get((source_set, source_number, source_name), set())
        method = "ptcgo_code_number_exact_name"
        if not candidates:
            candidates = exact.get(source_id, set())
            method = "pokemon_tcg_api_id"
        if not candidates:
            candidates = by_name.get(source_name, set())
            method = "normalized_name_lookup_aid"
        status = "matched" if len(candidates) == 1 else "ambiguous" if len(candidates) > 1 else "unmatched"
        fid = next(iter(candidates)) if status == "matched" else None
        key = (row["event"]["id"], fid or "%s:%s" % (status, source_id or normalize_identity_text(row.get("name"))))
        agg = grouped.setdefault(key, {"sample":row, "fid":fid, "status":status, "method":method,
                                       "decks":set(), "top":set(), "copies":0})
        agg["decks"].add(row["deckId"]); agg["copies"] += row["copies"]
        if row.get("placing") and int(row["placing"]) <= 32: agg["top"].add(row["deckId"])
    output = []
    for agg in grouped.values():
        row, event = agg["sample"], agg["sample"]["event"]
        age = max(0, (reference_day - datetime.fromisoformat(event["date"].replace("Z", "+00:00")).date()).days)
        weight = min(2.0, math.log1p(event["players"]) / math.log(129)) * math.exp(-math.log(2) * age / 30)
        output.append({
            "functional_reference_id":agg["fid"], "raw_card_name":row["name"], "event_external_id":event["id"],
            "event_name":event["name"], "event_date":event["date"][:10], "format_name":"STANDARD",
            "field_deck_count":event["decklists"], "deck_appearance_count":len(agg["decks"]),
            "copy_count":agg["copies"], "top_cut_deck_count":len(agg["top"]),
            "deck_share":len(agg["decks"]) / event["decklists"],
            "top_cut_share":len(agg["top"]) / min(32, event["decklists"]), "weighted_points":weight,
            "match_status":agg["status"], "match_confidence":1.0 if agg["method"] in {"ptcgo_code_number_exact_name", "pokemon_tcg_api_id"} and agg["status"] == "matched" else .8 if agg["status"] == "matched" else None,
            "raw_row_json":{"sourceStatus":"valid", "sourceSet":row.get("set"), "sourceNumber":row.get("number"),
                            "cardGroup":row["group"], "mappingMethod":agg["method"], "energyExcludedV1":True},
        })
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--commit", action="store_true")
    p.add_argument("--window-days", type=int, default=30); p.add_argument("--minimum-players", type=int, default=32)
    p.add_argument("--minimum-coverage", type=float, default=.8); p.add_argument("--maximum-events", type=int, default=5)
    p.add_argument("--pages", type=int, default=5); p.add_argument("--page-size", type=int, default=100)
    args = p.parse_args(); load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import supabase
    telemetry = Telemetry(); repo = Repository(supabase, telemetry); client = Client(telemetry)
    today = date.today(); discovered, candidates = discover(client, today, args.window_days, args.pages, args.page_size, args.minimum_players)
    events, excluded, deck_rows = collect(client, candidates, args.minimum_coverage, args.maximum_events)
    reconcile_start = time.perf_counter(); exact, source_card, by_name = repo.identity_index(); observations = reconcile(deck_rows, exact, source_card, by_name, today)
    telemetry.data["reconciliationDurationSeconds"] = round(time.perf_counter() - reconcile_start, 3)
    fingerprint = hashlib.sha256(json.dumps({"events":events, "observations":observations}, sort_keys=True, default=str).encode()).hexdigest()
    diagnostics = {**telemetry.data, "eventsDiscovered":len(discovered), "eventsEligibleByList":len(candidates),
                   "eventsSelected":len(events), "eventsExcluded":len(excluded), "decklistsObserved":sum(e["decklists"] for e in events),
                   "rawCardRows":len(deck_rows), "observations":len(observations),
                   "matched":sum(x["match_status"] == "matched" for x in observations),
                   "unmatched":sum(x["match_status"] == "unmatched" for x in observations),
                   "ambiguous":sum(x["match_status"] == "ambiguous" for x in observations)}
    diagnostics["meanDecklistCoverage"] = sum(e["coverage"] for e in events) / max(len(events), 1)
    diagnostics["qualityGate"] = limitless_gate(diagnostics)
    if args.commit:
        now = datetime.now(timezone.utc); run_id = repo.create_run({"source_name":SOURCE, "source_kind":"playability",
            "run_key":"%s-%s" % (today.isoformat(), fingerprint[:12]), "capture_version":VERSION, "status":"running",
            "source_url":API, "window_start":(today-timedelta(days=args.window_days)).isoformat(), "window_end":today.isoformat(),
            "raw_payload_json":{"events":events, "excluded":excluded}})
        write_start = time.perf_counter()
        try:
            for row in observations: row["source_run_id"] = run_id
            repo.insert_observations(observations)
            diagnostics["dbWriteDurationSeconds"] = round(time.perf_counter()-write_start, 3)
            diagnostics.update(telemetry.data)
            diagnostics["totalDurationSeconds"] = telemetry.duration()
            repo.finish_run(run_id, "success" if observations else "failed", len(observations), fingerprint, diagnostics, {"events":events,"excluded":excluded})
        except Exception as exc:
            repo.finish_run(run_id, "failed", 0, fingerprint, {**diagnostics,"error":"%s: %s"%(type(exc).__name__,exc)}, {"events":events,"excluded":excluded})
            raise
    diagnostics["totalDurationSeconds"] = telemetry.duration()
    try:
        import resource
        diagnostics["peakProcessMemoryBytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    except Exception:
        diagnostics["peakProcessMemoryBytes"] = None
    print(json.dumps({"status":"committed" if args.commit else "dry_run", "diagnostics":diagnostics,
                      "events":events, "excluded":excluded, "unresolvedSamples":[x for x in observations if x["match_status"] != "matched"][:20]}, indent=2, default=str))
    return 0


if __name__ == "__main__": raise SystemExit(main())
