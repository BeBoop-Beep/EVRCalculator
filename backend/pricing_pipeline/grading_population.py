"""Provider-neutral normalization for observed grading-service populations.

Population means submissions represented by a grading service. It never means
the number of physical copies in existence and is never a pricing authority.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

ADAPTER_VERSION = "grading_population_adapter_v1"
NAMESPACE = uuid.UUID("729806d0-9a62-42e2-9cb3-d257445c5ed5")
EDITION_SCOPES = {"FIRST_EDITION", "UNLIMITED", "SHADOWLESS", "OTHER", "NOT_APPLICABLE"}


@dataclass(frozen=True)
class ExactPopulationMapping:
    canonical_card_id: str
    card_variant_id: str
    edition_scope: str
    source_card_id: str
    source_card_name: str
    source_set_name: str
    match_basis: str
    match_confidence: str
    provider_edition_scope: str

    def validate(self) -> None:
        if self.edition_scope not in EDITION_SCOPES:
            raise ValueError("invalid internal edition scope")
        if self.provider_edition_scope not in EDITION_SCOPES:
            raise ValueError("invalid provider edition scope")
        if self.edition_scope != self.provider_edition_scope:
            raise ValueError("physical edition mismatch")
        if not all((self.canonical_card_id, self.card_variant_id, self.source_card_id,
                    self.match_basis, self.match_confidence)):
            raise ValueError("exact population mapping is incomplete")


def _identity_id(source_provider: str, source_card_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{source_provider}:{source_card_id}"))


def _grade_parts(grader: str, label_key: str) -> tuple[str, str]:
    prefix = grader.casefold() + "_"
    if not label_key.casefold().startswith(prefix):
        raise ValueError("grade key does not belong to grader")
    opaque = label_key[len(prefix):]
    qualifier = ""
    if opaque.casefold().startswith("q") and len(opaque) > 1:
        opaque, qualifier = opaque[1:], "Q"
    for suffix in ("_black", "_pristine", "_perfect"):
        if opaque.casefold().endswith(suffix):
            opaque, qualifier = opaque[:-len(suffix)], suffix[1:]
            break
    # Provider underscores encode decimal labels. Keep the resulting value a
    # string; never parse it numerically.
    grade = opaque.replace("_", ".")
    if not grade:
        raise ValueError("empty grade label")
    return grade, qualifier


def normalize_population_payload(
    payload: Mapping[str, Any],
    mapping: ExactPopulationMapping,
    *,
    source_provider: str = "gemrate",
    collected_at: str,
) -> dict[str, Any]:
    """Map one fixture/API response into the two Bucket A table contracts."""
    mapping.validate()
    population = payload.get("population") or {}
    population_data = population.get("population_data") or {}
    observed = str(population_data.get("data_last_updated") or "")
    date.fromisoformat(observed)
    datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    provider_id = str(payload.get("gemrate_id") or "")
    if provider_id != mapping.source_card_id:
        raise ValueError("provider card identity mismatch")
    identity_id = _identity_id(source_provider, provider_id)
    identity = {
        "id": identity_id,
        "source_provider": source_provider,
        "source_card_id": provider_id,
        "card_variant_id": mapping.card_variant_id,
        "canonical_card_id": mapping.canonical_card_id,
        "edition_scope": mapping.edition_scope,
        "source_card_name": mapping.source_card_name,
        "source_set_name": mapping.source_set_name,
        "match_state": "EXACT",
        "match_basis": mapping.match_basis,
        "verified_at": collected_at,
        "metadata": {
            "adapter_version": ADAPTER_VERSION,
            "match_confidence": mapping.match_confidence,
            "universal_source_card_id": payload.get("universal_gemrate_id"),
            "population_semantics": "observed graded population / submissions represented by the grading service",
        },
    }
    snapshots = []
    by_grader = population_data.get("by_grader") or {}
    for grader, grader_data in sorted(by_grader.items()):
        grades = grader_data.get("grades") or {}
        qualifiers = grader_data.get("qualifiers") or {}
        for label_key, count in sorted({**grades, **qualifiers}.items()):
            grade, qualifier = _grade_parts(str(grader), str(label_key))
            value = int(count)
            if value < 0:
                raise ValueError("negative observed population")
            snapshots.append({
                "provider_identity_id": identity_id,
                "source_provider": source_provider,
                "grading_company": str(grader),
                "grade": grade,
                "grade_qualifier": qualifier,
                "population_count": value,
                "observed_date": observed,
                "source_observed_at": payload.get("source_observed_at"),
                "collected_at": collected_at,
                "source_payload": {
                    "adapter_version": ADAPTER_VERSION,
                    "source_card_id": provider_id,
                    "label_key": label_key,
                    "raw_population": count,
                    "provider_payload": dict(payload),
                    "population_semantics": "observed graded population / submissions represented by the grading service",
                },
            })
    if not snapshots:
        raise ValueError("population payload has no grade rows")
    return {"identity": identity, "snapshots": snapshots}


class GradingPopulationStore:
    """Persistence boundary; callers must normalize and review exact mapping first."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def persist(self, normalized: Mapping[str, Any]) -> tuple[int, int]:
        identity = dict(normalized["identity"])
        snapshots = [dict(row) for row in normalized["snapshots"]]
        existing_rows = (
            self.client.table("grading_population_provider_identities_v1")
            .select("source_provider,source_card_id,canonical_card_id,card_variant_id,edition_scope")
            .eq("source_provider", identity["source_provider"])
            .eq("source_card_id", identity["source_card_id"])
            .limit(1).execute().data or []
        )
        if existing_rows:
            existing = existing_rows[0]
            immutable = ("canonical_card_id", "card_variant_id", "edition_scope")
            if any(str(existing.get(field)) != str(identity.get(field)) for field in immutable):
                raise ValueError("population provider identity conflict")
        self.client.table("grading_population_provider_identities_v1").upsert(
            identity, on_conflict="source_provider,source_card_id"
        ).execute()
        if snapshots:
            self.client.table("grading_population_snapshots_v1").upsert(
                snapshots,
                on_conflict="provider_identity_id,grading_company,grade,grade_qualifier,observed_date",
                ignore_duplicates=True,
            ).execute()
        return 1, len(snapshots)
