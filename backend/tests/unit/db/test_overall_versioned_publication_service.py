from types import SimpleNamespace

import pytest

from backend.db.services.overall_versioned_publication_service import read_active_overall_rows


class Client:
    def __init__(self, rows): self.rows = rows
    def table(self, name): assert name == "pokemon_overall_rip_active_v"; return self
    def select(self, fields): assert "publication_run_id" in fields; return self
    def execute(self): return SimpleNamespace(data=self.rows)


def row(**updates):
    value = {"model_version":"overall_test_v99","publication_run_id":"run",
        "rankings_generation_id":"rank-gen","set_page_generation_id":"page-gen",
        "market_date":"2026-09-11","formula_fingerprint":"formula",
        "cohort_fingerprint":"cohort","sealed_product_id":"product",
        "source_result_id":"result","score":80,"rank":1,"tier":"A",
        "eligibility_state":"ready","component_lineage":{"collectorVersion":"v44"}}
    value.update(updates); return value


def test_service_projects_stable_names_from_generic_view():
    assert read_active_overall_rows(Client([row()]))[0]["version"] == "overall_test_v99"


def test_service_rejects_mixed_authorities():
    with pytest.raises(ValueError, match="mixed Overall"):
        read_active_overall_rows(Client([row(), row(source_result_id="r2", model_version="other")]))
