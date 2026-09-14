from pathlib import Path

from backend.scripts import research_best_open_price_bucket2 as bucket2
from backend.scripts.research_best_open_price_bucket1 import (
    EXPECTED_AUTHORITY_FINGERPRINT,
    SOURCE_SNAPSHOT_ID,
)


def test_research_defaults_remain_pinned_to_original_bucket2_authority():
    defaults = bucket2.run.__kwdefaults__
    assert defaults["source_snapshot_id"] == SOURCE_SNAPSHOT_ID
    assert defaults["expected_source_authority_fingerprint"] == EXPECTED_AUTHORITY_FINGERPRINT


def test_current_source_mode_is_explicitly_parameterized_not_a_second_engine():
    source = Path(bucket2.__file__).read_text(encoding="utf-8")
    assert "source_snapshot_id: str = SOURCE_SNAPSHOT_ID" in source
    assert "expected_source_authority_fingerprint: str | None = EXPECTED_AUTHORITY_FINGERPRINT" in source
    assert "_load_source(client, source_snapshot_id)" in source
    assert "expected_source_authority_fingerprint=expected_fingerprint" not in source  # constructor takes the value directly
    assert "expected_source_authority_fingerprint=expected_fingerprint" not in source
    assert "expected_source_authority_fingerprint=expected_fingerprint" not in source
    # The exact search class remains the one validated in Bucket 1/2.x.
    assert "ExactBestOpenPriceSearch(" in source
    assert source.count("class ExactBestOpenPriceSearch") == 0


def test_current_source_reconstructs_and_checks_published_cohort_fingerprint():
    source = Path(bucket2.__file__).read_text(encoding="utf-8")
    assert "reconstructed_cohort_fingerprint = cohort_fingerprint" in source
    assert "pinned cohort fingerprint does not match the published source snapshot" in source
    assert "pinned cohort SKU identities do not exactly match Full Market rows" in source


def test_engine_rows_now_carry_every_source_evidence_field_required_by_bucket3a():
    source = Path(bucket2.__file__).read_text(encoding="utf-8")
    for field in (
        "currentFinancialRipV4Score",
        "currentCollectorAppealScore",
        "currentChaseAccessibilityRaw",
        "currentChanceToRecoverCapital",
        "currentActualCommittedCapital",
        "benchmarkFinancialRipV4Score",
        "benchmarkChanceToRecoverCapital",
        "benchmarkActualCommittedCapital",
    ):
        assert f'"{field}"' in source


def test_cli_accepts_current_snapshot_without_removing_historical_defaults():
    source = Path(bucket2.__file__).read_text(encoding="utf-8")
    assert 'parser.add_argument("--source-snapshot-id", default=SOURCE_SNAPSHOT_ID)' in source
    assert 'parser.add_argument("--expected-source-authority-fingerprint")' in source
    assert "if args.source_snapshot_id == SOURCE_SNAPSHOT_ID and expected is None" in source
