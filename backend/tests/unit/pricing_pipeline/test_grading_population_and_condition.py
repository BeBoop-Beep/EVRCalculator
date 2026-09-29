from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.pricing_pipeline.grading_population import (
    ExactPopulationMapping,
    GradingPopulationStore,
    normalize_population_payload,
)
from backend.pricing_pipeline.sold_condition_classifier import classification_record, classify_sold_title
from backend.scripts.validate_sold_condition_classifier_v1 import build_report

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "backend/tests/fixtures/grading_population/gemrate_population_v1.json"


def mapping(**overrides):
    values = {
        "canonical_card_id": "00000000-0000-0000-0000-000000000001",
        "card_variant_id": "00000000-0000-0000-0000-000000000002",
        "edition_scope": "FIRST_EDITION",
        "source_card_id": "fixture-gemrate-base-charizard-first-edition",
        "source_card_name": "Charizard 4",
        "source_set_name": "Pokemon Base Set",
        "match_basis": "year+set+number+subject+first-edition",
        "match_confidence": "HIGH",
        "provider_edition_scope": "FIRST_EDITION",
    }
    values.update(overrides)
    return ExactPopulationMapping(**values)


def normalized():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return normalize_population_payload(
        payload, mapping(), collected_at="2026-09-29T20:00:00Z"
    )


def test_fixture_maps_to_bucket_a_contract_with_opaque_grades_and_qualifiers():
    result = normalized()
    identity = result["identity"]
    assert identity["edition_scope"] == "FIRST_EDITION"
    assert identity["match_state"] == "EXACT"
    assert "observed graded population" in identity["metadata"]["population_semantics"]
    keys = {(row["grading_company"], row["grade"], row["grade_qualifier"]): row["population_count"]
            for row in result["snapshots"]}
    assert keys[("beckett", "10", "black")] == 2
    assert keys[("beckett", "10", "pristine")] == 8
    assert keys[("cgc", "10", "")] == 31
    assert keys[("cgc", "10", "pristine")] == 11
    assert keys[("cgc", "10", "perfect")] == 1
    assert keys[("psa", "8.5", "")] == 77
    assert keys[("psa", "8", "Q")] == 4
    assert all(isinstance(row["grade"], str) for row in result["snapshots"])
    assert all(row["observed_date"] == "2026-09-28" for row in result["snapshots"])
    assert all("label_key" in row["source_payload"] for row in result["snapshots"])
    assert all("provider_payload" in row["source_payload"] for row in result["snapshots"])


@pytest.mark.parametrize("provider_scope", ["UNLIMITED", "SHADOWLESS", "OTHER"])
def test_exact_mapping_never_merges_physical_editions(provider_scope):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="physical edition mismatch"):
        normalize_population_payload(
            payload, mapping(provider_edition_scope=provider_scope),
            collected_at="2026-09-29T20:00:00Z",
        )


def test_provider_identity_mismatch_fails_closed():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="provider card identity mismatch"):
        normalize_population_payload(
            payload, mapping(source_card_id="some-other-id"),
            collected_at="2026-09-29T20:00:00Z",
        )


class Query:
    def __init__(self, client, table):
        self.client, self.table = client, table

    def upsert(self, rows, **kwargs):
        self.client.calls.append((self.table, rows, kwargs))
        return self

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        return type("Response", (), {"data": self.client.existing if not self.client.calls else []})()


class Client:
    def __init__(self, existing=None):
        self.calls = []
        self.existing = existing or []

    def table(self, name):
        return Query(self, name)


def test_store_writes_only_bucket_a_population_tables():
    client = Client()
    assert GradingPopulationStore(client).persist(normalized()) == (1, 9)
    assert [call[0] for call in client.calls] == [
        "grading_population_provider_identities_v1", "grading_population_snapshots_v1"
    ]


def test_store_refuses_silent_existing_physical_identity_remap():
    result = normalized()
    client = Client(existing=[{
        "source_provider": "gemrate", "source_card_id": result["identity"]["source_card_id"],
        "canonical_card_id": result["identity"]["canonical_card_id"],
        "card_variant_id": "different-variant", "edition_scope": "UNLIMITED",
    }])
    with pytest.raises(ValueError, match="population provider identity conflict"):
        GradingPopulationStore(client).persist(result)
    assert client.calls == []


@pytest.mark.parametrize(
    ("title", "label"),
    [
        ("Charizard Near Mint", "NM"), ("Pikachu LP", "LP"),
        ("Blastoise moderately played", "MP"), ("Venusaur HP", "HP"),
        ("Mewtwo with creased corner", "DAMAGED"),
        ("NM front, damaged back", "AMBIGUOUS"),
        ("Pack fresh minty card", "UNLABELED"),
        ("Damage Pump 156/195", "UNLABELED"),
        ("Mint Berry Neo Genesis", "UNLABELED"),
    ],
)
def test_condition_classifier_contract(title, label):
    result = classify_sold_title(title)
    assert result["condition_label"] == label
    assert result["classifier_version"] == "pkmnprices_sold_title_condition_v1"


def test_classification_record_is_a_separate_versioned_derived_row():
    row = classification_record("evidence-id", "Charizard LP", classified_at="2026-09-29T22:00:00Z")
    assert row == {
        "sold_evidence_id": "evidence-id", "condition_label": "LP", "confidence": "MEDIUM",
        "evidence_tokens": ["lp"], "classifier_version": "pkmnprices_sold_title_condition_v1",
        "ambiguity_reason": None, "classified_at": "2026-09-29T22:00:00Z",
    }


def test_reviewed_validation_sample_has_full_precision_and_required_coverage():
    report = build_report()
    assert report["reviewed"] is True
    assert report["row_count"] == 35
    assert report["accuracy"] == 1.0
    assert set(report["precision_by_class"]) == {"NM", "LP", "MP", "HP", "DAMAGED", "AMBIGUOUS", "UNLABELED"}
    assert all(row["precision"] == 1.0 for row in report["precision_by_class"].values())
    assert set(report["coverage"]["era"]) == {"modern", "vintage"}
    assert set(report["coverage"]["value_band"]) == {"low", "mid", "high"}
    assert set(report["coverage"]["title_length"]) == {"short", "verbose"}
    assert report["pricing_use_authorized"] is False


def test_condition_migration_is_mirrored_separate_and_research_only():
    backend = ROOT / "backend/db/migrations/20260929233000_sold_condition_classification_research_v1.sql"
    supabase = ROOT / "supabase/migrations/20260929233000_sold_condition_classification_research_v1.sql"
    assert backend.read_bytes() == supabase.read_bytes()
    sql = backend.read_text(encoding="utf-8").lower()
    assert "references public.pkmnprices_ebay_sold_evidence_v1(id)" in sql
    assert "update public.pkmnprices_ebay_sold_evidence_v1" not in sql
    assert "pricing authority" in sql
