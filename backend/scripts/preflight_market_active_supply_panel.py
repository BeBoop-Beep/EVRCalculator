"""Fail-closed activation preflight for the 207-card active-supply panel."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from backend.pricing_pipeline.active_supply_credentials import load_active_supply_credentials
from backend.pricing_pipeline.ebay_credentials import parse_env_file
from backend.pricing_pipeline.pkmnprices_credentials import load_pkmnprices_credentials
from backend.scripts.run_market_active_supply_snapshot import (
    FULL_PANEL_CREDIT_CAP, FULL_PANEL_TARGETS, MANIFEST_PATH, preflight,
)

REQUIRED_INDEXES = {
    "market_active_supply_snapshots_canonical_observed_idx",
    "market_active_supply_snapshots_variant_idx",
    "pkmnprices_card_identity_v1_canonical_idx",
}


def exact_identity_counts(db: Any, targets: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
    resolved = 0
    mismatches: list[str] = []
    for target in targets:
        rows = (db.table("pkmnprices_card_identity_v1")
                .select("provider_card_id,canonical_card_id,tcgplayer_product_id,language")
                .eq("canonical_card_id", target["canonical_card_id"])
                .eq("language", "English").limit(1).execute().data or [])
        if not rows:
            continue
        row = rows[0]
        if (str(row.get("canonical_card_id")) == str(target["canonical_card_id"])
                and str(row.get("tcgplayer_product_id")) == str(target["tcgplayer_product_id"])
                and str(row.get("language")) == "English"):
            resolved += 1
        else:
            mismatches.append(str(target["card_variant_id"]))
    return resolved, len(targets) - resolved, mismatches


def inspect_postgres(dsn: str) -> dict[str, Any]:
    import psycopg
    with psycopg.connect(dsn, connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute("""select indexname from pg_indexes where schemaname='public'
                       and tablename in ('market_active_supply_snapshots_v1','pkmnprices_card_identity_v1')""")
        indexes = {row[0] for row in cur.fetchall()}
        cur.execute("""select column_name from information_schema.columns
                       where table_schema='public' and table_name='market_active_supply_listing_observations_v1'""")
        columns = {row[0] for row in cur.fetchall()}
    missing_indexes = sorted(REQUIRED_INDEXES - indexes)
    required_columns = {"landed_price", "listing_updated_at", "provider_snapshot_at", "seller_rating", "seller_sales_count"}
    return {"missing_indexes": missing_indexes, "missing_typed_columns": sorted(required_columns - columns)}


def run_preflight(db: Any, *, dsn: str, source_commit_sha: str) -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    seller = load_active_supply_credentials()
    provider = load_pkmnprices_credentials(allow_frontend_fallback=False)
    resolved, unresolved, mismatches = exact_identity_counts(db, manifest["rows"])
    plan = preflight(target_limit=FULL_PANEL_TARGETS, offer_limit=19,
                     credit_cap=FULL_PANEL_CREDIT_CAP, full_panel=True,
                     unresolved_identity_count=unresolved)
    schema = inspect_postgres(dsn)
    failures = []
    if manifest["panel_fingerprint"] != "9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f":
        failures.append("panel_fingerprint_mismatch")
    if mismatches:
        failures.append("cached_identity_mismatch")
    if schema["missing_indexes"]:
        failures.append("required_indexes_missing")
    if schema["missing_typed_columns"]:
        failures.append("typed_schema_missing")
    if plan["projected_max_credits"] > 4140 or plan["projected_max_credits"] > FULL_PANEL_CREDIT_CAP:
        failures.append("credit_projection_exceeds_reviewed_ceiling")
    if len(source_commit_sha) != 40 or any(c not in "0123456789abcdef" for c in source_commit_sha):
        failures.append("source_commit_sha_invalid")
    return {
        **plan, "mode": "full_panel_activation_preflight", "dry_run": True,
        "resolved_identity_count": resolved, "unresolved_identity_count": unresolved,
        "identity_mismatch_count": len(mismatches), "identity_mismatch_variants": mismatches,
        "seller_hmac_credential": "present", "seller_hmac_source": seller.source,
        "seller_key_fingerprint": seller.fingerprint,
        "pkmnprices_credential": "present", "pkmnprices_source": provider.source,
        "source_commit_sha": source_commit_sha, **schema,
        "database_writes": 0, "provider_requests": 0, "provider_credits_used": 0,
        "turnover_enabled": False, "market_scarcity_enabled": False,
        "preflight_passed": not failures, "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    env_file = parse_env_file(Path(__file__).resolve().parents[2] / "backend/.env")
    parser.add_argument("--database-url", default=(os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
                                                   or env_file.get("DATABASE_URL") or env_file.get("SUPABASE_DB_URL")))
    parser.add_argument("--source-commit-sha")
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL or SUPABASE_DB_URL is required for index proof")
    from backend.db.clients.supabase_client import create_service_role_client
    sha = args.source_commit_sha or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True
    ).strip()
    result = run_preflight(create_service_role_client(), dsn=args.database_url, source_commit_sha=sha)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["preflight_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
