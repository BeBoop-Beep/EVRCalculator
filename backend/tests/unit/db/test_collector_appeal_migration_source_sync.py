"""Contract tests for the repo mirror of production Collector Appeal migrations.

These are frozen historical mirrors of exactly what ran in production
(`supabase_migrations.schema_migrations`).  The MD5 values below were read from
the live ledger at mirror time.  This suite intentionally does not rewrite or
"clean up" historical SQL: later migrations supersede earlier definitions.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = ROOT / "backend/db/migrations"

MIRRORED = {
    "20260904041626_create_collector_card_appeal_identity_and_evidence": "946b8e1b2b920ad9c5086d47e70fedad",
    "20260904041708_create_collector_card_appeal_scoring_and_publication": "5ad4542678f3b8b9deb0ccf7afd56373",
    "20260904041730_seed_collector_card_appeal_authoritative_entities": "5bb99dadeef19a5615d69fbeb09c304b",
    "20260904041906_index_collector_card_appeal_set_fk": "b3430ad6dcbf6dcb2d5165ac59eef2f3",
    "20260904050026_harden_collector_card_appeal_validation_and_current_reads": "f4eaf1ad3c4fef3cd3f8cba6bd3e7a65",
    "20260904050120_add_collector_source_freshness_gate": "daeca9757883650ea3fd740a6c8875f3",
    "20260904060447_seal_collector_appeal_run_boundaries": "72aec89bb4c95d2ef27b579f7c25dbce",
    "20260904060604_add_collector_appeal_operational_health_views": "fd57838bf983b179c825515b19b54ece",
    "20260905035236_harden_collector_source_run_usability_gate": "f9fc7c1d95d524644c35d1a8ff9bc721",
}


def _path(stem: str) -> Path:
    return MIGRATIONS_DIR / f"{stem}.sql"


def _text(stem: str) -> str:
    return _path(stem).read_text(encoding="utf-8")


def test_every_production_collector_appeal_migration_has_repo_mirror():
    for stem in MIRRORED:
        assert _path(stem).is_file(), f"missing mirrored file for {stem}"


def test_mirrored_sql_is_byte_identical_to_live_ledger_at_mirror_time():
    for stem, expected_md5 in MIRRORED.items():
        payload = _path(stem).read_bytes()
        assert hashlib.md5(payload).hexdigest() == expected_md5, stem  # noqa: S324 -- historical integrity fingerprint


def test_migration_versions_preserve_production_order():
    versions = [stem.split("_", 1)[0] for stem in MIRRORED]
    assert versions == sorted(versions)


def test_foundation_separates_collector_subject_and_functional_identity():
    sql = _text("20260904041626_create_collector_card_appeal_identity_and_evidence").lower()
    assert "pokemon_collector_entity_reference" in sql
    assert "pokemon_card_collector_entity_links" in sql
    assert "pokemon_card_functional_reference" in sql
    assert "pokemon_card_functional_links" in sql
    assert "functional card identity registry used for playability evidence" in sql


def test_scoring_schema_keeps_price_treatment_and_hit_eligibility_out_of_v1_inputs():
    sql = _text("20260904041708_create_collector_card_appeal_scoring_and_publication").lower()
    assert "price_policy text not null default 'excluded'" in sql
    assert "treatment_policy text not null default 'disabled_v1'" in sql
    assert "hit_eligibility_policy text not null default 'independent'" in sql
    assert "price_input_excluded boolean not null default true" in sql
    assert "treatment_input_excluded boolean not null default true" in sql
    assert "hit_eligibility_independent boolean not null default true" in sql


def test_hardening_enforces_positive_only_lift_and_database_owned_validation():
    sql = _text("20260904050026_harden_collector_card_appeal_validation_and_current_reads").lower()
    assert "pokemon_card_collector_appeal_positive_lift_floor" in sql
    assert "collector_card_appeal_score >= subject_baseline_score" in sql
    assert "collector_json_has_forbidden_price_key" in sql
    assert "validate_pokemon_collector_appeal_model_run" in sql
    assert "revoke update on table public.pokemon_collector_appeal_model_runs from service_role" in sql


def test_run_boundary_migration_blocks_late_evidence_and_output_inserts():
    sql = _text("20260904060447_seal_collector_appeal_run_boundaries").lower()
    assert "require_running_pokemon_collector_source_run" in sql
    assert "require_building_pokemon_collector_appeal_model_run" in sql
    assert "require_published_pokemon_collector_appeal_model_run" in sql
    assert "revoke insert on table public.pokemon_set_collector_appeal_history from service_role" in sql


def test_latest_usability_hardening_is_the_final_source_authority():
    old = _text("20260904060604_add_collector_appeal_operational_health_views").lower()
    latest = _text("20260905035236_harden_collector_source_run_usability_gate").lower()
    assert "s.status in ('success','partial_failure')" in old
    assert "coalesce(h.usable_for_model, false) = false" in latest
    assert "join public.pokemon_collector_source_run_health_v h" in latest
    assert "failed, empty, or count-inconsistent source runs do not suppress refresh" in latest
