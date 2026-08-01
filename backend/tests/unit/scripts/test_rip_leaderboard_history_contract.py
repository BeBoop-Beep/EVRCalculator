from pathlib import Path

import pytest

from backend.scripts import pokemon_explore_rankings_publisher as command


def _row(*, target_count=1, ca7_version="ca7-v1"):
    targets = [{
        "set_id": f"00000000-0000-0000-0000-{index:012d}",
        "canonical_key": f"set-{index}",
        "rip": {"score": 80 - index, "rank": index + 1},
        "ripCore": {"score": 75 - index, "rank": index + 1},
        "openingExperience": {"collectorAppeal": {"version": ca7_version}},
        "pack_cost": 5,
    } for index in range(target_count)]
    return {"ranking_payload_json": {
        "targets": targets,
        "meta": {
            "comparisonSnapshots": {"currentMarketDate": "2026-08-01"},
            "snapshot": {"builtAt": "2026-08-01T08:00:00Z"},
            "publicAnalyticsCohort": {
                "version": "cohort-v1",
                "eligibleSetCount": target_count,
                "overallRanked": {"rankedSetCount": 1},
            },
            "ripWeightsConfig": {
                "overallRip": {"version": "overall-v4"},
                "financialRip": {"version": "financial-v2"},
            },
        },
    }}


def test_complete_cohort_builds_history_publication_contract():
    snapshot, rows = command.publication_contract(_row())
    assert snapshot["market_date"] == "2026-08-01"
    assert snapshot["eligible_cohort_count"] == 1
    assert len(rows) == 1


def test_incomplete_cohort_fails_closed():
    with pytest.raises(RuntimeError, match="incomplete Overall RIP cohort"):
        command.publication_contract(_row(target_count=2))


def test_missing_or_mixed_ca7_version_fails_closed():
    with pytest.raises(RuntimeError, match="incompatible CA7 versions"):
        command.publication_contract(_row(ca7_version=None))


def test_atomic_rpc_is_idempotent_and_promotes_latest_after_history_rows():
    migration = (
        Path(__file__).resolve().parents[3]
        / "db/migrations/049_add_pokemon_public_rip_leaderboard_history.sql"
    ).read_text(encoding="utf-8")
    assert "ON CONFLICT (market_date, cohort_version, overall_rip_version, financial_rip_version, ca7_version)" in migration
    assert migration.index("INSERT INTO pokemon_public_rip_leaderboard_rows") < migration.index(
        "INSERT INTO pokemon_explore_rankings_snapshot_latest"
    )


def test_production_code_has_no_direct_latest_writer_outside_canonical_rpc():
    root = Path(__file__).resolve().parents[4]
    offenders = []
    for path in (root / "backend").rglob("*"):
        if path.suffix not in {".py", ".sql"} or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "pokemon_explore_rankings_snapshot_latest" not in text:
            continue
        writes = "INSERT INTO pokemon_explore_rankings_snapshot_latest" in text
        writes = writes or any(
            "pokemon_explore_rankings_snapshot_latest" in block
            for block in text.split("upsert_row(")[1:]
            if ")" in block and "pokemon_explore_rankings_snapshot_latest" in block.split(")", 1)[0]
        )
        approved = path.name in {
            "049_add_pokemon_public_rip_leaderboard_history.sql",
            "053_harden_pokemon_public_rip_leaderboard_publication.sql",
        }
        if writes and not approved:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


class _Query:
    def __init__(self, data):
        self.data = data
    def select(self, *_args):
        return self
    def eq(self, *_args):
        return self
    def limit(self, *_args):
        return self
    def execute(self):
        return type("Result", (), {"data": self.data})()


class _Client:
    def __init__(self, previous=None, existing=None):
        self.previous = previous
        self.existing = existing
        self.calls = []
    def table(self, name):
        if name == "pokemon_public_rip_leaderboard_snapshots":
            data = self.previous if self.calls == [] else self.existing
            self.calls.append(("table", name))
            return _Query(data or [])
        raise AssertionError(name)
    def rpc(self, name, params):
        self.calls.append(("rpc", name, params))
        return _Query([])


def test_shared_publisher_enriches_metadata_and_publishes_through_rpc(monkeypatch):
    row = _row()
    client = _Client(previous=[])
    monkeypatch.setattr(command, "build_explore_rankings_snapshot_row", lambda **_kwargs: row)
    result = command.publish_explore_rip_rankings_snapshot(client, commit=True)
    rpc = next(call for call in client.calls if call[0] == "rpc")
    assert rpc[1] == "publish_pokemon_public_rip_leaderboard"
    assert result["ranking_payload_json"]["meta"]["snapshot"]["publicationId"]
    assert result["ranking_payload_json"]["meta"]["snapshot"]["marketDate"] == "2026-08-01"
    assert result["ranking_payload_json"]["targets"][0]["overallRipRankComparisonStatus1d"] == "unavailable"


def test_previous_calendar_day_query_does_not_substitute_older_snapshot():
    calls = []
    class Client:
        def table(self, _name):
            return self
        def select(self, _fields):
            return self
        def eq(self, field, value):
            calls.append((field, value))
            return self
        def limit(self, _value):
            return self
        def execute(self):
            return type("Result", (), {"data": []})()
    assert command.previous_calendar_day_payload(Client(), "2026-08-01") is None
    assert ("market_date", "2026-07-31") in calls


def test_requested_market_date_cannot_backdate_payload(monkeypatch):
    monkeypatch.setattr(command, "build_explore_rankings_snapshot_row", lambda **_kwargs: _row())
    with pytest.raises(RuntimeError, match="Refusing to backdate"):
        command.publish_explore_rip_rankings_snapshot(
            _Client(), market_date="2026-07-31", commit=False
        )
