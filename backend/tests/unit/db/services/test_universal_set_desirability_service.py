"""The PUBLIC Universal Desirability reader's source-selection contract.

WHY THIS FILE EXISTS
--------------------
Phase 8.1 repaired version-exact source selection for CA7 — an internal
candidate that writes nothing — and left the same defect live on the reader that
powers the PUBLIC score. ``_load_latest_v2_rows`` took the newest row per set by
``built_at`` and compared ``scoring_version`` only. All three version columns are
part of the table's unique key, so agreeing on one says nothing about the other
two: in production the newest row for 170 of 171 sets carried
``hit_policy_version = ..._v1`` while the code computed ``..._v2_coverage_cleanup``.
The public score was served from v1 inputs for every set but one, and no test
noticed, because no test asserted WHICH row was chosen.

These tests assert the choice itself. The decisive case is the one production
actually held: the wrong row is NEWER, so any test whose fixture makes the
correct row the newest would pass under the defect and prove nothing.
"""

from __future__ import annotations

import pytest

from backend.db.services import universal_set_desirability_service as service
from backend.desirability.component_source import (
    EXPECTED_COMPOSITE_SCORING_VERSION,
    EXPECTED_HIT_POLICY_VERSION,
    EXPECTED_SCORING_VERSION,
)

V1 = "pokemon_card_desirability_hit_policy_v1"
V2 = "pokemon_card_desirability_hit_policy_v2"
V2_CLEANUP = EXPECTED_HIT_POLICY_VERSION

COMPONENT_TABLE = "pokemon_set_desirability_component_scores"
SET_VALUE_TABLE = "pokemon_set_value_daily_history"

# The real Chaos Rising identity, so the fixture describes production rather
# than a convenient invention.
CHAOS_SET_ID = "5bdbfae1-3f2e-44e7-b8c9-1035ad45b896"
CHAOS_EXACT_ROW_ID = "6e4cf65f-6846-4e7a-91dd-346550d31dca"
CHAOS_V1_ROW_ID = "23ad1e53-11c0-422e-beed-6ef2afcfcf63"


def _rollups(count=6, top=95.0):
    """Subject rollups that produce a real, non-zero v3 score."""
    return [
        {
            "subject_key": f"subject-{index}",
            "subject_name": f"Subject {index}",
            "pokemon_reference_id": index,
            "max_desirability_score": max(top - index * 5.0, 55.0),
            "rarity_buckets_present": ["major_hit"],
            "best_rarity_bucket": "major_hit",
            "card_count": 2,
            "representative_card_name": f"Card {index}",
        }
        for index in range(count)
    ]


def _row(
    set_id,
    hit_policy,
    *,
    row_id=None,
    built_at="2026-06-16T17:03:14Z",
    rollups=None,
    score=70.0,
    scoring_version=EXPECTED_SCORING_VERSION,
    composite_version=EXPECTED_COMPOSITE_SCORING_VERSION,
    config_fingerprint=None,
    eligible=10,
    scored=10,
    subjects=6,
):
    return {
        "id": row_id or f"{set_id}-{hit_policy}",
        "set_id": set_id,
        "set_name": f"Set {set_id}",
        "set_canonical_key": f"key{set_id}",
        "scoring_version": scoring_version,
        "hit_policy_version": hit_policy,
        "composite_scoring_version": composite_version,
        "fan_popularity_snapshot_id": "2",
        "config_fingerprint": config_fingerprint or f"cfg-{set_id}",
        "built_at": built_at,
        "set_desirability_score": score,
        "hit_eligible_card_count": eligible,
        "scored_hit_eligible_card_count": scored,
        "unique_subject_count": subjects,
        "subject_rollups_json": _rollups() if rollups is None else rollups,
        "diagnostics_json": {"coverage_audit": {"canonical_card_count": 100}},
    }


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    """A fake that paginates the way the real client does."""

    def __init__(self, rows, calls, table):
        self._rows = rows
        self._calls = calls
        self._table = table
        self._range = (0, len(rows))

    def select(self, fields):
        self._calls.append({"op": "select", "table": self._table, "fields": fields})
        return self

    def order(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        start, end = self._range
        return _Result(self._rows[start:end + 1])


class _Client:
    def __init__(self, component_rows, set_value_rows=None):
        self.component_rows = component_rows
        self.set_value_rows = set_value_rows or []
        self.calls = []

    def table(self, name):
        if name == COMPONENT_TABLE:
            return _Query(self.component_rows, self.calls, name)
        if name == SET_VALUE_TABLE:
            return _Query(self.set_value_rows, self.calls, name)
        raise AssertionError(f"unexpected table read: {name}")


@pytest.fixture(autouse=True)
def _reset_cache():
    service._cache.update(
        {"built_at": 0.0, "payloads": None, "setValueAssociation": None, "sourceSelection": None}
    )
    yield
    service._cache.update(
        {"built_at": 0.0, "payloads": None, "setValueAssociation": None, "sourceSelection": None}
    )


def _bundle(monkeypatch, rows):
    client = _Client(rows)
    monkeypatch.setattr(service, "public_read_client", client)
    return service.get_universal_desirability_bundle(force_refresh=True)


# ---------------------------------------------------------------------------
# The defect itself
# ---------------------------------------------------------------------------

def test_newer_v1_row_loses_to_older_exact_version_row(monkeypatch):
    """The production shape: the WRONG row is newer.

    Under the old ``built_at DESC`` rule this returns the v1 row, so this test
    fails on the pre-repair reader — which is the only reason it is worth having.
    """
    rows = [
        _row("s1", V1, row_id="new-v1", built_at="2026-07-01T00:00:00Z", score=10.0),
        _row("s1", V2_CLEANUP, row_id="old-exact", built_at="2026-01-01T00:00:00Z", score=70.0),
    ]
    bundle = _bundle(monkeypatch, rows)

    assert bundle["sourceSelection"]["counts"]["exact_version_rows_found"] == 1
    assert bundle["sourceSelection"]["counts"]["sets_missing_exact_version_row"] == 0
    assert bundle["payloads"]["s1"]["prior_v2_score"] == 70.0


def test_intermediate_v2_policy_is_not_a_near_enough_match(monkeypatch):
    """``_v2`` is not ``_v2_coverage_cleanup``. Prefix similarity is not a match."""
    rows = [
        _row("s1", V2, row_id="newer-v2", built_at="2026-07-01T00:00:00Z"),
        _row("s1", V2_CLEANUP, row_id="exact", built_at="2026-01-01T00:00:00Z"),
    ]
    bundle = _bundle(monkeypatch, rows)
    assert bundle["sourceSelection"]["counts"]["exact_version_rows_found"] == 1
    assert "s1" in bundle["payloads"]


def test_matching_scoring_version_alone_is_not_enough(monkeypatch):
    """The old rule's exact test: right scoring_version, wrong composite version."""
    rows = [
        _row("s1", V2_CLEANUP, row_id="wrong-composite",
             composite_version="pokemon_desirability_composite_v99",
             built_at="2026-07-01T00:00:00Z"),
    ]
    bundle = _bundle(monkeypatch, rows)
    assert bundle["payloads"] == {}
    assert bundle["sourceSelection"]["counts"]["sets_missing_exact_version_row"] == 1


# ---------------------------------------------------------------------------
# Absence and duplication
# ---------------------------------------------------------------------------

def test_no_exact_row_is_unavailable_not_a_fallback(monkeypatch):
    rows = [
        _row("s1", V1, row_id="v1", built_at="2026-07-01T00:00:00Z"),
        _row("s1", V2, row_id="v2", built_at="2026-06-01T00:00:00Z"),
    ]
    bundle = _bundle(monkeypatch, rows)

    assert bundle["payloads"] == {}
    missing = bundle["sourceSelection"]["missing"]
    assert len(missing) == 1
    assert missing[0]["reason"] == "missing_current_component_source_row"
    # The evidence names the versions it DOES have, so the gap is diagnosable
    # without a second query.
    assert sorted(missing[0]["available_hit_policy_versions"]) == sorted([V1, V2])


def test_missing_set_is_absent_rather_than_scored_zero(monkeypatch):
    """Absence must never be rendered as a real score of 0.

    A zero is a claim about the set; absence is a claim about our data. Serving
    the first when we mean the second puts a fabricated 0.0 on a leaderboard.
    """
    rows = [_row("present", V2_CLEANUP), _row("absent", V1)]
    bundle = _bundle(monkeypatch, rows)

    assert "absent" not in bundle["payloads"]
    assert service.public_payload(bundle["payloads"].get("absent"), None) is None
    assert bundle["payloads"]["present"]["score"] > 0


def test_duplicate_exact_rows_are_refused_not_arbitrated(monkeypatch):
    """Two exact rows differ in an input; picking one would pick an input set."""
    rows = [
        _row("dup", V2_CLEANUP, row_id="a", config_fingerprint="cfg-a"),
        _row("dup", V2_CLEANUP, row_id="b", config_fingerprint="cfg-b"),
        _row("ok", V2_CLEANUP, row_id="c"),
    ]
    bundle = _bundle(monkeypatch, rows)

    assert "dup" not in bundle["payloads"], "a duplicated set must not be served"
    assert "ok" in bundle["payloads"], "one bad set must not take down the others"
    duplicates = bundle["sourceSelection"]["duplicates"]
    assert len(duplicates) == 1
    assert duplicates[0]["set_id"] == "dup"
    assert duplicates[0]["row_count"] == 2
    assert duplicates[0]["reason"] == "duplicate_current_component_source_row"


def test_duplicate_exact_rows_are_logged_as_an_integrity_error(monkeypatch, caplog):
    rows = [
        _row("dup", V2_CLEANUP, row_id="a", config_fingerprint="cfg-a"),
        _row("dup", V2_CLEANUP, row_id="b", config_fingerprint="cfg-b"),
    ]
    with caplog.at_level("ERROR"):
        _bundle(monkeypatch, rows)
    assert any("INTEGRITY" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Chaos Rising
# ---------------------------------------------------------------------------

def test_chaos_rising_uses_its_newly_committed_exact_row(monkeypatch):
    """Chaos Rising holds both a v1 row and the new exact row."""
    rows = [
        _row(CHAOS_SET_ID, V2_CLEANUP, row_id=CHAOS_EXACT_ROW_ID,
             built_at="2026-07-16T16:18:08Z", score=43.3903),
        _row(CHAOS_SET_ID, V1, row_id=CHAOS_V1_ROW_ID,
             built_at="2026-06-16T17:03:14Z", score=43.3903),
    ]
    bundle = _bundle(monkeypatch, rows)

    assert bundle["sourceSelection"]["counts"]["exact_version_rows_found"] == 1
    assert bundle["sourceSelection"]["missing"] == []
    assert CHAOS_SET_ID in bundle["payloads"]


def test_chaos_rising_historical_v1_row_is_never_selected(monkeypatch):
    """Even if the v1 row were rebuilt and became the newest row."""
    rows = [
        _row(CHAOS_SET_ID, V1, row_id=CHAOS_V1_ROW_ID,
             built_at="2027-01-01T00:00:00Z", score=1.0),
        _row(CHAOS_SET_ID, V2_CLEANUP, row_id=CHAOS_EXACT_ROW_ID,
             built_at="2026-07-16T16:18:08Z", score=43.3903),
    ]
    bundle = _bundle(monkeypatch, rows)
    assert bundle["payloads"][CHAOS_SET_ID]["prior_v2_score"] == 43.3903


# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

# The exact public field names the API and frontend already consume. Frozen so
# the reader repair cannot rename or drop one.
PUBLIC_FIELDS = {
    "score", "rank", "percentile", "rankedSetCount", "version",
    "eligibilityPolicyVersion", "asOf", "components", "componentWeights",
    "weightsLabel", "topSubjects", "distinctEligibleSubjectCount",
    "effectiveSubjectCount", "setValueAssociation", "setValueCorrelation",
    "coverage",
}


def test_public_payload_field_names_are_unchanged(monkeypatch):
    bundle = _bundle(monkeypatch, [_row("s1", V2_CLEANUP)])
    payload = service.public_payload(bundle["payloads"]["s1"], bundle["setValueAssociation"])
    assert set(payload) == PUBLIC_FIELDS


def test_source_diagnostics_are_not_exposed_publicly(monkeypatch):
    """``sourceSelection`` is internal. It must not leak into the API shape."""
    bundle = _bundle(monkeypatch, [_row("s1", V2_CLEANUP)])
    payload = service.public_payload(bundle["payloads"]["s1"], bundle["setValueAssociation"])
    assert "sourceSelection" not in payload
    assert not {key for key in payload if "hit_policy" in key or "source" in key.lower()} - {
        "setValueAssociation", "setValueCorrelation"
    }


def test_every_covered_set_still_receives_a_score_and_rank(monkeypatch):
    rows = [_row(f"s{index}", V2_CLEANUP, score=50.0 + index) for index in range(5)]
    bundle = _bundle(monkeypatch, rows)

    assert len(bundle["payloads"]) == 5
    ranked = [row for row in bundle["payloads"].values() if row.get("rank") is not None]
    assert len(ranked) == 5
    assert sorted(row["rank"] for row in ranked) == [1, 2, 3, 4, 5]


# ---------------------------------------------------------------------------
# Contract sharing and determinism
# ---------------------------------------------------------------------------

def test_reader_does_not_restate_the_expected_versions():
    """The version strings must live in ONE place.

    A second loader holding its own copy is how the two readers drift apart
    again — which is the whole defect, reintroduced with extra steps.
    """
    source = (
        __import__("pathlib").Path(service.__file__).read_text(encoding="utf-8")
    )
    assert "pokemon_card_desirability_hit_policy_v2_coverage_cleanup" not in source
    assert "pokemon_set_desirability_components_v2_40_25_20_15" not in source
    assert "pokemon_desirability_composite_v1" not in source


def test_selection_is_independent_of_row_order(monkeypatch):
    """Input order must not decide the output. ``built_at`` order is not truth."""
    rows = [
        _row("s1", V1, row_id="v1", built_at="2026-07-01T00:00:00Z", score=10.0),
        _row("s1", V2_CLEANUP, row_id="exact", built_at="2026-01-01T00:00:00Z", score=70.0),
        _row("s2", V2_CLEANUP, row_id="exact-2", score=60.0),
    ]
    forward = _bundle(monkeypatch, list(rows))
    service._cache.update({"built_at": 0.0, "payloads": None, "setValueAssociation": None,
                           "sourceSelection": None})
    reversed_bundle = _bundle(monkeypatch, list(reversed(rows)))

    assert forward["payloads"]["s1"]["score"] == reversed_bundle["payloads"]["s1"]["score"]
    assert forward["payloads"]["s1"]["prior_v2_score"] == 70.0
    assert reversed_bundle["payloads"]["s1"]["prior_v2_score"] == 70.0
    assert (forward["sourceSelection"]["counts"]
            == reversed_bundle["sourceSelection"]["counts"])


def test_reader_reads_every_column_the_calculation_needs(monkeypatch):
    """The select must carry the identity AND the payload columns."""
    client = _Client([_row("s1", V2_CLEANUP)])
    monkeypatch.setattr(service, "public_read_client", client)
    service.get_universal_desirability_bundle(force_refresh=True)

    fields = next(
        call["fields"] for call in client.calls
        if call["op"] == "select" and call["table"] == COMPONENT_TABLE
    )
    for column in (
        "id", "set_id", "scoring_version", "hit_policy_version",
        "composite_scoring_version", "fan_popularity_snapshot_id",
        "config_fingerprint", "subject_rollups_json", "diagnostics_json",
    ):
        assert column in fields, f"{column} missing from the reader's select"
