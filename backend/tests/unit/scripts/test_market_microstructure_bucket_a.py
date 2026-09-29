from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.scripts.freeze_market_microstructure_core_panel_v1 import (
    F1_FINGERPRINT,
    PER_BAND,
    SEED,
)

ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "docs/research/index_fair_value/core_panel_v1_manifest.json"
BACKEND_MIGRATION = ROOT / "backend/db/migrations/20260929210000_market_microstructure_bucket_a_contracts_v1.sql"
SUPABASE_MIGRATION = ROOT / "supabase/migrations/20260929210000_market_microstructure_bucket_a_contracts_v1.sql"


def _fingerprint(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def test_core_panel_manifest_is_deterministic_and_exact_physical_identity():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    audit = manifest.pop("audit")
    expected = manifest.pop("panel_fingerprint")
    assert _fingerprint(manifest) == expected
    assert manifest["source_f1_fingerprint"] == F1_FINGERPRINT
    assert manifest["sample_seed"] == SEED
    assert manifest["per_band_target"] == PER_BAND
    assert manifest["provider_requests"] == manifest["provider_credits_used"] == 0
    assert manifest["production_pricing_authority_changed"] is False
    rows = manifest["rows"]
    assert len(rows) == audit["row_count"] == 207
    physical = [(row["canonical_card_id"], row["card_variant_id"]) for row in rows]
    assert len(physical) == len(set(physical))
    assert audit["duplicate_physical_identity_count"] == 0
    assert all(row["tcgplayer_product_id"].isdigit() for row in rows)
    assert all(row["source_f1_fingerprint"] == F1_FINGERPRINT for row in rows)


def test_panel_audit_has_all_required_dimensions_and_provider_gaps():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    audit = manifest["audit"]
    assert sum(audit["by_price_band"].values()) == 207
    assert sum(audit["by_root_set"].values()) == 207
    assert sum(audit["by_era"].values()) == 207
    assert sum(audit["edition_scopes"].values()) == 207
    assert audit["unresolved_provider_identity_count"] == len(audit["unresolved_provider_canonical_card_ids"])


def test_bucket_a_migration_is_mirrored_and_shadow_only():
    backend = BACKEND_MIGRATION.read_bytes()
    assert backend == SUPABASE_MIGRATION.read_bytes()
    sql = backend.decode().lower()
    assert "add column grade_qualifier text" in sql
    assert "market_active_supply_snapshots_v1" in sql
    assert "grading_population_provider_identities_v1" in sql
    assert "grading_population_snapshots_v1" in sql
    assert "enable row level security" in sql
    assert "grant select, insert" in sql
    forbidden = (
        "pokemon_canonical_card_market_prices_latest",
        "set_value_nm_eligible = true",
        "create or replace view",
        "create or replace function",
    )
    assert not any(token in sql for token in forbidden)
    assert sql.startswith("begin;") and sql.rstrip().endswith("commit;")
    rollback_sql = sql.rsplit("commit;", 1)[0] + "rollback;"
    assert rollback_sql.startswith("begin;") and rollback_sql.rstrip().endswith("rollback;")


def test_existing_nm_fail_closed_migration_contract_is_unchanged():
    original = (ROOT / "backend/db/migrations/20260929161314_pkmnprices_sold_evidence_v1.sql").read_text(encoding="utf-8").lower()
    assert "set_value_nm_eligible boolean not null default false check (not set_value_nm_eligible)" in original
    assert "set_value_nm_eligible_count integer not null default 0 check (set_value_nm_eligible_count = 0)" in original
