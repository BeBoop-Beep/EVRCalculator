"""Recheck due catalog identities and refresh catalog-only sets when availability changes.

This is intentionally separate from the daily scrape cohort. Catalog-only/preorder
sets are excluded from the normal daily scraper, so a provider identity that was
onboarded sealed-only would otherwise stay sealed-only forever when TCGplayer later
publishes its card catalog.

The flow is bounded:
  recheck due identities -> refresh changed/lagging catalog sets only ->
  canonical-only projection -> targeted public snapshots.

Provider failures never trigger a refresh, and dry-run performs no DB/Git mutation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.run_pokemon_set_scrape import _load_backend_env
from backend.services.pokemon_set_onboarding_recheck_service import run_recheck

_PROVIDER_ID_RE = re.compile(r"/priceguide/set/(\d+)/")


def _provider_id_from_url(value: Any) -> Optional[str]:
    match = _PROVIDER_ID_RE.search(str(value or ""))
    return match.group(1) if match else None


def _catalog_state(client: Any) -> Dict[str, Dict[str, Any]]:
    rows = list(
        client.table("sets")
        .select("id,name,canonical_key,catalog_only,card_details_url,sealed_details_url")
        .eq("catalog_only", True)
        .execute()
        .data
        or []
    )
    by_provider: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        provider_ids = {
            value
            for value in (
                _provider_id_from_url(row.get("card_details_url")),
                _provider_id_from_url(row.get("sealed_details_url")),
            )
            if value
        }
        for provider_id in provider_ids:
            by_provider[provider_id] = dict(row)
    return by_provider


def _row_count(client: Any, table: str, set_id: str) -> int:
    return len(
        list(
            client.table(table)
            .select("id")
            .eq("set_id", set_id)
            .execute()
            .data
            or []
        )
    )


def _run(command: list[str]) -> Dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


def _planned_commands(canonical_key: str, *, has_processable_cards: bool) -> list[list[str]]:
    commands = [
        [
            sys.executable,
            "backend/scripts/run_pokemon_set_scrape.py",
            "--run",
            "--catalog-set",
            canonical_key,
        ]
    ]
    if has_processable_cards:
        commands.extend(
            [
                [
                    sys.executable,
                    "backend/scripts/build_pokemon_set_desirability_inputs.py",
                    "--set",
                    canonical_key,
                    "--commit",
                    "--canonical-only",
                ],
                [
                    sys.executable,
                    "backend/scripts/build_pokemon_set_cards_snapshots.py",
                    "--set-id",
                    canonical_key,
                    "--commit",
                ],
            ]
        )
    commands.extend(
        [
            [
                sys.executable,
                "backend/scripts/build_pokemon_set_sealed_market_snapshots.py",
                "--set-id",
                canonical_key,
                "--commit",
            ],
            [
                sys.executable,
                "backend/scripts/build_pokemon_set_page_snapshots.py",
                "--set-id",
                canonical_key,
                "--commit",
            ],
        ]
    )
    return commands


def run(*, commit: bool, limit: int, max_provider_requests: Optional[int]) -> Dict[str, Any]:
    from backend.db.clients.supabase_client import service_read_client

    recheck = run_recheck(
        commit=commit,
        limit=max(1, limit),
        max_provider_requests=max_provider_requests,
    )
    if recheck.get("status") != "ok":
        return {
            "status": "recheck_failed",
            "dry_run": not commit,
            "recheck": recheck,
            "refreshes": [],
        }

    catalog = _catalog_state(service_read_client)
    refreshes: list[Dict[str, Any]] = []
    critical_failures = 0

    for item in recheck.get("identities") or []:
        if item.get("provider_error"):
            continue
        provider_id = str(item.get("source_set_id") or "")
        set_row = catalog.get(provider_id)
        if not set_row:
            continue

        set_id = str(set_row["id"])
        canonical_key = str(set_row.get("canonical_key") or "")
        if not canonical_key:
            continue

        card_count = _row_count(service_read_client, "cards", set_id)
        canonical_count = _row_count(service_read_client, "pokemon_canonical_cards", set_id)
        sealed_count = _row_count(service_read_client, "sealed_products", set_id)
        processable = (item.get("card_quality") or {}).get("processable_card_listing_count")
        provider_sealed = item.get("sealed_listing_count")
        try:
            processable_count = int(processable) if processable is not None else 0
        except (TypeError, ValueError):
            processable_count = 0
        try:
            provider_sealed_count = int(provider_sealed) if provider_sealed is not None else 0
        except (TypeError, ValueError):
            provider_sealed_count = 0

        scrape_needed = bool(item.get("availability_changed"))
        if processable_count > card_count:
            scrape_needed = True
        if provider_sealed_count > sealed_count:
            scrape_needed = True
        canonical_needed = processable_count > 0 and canonical_count < max(card_count, processable_count)
        if not scrape_needed and not canonical_needed:
            continue

        commands = _planned_commands(
            canonical_key,
            has_processable_cards=processable_count > 0,
        )
        entry: Dict[str, Any] = {
            "source_set_id": provider_id,
            "set_id": set_id,
            "canonical_key": canonical_key,
            "availability_changed": bool(item.get("availability_changed")),
            "before": {
                "cards": card_count,
                "canonical_cards": canonical_count,
                "sealed_products": sealed_count,
            },
            "provider": {
                "processable_cards": processable_count,
                "sealed_listings": provider_sealed_count,
            },
            "planned_commands": commands,
            "results": [],
        }
        refreshes.append(entry)

        if not commit:
            entry["status"] = "would_refresh"
            continue

        # Scrape is the critical mutation. If it fails, do not project stale
        # downstream snapshots and leave the mismatch detectable on the next run.
        if scrape_needed:
            scrape_result = _run(commands[0])
            entry["results"].append(scrape_result)
            if scrape_result["exit_code"] != 0:
                entry["status"] = "scrape_failed"
                critical_failures += 1
                continue

        start_index = 1
        if not scrape_needed:
            # Skip the first planned command (catalog scrape) when only canonical
            # projection was lagging.
            start_index = 1

        snapshot_warnings = 0
        for command in commands[start_index:]:
            result = _run(command)
            entry["results"].append(result)
            if result["exit_code"] != 0:
                # Canonical projection is critical when processable cards exist.
                if "build_pokemon_set_desirability_inputs.py" in command:
                    entry["status"] = "canonical_projection_failed"
                    critical_failures += 1
                    break
                snapshot_warnings += 1
        else:
            entry["status"] = (
                "refreshed_with_snapshot_warnings" if snapshot_warnings else "refreshed"
            )

    return {
        "status": "ok" if critical_failures == 0 else "failed",
        "dry_run": not commit,
        "critical_failures": critical_failures,
        "recheck": recheck,
        "refreshes": refreshes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--max-provider-requests", type=int, default=None)
    args = parser.parse_args()
    _load_backend_env()

    report = run(
        commit=bool(args.commit),
        limit=max(1, args.limit),
        max_provider_requests=args.max_provider_requests,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
