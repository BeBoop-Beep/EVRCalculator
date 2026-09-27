"""Service-role reader for the one active, versioned Overall RIP authority."""

from __future__ import annotations

from typing import Any

from backend.desirability.overall_versioned_publication import (
    OverallAuthority,
    project_active,
    validate_generation,
)

ACTIVE_VIEW = "pokemon_overall_rip_active_v"
ACTIVE_FIELDS = (
    "model_version,publication_run_id,rankings_generation_id,"
    "set_page_generation_id,market_date,formula_fingerprint,"
    "cohort_fingerprint,sealed_product_id,source_result_id,score,rank,tier,"
    "eligibility_state,component_lineage"
)


def read_active_overall_rows(client: Any) -> list[dict[str, Any]]:
    """Return stable public objects sourced entirely from one atomic pointer."""
    response = client.table(ACTIVE_VIEW).select(ACTIVE_FIELDS).execute()
    rows = list((response.data if response else []) or [])
    if not rows:
        return []
    first = rows[0]
    authority = OverallAuthority(
        model_version=str(first["model_version"]),
        publication_run_id=str(first["publication_run_id"]),
        rankings_generation_id=str(first["rankings_generation_id"]),
        set_page_generation_id=str(first["set_page_generation_id"]),
        market_date=str(first["market_date"]),
        formula_fingerprint=str(first["formula_fingerprint"]),
        cohort_fingerprint=str(first["cohort_fingerprint"]),
    )
    validate_generation(authority, rows)
    for row in rows:
        if any(
            str(row[field]) != str(getattr(authority, field))
            for field in (
                "model_version",
                "publication_run_id",
                "rankings_generation_id",
                "set_page_generation_id",
                "market_date",
                "formula_fingerprint",
                "cohort_fingerprint",
            )
        ):
            raise ValueError("mixed Overall publication authority")
    projected = []
    for row in rows:
        public_row = project_active(authority, row)
        public_row.update({
            "sealedProductId": str(row["sealed_product_id"]),
            "sourceResultId": str(row["source_result_id"]),
        })
        projected.append(public_row)
    return projected


def active_overall_public_index(client: Any) -> dict[str, dict[str, Any]]:
    """``sealedProductId -> generic public Overall projection`` from the ONE active authority.

    Model-number independent: whichever Overall model the singleton pointer names (V12 today, V14 after
    an authorized activation) is what comes back, with its own ``version`` and ``componentLineage``. A
    service that needs the current Overall for a product reads this instead of a model-specific
    ``overall_rip_v12_*`` column, so a pointer flip needs no application change. Empty when nothing is
    published. Read-only; it can never move the pointer.
    """
    return {row["sealedProductId"]: row for row in read_active_overall_rows(client)}
