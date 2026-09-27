"""The generic active Overall reader reproduces the current V12 result and carries V14 unchanged.

The active view is model-number independent. While the pointer names V12, routing a read through it
must give the same public fields (score / rank / tier / version) as the legacy V12 columns; with a V14
fixture as the active publication the same code path returns V14 with no model-specific field family.
No production pointer is involved: the view is a fixture.
"""
import pytest

from backend.db.services.overall_versioned_publication_service import (
    ACTIVE_FIELDS, ACTIVE_VIEW, active_overall_public_index, read_active_overall_rows,
)
from backend.desirability import scoring_config as sc
from backend.desirability.composite import assign_composite_tier
from backend.desirability.overall_versioned_publication import rank_and_tier

PIDS = [f"00000000-0000-0000-0000-{i:012d}" for i in range(1, 9)]
V12_SCORES = [71.2345, 88.0, 55.0, 55.0, 90.5, 34.9999, 14.0, 62.4]  # ties + tier boundaries on purpose


class FakeActiveClient:
    def __init__(self, rows):
        self.rows, self.selected, self.tables = rows, None, []

    def table(self, name):
        self.tables.append(name)
        return self

    def select(self, fields):
        self.selected = fields
        return self

    def execute(self):
        return type("R", (), {"data": self.rows})()


def _legacy_v12_rows():
    """What the legacy V12 columns hold per product (score) - the reference behavior."""
    return [{"sealed_product_id": p, "source_result_id": p.replace("0000", "1111", 1), "overall_rip_v12_score": s}
            for p, s in zip(PIDS, V12_SCORES)]


def _active_rows(model_version, scores, lineage):
    material = [{"sealed_product_id": p, "source_result_id": p.replace("0000", "1111", 1), "score": s,
                 "component_lineage": lineage} for p, s in zip(PIDS, scores)]
    out = []
    for row in rank_and_tier(material):
        out.append({"model_version": model_version, "publication_run_id": "run-1", "rankings_generation_id": "rg-1",
                    "set_page_generation_id": "sg-1", "market_date": "2026-09-14", "formula_fingerprint": "f",
                    "cohort_fingerprint": "c", **row})
    return out


def test_active_view_field_list_has_no_model_specific_columns():
    assert ACTIVE_VIEW == "pokemon_overall_rip_active_v"
    assert not [f for f in ACTIVE_FIELDS.split(",") if "v12" in f or "v14" in f or "v4" in f or "v5" in f]


def test_generic_path_reproduces_the_legacy_v12_public_fields_while_active_is_v12():
    lineage = {"financialVersion": sc.FINANCIAL_RIP_V4_VERSION}
    client = FakeActiveClient(_active_rows(sc.OVERALL_RIP_V12_VERSION, V12_SCORES, lineage))
    index = active_overall_public_index(client)
    assert client.tables == [ACTIVE_VIEW] and len(index) == len(PIDS)
    # legacy reference: rank by score desc then id; tier from the shared composite thresholds
    legacy = sorted(_legacy_v12_rows(), key=lambda r: (-r["overall_rip_v12_score"], r["sealed_product_id"]))
    for rank, row in enumerate(legacy, 1):
        got = index[row["sealed_product_id"]]
        assert got["score"] == row["overall_rip_v12_score"]
        assert got["rank"] == rank
        assert got["tier"] == assign_composite_tier(row["overall_rip_v12_score"])
        assert got["version"] == sc.OVERALL_RIP_V12_VERSION and got["eligibility"] == "ready"
        assert got["componentLineage"] == lineage


def test_same_reader_returns_v14_when_the_active_publication_is_v14_without_new_field_families():
    lineage = {"financialVersion": "financial_rip_v5_shortfall_resilience_25_20_15_25_10_5",
               "chaseVersion": "chase", "collectorVersion": "collector"}
    scores = [s - 1.5 for s in V12_SCORES]
    rows = read_active_overall_rows(FakeActiveClient(_active_rows(sc.OVERALL_RIP_V14_VERSION, scores, lineage)))
    assert {r["version"] for r in rows} == {sc.OVERALL_RIP_V14_VERSION}
    assert all(set(r) == set(rows[0]) for r in rows)
    keys = set(rows[0])
    assert not [k for k in keys if "v12" in k.lower() or "v14" in k.lower() or "v4" in k.lower() or "v5" in k.lower()]
    top = min(rows, key=lambda r: r["rank"])
    assert top["score"] == max(scores) and top["rank"] == 1 and top["tier"] == assign_composite_tier(max(scores))
    assert top["componentLineage"]["financialVersion"].startswith("financial_rip_v5")


def test_mixed_publication_authority_is_refused():
    rows = _active_rows(sc.OVERALL_RIP_V12_VERSION, V12_SCORES, {})
    rows[3]["model_version"] = sc.OVERALL_RIP_V14_VERSION
    with pytest.raises(ValueError, match="mixed Overall publication authority"):
        read_active_overall_rows(FakeActiveClient(rows))


def test_score_without_rank_or_tier_is_refused_and_empty_is_empty():
    rows = _active_rows(sc.OVERALL_RIP_V12_VERSION, V12_SCORES, {})
    rows[0]["rank"] = None
    with pytest.raises(ValueError, match="atomically present"):
        read_active_overall_rows(FakeActiveClient(rows))
    assert active_overall_public_index(FakeActiveClient([])) == {}


def test_reading_the_active_index_never_writes_or_selects_a_pointer():
    client = FakeActiveClient(_active_rows(sc.OVERALL_RIP_V12_VERSION, V12_SCORES, {}))
    active_overall_public_index(client)
    assert client.tables == [ACTIVE_VIEW]
    assert not hasattr(client, "insert") and not hasattr(client, "update") and not hasattr(client, "rpc")
