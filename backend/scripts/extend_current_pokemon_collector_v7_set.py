"""Safely add or refresh one root set in the current frozen Collector Appeal V7 cohort.

Historical V7 members are rebuilt from the frozen artifact with the exact current
source authorities. Only explicitly requested additive root sets are projected from
live canonical/desirability inputs. Publication remains atomic with a validated
set-page generation; Market/Explorer publication is intentionally untouched.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.build_pokemon_collector_appeal_v7_expanded import (
    FROZEN_FORMULA_FINGERPRINT,
    MODEL_VERSION,
    build as build_v7,
    persist_built_model,
)

V7_PREFIX = "pokemon_collector_appeal_v7_"
SET_SCORE_EPSILON = 1e-9


def _paged(factory, size: int = 500) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        page = list(factory().range(start, start + size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < size:
            return rows
        start += size


def _current_authority(client: Any) -> Dict[str, Any]:
    pointer_rows = list(
        client.table("pokemon_collector_appeal_current")
        .select("model_run_id,model_version,as_of_date")
        .eq("scope", "pokemon")
        .limit(1)
        .execute()
        .data
        or []
    )
    if not pointer_rows:
        raise RuntimeError("current Collector Appeal pointer is missing")
    pointer = pointer_rows[0]
    if not str(pointer.get("model_version") or "").startswith(V7_PREFIX):
        raise RuntimeError("current Collector Appeal authority is not V7")
    run_rows = list(
        client.table("pokemon_collector_appeal_model_runs")
        .select(
            "id,model_version,status,validation_passed,source_run_ids,"
            "input_fingerprint,scoring_config_json"
        )
        .eq("id", str(pointer["model_run_id"]))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not run_rows:
        raise RuntimeError("current Collector V7 model run is missing")
    run = run_rows[0]
    if run.get("status") != "published" or run.get("validation_passed") is not True:
        raise RuntimeError("current Collector V7 model run is not published/validated")

    config = dict(run.get("scoring_config_json") or {})
    authority = dict(config.get("sourceAuthority") or {})
    if not authority:
        ids = [str(value) for value in (run.get("source_run_ids") or [])]
        if len(ids) != 6:
            raise RuntimeError("current Collector V7 does not expose six-source authority")
        authority = dict(
            zip(
                ("pokemonTrends", "trainer12m", "trainer5y", "playability", "artist12m", "artist5y"),
                ids,
            )
        )
    required = {"pokemonTrends", "trainer12m", "trainer5y", "playability", "artist12m", "artist5y"}
    if set(authority) != required or any(not authority[key] for key in required):
        raise RuntimeError("current Collector V7 sourceAuthority is incomplete")
    return {"pointer": pointer, "run": run, "sourceAuthority": authority}


def _resolve_target(client: Any, canonical_key: str) -> Dict[str, Any]:
    rows = list(
        client.table("sets")
        .select(
            "id,name,canonical_key,catalog_only,is_subset,parent_opening_set_id,"
            "ready_for_daily_scrape,supports_opening_simulation"
        )
        .eq("canonical_key", canonical_key)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise RuntimeError(f"unknown Pokemon set canonical key {canonical_key!r}")
    return dict(rows[0])


def _current_set_rows(client: Any, run_id: str) -> Dict[str, Dict[str, Any]]:
    rows = _paged(
        lambda: client.table("pokemon_set_collector_desirability_scores")
        .select("set_id,collector_desirability_score,collector_desirability_rank")
        .eq("model_run_id", run_id)
    )
    return {str(row["set_id"]): row for row in rows}


def _current_appeal_rows(client: Any, run_id: str) -> Dict[str, Dict[str, Any]]:
    rows = _paged(
        lambda: client.table("pokemon_set_collector_appeal_scores")
        .select("set_id,collector_appeal_score,score_status")
        .eq("model_run_id", run_id)
    )
    return {str(row["set_id"]): row for row in rows}


def _target_preflight(client: Any, target: Dict[str, Any]) -> Dict[str, Any]:
    set_id = str(target["id"])
    canonical = _paged(
        lambda: client.table("pokemon_canonical_cards")
        .select("id,supertype,source,image_small_url,image_large_url")
        .eq("set_id", set_id)
        .eq("catalog_role", "main")
        .eq("opening_eligible", True)
        .eq("canonical_review_status", "approved")
    )
    if not canonical:
        raise RuntimeError("target has no approved main/opening canonical cards")
    fallback = sum(str(row.get("source") or "") == "tcgplayer_cards_fallback" for row in canonical)
    missing_art = sum(not (row.get("image_small_url") or row.get("image_large_url")) for row in canonical)
    pokemon_ids = [
        str(row["id"])
        for row in canonical
        if str(row.get("supertype") or "").casefold() in {"pokémon", "pokemon"}
    ]
    linked: set[str] = set()
    for start in range(0, len(pokemon_ids), 200):
        page = (
            client.table("pokemon_card_desirability_links")
            .select("pokemon_canonical_card_id")
            .in_("pokemon_canonical_card_id", pokemon_ids[start:start + 200])
            .execute()
            .data
            or []
        )
        linked.update(str(row["pokemon_canonical_card_id"]) for row in page)
    missing_subjects = len(set(pokemon_ids) - linked)
    if fallback or missing_art or missing_subjects:
        raise RuntimeError(
            "target Collector preflight incomplete: "
            f"fallback={fallback} missing_art={missing_art} missing_pokemon_subjects={missing_subjects}"
        )
    return {
        "canonicalCards": len(canonical),
        "pokemonCards": len(pokemon_ids),
        "fallbackCards": fallback,
        "missingArtwork": missing_art,
        "missingPokemonSubjects": missing_subjects,
    }


def _assert_control_stability(
    *,
    target_set_id: str,
    current_sets: Dict[str, Dict[str, Any]],
    current_appeal: Dict[str, Dict[str, Any]],
    built: Dict[str, Any],
) -> Dict[str, Any]:
    new_sets = {str(row["set_id"]): row for row in built["sets"]}
    removed = sorted(set(current_sets) - set(new_sets))
    added = sorted(set(new_sets) - set(current_sets))
    if removed:
        raise RuntimeError(f"Collector cohort extension would remove current sets: {removed}")
    if any(set_id != target_set_id for set_id in added):
        raise RuntimeError(f"Collector cohort extension added unexpected sets: {added}")

    max_d_delta = 0.0
    max_appeal_delta = 0.0
    changed_controls = []
    for set_id, old in current_sets.items():
        if set_id == target_set_id:
            continue
        new = new_sets.get(set_id)
        if new is None:
            continue
        d_delta = abs(
            float(new.get("D_final") or 0.0)
            - float(old.get("collector_desirability_score") or 0.0)
        )
        old_appeal = (current_appeal.get(set_id) or {}).get("collector_appeal_score")
        new_appeal = new.get("collector_appeal")
        if old_appeal is None and new_appeal is None:
            appeal_delta = 0.0
        elif old_appeal is None or new_appeal is None:
            appeal_delta = float("inf")
        else:
            appeal_delta = abs(float(new_appeal) - float(old_appeal))
        max_d_delta = max(max_d_delta, d_delta)
        max_appeal_delta = max(max_appeal_delta, appeal_delta)
        if d_delta > SET_SCORE_EPSILON or appeal_delta > SET_SCORE_EPSILON:
            changed_controls.append(
                {
                    "setId": set_id,
                    "dDelta": d_delta,
                    "collectorAppealDelta": appeal_delta,
                }
            )
    if changed_controls:
        raise RuntimeError(
            "Collector V7 control scores changed during cohort extension: "
            + json.dumps(changed_controls[:10], sort_keys=True)
        )
    return {
        "currentSetCount": len(current_sets),
        "builtSetCount": len(new_sets),
        "addedSetIds": added,
        "maxControlDDelta": max_d_delta,
        "maxControlCollectorAppealDelta": max_appeal_delta,
    }


def _run_json(command: Iterable[str]) -> Dict[str, Any]:
    completed = subprocess.run(
        list(command),
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=True,
    )
    decoder = json.JSONDecoder()
    parsed = None
    for index, char in enumerate(completed.stdout):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(completed.stdout[index:])
        except json.JSONDecodeError:
            continue
    if parsed is None:
        raise RuntimeError(f"command emitted no JSON: {list(command)}")
    return parsed


def execute(client: Any, *, canonical_key: str, commit: bool, publish: bool) -> Dict[str, Any]:
    target = _resolve_target(client, canonical_key)
    if target.get("catalog_only") or target.get("is_subset"):
        return {
            "status": "not_applicable",
            "canonicalKey": canonical_key,
            "setId": str(target["id"]),
            "reason": "collector_v7_root_only",
            "mutationsPerformed": 0,
        }

    current = _current_authority(client)
    run_id = str(current["run"]["id"])
    authority = current["sourceAuthority"]
    preflight = _target_preflight(client, target)
    current_sets = _current_set_rows(client, run_id)
    current_appeal = _current_appeal_rows(client, run_id)

    built = build_v7(
        client,
        pokemon_trends_source_run_id=str(authority["pokemonTrends"]),
        trainer_12m_source_run_id=str(authority["trainer12m"]),
        trainer_5y_source_run_id=str(authority["trainer5y"]),
        playability_source_run_id=str(authority["playability"]),
        artist_12m_source_run_id=str(authority["artist12m"]),
        artist_5y_source_run_id=str(authority["artist5y"]),
        additional_set_ids=[str(target["id"])],
    )
    manifest = built.get("manifest") or {}
    if manifest.get("formulaFingerprint") != FROZEN_FORMULA_FINGERPRINT:
        raise RuntimeError("V7_FROZEN_FORMULA_DRIFT_BLOCKER")
    if manifest.get("modelVersion") != MODEL_VERSION:
        raise RuntimeError("Collector V7 model version drift")
    stability = _assert_control_stability(
        target_set_id=str(target["id"]),
        current_sets=current_sets,
        current_appeal=current_appeal,
        built=built,
    )
    target_set = next(
        (row for row in built["sets"] if str(row["set_id"]) == str(target["id"])),
        None,
    )
    if target_set is None:
        raise RuntimeError("target set missing from expanded Collector V7 build")

    report: Dict[str, Any] = {
        "status": "validated_dry_run" if not commit else "staged",
        "canonicalKey": canonical_key,
        "setId": str(target["id"]),
        "setName": target.get("name"),
        "currentModelRunId": run_id,
        "preflight": preflight,
        "stability": stability,
        "targetCollectorRosterDesirability": target_set.get("D_final"),
        "targetGeneralizedFrequency": target_set.get("F"),
        "targetCollectorAppeal": target_set.get("collector_appeal"),
        "targetStatus": "scored" if target_set.get("collector_appeal") is not None else "unavailable",
        "targetUnavailableReason": target_set.get("unavailable_reason"),
        "modelFingerprint": manifest.get("modelFingerprint"),
        "formulaFingerprint": manifest.get("formulaFingerprint"),
        "mutationsPerformed": 0,
    }
    if not commit:
        return report

    new_run_id, validation, created = persist_built_model(
        client, built, as_of_date=date.today().isoformat()
    )
    report.update(
        newModelRunId=new_run_id,
        modelCreated=created,
        validation=validation,
        mutationsPerformed=int(created),
    )
    if not publish:
        report["status"] = "validated_staged"
        return report

    if new_run_id == run_id:
        report["status"] = "already_current"
        return report

    page = _run_json(
        [
            sys.executable,
            str(ROOT / "backend/scripts/build_atomic_set_page_snapshot_generation.py"),
            "--write-stage",
            "--collector-authority",
            "model-run",
            "--collector-model-run-id",
            new_run_id,
            "--extra-fresh-set-id",
            str(target["id"]),
        ]
    )
    validation_report = page.get("validation") or {}
    if validation_report.get("passed") is not True:
        raise RuntimeError("expanded Collector set-page generation failed validation")
    generation_id = str(page.get("generationId") or "")
    if not generation_id:
        raise RuntimeError("expanded Collector set-page generation id missing")

    promoted = client.rpc(
        "promote_pokemon_collector_v7_with_set_page_generation",
        {"p_model_run_id": new_run_id, "p_generation_id": generation_id},
    ).execute().data
    history_rows = client.rpc(
        "append_current_collector_v7_history",
        {"p_as_of_date": date.today().isoformat()},
    ).execute().data

    cards_snapshot = _run_json(
        [
            sys.executable,
            str(ROOT / "backend/scripts/build_pokemon_set_cards_snapshots.py"),
            "--set-id",
            canonical_key,
            "--commit",
        ]
    )
    report.update(
        status="published",
        setPageGenerationId=generation_id,
        atomicPromotion=promoted,
        temporalHistoryRows=int(history_rows or 0),
        cardsSnapshot=cards_snapshot,
        mutationsPerformed=report["mutationsPerformed"] + 2 + int(history_rows or 0),
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", dest="canonical_key", required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.publish and not args.commit:
        parser.error("--publish requires --commit")

    load_dotenv(ROOT / "backend" / ".env", override=False)
    from backend.db.clients.supabase_client import supabase

    report = execute(
        supabase,
        canonical_key=args.canonical_key,
        commit=bool(args.commit),
        publish=bool(args.publish),
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
