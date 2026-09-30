from __future__ import annotations

import copy
import json
import socket
from pathlib import Path
from uuid import UUID

import pytest

from backend.pricing_pipeline.market_activity_projection import MarketActivityProjectionBuilder, raw_instrument_key

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "docs" / "research" / "market_activity_v1" / "fixtures"


@pytest.fixture(autouse=True)
def no_egress(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("projection attempted provider/network egress")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _fixture_inputs():
    return json.loads((FIXTURES / "fma_fixture_12_legacy_no_receipts.json").read_text())["inputs"]


class Source:
    def __init__(self, count=3, duplicate_rank=False):
        self.members = []
        for rank in range(1, count + 1):
            variant = str(UUID(int=rank))
            self.members.append({"rank": 1 if duplicate_rank and rank == 2 else rank,
                                 "cardVariantId": variant, "instrumentKey": raw_instrument_key(variant)})

    def pin_roster(self, market_key):
        return {"revision": {"kind": "SURFACE_V2_GENERATION",
                              "generationId": "11111111-1111-4111-8111-111111111111", "marketKey": market_key},
                "surfaceGenerationId": "11111111-1111-4111-8111-111111111111",
                "asOf": "2026-09-29", "denominator": len(self.members), "members": self.members}

    def load_instrument(self, card_variant_id, *, cutoff):
        data = copy.deepcopy(_fixture_inputs())
        data.pop("request", None); data.pop("evaluatedAt", None); data.pop("roster", None)
        data.pop("activityGeneration", None); data.pop("servedGenerationId", None)
        sold = data["sold"]
        sold["records"] = []
        sold["walks"] = []
        sold["candidates"] = [{"cardVariantId": card_variant_id, "edition": "UNLIMITED", "printing": "HOLO"}]
        data["_rowsRead"] = 0
        return data


class Sink:
    def __init__(self): self.generations=[]; self.writes=[]; self.finished=[]
    def create_generation(self, row): self.generations.append(dict(row))
    def write_batch(self, table, rows): self.writes.append((table, copy.deepcopy(list(rows))))
    def finish_generation(self, generation_id, state, diagnostics): self.finished.append((generation_id,state,dict(diagnostics)))


@pytest.mark.parametrize("count", [101, 207])
def test_full_roster_is_not_limited_by_page_size(count):
    sink = Sink()
    result = MarketActivityProjectionBuilder(Source(count), sink, batch_size=50).build(
        "quick:core", as_of="2026-09-29", evidence_cutoff="2026-09-30T12:00:00Z")
    assert result["state"] == "VALIDATED"
    rows = [row for table, batch in sink.writes if table == "market_activity_roster_members_v1" for row in batch]
    assert len(rows) == count
    groups = [row for table, batch in sink.writes if table == "market_activity_group_payloads_v1" for row in batch]
    assert {row["payload"]["coverage"]["rosterDenominator"] for row in groups} == {count}


def test_duplicate_rank_rejects_and_does_not_publish_rows():
    sink = Sink()
    result = MarketActivityProjectionBuilder(Source(3, duplicate_rank=True), sink).build(
        "quick:core", as_of="2026-09-29", evidence_cutoff="2026-09-30T12:00:00Z")
    assert result["state"] == "REJECTED"
    assert not sink.generations and not sink.writes


def test_dry_run_has_zero_writes_and_is_deterministic():
    sink = Sink(); builder = MarketActivityProjectionBuilder(Source(3), sink)
    kwargs = dict(as_of="2026-09-29", evidence_cutoff="2026-09-30T12:00:00Z",
                  generation_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", dry_run=True)
    first = builder.build("quick:core", **kwargs); second = builder.build("quick:core", **kwargs)
    first["diagnostics"].pop("elapsed_seconds"); second["diagnostics"].pop("elapsed_seconds")
    assert first == second
    assert first["state"] == "VALIDATED"
    assert not sink.generations and not sink.writes and not sink.finished


def test_resume_writes_only_members_after_checkpoint_but_aggregates_full_roster():
    sink = Sink()
    result = MarketActivityProjectionBuilder(Source(101), sink, batch_size=25).build(
        "quick:core", as_of="2026-09-29", evidence_cutoff="2026-09-30T12:00:00Z", resume_after_rank=75)
    assert result["state"] == "VALIDATED"
    rows = [row for table, batch in sink.writes if table == "market_activity_roster_members_v1" for row in batch]
    assert [row["rank"] for row in rows] == list(range(76, 102))
    groups = [row for table, batch in sink.writes if table == "market_activity_group_payloads_v1" for row in batch]
    assert groups[0]["payload"]["coverage"]["rosterDenominator"] == 101
