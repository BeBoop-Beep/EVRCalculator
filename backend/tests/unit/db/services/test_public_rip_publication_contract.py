"""The ONE definition of "is this published RIP leaderboard still current?".

THE DEFECT THESE PIN
--------------------
Production's newest published leaderboard reported

    overall_rip_v4_90_financial_10_ca7
    financial_rip_v2_60_25_15

while 22 fresh Financial RIP V3 simulations already existed underneath it, and
nothing classified it stale. The reason freshness never noticed is the property
these tests exist to lock down: **a scoring-version change moves no timestamp**,
so a check built entirely on timestamps and structural markers can never see one.

The central assertion in this file is therefore the negative one - a snapshot
whose market date, timestamps and structure are all perfect is STILL stale when
its scoring contract is obsolete.
"""

from __future__ import annotations

import pytest

from backend.db.services.public_rip_publication_contract import (
    DIAGNOSTICS_COHORT_FINGERPRINT_KEY,
    DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY,
    DIAGNOSTICS_CONTRACT_VERSION_KEY,
    REASON_COHORT_FINGERPRINT,
    REASON_COLLECTOR_APPEAL_VERSION,
    REASON_CONTRACT_VERSION,
    REASON_FINANCIAL_VERSION,
    REASON_NOT_COMPLETE,
    REASON_NOT_PUBLISHED,
    REASON_OVERALL_VERSION,
    REASON_ROW_COUNT,
    REASON_SNAPSHOT_MISSING,
    REASON_SOURCE_RUN_SUPERSEDED,
    build_publication_diagnostics,
    canonical_publication_identity,
    evaluate_leaderboard_staleness,
    read_published_identity,
    supported_cohort_fingerprint,
)
from backend.desirability.collector_appeal import (
    COLLECTOR_APPEAL_V5_VERSION,
    COLLECTOR_APPEAL_CA7_VERSION,
    COLLECTOR_APPEAL_V2_VERSION,
    COLLECTOR_APPEAL_V4_VERSION,
)
from backend.desirability.scoring_config import (
    FINANCIAL_RIP_V2_VERSION,
    FINANCIAL_RIP_V4_VERSION,
    OVERALL_RIP_V4_VERSION,
    OVERALL_RIP_V6_VERSION,
    OVERALL_RIP_V8_VERSION,
    OVERALL_RIP_V12_VERSION,
)

CANONICAL = canonical_publication_identity()

COHORT = {
    "version": "supported_opening_cohort_fingerprint_v1",
    "fingerprint": "cohort-fp",
    "keys": [f"set-{index}" for index in range(22)],
    "count": 22,
}


def _snapshot(**overrides):
    """A snapshot row that is CURRENT in every respect, before overrides."""
    row = {
        "id": "publication-1",
        "market_date": "2026-08-04",
        "published_at": "2026-08-04T09:00:00Z",
        "publication_status": "complete",
        "eligible_cohort_count": 22,
        "overall_rip_version": CANONICAL["overallRipVersion"],
        "financial_rip_version": CANONICAL["financialRipVersion"],
        "ca7_version": CANONICAL["collectorAppealVersion"],
        "diagnostics_json": {
            DIAGNOSTICS_CONTRACT_VERSION_KEY: CANONICAL["publicRipContractVersion"],
            DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY: CANONICAL["collectorAppealVersion"],
            DIAGNOSTICS_COHORT_FINGERPRINT_KEY: COHORT["fingerprint"],
        },
    }
    diagnostics = overrides.pop("diagnostics", None)
    row.update(overrides)
    if diagnostics is not None:
        row["diagnostics_json"] = {**row["diagnostics_json"], **diagnostics}
    return row


def _evaluate(row, **kwargs):
    kwargs.setdefault("ranked_row_count", 22)
    kwargs.setdefault("cohort", COHORT)
    return evaluate_leaderboard_staleness(row, **kwargs)


def _codes(reasons):
    return sorted(reason["code"] for reason in reasons)


# ===========================================================================
# The canonical identity
# ===========================================================================

def test_the_canonical_identity_is_read_from_the_one_cutover_switch():
    """UPDATED FOR THE 2026-09-03 V12 CUTOVER (and the earlier, already-landed
    V4/V5 financial/collector-appeal promotions this test had fallen behind
    on): the canonical identity now reads Financial RIP V4, Collector Appeal
    V5, Overall RIP V12, and public RIP contract v11."""
    assert CANONICAL == {
        "financialRipVersion": FINANCIAL_RIP_V4_VERSION,
        "collectorAppealVersion": COLLECTOR_APPEAL_V5_VERSION,
        "overallRipVersion": OVERALL_RIP_V12_VERSION,
        "publicRipContractVersion": "public_rip_contract_v11",
    }


# ===========================================================================
# The baseline: a current snapshot has no reasons
# ===========================================================================

def test_a_fully_canonical_snapshot_reports_no_staleness_reasons():
    assert _evaluate(_snapshot()) == []


def test_a_missing_snapshot_is_stale():
    assert _codes(evaluate_leaderboard_staleness(None)) == [REASON_SNAPSHOT_MISSING]


# ===========================================================================
# THE central case: version staleness that no timestamp could reveal
# ===========================================================================

def test_a_structurally_perfect_snapshot_on_obsolete_versions_is_stale():
    """The exact production state: right date, right shape, wrong model.

    All four version identifiers are checked, and ALL FOUR reasons are reported
    rather than just the first - one rebuild resolves them together, and naming
    one sends an operator to a partial fix.
    """
    row = _snapshot(
        overall_rip_version=OVERALL_RIP_V4_VERSION,
        financial_rip_version=FINANCIAL_RIP_V2_VERSION,
        ca7_version=COLLECTOR_APPEAL_CA7_VERSION,
        diagnostics={
            DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY: COLLECTOR_APPEAL_CA7_VERSION,
            DIAGNOSTICS_CONTRACT_VERSION_KEY: "public_rip_contract_v4",
        },
    )
    assert _codes(_evaluate(row)) == sorted([
        REASON_FINANCIAL_VERSION,
        REASON_COLLECTOR_APPEAL_VERSION,
        REASON_OVERALL_VERSION,
        REASON_CONTRACT_VERSION,
    ])


def test_a_matching_market_date_alone_never_establishes_freshness():
    """The market date is not consulted at all, and that is deliberate.

    It records when the PRICES were promoted; it says nothing about which formula
    scored them. Freshness by market date is precisely how an obsolete contract
    survived a scoring cutover.
    """
    stale = _snapshot(
        market_date="2026-08-04",
        overall_rip_version=OVERALL_RIP_V6_VERSION,
    )
    assert REASON_OVERALL_VERSION in _codes(_evaluate(stale))
    # Changing only the market date changes nothing about the verdict.
    assert _codes(_evaluate(stale)) == _codes(
        _evaluate(_snapshot(market_date="1999-01-01", overall_rip_version=OVERALL_RIP_V6_VERSION))
    )


@pytest.mark.parametrize("field,value,code", [
    ("overall_rip_version", OVERALL_RIP_V6_VERSION, REASON_OVERALL_VERSION),
    ("financial_rip_version", FINANCIAL_RIP_V2_VERSION, REASON_FINANCIAL_VERSION),
])
def test_each_version_mismatch_is_reported_individually(field, value, code):
    assert _codes(_evaluate(_snapshot(**{field: value}))) == [code]


def test_a_superseded_collector_appeal_version_is_stale():
    row = _snapshot(
        ca7_version=COLLECTOR_APPEAL_V2_VERSION,
        diagnostics={DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY: COLLECTOR_APPEAL_V2_VERSION},
    )
    assert _codes(_evaluate(row)) == [REASON_COLLECTOR_APPEAL_VERSION]


# ===========================================================================
# Fail-closed on absent evidence
# ===========================================================================

def test_a_snapshot_with_no_recorded_contract_version_is_stale():
    """"We cannot tell which contract built this" is not "it is current"."""
    row = _snapshot()
    row["diagnostics_json"].pop(DIAGNOSTICS_CONTRACT_VERSION_KEY)
    assert REASON_CONTRACT_VERSION in _codes(_evaluate(row))


def test_a_snapshot_with_no_diagnostics_at_all_is_stale():
    row = _snapshot()
    row["diagnostics_json"] = {}
    codes = _codes(_evaluate(row))
    assert REASON_CONTRACT_VERSION in codes
    assert REASON_COHORT_FINGERPRINT in codes


# ===========================================================================
# Cohort and row-count
# ===========================================================================

def test_a_changed_supported_cohort_fingerprint_is_stale():
    row = _snapshot(diagnostics={DIAGNOSTICS_COHORT_FINGERPRINT_KEY: "a-different-cohort"})
    assert _codes(_evaluate(row)) == [REASON_COHORT_FINGERPRINT]


@pytest.mark.parametrize("count", [21, 23])
def test_too_few_or_too_many_ranked_rows_is_stale(count):
    """Both directions. A 23rd row is as wrong as a missing 22nd."""
    assert REASON_ROW_COUNT in _codes(_evaluate(_snapshot(), ranked_row_count=count))


def test_the_supported_cohort_fingerprint_describes_the_set_not_the_order():
    a = supported_cohort_fingerprint(["b", "a", "c"])
    b = supported_cohort_fingerprint(["c", "b", "a"])
    assert a["fingerprint"] == b["fingerprint"]
    assert a["keys"] == ["a", "b", "c"]
    assert a["count"] == 3
    # A genuinely different cohort produces a different fingerprint.
    assert supported_cohort_fingerprint(["a", "b"])["fingerprint"] != a["fingerprint"]


# ===========================================================================
# Publication state
# ===========================================================================

def test_an_incomplete_publication_is_stale():
    assert REASON_NOT_COMPLETE in _codes(_evaluate(_snapshot(publication_status="failed")))


def test_an_unpublished_snapshot_is_stale():
    assert REASON_NOT_PUBLISHED in _codes(_evaluate(_snapshot(published_at=None)))


# ===========================================================================
# Source simulation runs
# ===========================================================================

def test_a_superseded_source_run_is_stale():
    """Compared by run IDENTITY, not by date.

    Two runs on the same day share a date and are different runs, and it is the
    second - the re-run after a fix - whose absence from the leaderboard matters.
    """
    reasons = _evaluate(
        _snapshot(),
        published_run_id_by_set={"set-a": "run-1", "set-b": "run-9"},
        latest_eligible_run_id_by_set={"set-a": "run-2", "set-b": "run-9"},
    )
    assert _codes(reasons) == [REASON_SOURCE_RUN_SUPERSEDED]
    assert reasons[0]["set_key"] == "set-a"
    assert reasons[0]["observed"] == "run-1"
    assert reasons[0]["expected"] == "run-2"


def test_matching_source_runs_are_not_reported():
    assert _evaluate(
        _snapshot(),
        published_run_id_by_set={"set-a": "run-1"},
        latest_eligible_run_id_by_set={"set-a": "run-1"},
    ) == []


def test_a_supported_set_absent_from_the_leaderboard_is_reported():
    reasons = _evaluate(
        _snapshot(),
        published_run_id_by_set={},
        latest_eligible_run_id_by_set={"set-a": "run-1"},
    )
    assert _codes(reasons) == [REASON_SOURCE_RUN_SUPERSEDED]
    assert reasons[0]["observed"] is None


# ===========================================================================
# Reading and writing the identity
# ===========================================================================

def test_the_diagnostics_block_carries_the_two_identifiers_with_no_column():
    diagnostics = build_publication_diagnostics(
        set_ids=["b", "a"], cohort=COHORT, source_run_ids={"set-a": "run-1", "set-b": None}
    )
    assert diagnostics[DIAGNOSTICS_CONTRACT_VERSION_KEY] == CANONICAL["publicRipContractVersion"]
    assert diagnostics[DIAGNOSTICS_COHORT_FINGERPRINT_KEY] == COHORT["fingerprint"]
    assert diagnostics[DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY] == (
        CANONICAL["collectorAppealVersion"]
    )
    assert diagnostics["set_ids"] == ["a", "b"]
    assert diagnostics["source_calculation_run_ids"] == {"set-a": "run-1", "set-b": None}


def test_the_historical_ca7_column_is_read_as_the_collector_appeal_version():
    """``ca7_version`` is a HISTORICAL column name.

    It is part of the snapshot table's uniqueness key, so renaming it would be a
    migration for no behavioural gain. It carries the canonical Collector Appeal
    version, whichever that currently is - and a row published before the
    diagnostics key existed still reads correctly from it.
    """
    row = _snapshot()
    row["diagnostics_json"].pop(DIAGNOSTICS_COLLECTOR_APPEAL_VERSION_KEY)
    identity = read_published_identity(row)
    assert identity["collectorAppealVersion"] == COLLECTOR_APPEAL_V5_VERSION


def test_the_diagnostics_copy_wins_over_the_historical_column():
    row = _snapshot(ca7_version="something-stale")
    assert read_published_identity(row)["collectorAppealVersion"] == COLLECTOR_APPEAL_V5_VERSION


def test_a_round_trip_through_the_diagnostics_block_reports_current():
    """What the publisher writes is what the evaluator accepts."""
    diagnostics = build_publication_diagnostics(set_ids=["a"], cohort=COHORT)
    row = _snapshot()
    row["diagnostics_json"] = diagnostics
    assert _evaluate(row) == []


# ---------------------------------------------------------------------------
# ONE canonical authority — publisher and public reader must not drift
# ---------------------------------------------------------------------------
#
# The defect this module exists for was "current" being defined per call site.
# The public rankings READER is now a third call site (it refuses to serve a
# snapshot whose publication identity is superseded), so it has to be pinned to
# the same authority as the publisher rather than acquiring its own copy of the
# cutover switch.


def _canonical_ranking_payload():
    """A rankings payload carrying the identity block the builder writes."""
    identity = canonical_publication_identity()
    return {
        "targets": [],
        "meta": {
            "ripWeightsConfig": {
                "overallRip": {"version": identity["overallRipVersion"]},
                "financialRip": {"version": identity["financialRipVersion"]},
                "collectorAppeal": {"version": identity["collectorAppealVersion"]},
                "publicContract": {"version": identity["publicRipContractVersion"]},
            }
        },
    }


def test_the_public_reader_accepts_exactly_the_canonical_identity():
    from backend.db.services.pokemon_public_snapshot_service import (
        _rankings_publication_identity_mismatches,
    )

    assert _rankings_publication_identity_mismatches(_canonical_ranking_payload()) == []


@pytest.mark.parametrize(
    "key",
    ["overallRip", "financialRip", "collectorAppeal", "publicContract"],
)
def test_the_public_reader_rejects_every_superseded_identifier(key):
    from backend.db.services.pokemon_public_snapshot_service import (
        _rankings_publication_identity_mismatches,
    )

    payload = _canonical_ranking_payload()
    payload["meta"]["ripWeightsConfig"][key]["version"] = "superseded_model_v0"
    assert _rankings_publication_identity_mismatches(payload), (
        f"a superseded {key} version must not read as the current publication"
    )


def test_the_public_reader_does_not_restate_any_version_literal():
    """THE point of this file, applied to the reader.

    A second hand-maintained copy of a version string is a second cutover: the
    reader would keep accepting the old model after scoring_config moved on, and
    nothing would contradict it. The reader must import the authority, never
    restate it.
    """
    from pathlib import Path

    import backend.db.services.pokemon_public_snapshot_service as reader

    source = Path(reader.__file__).read_text(encoding="utf-8")
    for identifier, version in canonical_publication_identity().items():
        # Quoted forms only. The bare text also matches ordinary Python
        # identifiers (the module has a local `public_rip_contract_v8`, which is
        # a variable name and not a second copy of the cutover switch).
        for literal in (f'"{version}"', f"'{version}'"):
            assert literal not in source, (
                f"{identifier} literal {version!r} is restated in the reader; "
                "it must come from canonical_publication_identity()"
            )
