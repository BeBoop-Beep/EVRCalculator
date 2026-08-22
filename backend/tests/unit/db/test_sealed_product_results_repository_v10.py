from backend.db.repositories.sealed_product_results_repository import (
    ENRICHMENT_FIELDS,
    _SELECT_FIELDS,
    update_sealed_product_enrichment,
)


def test_select_fields_include_v4_and_v10_columns():
    for column in (
        "financial_rip_v4_score", "financial_rip_v4_status", "financial_rip_v4_rankable",
        "financial_rip_v4_version", "financial_rip_v4_payload",
        "overall_rip_v10_score", "overall_rip_v10_version",
        "overall_rip_v10_rankable", "overall_rip_v10_payload",
    ):
        assert column in _SELECT_FIELDS


def test_enrichment_fields_accept_v10_columns():
    for column in (
        "overall_rip_v10_score", "overall_rip_v10_version",
        "overall_rip_v10_rankable", "overall_rip_v10_payload",
    ):
        assert column in ENRICHMENT_FIELDS


def test_enrichment_still_fails_closed_on_unknown_key():
    import pytest
    with pytest.raises(ValueError):
        update_sealed_product_enrichment("row-1", {"financial_rip_v4_score": 10.0})
