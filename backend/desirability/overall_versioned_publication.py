"""Generic Overall RIP publication objects; independent of model version numbers."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from backend.desirability.composite import assign_composite_tier


@dataclass(frozen=True)
class OverallAuthority:
    model_version: str
    publication_run_id: str
    rankings_generation_id: str
    set_page_generation_id: str
    market_date: str
    formula_fingerprint: str
    cohort_fingerprint: str


def rank_and_tier(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Bind score/rank/model-tier in one deterministic authority row."""
    material = [dict(row) for row in rows]
    ready = sorted(
        (r for r in material if r.get("score") is not None),
        key=lambda r: (
            -float(r["score"]),
            str(r["sealed_product_id"]),
            str(r.get("source_result_id", "")),
        ),
    )
    ranks = {id(row): index for index, row in enumerate(ready, 1)}
    result = []
    for row in material:
        score = row.get("score")
        row["eligibility_state"] = "ready" if score is not None else row.get("eligibility_state", "unavailable_missing_input")
        row["rank"] = ranks.get(id(row))
        row["tier"] = assign_composite_tier(float(score)) if score is not None else None
        result.append(row)
    return result


def project_active(authority: OverallAuthority, row: Mapping[str, Any]) -> dict[str, Any]:
    """Stable generic projection; every displayed value shares one authority."""
    return {"score":row.get("score"),"rank":row.get("rank"),"tier":row.get("tier"),
        "version":authority.model_version,"publicationRunId":authority.publication_run_id,
        "rankingsGenerationId":authority.rankings_generation_id,"setPageGenerationId":authority.set_page_generation_id,
        "marketDate":authority.market_date,"eligibility":row.get("eligibility_state"),
        "componentLineage":dict(row.get("component_lineage") or {}),
        "formulaFingerprint":authority.formula_fingerprint,"cohortFingerprint":authority.cohort_fingerprint}


def validate_generation(authority: OverallAuthority, rows: Iterable[Mapping[str, Any]]) -> None:
    for row in rows:
        projected = project_active(authority, row)
        if projected["version"] != authority.model_version:
            raise ValueError("mixed Overall model authority")
        if row.get("score") is not None and (row.get("rank") is None or row.get("tier") is None):
            raise ValueError("score/rank/tier must be atomically present")
