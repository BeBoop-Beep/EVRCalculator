"""Persistence bridge: Pokémon Trends V2 anchor-ladder checkpoint -> Collector source-run lineage.

Scope (see docs/research collector_v6 persistence-bridge task): this script ONLY
bridges the already-completed local capture
(backend/artifacts/collector_v6_redesign_research/trends_v2_capture/checkpoint_rows.jsonl)
into the existing generic Collector source-run lifecycle
(``pokemon_collector_source_runs`` + ``pokemon_collector_entity_observations``).

It does NOT: run new Trends queries, rebuild the corrected Collector Appeal
composite, create a Collector model run, or touch Trainer/Artist evidence.

Architecture decision (Phase 5/6 of the owning task):
  OPTION A -- reuse ``pokemon_collector_entity_observations`` directly. Verified
  (read-only) against the live schema before choosing this:
    * ``pokemon_collector_entity_reference.entity_type`` CHECK constraint is
      ``in ('pokemon','trainer','artist')`` -- Pokémon are ALREADY a first-class
      entity_type, not a Trainer/Artist-only concept. In the connected project,
      1,025 rows exist with entity_type='pokemon', one per pokemon_reference row
      (canonical_key ``pokemon:<pokedex_number>``), matching the checkpoint's
      1,025 unique subject_id/pokedex_number values exactly.
    * ``dimension_key`` on the observations table is free text (no CHECK/enum) --
      open for a new ``pokemon_search_interest_v2`` value alongside the existing
      ``trainer_search_interest`` / ``artist_search_interest`` rows.
    * ``raw_row_json`` is an open jsonb provenance column -- sufficient to carry
      every anchor-ladder audit field (Phase 3 contract) without a new table.
    * The observations table is already trigger-guarded append-only
      (``trg_pokemon_collector_entity_observations_append_only``), already has a
      per-run uniqueness index on (source_run_id, dimension_key, external_entity_key),
      and is already covered by the existing freshness/health views
      (``pokemon_collector_source_run_health_v``,
      ``pokemon_collector_source_latest_valid_v``,
      ``is_pokemon_collector_source_refresh_due``). No schema changes needed.
  Rejected:
    OPTION B (generic row + additive 1:1 provenance table) -- unnecessary; the
      existing raw_row_json jsonb column already has full capacity for the V2
      audit contract, so a second table would only add join complexity with no
      semantic benefit.
    OPTION C (new Pokémon-specific observation table) -- unnecessary and
      explicitly disallowed unless entity_observations is proven trainer/artist-
      only; it is not (see above). A new table would also require its own FK to
      pokemon_collector_source_runs, duplicating machinery that already exists.
    A second source-run table (e.g. ``pokemon_trends_source_runs``) -- explicitly
      disallowed by the owning task's guardrails; ``pokemon_collector_source_runs``
      is reused unmodified.

No production DB writes happen from this script unless invoked with BOTH
``--commit`` and ``--i-understand-this-writes-to-production``. Default mode is
always a dry run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCE_NAME = "google_trends_pokemon_v2"
SOURCE_KIND = "search_interest"
DIMENSION_KEY = "pokemon_search_interest_v2"
INGEST_CODE_VERSION = "ingest_pokemon_trends_v2_source_run_r1"

EXPECTED_MANIFEST_VERSION = "pokemon_trends_anchor_ladder_manifest_v1"
EXPECTED_CODE_VERSION = "capture_pokemon_trends_anchor_ladder_v2_r1"
EXPECTED_TIMEFRAME = "today 1-m"
EXPECTED_GEO = "US"
EXPECTED_SUBJECT_COUNT = 1025

KNOWN_ANCHORS = {"Purugly", "Stunky", "Torkoal", "Lucario", "Charizard", "Pikachu"}

# Phase 4 classification semantics -- explicit, versioned treatment. Do not
# convert FAILED/MISSING to numeric zero anywhere below.
USABLE_NUMERIC_CLASSIFICATIONS = {"SCORED", "scored_zero_high_confidence"}
EXPLICIT_UNAVAILABLE_CLASSIFICATIONS = {"failed", "missing_evidence"}
ALL_KNOWN_CLASSIFICATIONS = USABLE_NUMERIC_CLASSIFICATIONS | EXPLICIT_UNAVAILABLE_CLASSIFICATIONS

CHECKPOINT_ROWS_PATH = (
    ROOT / "backend/artifacts/collector_v6_redesign_research/trends_v2_capture/checkpoint_rows.jsonl"
)
CHECKPOINT_HEADER_PATH = (
    ROOT / "backend/artifacts/collector_v6_redesign_research/trends_v2_capture/checkpoint_header.json"
)


class ValidationError(RuntimeError):
    """A checkpoint failed one of the Phase 9 source-run validation rules."""


@dataclass
class LoadedCheckpoint:
    header: dict
    rows: List[dict]


def load_checkpoint(rows_path: Path, header_path: Path) -> LoadedCheckpoint:
    if not rows_path.exists():
        raise ValidationError(f"checkpoint rows file not found: {rows_path}")
    if not header_path.exists():
        raise ValidationError(f"checkpoint header file not found: {header_path}")
    header = json.loads(header_path.read_text(encoding="utf-8"))
    rows: List[dict] = []
    with open(rows_path, "r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValidationError(f"checkpoint row {line_no} is not valid JSON: {exc}") from exc
    return LoadedCheckpoint(header=header, rows=rows)


def capture_identity(header: dict) -> str:
    """Immutable capture identity (Phase 8) used for idempotency detection.

    Built from fields that uniquely pin *this* completed capture: manifest
    fingerprint, capture code version, timeframe, and geo. Two independent
    captures of the same subjects with the same manifest/version/query
    contract are, by definition, the same logical capture for idempotency
    purposes -- a second run against the same header must be detected, not
    silently re-ingested.
    """
    payload = {
        "manifestFingerprint": header.get("manifest_fingerprint"),
        "codeVersion": header.get("code_version"),
        "timeframe": header.get("timeframe"),
        "geo": header.get("geo"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def validate_checkpoint(loaded: LoadedCheckpoint) -> dict:
    """Phase 9 source-run validation. Raises ValidationError on any hard failure.

    Returns a report dict of counts/classification breakdowns for the caller
    (dry-run report / commit diagnostics) to reuse verbatim.
    """
    header = loaded.header
    rows = loaded.rows

    if header.get("manifest_fingerprint") != "009418a05f6b9631":
        raise ValidationError(
            f"unexpected manifest_fingerprint={header.get('manifest_fingerprint')!r}; "
            "this ingestion path is pinned to the reviewed capture"
        )
    if header.get("code_version") != EXPECTED_CODE_VERSION:
        raise ValidationError(f"unexpected header code_version={header.get('code_version')!r}")
    if header.get("timeframe") != EXPECTED_TIMEFRAME:
        raise ValidationError(f"unexpected timeframe={header.get('timeframe')!r}")
    if header.get("geo") != EXPECTED_GEO:
        raise ValidationError(f"unexpected geo={header.get('geo')!r}")

    if len(rows) != EXPECTED_SUBJECT_COUNT:
        raise ValidationError(f"expected {EXPECTED_SUBJECT_COUNT} rows, found {len(rows)}")

    seen_subjects: Dict[int, dict] = {}
    manifest_versions = set()
    code_versions = set()
    classifications: Dict[str, int] = {}
    anchor_distribution: Dict[str, int] = {}
    unavailable_count = 0
    price_keys_found = []

    for idx, row in enumerate(rows, start=1):
        subject_id = row.get("subject_id")
        if subject_id is None:
            raise ValidationError(f"row {idx} is missing subject_id (Pokémon identity)")
        if subject_id in seen_subjects:
            raise ValidationError(f"duplicate subject_id={subject_id} (rows {seen_subjects[subject_id]} and {idx})")
        seen_subjects[subject_id] = idx

        if not row.get("pokemon_name") or row.get("pokedex_number") is None:
            raise ValidationError(f"row {idx} (subject_id={subject_id}) missing Pokémon identity fields")

        manifest_versions.add(row.get("manifest_version"))
        code_versions.add(row.get("code_version"))

        classification = row.get("classification")
        if classification not in ALL_KNOWN_CLASSIFICATIONS:
            raise ValidationError(
                f"row {idx} (subject_id={subject_id}) has unknown classification={classification!r}"
            )
        classifications[classification] = classifications.get(classification, 0) + 1

        anchor = row.get("assigned_anchor")
        if anchor is not None and anchor not in KNOWN_ANCHORS:
            raise ValidationError(f"row {idx} (subject_id={subject_id}) has unknown anchor identity={anchor!r}")
        if anchor is not None:
            anchor_distribution[anchor] = anchor_distribution.get(anchor, 0) + 1

        if classification in USABLE_NUMERIC_CLASSIFICATIONS:
            gr = row.get("global_relative")
            if gr is None:
                raise ValidationError(
                    f"row {idx} (subject_id={subject_id}) classification={classification} but global_relative is null"
                )
            try:
                gr_f = float(gr)
            except (TypeError, ValueError):
                raise ValidationError(
                    f"row {idx} (subject_id={subject_id}) has non-numeric calibrated score {gr!r}"
                ) from None
            if gr_f != gr_f or gr_f in (float("inf"), float("-inf")):  # NaN/inf check
                raise ValidationError(
                    f"row {idx} (subject_id={subject_id}) has a non-finite calibrated score {gr!r}"
                )
        else:
            unavailable_count += 1
            if row.get("global_relative") is not None:
                raise ValidationError(
                    f"row {idx} (subject_id={subject_id}) classification={classification} "
                    "must not carry a numeric global_relative value (would silently coerce failure to a score)"
                )

        # Price contamination check: no price-shaped keys anywhere in the row.
        for key in row.keys():
            lowered = key.lower()
            if "price" in lowered or "cost_basis" in lowered or "usd" in lowered:
                price_keys_found.append((idx, key))

    if price_keys_found:
        raise ValidationError(f"price-contaminated checkpoint fields found: {price_keys_found[:5]}")

    if manifest_versions != {EXPECTED_MANIFEST_VERSION}:
        raise ValidationError(f"non-uniform or unexpected manifest_version values: {manifest_versions}")
    if code_versions != {EXPECTED_CODE_VERSION}:
        raise ValidationError(f"non-uniform or unexpected code_version values: {code_versions}")

    if len(seen_subjects) != EXPECTED_SUBJECT_COUNT:
        raise ValidationError(
            f"expected {EXPECTED_SUBJECT_COUNT} unique subjects, found {len(seen_subjects)}"
        )

    usable = sum(classifications.get(c, 0) for c in USABLE_NUMERIC_CLASSIFICATIONS)
    failed = classifications.get("failed", 0)
    missing = classifications.get("missing_evidence", 0)

    return {
        "totalRows": len(rows),
        "uniqueSubjects": len(seen_subjects),
        "classifications": classifications,
        "usableScoredRows": usable,
        "failedRows": failed,
        "missingRows": missing,
        "unavailableRows": unavailable_count,
        "anchorDistribution": anchor_distribution,
        "manifestVersion": EXPECTED_MANIFEST_VERSION,
        "codeVersion": EXPECTED_CODE_VERSION,
    }


def build_observation_row(source_run_id: Optional[str], entity_id: Optional[str], row: dict) -> dict:
    """Phase 3 persisted evidence contract for one checkpoint row.

    Preserves the full audit trail in ``raw_row_json`` -- source_run_id,
    Pokémon identity, calibrated value, anchor identity/rung, raw
    target/anchor measurements, terminal classification, retry count,
    escalation path, manifest/version identity, timeframe/geo/query
    settings, and captured timestamp -- never only ``pokemon_id + score``.
    """
    classification = row["classification"]
    is_usable = classification in USABLE_NUMERIC_CLASSIFICATIONS
    global_relative = row.get("global_relative")
    captured_iso = None
    if row.get("timestamp") is not None:
        captured_iso = datetime.fromtimestamp(float(row["timestamp"]), tz=timezone.utc).isoformat()

    return {
        "source_run_id": source_run_id,
        "collector_entity_id": entity_id,
        "dimension_key": DIMENSION_KEY,
        "raw_entity_name": row["pokemon_name"],
        "external_entity_key": f"pokedex:{row['pokedex_number']}",
        "raw_rank": None,
        "raw_vote_count": None,
        "raw_score": None,
        "raw_value": row.get("raw_target"),
        "normalized_observation_score": (
            min(100.0, max(0.0, float(global_relative))) if is_usable and global_relative is not None else None
        ),
        "match_status": "matched" if entity_id is not None else "unmatched",
        "match_confidence": 1.0 if entity_id is not None else None,
        "source_detail_url": None,
        "raw_row_json": {
            "subjectId": row["subject_id"],
            "pokedexNumber": row["pokedex_number"],
            "pokemonName": row["pokemon_name"],
            "assignedAnchor": row.get("assigned_anchor"),
            "escalated": row.get("escalated"),
            "rawTarget": row.get("raw_target"),
            "rawAnchor": row.get("raw_anchor"),
            "globalRelative": global_relative,
            "classification": classification,
            "retryCount": row.get("retry_count"),
            "failureDetail": row.get("failure_detail"),
            "manifestVersion": row.get("manifest_version"),
            "captureCodeVersion": row.get("code_version"),
            "ingestCodeVersion": INGEST_CODE_VERSION,
            "calibrationAlgorithm": "pokemon_trends_anchor_ladder_v2",
            "querySettings": row.get("query_settings"),
            "capturedAt": captured_iso,
        },
    }


def resolve_entities(supabase, rows: List[dict]) -> Dict[int, dict]:
    """Map pokedex_number -> collector_entity_reference row (entity_type='pokemon')."""
    pokedex_numbers = sorted({r["pokedex_number"] for r in rows})
    by_pokedex: Dict[int, dict] = {}
    start = 0
    while start < len(pokedex_numbers):
        chunk = pokedex_numbers[start : start + 500]
        resp = (
            supabase.table("pokemon_collector_entity_reference")
            .select("id,pokemon_reference_id,active")
            .eq("entity_type", "pokemon")
            .in_("pokemon_reference_id", chunk)
            .execute()
        )
        for entity in resp.data:
            by_pokedex[entity["pokemon_reference_id"]] = entity
        start += 500
    return by_pokedex


def find_existing_source_run(supabase, capture_hash: str) -> Optional[dict]:
    resp = (
        supabase.table("pokemon_collector_source_runs")
        .select("id,status,source_fingerprint,run_key,completed_at")
        .eq("source_name", SOURCE_NAME)
        .eq("source_fingerprint", capture_hash)
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


def plan_ingestion(loaded: LoadedCheckpoint, report: dict, entity_map: Optional[Dict[int, dict]]) -> dict:
    matched = 0
    unmatched = 0
    for row in loaded.rows:
        if entity_map is not None and row["pokedex_number"] in entity_map:
            matched += 1
        else:
            unmatched += 1
    return {
        "plannedTables": ["pokemon_collector_source_runs", "pokemon_collector_entity_observations"],
        "plannedSourceRun": {
            "source_name": SOURCE_NAME,
            "source_kind": SOURCE_KIND,
            "capture_version": EXPECTED_CODE_VERSION,
            "geo": EXPECTED_GEO,
        },
        "plannedObservationCount": report["totalRows"],
        "dimensionKey": DIMENSION_KEY,
        "entitiesMatched": matched,
        "entitiesUnmatched": unmatched,
        "validationOutcome": "valid" if unmatched == 0 else "valid_with_unmatched_entities",
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT_ROWS_PATH)
    parser.add_argument("--header", type=Path, default=CHECKPOINT_HEADER_PATH)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Attempt a real write. Also requires --i-understand-this-writes-to-production.",
    )
    parser.add_argument(
        "--i-understand-this-writes-to-production",
        action="store_true",
        dest="confirm_production_write",
        help="Second explicit confirmation flag required alongside --commit.",
    )
    parser.add_argument(
        "--skip-entity-lookup",
        action="store_true",
        help="For offline dry runs / tests: skip the DB entity-resolution read.",
    )
    args = parser.parse_args(argv)

    loaded = load_checkpoint(args.checkpoint, args.header)
    report = validate_checkpoint(loaded)
    capture_hash = capture_identity(loaded.header)

    result = {
        "captureIdentity": capture_hash,
        "sourceName": SOURCE_NAME,
        "sourceKind": SOURCE_KIND,
        "dimensionKey": DIMENSION_KEY,
        "manifestFingerprint": loaded.header.get("manifest_fingerprint"),
        "validation": report,
    }

    entity_map: Optional[Dict[int, dict]] = None
    supabase = None
    if not args.skip_entity_lookup:
        from backend.db.clients.supabase_client import supabase as _supabase

        supabase = _supabase
        entity_map = resolve_entities(supabase, loaded.rows)

    plan = plan_ingestion(loaded, report, entity_map)
    result["plan"] = plan

    if not args.commit:
        result["mode"] = "dry_run"
        result["mutationsPerformed"] = 0
        print(json.dumps(result, indent=2, default=str))
        return 0

    if not args.confirm_production_write:
        raise SystemExit(
            "--commit requires --i-understand-this-writes-to-production as an explicit second "
            "confirmation. Refusing to write. (This task is design/dry-run only; production "
            "execution is a separately authorized follow-up.)"
        )

    assert supabase is not None  # commit mode always resolves entities

    existing = find_existing_source_run(supabase, capture_hash)
    if existing is not None:
        result["mode"] = "idempotent_skip"
        result["existingSourceRunId"] = existing["id"]
        result["mutationsPerformed"] = 0
        print(json.dumps(result, indent=2, default=str))
        return 0

    now = datetime.now(timezone.utc).isoformat()
    run_key = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{capture_hash[:12]}"
    run = (
        supabase.table("pokemon_collector_source_runs")
        .insert(
            {
                "source_name": SOURCE_NAME,
                "source_kind": SOURCE_KIND,
                "run_key": run_key,
                "capture_version": EXPECTED_CODE_VERSION,
                "status": "running",
                "source_url": "https://trends.google.com/trends/",
                "geo": EXPECTED_GEO,
                "anchor_term": None,
                "source_fingerprint": capture_hash,
                "raw_payload_json": {
                    "manifestFingerprint": loaded.header.get("manifest_fingerprint"),
                    "manifestVersion": report["manifestVersion"],
                    "timeframe": loaded.header.get("timeframe"),
                    "geo": loaded.header.get("geo"),
                    "checkpointStartedAt": loaded.header.get("started_at"),
                    "ingestCodeVersion": INGEST_CODE_VERSION,
                },
            }
        )
        .execute()
        .data[0]
    )
    run_id = run["id"]

    observation_rows = [
        build_observation_row(run_id, (entity_map or {}).get(row["pokedex_number"], {}).get("id"), row)
        for row in loaded.rows
    ]
    supabase.table("pokemon_collector_entity_observations").insert(observation_rows).execute()

    usable = report["usableScoredRows"]
    total = report["totalRows"]
    status = "success" if usable == total else "partial_failure" if usable else "failed"

    supabase.table("pokemon_collector_source_runs").update(
        {
            "status": status,
            "completed_at": now,
            "captured_at": now,
            "item_count": len(observation_rows),
            "diagnostics_json": {**report, "captureIdentity": capture_hash},
        }
    ).eq("id", run_id).execute()

    result["mode"] = "committed"
    result["sourceRunId"] = run_id
    result["status"] = status
    result["mutationsPerformed"] = 1 + len(observation_rows)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
