"""Acceptance harness for the Market Explorer variant engine.

Read-only unless ``--commit`` is explicitly supplied with ``--pilot`` or
``--full-acceptance``. Catalog population is never performed by this command.
Direct PostgreSQL access is optional but required for catalog ACL checks and
the TEMP-only EXPLAIN benchmark.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MIGRATION = ROOT / "supabase/migrations/20260829210512_market_explorer_filtered_card_cohorts.sql"
BENCHMARK_SQL = ROOT / "backend/research/market_explorer/effort1c_interval_vs_fact_benchmark.sql"
ARTIFACT_ROOT = ROOT / "artifacts/market_explorer_acceptance"
MIGRATION_VERSION = "20260829210512"
QUERY_CONTRACT_VERSION = "pokemon-market-explorer-query-v3-variant"
SERVICE_VERSION = "pokemon-market-explorer-query-service-v2-variant"

PILOTS = {
    "celebrations": {"name": "Celebrations", "setId": "be7c981b-c55e-4f60-a1b8-be922531452d"},
    "fossil": {"name": "Fossil", "setId": "c86889c9-ea25-4caa-b63c-7aa0b9796da8"},
}
REQUIRED_RPCS = {
    "get_pokemon_canonical_card_variant_authority",
    "refresh_pokemon_card_variant_market_price_intervals",
    "refresh_pokemon_card_variant_market_price_intervals_for_sets",
    "get_pokemon_market_explorer_filtered_cohort",
}
REQUIRED_INDEXES = {
    "idx_pokemon_variant_market_intervals_set_validity",
    "idx_pokemon_variant_market_intervals_variant_validity",
    "idx_pokemon_variant_market_intervals_canonical_validity",
}
STATUSES = {"PASS", "FAIL", "BLOCKED"}


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    evidence: Any = None

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"invalid check status: {self.status}")


def check(name: str, status: str, detail: str, evidence: Any = None) -> dict[str, Any]:
    return asdict(Check(name, status, detail, evidence))


def redacted_command(arguments: Sequence[str]) -> str:
    result, redact_next = [], False
    for argument in arguments:
        if redact_next:
            result.append("<REDACTED_DATABASE_URL>")
            redact_next = False
        elif argument == "--database-url":
            result.append(argument)
            redact_next = True
        elif argument.startswith("--database-url="):
            result.append("--database-url=<REDACTED_DATABASE_URL>")
        else:
            result.append(argument)
    return " ".join(result)


def safe_error(exc: Exception, secret: str | None = None) -> str:
    message = f"{type(exc).__name__}: {exc}"
    return message.replace(secret, "<REDACTED_DATABASE_URL>") if secret else message


def _paged(query_factory: Callable[[], Any], page_size: int = 1000) -> list[dict[str, Any]]:
    rows, start = [], 0
    while True:
        page = list(query_factory().range(start, start + page_size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def _chunks(values: Sequence[str], size: int = 100) -> Iterable[list[str]]:
    for offset in range(0, len(values), size):
        yield list(values[offset:offset + size])


def audit_local_artifacts() -> list[dict[str, Any]]:
    migration = MIGRATION.read_text(encoding="utf-8") if MIGRATION.exists() else ""
    fixture = BENCHMARK_SQL.read_text(encoding="utf-8") if BENCHMARK_SQL.exists() else ""
    executable = "\n".join(line for line in migration.splitlines() if not line.lstrip().startswith("--"))
    fixture_normalized = " ".join(line for line in fixture.lower().splitlines()
                                  if not line.lstrip().startswith("--"))
    return [
        check("migration_exists", "PASS" if migration else "FAIL", str(MIGRATION)),
        check("no_global_migration_backfill",
              "PASS" if "refresh_pokemon_card_variant_market_price_intervals(NULL" not in executable else "FAIL",
              "migration must not invoke an unbounded refresh"),
        check("empty_refresh_is_noop",
              "PASS" if "IF p_card_variant_ids IS NULL OR cardinality(p_card_variant_ids) = 0 THEN" in migration
              and "RETURN 0;" in migration else "FAIL", "null/empty scope returns zero"),
        check("distinct_set_refresh_rpc", "PASS" if
              "refresh_pokemon_card_variant_market_price_intervals_for_sets" in migration else "FAIL",
              "set refresh has a distinct PostgREST name"),
        check("service_only_sql", "PASS" if "TO service_role" in migration and
              "FROM PUBLIC, anon, authenticated" in migration and "SECURITY DEFINER" not in migration else "FAIL",
              "invoker functions and explicit backend-only grants"),
        check("benchmark_fixture_exists", "PASS" if fixture else "FAIL", str(BENCHMARK_SQL)),
        check("benchmark_temp_only", "PASS" if "create temp table" in fixture_normalized and
              "create table public." not in fixture_normalized and
              "drop table public." not in fixture_normalized and
              "alter table public." not in fixture_normalized else "FAIL",
              "fixture may create session-local objects only"),
    ]


def _probe_table(client: Any, name: str) -> dict[str, Any]:
    try:
        client.table(name).select("*").limit(1).execute()
        return check(f"table:{name}", "PASS", "object is visible to service role")
    except Exception as exc:
        return check(f"table:{name}", "FAIL", "required table is unavailable", getattr(exc, "code", None))


def _probe_rpc(client: Any, name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        client.rpc(name, dict(payload)).execute()
        return check(f"rpc:{name}", "PASS", "signature resolved through PostgREST")
    except Exception as exc:
        code = str(getattr(exc, "code", ""))
        return check(f"rpc:{name}", "FAIL" if code == "PGRST202" else "BLOCKED",
                     "RPC signature unavailable" if code == "PGRST202" else "RPC probe could not complete", code)


def run_preflight(client: Any, catalog: Mapping[str, Any] | None = None) -> dict[str, Any]:
    checks = audit_local_artifacts()
    checks.append(_probe_table(client, "pokemon_card_variant_market_price_intervals"))
    rpc_payloads = {
        "get_pokemon_canonical_card_variant_authority": {"p_set_ids": [PILOTS["celebrations"]["setId"]]},
        "refresh_pokemon_card_variant_market_price_intervals": {"p_card_variant_ids": []},
        "refresh_pokemon_card_variant_market_price_intervals_for_sets": {"p_set_ids": []},
        "get_pokemon_market_explorer_filtered_cohort": {
            "p_set_ids": [PILOTS["celebrations"]["setId"]], "p_start_date": "2026-08-28",
            "p_end_date": "2026-08-28", "p_card_ids": None, "p_segment_ids": None,
            "p_pokemon_ids": None, "p_price_segment_ids": None,
            "p_release_age_cohort_ids": None, "p_top_n": None,
        },
    }
    checks.extend(_probe_rpc(client, name, payload) for name, payload in rpc_payloads.items())

    conditions = list(client.table("conditions").select("id,name,abbreviation")
                      .eq("name", "Near Mint").eq("abbreviation", "NM").execute().data or [])
    checks.append(check("near_mint_authority", "PASS" if len(conditions) == 1 else "FAIL",
                        "exactly one Near Mint/NM row required", {"count": len(conditions)}))
    dates = _paged(lambda: client.table("pokemon_market_date_quality").select("market_date")
                   .eq("tcg", "pokemon").in_("status", ["READY", "LEGACY_VERIFIED"])
                   .order("market_date"))
    checks.append(check("market_date_authority", "PASS" if dates else "FAIL",
                        "canonical usable Market dates", {"count": len(dates),
                        "first": dates[0]["market_date"] if dates else None,
                        "latest": dates[-1]["market_date"] if dates else None}))
    for key, pilot in PILOTS.items():
        sets = list(client.table("sets").select("id,name").eq("id", pilot["setId"]).execute().data or [])
        cards = list(client.table("cards").select("id").eq("set_id", pilot["setId"]).limit(1).execute().data or [])
        checks.append(check(f"pilot:{key}", "PASS" if sets and cards else "FAIL",
                            f"{pilot['name']} exists with source card data",
                            {"setId": pilot["setId"]}))

    if catalog is None:
        for name in ("function_signatures", "ambiguous_overload_absent", "interval_indexes",
                     "rls_enabled", "privileges"):
            checks.append(check(f"catalog:{name}", "BLOCKED",
                                "direct PostgreSQL catalog access was not supplied"))
    else:
        signatures = set(catalog.get("functionSignatures") or [])
        checks.append(check("catalog:function_signatures", "PASS" if REQUIRED_RPCS <= signatures else "FAIL",
                            "required exact function names/signatures", sorted(signatures)))
        checks.append(check("catalog:ambiguous_overload_absent",
                            "PASS" if not catalog.get("ambiguousCohortOverload") else "FAIL",
                            "only the current cohort signature may remain"))
        indexes = set(catalog.get("indexes") or [])
        checks.append(check("catalog:interval_indexes", "PASS" if REQUIRED_INDEXES <= indexes else "FAIL",
                            "required interval indexes", sorted(indexes)))
        checks.append(check("catalog:rls_enabled", "PASS" if catalog.get("rlsEnabled") is True else "FAIL",
                            "interval table RLS must be enabled"))
        checks.append(check("catalog:privileges", "PASS" if catalog.get("privilegesCorrect") is True else "FAIL",
                            "PUBLIC/anon/authenticated denied; service_role intended grants only"))
    return {"checks": checks, "status": aggregate_status(checks), "marketDates": dates}


def _psql(database_url: str, *arguments: str, input_text: str | None = None) -> str:
    """Run psql without ever logging or persisting the connection URL."""
    command = ["psql", database_url, "-X", "-v", "ON_ERROR_STOP=1", *arguments]
    completed = subprocess.run(command, input=input_text, text=True, capture_output=True, check=True)
    return completed.stdout


def load_catalog_evidence(database_url: str) -> dict[str, Any]:
    sql = r"""
WITH functions AS (
  SELECT p.oid, p.proname, pg_get_function_identity_arguments(p.oid) args
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public' AND p.proname IN (
    'get_pokemon_canonical_card_variant_authority',
    'refresh_pokemon_card_variant_market_price_intervals',
    'refresh_pokemon_card_variant_market_price_intervals_for_sets',
    'get_pokemon_market_explorer_filtered_cohort')),
expected(name,args) AS (VALUES
 ('get_pokemon_canonical_card_variant_authority','p_set_ids uuid[]'),
 ('refresh_pokemon_card_variant_market_price_intervals','p_card_variant_ids uuid[]'),
 ('refresh_pokemon_card_variant_market_price_intervals_for_sets','p_set_ids uuid[]'),
 ('get_pokemon_market_explorer_filtered_cohort','p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[], p_segment_ids text[], p_pokemon_ids bigint[], p_price_segment_ids text[], p_release_age_cohort_ids text[], p_top_n integer'))
SELECT json_build_object(
 'functionSignatures',coalesce((SELECT json_agg(e.name) FROM expected e JOIN functions f USING(name,args)),'[]'::json),
 'ambiguousCohortOverload',(SELECT count(*)<>1 FROM functions WHERE proname='get_pokemon_market_explorer_filtered_cohort'),
 'indexes',coalesce((SELECT json_agg(indexname) FROM pg_indexes WHERE schemaname='public' AND tablename='pokemon_card_variant_market_price_intervals'),'[]'::json),
 'rlsEnabled',coalesce((SELECT relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname='pokemon_card_variant_market_price_intervals'),false),
 'privilegesCorrect',
   NOT has_table_privilege('anon','public.pokemon_card_variant_market_price_intervals','SELECT')
   AND NOT has_table_privilege('authenticated','public.pokemon_card_variant_market_price_intervals','SELECT')
   AND has_table_privilege('service_role','public.pokemon_card_variant_market_price_intervals','SELECT,INSERT,DELETE')
   AND NOT EXISTS (SELECT 1 FROM functions f WHERE has_function_privilege('anon',f.oid,'EXECUTE') OR has_function_privilege('authenticated',f.oid,'EXECUTE'))
   AND NOT EXISTS (SELECT 1 FROM functions f WHERE NOT has_function_privilege('service_role',f.oid,'EXECUTE'))
)::text;
"""
    output = _psql(database_url, "-At", "-c", sql).strip()
    if not output:
        raise RuntimeError("catalog query returned no evidence")
    return json.loads(output.splitlines()[-1])


def run_temp_benchmark(database_url: str, artifact_directory: Path) -> dict[str, Any]:
    artifact_directory.mkdir(parents=True, exist_ok=True)
    output = _psql(database_url, "-f", str(BENCHMARK_SQL))
    (artifact_directory / "benchmark-psql.txt").write_text(output, encoding="utf-8")
    parsed = parse_benchmark_output(output)
    execution = parsed["executionMs"]
    paired = {"intervalExecutionMs": [execution[0], execution[2]],
              "factExecutionMs": [execution[1], execution[3]]} if len(execution) >= 4 else {}
    storage_match = re.search(r"EFFORT1C_STORAGE\s+(\{.*?\})", output)
    storage = json.loads(storage_match.group(1)) if storage_match else {}
    if storage.get("intervalTotalBytes"):
        paired["storageRatio"] = storage.get("factTotalBytes", 0) / storage["intervalTotalBytes"]
    # The first psql timing belongs to CREATE TEMP TABLE AS and is the fact
    # build cost; index creation timings remain in the raw retained output.
    wall_times = [float(value) for value in re.findall(r"^Time:\s*([0-9.]+)\s*ms", output, re.MULTILINE)]
    if wall_times:
        paired["factBuildMs"] = wall_times[0]
    decision = architecture_decision(paired)
    return {"status": "PASS" if not decision["decision"].startswith("BLOCKED") else "BLOCKED",
            "fixture": str(BENCHMARK_SQL), "storage": storage,
            "architectureDecision": decision, **parsed}


def aggregate_status(checks: Sequence[Mapping[str, Any]]) -> str:
    statuses = {str(item.get("status")) for item in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    return "PASS"


def validate_intervals(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    violations = {key: 0 for key in (
        "nonIncreasingStart", "nextBoundaryMismatch", "finalBoundaryNotNull", "overlap",
        "zeroLength", "duplicateStart", "nonPositivePrice", "sourceDateMismatch",
        "conditionMismatch", "currencyMismatch",
    )}
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("card_variant_id")), []).append(row)
        if float(row.get("market_price") or 0) <= 0:
            violations["nonPositivePrice"] += 1
        if str(row.get("source_date"))[:10] != str(row.get("valid_from"))[:10]:
            violations["sourceDateMismatch"] += 1
        if row.get("condition_ok") is False:
            violations["conditionMismatch"] += 1
        if row.get("currency_ok") is False:
            violations["currencyMismatch"] += 1
    for chain in grouped.values():
        chain = sorted(chain, key=lambda row: (str(row.get("valid_from")), str(row.get("observation_id"))))
        starts = [str(row.get("valid_from"))[:10] for row in chain]
        violations["duplicateStart"] += len(starts) - len(set(starts))
        for index, row in enumerate(chain):
            start, end = starts[index], str(row.get("valid_to"))[:10] if row.get("valid_to") else None
            if index and start <= starts[index - 1]:
                violations["nonIncreasingStart"] += 1
            if end is not None and end <= start:
                violations["zeroLength"] += 1
            if index + 1 < len(chain):
                next_start = starts[index + 1]
                if end != next_start:
                    violations["nextBoundaryMismatch"] += 1
                if end is None or end > next_start:
                    violations["overlap"] += 1
            elif end is not None:
                violations["finalBoundaryNotNull"] += 1
    return violations


def compare_parity(old_rows: Sequence[Mapping[str, Any]], new_rows: Sequence[Mapping[str, Any]],
                   tolerance: float = 1e-8) -> dict[str, Any]:
    def derived(rows):
        index_value = 100.0
        result = {}
        for row in sorted(rows, key=lambda item: str(item["market_date"])):
            current = float(row.get("common_current_value") or 0)
            previous = float(row.get("common_previous_value") or 0)
            daily_return = current / previous - 1 if previous > 0 else 0.0
            index_value *= 1 + daily_return
            result[str(row["market_date"])[:10]] = {
                **row, "daily_return": daily_return, "normalized_index": index_value,
            }
        return result
    fields = ("basket_value", "common_current_value", "common_previous_value",
              "daily_return", "normalized_index")
    old, new = derived(old_rows), derived(new_rows)
    dates = sorted(set(old) & set(new))
    absolute, relative = [], []
    for market_date in dates:
        for field in fields:
            a, b = float(old[market_date].get(field) or 0), float(new[market_date].get(field) or 0)
            difference = abs(a - b)
            absolute.append(difference)
            relative.append(difference / max(abs(a), abs(b), 1.0))
    max_abs, max_rel = max(absolute, default=0.0), max(relative, default=0.0)
    return {"rowsCompared": len(dates), "numericTolerance": tolerance,
            "maxAbsoluteDifference": max_abs, "maxRelativeDifference": max_rel,
            "status": "PASS" if dates and max_abs <= tolerance and max_rel <= tolerance else "FAIL"}


def build_canonical_legacy_cohort(
    constituent_rows: Sequence[Mapping[str, Any]],
    canonical_market_dates: Sequence[str],
) -> list[dict[str, Any]]:
    """Rebuild legacy card-level parity on canonical usable Market dates.

    The legacy aggregate RPC includes DEGRADED dates and therefore carries a
    different predecessor into ``common_previous_value``.  Build from the
    underlying canonical-card panel so both engines use the same previous
    usable Market date before common-cohort and chain-link math are compared.
    """
    usable_dates = sorted({str(value)[:10] for value in canonical_market_dates})
    usable_set = set(usable_dates)
    panel: dict[str, dict[str, float]] = {market_date: {} for market_date in usable_dates}
    for row in constituent_rows:
        market_date = str(row.get("market_date"))[:10]
        if market_date not in usable_set:
            continue
        canonical_card_id = str(row.get("canonical_card_id") or "")
        if not canonical_card_id:
            raise ValueError("legacy constituent is missing canonical_card_id")
        if canonical_card_id in panel[market_date]:
            raise ValueError(
                f"duplicate legacy constituent for {canonical_card_id} on {market_date}"
            )
        panel[market_date][canonical_card_id] = float(row.get("market_price") or 0)

    result: list[dict[str, Any]] = []
    previous_usable_market_date: str | None = None
    for market_date in usable_dates:
        current = panel[market_date]
        if not current:
            continue
        previous = panel.get(previous_usable_market_date or "", {})
        common_ids = set(current) & set(previous)
        result.append({
            "market_date": market_date,
            "constituent_count": len(current),
            "eligible_universe_count": len(current),
            "basket_value": sum(current.values()),
            "common_count": len(common_ids),
            "common_current_value": sum(current[card_id] for card_id in common_ids),
            "common_previous_value": sum(previous[card_id] for card_id in common_ids),
            "previous_usable_market_date": previous_usable_market_date,
        })
        previous_usable_market_date = market_date
    return result


def classify_high_impact(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def price(row):
        try: return float(row.get("currentPrice") or row.get("market_price") or 0)
        except (TypeError, ValueError): return 0.0
    enriched = []
    for row in rows:
        name = str(row.get("cardName") or row.get("name") or "")
        enriched.append({**dict(row), "flags": {
            "dragonite": "dragonite" in name.lower(), "charizard": "charizard" in name.lower(),
            "pikachu": "pikachu" in name.lower(), "highValue": price(row) >= 100,
            "firstEdition": bool(row.get("firstEdition")), "unlimited": bool(row.get("unlimited")),
        }, "resolvedPrice": price(row)})
    top = sorted(enriched, key=lambda row: (-row["resolvedPrice"], str(row.get("cardName") or "")))[:25]
    return {"count": len(rows), "marketValueRepresented": round(sum(price(row) for row in rows), 2),
            "namedCounts": {name: sum(bool(row["flags"][name]) for row in enriched)
                            for name in ("dragonite", "charizard", "pikachu")},
            "highValueCount": sum(row["flags"]["highValue"] for row in enriched), "top25": top}


def parse_benchmark_output(text: str) -> dict[str, Any]:
    planning = [float(value) for value in re.findall(r"Planning Time[\"']?\s*:\s*([0-9.]+)(?:\s*ms)?", text)]
    execution = [float(value) for value in re.findall(r"Execution Time[\"']?\s*:\s*([0-9.]+)(?:\s*ms)?", text)]
    return {"planningMs": planning, "executionMs": execution,
            "medianExecutionMs": statistics.median(execution) if execution else None,
            "rangeExecutionMs": [min(execution), max(execution)] if execution else None}


def performance_class(milliseconds: float) -> str:
    if milliseconds < 250:
        return "PASS_TARGET"
    if milliseconds <= 2000:
        return "PASS_ACCEPTABLE"
    return "FAIL_INTERACTIVE"


def architecture_decision(evidence: Mapping[str, Any]) -> dict[str, Any]:
    interval = list(evidence.get("intervalExecutionMs") or [])
    fact = list(evidence.get("factExecutionMs") or [])
    if len(interval) < 2 or len(fact) < 2 or not evidence.get("factBuildMs") or not evidence.get("storageRatio"):
        return {"decision": "BLOCKED_INSUFFICIENT_EVIDENCE",
                "criteria": "requires >=2 paired samples, fact build time, and storage ratio"}
    interval_median, fact_median = statistics.median(interval), statistics.median(fact)
    ratio = fact_median / interval_median if interval_median else 0
    storage_ratio = float(evidence["storageRatio"])
    if max(interval) <= 1000 and ratio >= 0.75:
        decision = "DECISION_A_INTERVALS"
    elif ratio <= 0.60 and max(fact) <= 1000 and storage_ratio <= 4.0:
        decision = "DECISION_B_DAILY_FACT"
    elif min(interval) < min(fact) and max(fact) < max(interval) and ratio <= 0.75:
        decision = "DECISION_C_HYBRID"
    else:
        decision = "BLOCKED_MIXED_OR_FAILED_GATES"
    return {"decision": decision, "intervalMedianMs": interval_median,
            "factMedianMs": fact_median, "factToIntervalRatio": ratio,
            "storageRatio": storage_ratio,
            "intervalClass": performance_class(interval_median),
            "factClass": performance_class(fact_median)}


def run_pilot(client: Any, pilot_key: str, *, commit: bool, verify_existing: bool = False,
              batch_size: int = 25) -> dict[str, Any]:
    from backend.scripts.backfill_market_explorer_variant_intervals import run_backfill
    pilot = PILOTS[pilot_key]
    authority = _paged(lambda: client.rpc("get_pokemon_canonical_card_variant_authority",
                                          {"p_set_ids": [pilot["setId"]]}))
    variants = sorted({str(row["card_variant_id"]) for row in authority})
    canonical = sorted({str(row["canonical_card_id"]) for row in authority})
    canonical_response = client.table("pokemon_canonical_cards").select("id", count="exact") \
        .eq("set_id", pilot["setId"]).limit(0).execute()
    canonical_count = int(canonical_response.count or 0)
    conditions = list(client.table("conditions").select("id").eq("name", "Near Mint")
                      .eq("abbreviation", "NM").execute().data or [])
    if len(conditions) != 1:
        return {"pilot": pilot, "commit": commit, "status": "FAIL",
                "blockingCondition": "Near Mint/NM authority is not unique"}
    nm_id = str(conditions[0]["id"])
    history_variants: set[str] = set()
    for batch in _chunks(variants):
        rows = _paged(lambda batch=batch: client.table("card_variant_price_observations")
                      .select("card_variant_id").in_("card_variant_id", batch)
                      .eq("condition_id", nm_id).gt("market_price", 0).eq("currency", "USD"))
        history_variants.update(str(row["card_variant_id"]) for row in rows)
    backfill = run_backfill(client, commit=commit, batch_size=batch_size, set_ids=[pilot["setId"]])
    inspect_intervals = commit or verify_existing
    interval_rows = (_paged(lambda: client.table("pokemon_card_variant_market_price_intervals")
                            .select("*").eq("set_id", pilot["setId"]).order("card_variant_id")
                            .order("valid_from")) if inspect_intervals else [])
    if inspect_intervals and interval_rows:
        observations: dict[str, Mapping[str, Any]] = {}
        observation_ids = sorted({str(row["observation_id"]) for row in interval_rows})
        for batch in _chunks(observation_ids):
            for row in _paged(lambda batch=batch: client.table("card_variant_price_observations")
                              .select("id,condition_id,currency,captured_at").in_("id", batch)):
                observations[str(row["id"])] = row
        interval_rows = [{**row,
                          "condition_ok": str(observations.get(str(row["observation_id"]), {}).get("condition_id")) == nm_id,
                          "currency_ok": str(observations.get(str(row["observation_id"]), {}).get("currency") or "").strip('"').upper() == "USD"}
                         for row in interval_rows]
    integrity = validate_intervals(interval_rows) if inspect_intervals else None
    editions = {label: sum(str(row.get("edition") or "").lower() == value for row in authority)
                for label, value in (("firstEdition", "1st-edition"), ("unlimited", "unlimited"))}
    editions["unspecified"] = sum(not row.get("edition") for row in authority)
    printings = {label: sum(str(row.get("printing_type") or "").lower() == label for row in authority)
                 for label in ("holo", "non-holo", "reverse-holo")}
    current_examples = []
    cohort = None
    parity = None
    if inspect_intervals:
        latest_by_variant = {}
        for row in interval_rows:
            variant_id = str(row["card_variant_id"])
            if row.get("valid_to") is None:
                latest_by_variant[variant_id] = row
        by_canonical: dict[str, list[Mapping[str, Any]]] = {}
        for row in authority:
            if str(row["card_variant_id"]) in latest_by_variant:
                by_canonical.setdefault(str(row["canonical_card_id"]), []).append(row)
        for rows in by_canonical.values():
            if len(rows) > 1:
                for row in rows:
                    latest = latest_by_variant[str(row["card_variant_id"])]
                    current_examples.append({"canonicalCardId": row["canonical_card_id"],
                        "cardName": row.get("card_name"), "cardNumber": row.get("card_number"),
                        "cardVariantId": row["card_variant_id"], "edition": row.get("edition"),
                        "printingType": row.get("printing_type"), "specialType": row.get("special_type"),
                        "latestNmPrice": latest.get("market_price")})
                if len(current_examples) >= 20:
                    break
        market_dates = _paged(lambda: client.table("pokemon_market_date_quality").select("market_date")
                              .eq("tcg", "pokemon").in_("status", ["READY", "LEGACY_VERIFIED"])
                              .order("market_date"))
        if market_dates:
            start_date, end_date = str(market_dates[0]["market_date"])[:10], str(market_dates[-1]["market_date"])[:10]
            from backend.db.services.pokemon_market_explorer_query_service import load_filtered_daily_cohort_rows
            cohort_rows, basket = load_filtered_daily_cohort_rows(
                client, [pilot["setId"]], start_date=start_date, end_date=end_date,
                card_ids=None, chunk_days=30,
            )
            cohort = {"rows": len(cohort_rows), "currentBasketRows": len(basket),
                      "eligibleConstituents": cohort_rows[-1]["eligibleUniverseCount"] if cohort_rows else 0,
                      "currentBasketValid": bool(cohort_rows) and
                      len(basket) == int(cohort_rows[-1]["constituentCount"] or 0)}
            by_canonical_all: dict[str, list[str]] = {}
            for row in authority:
                by_canonical_all.setdefault(str(row["canonical_card_id"]), []).append(str(row["card_variant_id"]))
            parity_cards = sorted(card_id for card_id, ids in by_canonical_all.items()
                                  if len(ids) == 1 and ids[0] in history_variants)
            if parity_cards:
                legacy_constituents = _paged(lambda: client.rpc("get_pokemon_cards_daily_constituents", {
                    "p_set_ids": [pilot["setId"]], "p_start_date": start_date, "p_end_date": end_date,
                    "p_card_ids": parity_cards,
                }))
                canonical_market_dates = [str(row["market_date"])[:10] for row in market_dates]
                old_rows = build_canonical_legacy_cohort(
                    legacy_constituents, canonical_market_dates,
                )
                new_rows = list(client.rpc("get_pokemon_market_explorer_filtered_cohort", {
                    "p_set_ids": [pilot["setId"]], "p_start_date": start_date, "p_end_date": end_date,
                    "p_card_ids": parity_cards, "p_segment_ids": None, "p_pokemon_ids": None,
                    "p_price_segment_ids": None, "p_release_age_cohort_ids": None, "p_top_n": None,
                }).execute().data or [])
                parity = compare_parity(old_rows, new_rows)
            else:
                parity = {"status": "FAIL", "reason": "no one-variant compatibility cohort"}
        else:
            cohort = {"rows": 0, "currentBasketValid": False}
            parity = {"status": "FAIL", "reason": "no canonical Market dates"}
    pilot_failed = bool(backfill.get("failures")) or (
        integrity is not None and any(integrity.values())) or (
        inspect_intervals and (not cohort or not cohort.get("currentBasketValid") or parity.get("status") != "PASS"))
    return {"pilot": pilot, "commit": commit, "canonicalCards": canonical_count,
            "canonicalCardsResolved": len(canonical),
            "variants": len(variants), "variantsWithNmUsdHistory": len(history_variants),
            "backfill": backfill, "intervalRows": len(interval_rows),
            "distinctIntervalVariants": len({str(row.get("card_variant_id")) for row in interval_rows}),
            "integrity": integrity, "variantDistribution": {**editions, **printings,
            "specialTypes": sum(bool(row.get("special_type")) for row in authority)},
            "multiVariantCurrentExamples": current_examples[:25],
            "cohort": cohort, "legacyParity": parity,
            "status": "FAIL" if pilot_failed else "PASS"}


def write_artifacts(report: Mapping[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "acceptance.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    lines = ["# Market Explorer acceptance", "", f"- Status: **{report.get('status')}**",
             f"- Git SHA: `{report.get('gitSha')}`", f"- Mode: `{report.get('mode')}`",
             f"- Environment: `{report.get('environmentLabel')}`", "", "## Checks", ""]
    for item in report.get("checks") or []:
        lines.append(f"- **{item['status']}** `{item['name']}` — {item['detail']}")
    (directory / "acceptance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--pilot", choices=sorted(PILOTS))
    modes.add_argument("--benchmark", action="store_true")
    modes.add_argument("--coverage", action="store_true")
    modes.add_argument("--full-acceptance", action="store_true")
    write_mode = parser.add_mutually_exclusive_group()
    write_mode.add_argument("--commit", action="store_true", help="Allow only the selected pilot's bounded backfill.")
    write_mode.add_argument("--verify-existing", action="store_true", help="Inspect an already-populated pilot without writes.")
    parser.add_argument("--database-url", help="Direct PostgreSQL URL for catalog/EXPLAIN; never persisted.")
    parser.add_argument("--environment-label", default="unspecified")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--artifact-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.commit and not (args.pilot or args.full_acceptance):
        raise SystemExit("--commit is valid only with --pilot or --full-acceptance")
    if args.verify_existing and not (args.pilot or args.full_acceptance):
        raise SystemExit("--verify-existing is valid only with --pilot or --full-acceptance")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be positive")
    from backend.db.clients.supabase_client import create_service_role_client
    client = create_service_role_client()
    mode = "preflight" if args.preflight else (f"pilot:{args.pilot}" if args.pilot else
           "benchmark" if args.benchmark else "coverage" if args.coverage else "full-acceptance")
    started = time.perf_counter()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = args.artifact_dir or ARTIFACT_ROOT / timestamp
    catalog = None
    catalog_error = None
    if args.database_url:
        try:
            catalog = load_catalog_evidence(args.database_url)
        except Exception as exc:
            catalog_error = safe_error(exc, args.database_url)
    preflight = run_preflight(client, catalog=catalog)
    if catalog_error:
        preflight["checks"].append(check("catalog:connection", "BLOCKED",
                                                "direct PostgreSQL catalog query failed", catalog_error))
        preflight["status"] = aggregate_status(preflight["checks"])
    report: dict[str, Any] = {
        "schemaVersion": "market-explorer-acceptance-v1", "mode": mode,
        "gitSha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "queryContractVersion": QUERY_CONTRACT_VERSION, "serviceVersion": SERVICE_VERSION,
        "migrationVersion": MIGRATION_VERSION, "environmentLabel": args.environment_label,
        "databaseIdentity": "redacted", "exactCommand": redacted_command(sys.argv),
        "setIdsTested": [], "checks": preflight["checks"], "preflight": preflight,
    }
    # Any FAIL blocks all later phases. BLOCKED catalog checks permit a REST
    # preflight report but never permit writes or benchmark acceptance.
    if args.pilot or args.full_acceptance:
        if preflight["status"] != "PASS":
            report["blockingCondition"] = "preflight must PASS before any pilot"
        else:
            selected = [args.pilot] if args.pilot else ["celebrations", "fossil"]
            report["pilots"] = []
            for pilot_key in selected:
                result = run_pilot(client, pilot_key, commit=bool(args.commit),
                                   verify_existing=bool(args.verify_existing), batch_size=args.batch_size)
                report["pilots"].append(result)
                report["setIdsTested"].append(PILOTS[pilot_key]["setId"])
                if result["status"] != "PASS":
                    report["blockingCondition"] = f"pilot {pilot_key} failed; later phases stopped"
                    break
            if args.full_acceptance and not report.get("blockingCondition"):
                from backend.scripts.audit_market_explorer_variant_identity import audit
                report["coverage"] = audit(client)
                if args.database_url:
                    try:
                        report["benchmark"] = run_temp_benchmark(args.database_url, artifact_dir)
                        if report["benchmark"]["status"] != "PASS":
                            report["blockingCondition"] = "architecture benchmark did not clear decision gates"
                    except Exception as exc:
                        report["benchmark"] = {"status": "FAIL", "reason": safe_error(exc, args.database_url)}
                        report["blockingCondition"] = "TEMP benchmark failed"
                else:
                    report["benchmark"] = {"status": "BLOCKED", "reason": "--database-url is required"}
                    report["blockingCondition"] = "direct PostgreSQL benchmark access unavailable"
    if args.benchmark:
        if preflight["status"] != "PASS":
            report["benchmark"] = {"status": "BLOCKED", "reason": "preflight must PASS"}
        elif not args.database_url:
            report["benchmark"] = {"status": "BLOCKED", "reason": "--database-url is required"}
        else:
            try:
                report["benchmark"] = run_temp_benchmark(args.database_url, artifact_dir)
            except Exception as exc:
                report["benchmark"] = {"status": "FAIL", "reason": safe_error(exc, args.database_url)}
    if args.coverage:
        from backend.scripts.audit_market_explorer_variant_identity import audit
        identity = audit(client)
        report["coverage"] = identity
    report["status"] = "FAIL" if any(item["status"] == "FAIL" for item in report["checks"]) else (
        "BLOCKED" if report.get("blockingCondition") or any(item["status"] == "BLOCKED" for item in report["checks"])
        else "PASS")
    report["elapsedSeconds"] = round(time.perf_counter() - started, 3)
    write_artifacts(report, artifact_dir)
    print(json.dumps({"status": report["status"], "artifactDir": str(artifact_dir),
                      "blockingCondition": report.get("blockingCondition")}, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
