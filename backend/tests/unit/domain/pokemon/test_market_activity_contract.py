"""FMA-0: machine-readable contract, fixtures and manifest are executable.

* every schema uses only the validator's supported keyword subset;
* every fixture request/response validates against its schema;
* every fixture ``expected`` block is reproduced exactly by the pure domain
  assembler from its ``inputs`` (fixtures are a regression lock on the rules);
* the manifest's schema/fixture fingerprints match the committed files;
* the committed artifacts equal the generator's output (no hand drift);
* the schema reason-code enum equals the domain registry.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from backend.domain.pokemon import market_activity as ma
from backend.domain.pokemon.market_activity_contract import SchemaError, SchemaRegistry, content_fingerprint
from backend.scripts import build_market_activity_v1_contract_artifacts as gen

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / "docs" / "research" / "market_activity_v1"
CONTRACTS = OUT / "contracts"
FIXTURES = OUT / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
REQUIRED_SCENARIOS = {"fresh_complete", "partial_sales", "stale_asks", "zero_with_proof", "not_collected",
                      "missing_grade", "insufficient_peers", "unsupported_asset", "generation_mismatch"}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("contract tests attempted network egress")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture(scope="module")
def registry():
    return SchemaRegistry(CONTRACTS)


def _fixture(entry):
    return json.loads((FIXTURES / entry["file"]).read_text(encoding="utf-8"))


def test_contract_documents_exist():
    for name in ("CONTRACT.md", "SCHEMA_DECISION.md", "COLLECTOR_HANDOFF.md", "FMA0_REPORT.md",
                 "FMA0_REVIEW_CLOSURE.md"):
        assert (OUT / name).is_file(), name


def test_required_fixture_scenarios_are_present():
    assert REQUIRED_SCENARIOS <= {entry["scenario"] for entry in MANIFEST["fixtures"]}


def test_manifest_validates_and_pins_versions(registry):
    assert registry.validate(MANIFEST, "fixture_manifest.schema.json") == []
    assert MANIFEST["contractVersion"] == ma.CONTRACT_VERSION
    assert MANIFEST["versions"] == ma._versions()
    assert MANIFEST["policy"] == ma.DEFAULT_POLICY.as_contract()


def test_manifest_fingerprints_match_committed_files():
    committed_schemas = {p.name: content_fingerprint(p) for p in CONTRACTS.glob("*.schema.json")}
    assert committed_schemas == MANIFEST["schemas"]
    for entry in MANIFEST["fixtures"]:
        assert content_fingerprint(FIXTURES / entry["file"]) == entry["sha256"], entry["file"]


@pytest.mark.parametrize("entry", MANIFEST["fixtures"], ids=lambda e: e["scenario"])
def test_fixture_validates_and_is_reproduced_by_the_domain(entry, registry):
    fixture = _fixture(entry)
    assert fixture["requestSchema"] == entry["requestSchema"]
    assert registry.validate(fixture["inputs"]["request"], entry["requestSchema"]) == []
    assert registry.validate(fixture["expected"], entry["responseSchema"]) == []
    assembler = gen.ASSEMBLERS[entry["assembler"]][0]
    assert assembler(fixture["inputs"]) == fixture["expected"]
    assert fixture["expected"]["availability"]["state"] == entry["expectedAvailability"]
    assert fixture["expected"]["evidenceFingerprint"] == ma.fingerprint(fixture["inputs"])


def test_committed_artifacts_equal_generator_output():
    drift = []
    for path, text in gen.render().items():
        if not path.exists() or json.loads(path.read_text(encoding="utf-8")) != json.loads(text):
            drift.append(str(path.relative_to(ROOT)))
    assert drift == []


def test_schema_reason_enum_equals_domain_registry():
    common = json.loads((CONTRACTS / "common.schema.json").read_text(encoding="utf-8"))
    assert common["$defs"]["ReasonCode"]["enum"] == list(ma.REASON_CODES)


def test_validator_rejects_unsupported_keywords_and_bad_instances(tmp_path, registry):
    (tmp_path / "x.schema.json").write_text(json.dumps({"type": "object", "patternProperties": {}}))
    with pytest.raises(SchemaError):
        SchemaRegistry(tmp_path).validate({}, "x.schema.json")
    fixture = _fixture(MANIFEST["fixtures"][0])
    broken = json.loads(json.dumps(fixture["expected"]))
    broken["sales"]["windows"][0]["observedCount"] = -1
    broken["asks"]["lowestAsk"]["price"]["amount"] = 44.0
    broken["peers"]["claimsAllPokemon"] = True
    broken["roster"]["label"] = "Activity for all constituents ever"
    errors = registry.validate(broken, "instrument_detail_response.schema.json")
    assert len(errors) >= 4


def test_money_is_always_a_decimal_string_in_fixtures():
    def walk(node, path="$"):
        if isinstance(node, dict):
            if set(node) == {"amount", "currency"}:
                assert isinstance(node["amount"], str), path
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        else:
            assert not isinstance(node, float), path
    for entry in MANIFEST["fixtures"]:
        walk(_fixture(entry)["expected"])


def test_fixture_states_match_their_scenarios():
    by = {e["scenario"]: _fixture(e)["expected"] for e in MANIFEST["fixtures"]}
    assert by["fresh_complete"]["availability"]["state"] == "AVAILABLE"
    assert [w["readiness"]["state"] for w in by["partial_sales"]["sales"]["windows"]] == [
        "PROVEN", "PROVEN", "PARTIAL", "UNPROVEN"]
    assert by["stale_asks"]["asks"]["state"] == "STALE"
    assert by["stale_asks"]["capabilities"]["currentAsks"]["available"] is False
    assert by["stale_asks"]["asks"]["lowestAsk"]["basis"] == "ITEM_ONLY_LEGACY_UNVERIFIED"
    assert by["zero_with_proof"]["sales"]["windows"][1]["provenCount"] == 0
    assert by["zero_with_proof"]["asks"]["state"] == "ZERO_PROVEN"
    assert by["zero_with_proof"]["peers"]["state"] == "ALL_ZERO"
    assert by["not_collected"]["sales"]["windows"][1]["observedCount"] is None
    assert by["missing_grade"]["sales"]["excludedRecordCounts"]["GRADING_INCOMPLETE"] == 3
    assert by["missing_grade"]["asks"] is None
    assert by["insufficient_peers"]["peers"]["state"] == "INSUFFICIENT_PEERS"
    assert by["insufficient_peers"]["peers"]["activityPercentile"] is None
    assert by["unsupported_asset"]["availability"]["reasons"] == ["UNSUPPORTED_ASSET"]
    assert by["generation_mismatch"]["availability"]["reasons"] == ["GENERATION_MISMATCH"]
    assert by["generation_mismatch"]["sales"] is None
    page = by["constituent_page"]
    # FMA-0.1 F5: the FMA-0 expectation was ``"nextCursor": 2`` -- a bare rank
    # integer, which is the reviewed defect (not revision-bound). The cursor is
    # now opaque and bound to activity generation, roster ref, market, asOf
    # and window.
    assert {k: v for k, v in page["page"].items() if k != "nextCursor"} == {"afterRank": 0, "limit": 2,
                                                                           "totalCount": 3}
    assert ma.decode_cursor(page["page"]["nextCursor"])["k"] == 2
    assert [r["rank"] for r in page["rows"]] == [1, 2]
    group = by["group_activity"]
    assert group["label"] == "Activity for current constituents"
    assert group["coverage"]["rosterDenominator"] == 3
    assert group["totals"]["provenSaleCount"] == 8
    # FMA-0.1 fixtures
    legacy = by["legacy_no_receipts"]
    assert [w["observedCount"] for w in legacy["sales"]["windows"]] == [4, 8, 11, 12]
    assert all(w["provenCount"] is None for w in legacy["sales"]["windows"])
    assert legacy["capabilities"]["observedSales"]["available"] is True
    assert legacy["capabilities"]["saleCount"]["available"] is False
    assert legacy["peers"]["state"] == "UNAVAILABLE"
    assert all(w["readiness"]["state"] != "PROVEN" for w in by["future_right_edge"]["sales"]["windows"])
    mixed = by["mixed_unconfirmed_asks"]
    assert mixed["asks"]["state"] == "PARTIALLY_CONFIRMED"
    assert mixed["asks"]["lowestAsk"]["price"]["amount"] != "1.00"
    assert mixed["capabilities"]["currentAsks"]["available"] is False
    series = by["multi_date_series"]["series"]
    assert series["canonicalRange"]["startDate"] < series["activityRange"]["startDate"]
    assert any(p["ingestedAfterReconciliation"] for p in series["sales"]["counts"]["points"])
    assert any(p["collectionCount"] > 1 for p in series["supply"]["listings"]["points"])
    assert by["constituent_page_cursor"]["rows"][0]["rank"] == 3
    assert by["constituent_page_cursor"]["page"]["nextCursor"] is None
    assert by["cursor_mismatch"]["availability"]["reasons"] == ["CURSOR_MISMATCH"]
    assert by["activity_generation_expired"]["availability"]["reasons"] == ["ACTIVITY_GENERATION_EXPIRED"]
    assert by["group_roster_101"]["coverage"]["rosterDenominator"] == 101
