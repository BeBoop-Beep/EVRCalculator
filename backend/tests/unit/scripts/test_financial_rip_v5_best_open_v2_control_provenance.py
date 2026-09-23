"""The frozen Best-Open V2 control reference must declare its own generation
provenance, so a future runtime mismatch (the Python 3.12+ ``sum()`` change
that made the pre-3.13 reference stale at the 4th decimal, see
``docs/research/BEST_OPEN_PRICE_V2_CI_RUNTIME_VALIDATION.md``) is visible from
the artifact itself rather than requiring archaeology through commit history.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CONTROL = ROOT / "docs/research/financial_rip_v5_best_open_v2_control.json"

EXPECTED_COHORT_ID = "0e65fb6d-ff33-4331-99d5-d6a214ecc712"
EXPECTED_MARKET_DATE = "2026-09-14"


def _load() -> dict:
    return json.loads(CONTROL.read_text(encoding="utf-8"))


def test_the_control_artifact_declares_provenance():
    payload = _load()
    assert "provenance" in payload, "frozen reference must carry a provenance block"
    provenance = payload["provenance"]
    for key in (
        "schemaVersion", "pythonVersion", "numpyVersion", "generatorScript",
        "generationCommitSha", "frozenCohortId", "marketDate", "generatedAtUtc",
    ):
        assert key in provenance, f"provenance missing {key}"


def test_the_provenance_runtime_is_the_declared_repository_contract():
    provenance = _load()["provenance"]
    assert provenance["pythonVersion"] == "3.13.2"
    assert provenance["numpyVersion"] == "2.4.3"


def test_the_provenance_cohort_matches_the_artifacts_own_authority_fields():
    payload = _load()
    provenance = payload["provenance"]
    assert provenance["frozenCohortId"] == payload["sourceSnapshotId"] == EXPECTED_COHORT_ID
    assert provenance["marketDate"] == EXPECTED_MARKET_DATE


def test_the_provenance_generator_script_exists_in_the_repository():
    provenance = _load()["provenance"]
    generator_path = ROOT / provenance["generatorScript"]
    assert generator_path.exists(), generator_path


def test_the_control_artifact_is_still_the_complete_138_product_cohort():
    payload = _load()
    assert payload["status"] == "complete"
    assert len(payload["products"]) == 138
    assert len({row["sealedProductId"] for row in payload["products"]}) == 138
    assert all(row.get("resolved") for row in payload["products"])
