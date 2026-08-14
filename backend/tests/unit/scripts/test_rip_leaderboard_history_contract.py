"""The Explore RIP leaderboard publication contract.

WHAT CHANGED, AND WHY THE FIXTURE MOVED
---------------------------------------
The publisher used to build its rows from ``target['rip']`` (Overall RIP v4, off
the Financial RIP V2 pillars and legacy CA7) and ``target['ripCore']`` (Financial
RIP V2), and copied whatever version strings ``meta.ripWeightsConfig`` happened
to carry. That is why the newest published leaderboard reported
``overall_rip_v4_90_financial_10_ca7`` / ``financial_rip_v2_60_25_15`` while 22
fresh Financial RIP V3 simulations sat underneath it.

It now publishes ``overallRipV8`` and ``financialRipV3``, and VERIFIES the
version strings against the one canonical selection in ``scoring_config`` before
writing anything. So the fixture below carries the canonical objects and the
canonical versions - a fixture on the legacy shape would now be testing that the
publisher refuses to publish, which several tests here do deliberately.
"""

from pathlib import Path

import pytest

from backend.db.services.public_rip_publication_contract import (
    PUBLIC_SET_VALUE_CONTRACT_VERSION,
    SET_VALUE_AS_OF_FIELDS,
    SET_VALUE_VALUE_FIELDS,
    canonical_publication_identity,
    payload_guarantees_canonical_set_value,
)
from backend.desirability.scoring_config import CANONICAL_OVERALL_RIP_VERSION
from backend.scripts import pokemon_explore_rankings_publisher as command

CANONICAL = canonical_publication_identity()


# The supported-cohort keys the stubbed authority reports. `_row()` keeps this in
# step with whatever cohort it just built, so every test except the dedicated
# mismatch one sees an authority that agrees with its own fixture.
_SUPPORTED_KEYS: list = ["set-0"]


@pytest.fixture(autouse=True)
def _fixed_supported_cohort(monkeypatch):
    """Pin the authoritative supported cohort to the fixture's size.

    The publisher checks the ranked cohort against
    ``opening_simulation_gate.supported_opening_set_keys()``, which resolves the
    REAL set registry (22 sets). A unit test builds one or two synthetic sets, so
    without this the cohort-size assertion would fail for a reason that has
    nothing to do with what each test is exercising - and the suite would break
    every time a set is onboarded.
    """
    def _stub(keys=None):
        return {
            "version": "supported_opening_cohort_fingerprint_v1",
            "fingerprint": "stub-fingerprint",
            "keys": list(_SUPPORTED_KEYS),
            "count": len(_SUPPORTED_KEYS),
        }

    monkeypatch.setattr(command, "supported_cohort_fingerprint", _stub)
    return _stub


def _set_supported_keys(keys):
    """Point the stubbed authority at an explicit key list."""
    _SUPPORTED_KEYS[:] = list(keys)


def _score_block(index, *, fingerprint=True):
    """One canonical pillar block: BOTH score layers, plus its cohort identity.

    ``score`` and ``absoluteScore`` are the same absolute formula output;
    ``relativeScore`` is the cohort-relative display score. The publisher refuses
    to publish a set missing either layer rather than dropping it, so the fixture
    has to carry both for the happy path to be a happy path.
    """
    block = {
        "score": 80 - index,
        "absoluteScore": 80 - index,
        "relativeScore": 90 - index,
        "rank": index + 1,
        "tier": "A",
        "rankedSetCount": 1,
    }
    if fingerprint:
        block["cohortFingerprint"] = "stub-fingerprint"
    return block


def _contract_v7(index, contract_version):
    """The canonical public contract the publisher validates before publishing."""
    return {
        "contractVersion": contract_version,
        "overallRip": _score_block(index),
        "financialRip": {
            **_score_block(index),
            "components": {
                component: _score_block(index, fingerprint=False)
                for component in (
                    "trueWinFrequency", "typicalRetention", "lossResilience",
                    "realisticUpside", "jackpotUpside", "baseEconomicEfficiency",
                )
            },
        },
        "collectorAppeal": _score_block(index),
    }


def _row(*, target_count=1, appeal_version=CANONICAL["collectorAppealVersion"],
         overall_version=CANONICAL["overallRipVersion"],
         financial_version=CANONICAL["financialRipVersion"],
         contract_version=CANONICAL["publicRipContractVersion"],
         ranked_count=None):
    targets = [{
        "set_id": f"00000000-0000-0000-0000-{index:012d}",
        "canonical_key": f"set-{index}",
        # The CANONICAL objects the publisher now reads.
        "overallRipV8": {"score": 80 - index, "rank": index + 1},
        "financialRipV3": {"score": 75 - index, "rank": index + 1},
        # The legacy objects, still present. The publish RPC counts ranked
        # targets by `rip.rank`, so they must select the same rows.
        "rip": {"score": 78 - index, "rank": index + 1},
        "ripCore": {"score": 70 - index, "rank": index + 1},
        "openingExperience": {"collectorAppeal": {"version": appeal_version}},
        "publicRipContractV8": _contract_v7(index, contract_version),
        "cohortFingerprint": "stub-fingerprint",
        "calculation_run_id": f"run-{index}",
        "pack_cost": 5,
        # The canonical checklist Set Value the publication now guarantees. One
        # value, mirrored into the aliases the builder derives from it.
        **{field: 500.0 + index for field in SET_VALUE_VALUE_FIELDS},
        **{field: "2026-08-01" for field in SET_VALUE_AS_OF_FIELDS},
    } for index in range(target_count)]
    # Keep the stubbed authority in step with the cohort just built.
    _set_supported_keys(f"set-{index}" for index in range(target_count))
    return {"ranking_payload_json": {
        "targets": targets,
        "meta": {
            "comparisonSnapshots": {"currentMarketDate": "2026-08-01"},
            "snapshot": {"builtAt": "2026-08-01T08:00:00Z"},
            "publicAnalyticsCohort": {
                "version": "cohort-v1",
                "eligibleSetCount": target_count,
                "overallRanked": {
                    "rankedSetCount": target_count if ranked_count is None else ranked_count
                },
            },
            "ripWeightsConfig": {
                "overallRip": {"version": overall_version},
                "financialRip": {"version": financial_version},
                "collectorAppeal": {"version": appeal_version},
                "publicContract": {"version": contract_version},
            },
        },
    }}


def test_complete_cohort_builds_history_publication_contract():
    snapshot, rows = command.publication_contract(_row())
    assert snapshot["market_date"] == "2026-08-01"
    assert snapshot["eligible_cohort_count"] == 1
    assert len(rows) == 1


def test_published_rows_carry_the_canonical_scores_not_the_legacy_ones():
    """THE regression this file exists for.

    The fixture gives the canonical and legacy objects deliberately DIFFERENT
    scores, so a publisher that read `rip`/`ripCore` would produce 78/70 here
    instead of 80/75 and this assertion would catch it.
    """
    snapshot, rows = command.publication_contract(_row())
    assert rows[0]["overall_rip_score"] == 80
    assert rows[0]["financial_rip_score"] == 75
    assert snapshot["overall_rip_version"] == CANONICAL["overallRipVersion"]
    assert snapshot["financial_rip_version"] == CANONICAL["financialRipVersion"]
    # `ca7_version` is the historical COLUMN name; it carries the canonical
    # Collector Appeal version, and the diagnostics block records the same value
    # under an unambiguous key.
    assert snapshot["ca7_version"] == CANONICAL["collectorAppealVersion"]
    assert snapshot["diagnostics"]["collector_appeal_version"] == (
        CANONICAL["collectorAppealVersion"]
    )
    assert snapshot["diagnostics"]["public_rip_contract_version"] == (
        CANONICAL["publicRipContractVersion"]
    )
    assert snapshot["diagnostics"]["supported_cohort_fingerprint"] == "stub-fingerprint"
    assert snapshot["diagnostics"]["source_calculation_run_ids"] == {"set-0": "run-0"}


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"overall_version": "overall_rip_v6_80_financial_v3_20_collector_appeal_v2"},
         "Overall RIP version .* is not the canonical"),
        ({"financial_version": "financial_rip_v2_60_25_15"},
         "Financial RIP version .* is not the canonical"),
        ({"contract_version": "public_rip_contract_v6"},
         "public RIP contract version .* is not the canonical"),
        ({"appeal_version": "collector_appeal_v2_desirable_frequency_dual_path"},
         "Collector Appeal version .* is not the canonical"),
    ],
)
def test_a_superseded_version_refuses_to_publish(kwargs, expected):
    """Versions are VERIFIED, not merely copied.

    A payload built by an older worker, or a metadata block left behind by the
    next cutover, must refuse rather than mint a snapshot under a superseded
    contract that then reads as authoritative.
    """
    with pytest.raises(RuntimeError, match=expected):
        command.publication_contract(_row(**kwargs))


def test_incomplete_cohort_fails_closed():
    with pytest.raises(RuntimeError, match="incomplete Overall RIP V8 cohort"):
        command.publication_contract(_row(target_count=2, ranked_count=1))


def test_missing_or_mixed_appeal_version_fails_closed():
    with pytest.raises(RuntimeError, match="incompatible Collector Appeal versions"):
        command.publication_contract(_row(appeal_version=None))


def test_a_cohort_that_does_not_match_the_supported_set_list_fails_closed():
    """Support comes from the authoritative set list, never from "a score exists".

    A set whose simulation failed would otherwise leave the cohort silently and
    shrink every denominator with nothing recording that the population changed.
    """
    payload = _row()
    _set_supported_keys(["set-0", "set-1", "set-2"])
    with pytest.raises(RuntimeError, match="does not match the authoritative supported cohort"):
        command.publication_contract(payload)


def test_a_legacy_v4_rank_no_longer_gates_canonical_publication():
    """The transitional v4-cohort precondition is gone, and must stay gone.

    Migration 054's RPC counted ranked targets by the LEGACY ``rip.rank``, so the
    publisher carried a precondition requiring the Overall RIP v4 cohort to match
    the canonical V7 one. Migration 061 repointed the RPC at ``overallRipV8.rank``
    and made it verify ``publicRipContractV8.contractVersion`` itself; it is
    applied in production, so the database is now authoritative about the
    canonical cohort.

    Keeping the precondition would keep a retired model load-bearing for a
    publication that no longer consults it: a set with a perfectly good V7 score
    could be refused because a v4 score it does not publish happened to be null.
    """
    payload = _row()
    payload["ranking_payload_json"]["targets"][0]["rip"] = {"score": 78, "rank": None}

    snapshot, rows = command.publication_contract(payload)

    assert snapshot["overall_rip_version"] == CANONICAL_OVERALL_RIP_VERSION
    assert len(rows) == snapshot["eligible_cohort_count"]


def test_history_rows_carry_the_canonical_v7_and_v3_scores():
    """The stored history is the canonical model's, on its own fixed-anchor scale.

    A rank-movement consumer reads these rows, so a legacy score reaching them
    would reintroduce the cross-model comparison at the storage layer.
    """
    snapshot, rows = command.publication_contract(_row())
    targets = {
        str(target.get("set_id")): target
        for target in _row()["ranking_payload_json"]["targets"]
    }
    for row in rows:
        target = targets[str(row["set_id"])]
        assert row["overall_rip_score"] == target["overallRipV8"]["score"]
        assert row["overall_rip_rank"] == target["overallRipV8"]["rank"]
        assert row["financial_rip_score"] == target["financialRipV3"]["score"]
        assert row["financial_rip_rank"] == target["financialRipV3"]["rank"]
        # Never the legacy objects, which the fixture gives different values.
        assert row["overall_rip_score"] != target.get("rip", {}).get("score")
        assert row["financial_rip_score"] != target.get("ripCore", {}).get("score")


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda t: t["publicRipContractV8"]["overallRip"].pop("relativeScore"),
         "overallRip.relativeScore is missing"),
        (lambda t: t["publicRipContractV8"]["overallRip"].pop("absoluteScore"),
         "overallRip.absoluteScore is missing"),
        (lambda t: t["publicRipContractV8"]["overallRip"].pop("cohortFingerprint"),
         "overallRip.cohortFingerprint is missing"),
        (lambda t: t["publicRipContractV8"]["financialRip"].pop("relativeScore"),
         "financialRip.relativeScore is missing"),
        (lambda t: t["publicRipContractV8"]["collectorAppeal"].pop("relativeScore"),
         "collectorAppeal.relativeScore is missing"),
        (lambda t: t["publicRipContractV8"]["collectorAppeal"].pop("rankedSetCount"),
         "collectorAppeal.rankedSetCount is missing"),
        (lambda t: t["publicRipContractV8"]["financialRip"]["components"]["jackpotUpside"]
         .pop("relativeScore"),
         r"components\.jackpotUpside\.relativeScore is missing"),
        (lambda t: t.pop("publicRipContractV8"), "publicRipContractV8 is missing"),
    ],
)
def test_a_supported_set_missing_a_canonical_score_fails_publication(mutate, expected):
    """It FAILS; it does not quietly leave the cohort.

    Dropping the set would shrink every denominator and shift every relative
    score, with nothing downstream recording that the population moved - which
    is indistinguishable from the set never having existed.
    """
    payload = _row(target_count=2)
    mutate(payload["ranking_payload_json"]["targets"][1])
    with pytest.raises(RuntimeError, match=expected):
        command.publication_contract(payload)


def test_a_complete_cohort_reports_no_score_contract_problems():
    payload = _row(target_count=2)
    for target in payload["ranking_payload_json"]["targets"]:
        assert command._score_contract_problems(target) == []


def test_a_zero_relative_score_is_not_treated_as_missing():
    """The bottom-ranked set's relative score IS 0.0, and 0.0 is a value."""
    payload = _row(target_count=2)
    payload["ranking_payload_json"]["targets"][1]["publicRipContractV8"]["overallRip"][
        "relativeScore"
    ] = 0.0
    assert command._score_contract_problems(
        payload["ranking_payload_json"]["targets"][1]
    ) == []


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
            "054_fix_pokemon_public_rip_ranked_target_contract.sql",
            # The canonical V7 revision. It replaces 054's legacy `{rip,rank}`
            # ranked-target predicate with `{overallRipV7,rank}`; it is the same
            # single authoritative writer, not a second one.
            "061_update_public_rip_rpc_to_v7.sql",
            # The canonical V8 revision, and the writer in force today. It is a
            # forward-only CREATE OR REPLACE of the SAME function 061 defines,
            # repointed at `{overallRipV8,rank}` and the Collector Appeal V4
            # identity strings. Each entry above it is a superseded revision of
            # that one function retained for history, not an additional writer -
            # this list is "revisions of the single authoritative writer", which
            # is why it grows by one on every RPC cutover.
            "062_update_public_rip_rpc_to_v8.sql",
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


def _publication_parameters(*, ranked=22, unranked=12):
    row = _row(target_count=ranked)
    row["ranking_payload_json"]["meta"]["publicAnalyticsCohort"]["overallRanked"]["rankedSetCount"] = ranked
    row["ranking_payload_json"]["meta"]["publicAnalyticsCohort"]["eligibleSetCount"] = ranked
    for index in range(ranked, ranked + unranked):
        row["ranking_payload_json"]["targets"].append({
            "set_id": f"00000000-0000-0000-0000-{index:012d}",
            "canonical_key": f"set-{index}",
            "rip": {"score": None, "rank": None},
        })
    snapshot, history = command.publication_contract(row)
    # The publisher owns publication metadata; call the same writer it does so
    # the preflight tests below exercise the real marker and not a copy of it.
    command.attach_publication_metadata(row, snapshot)
    return row, snapshot, history


def test_complete_discovery_payload_can_exceed_ranked_cohort():
    row, snapshot, history = _publication_parameters(ranked=22, unranked=12)
    command.validate_publication_payload(row, snapshot, history)
    assert len(row["ranking_payload_json"]["targets"]) == 34
    assert len(history) == 22


def test_ranked_only_payload_remains_valid():
    row, snapshot, history = _publication_parameters(ranked=22, unranked=0)
    command.validate_publication_payload(row, snapshot, history)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda row, snapshot, history: history.pop(), "history row count"),
        (
            lambda row, snapshot, history: history[0].update(
                set_id="ffffffff-ffff-ffff-ffff-ffffffffffff"
            ),
            "ranked target/history set IDs differ",
        ),
        (
            lambda row, snapshot, history: row["ranking_payload_json"]["targets"][1].update(
                set_id=row["ranking_payload_json"]["targets"][0]["set_id"]
            ),
            "duplicate ranked target set IDs",
        ),
        (
            lambda row, snapshot, history: row["ranking_payload_json"]["meta"]["snapshot"].pop(
                "publicationId"
            ),
            "publicationId is missing",
        ),
        (
            lambda row, snapshot, history: row["ranking_payload_json"]["meta"]["snapshot"].update(
                publicationId="ffffffff-ffff-ffff-ffff-ffffffffffff"
            ),
            "publicationId does not match",
        ),
        (
            lambda row, snapshot, history: row["ranking_payload_json"]["meta"]["snapshot"].update(
                marketDate="2026-07-31"
            ),
            "marketDate does not match",
        ),
    ],
)
def test_application_preflight_rejects_malformed_contract(mutation, message):
    row, snapshot, history = _publication_parameters()
    mutation(row, snapshot, history)
    with pytest.raises(RuntimeError, match=message):
        command.validate_publication_payload(row, snapshot, history)


def test_application_preflight_rejects_ranked_count_mismatch():
    """The preflight counts the CANONICAL rank, matching what the publisher wrote.

    It used to count ``rip.rank`` (Overall RIP v4). Leaving it there after the
    publisher moved to ``overallRipV8`` would have made the preflight validate a
    different cohort from the one being published - the two could disagree and
    nothing would notice.
    """
    row, snapshot, history = _publication_parameters()
    row["ranking_payload_json"]["targets"][0]["overallRipV8"]["rank"] = None
    with pytest.raises(RuntimeError, match="ranked target count"):
        command.validate_publication_payload(row, snapshot, history)


def test_rpc_contract_counts_ranked_targets_and_checks_set_parity():
    migration = (
        Path(__file__).resolve().parents[3]
        / "db/migrations/054_fix_pokemon_public_rip_ranked_target_contract.sql"
    ).read_text(encoding="utf-8")
    assert "target #> '{rip,rank}' <> 'null'::JSONB" in migration
    assert "v_ranked_targets <> v_expected" in migration
    assert "v_total_targets < v_expected" in migration
    assert "EXCEPT" in migration
    assert "jsonb_array_length(v_payload->'targets') <> v_expected" not in migration


def test_shared_publisher_sends_complete_discovery_payload(monkeypatch):
    row, _snapshot, _history = _publication_parameters()
    # The publisher owns publication metadata, so start with the builder shape.
    row["ranking_payload_json"]["meta"]["snapshot"].pop("publicationId")
    row["ranking_payload_json"]["meta"]["snapshot"].pop("marketDate")
    client = _Client(previous=[], existing=[])
    monkeypatch.setattr(command, "build_explore_rankings_snapshot_row", lambda **_kwargs: row)
    command.publish_explore_rip_rankings_snapshot(client, commit=True)
    rpc = next(call for call in client.calls if call[0] == "rpc")
    assert len(rpc[2]["p_latest"]["ranking_payload_json"]["targets"]) == 34
    assert len(rpc[2]["p_rows"]) == 22


# ---------------------------------------------------------------------------
# The canonical checklist Set Value publication contract.
#
# The public targets reader used to run a compatibility DB fill on every healthy
# request because nothing on the publish path guaranteed the value was there.
# These tests are what turns that from an assumption into a contract: a candidate
# whose RANKED targets are missing the authoritative Set Value must not be able
# to replace the valid published leaderboard.
# ---------------------------------------------------------------------------


def _mutate_targets(row, mutate, *, ranked_only=True):
    for target in row["ranking_payload_json"]["targets"]:
        if ranked_only and (target.get("overallRipV8") or {}).get("rank") is None:
            continue
        mutate(target)
    return row


def test_ranked_target_with_a_valid_set_value_publishes():
    """A. The happy path: the canonical value and its as-of are present."""
    snapshot, rows = command.publication_contract(_row())
    assert len(rows) == 1


def test_ranked_target_missing_the_canonical_set_value_refuses_to_publish():
    """B. The defect this contract exists to prevent."""
    row = _mutate_targets(_row(), lambda target: [
        target.pop(field, None) for field in SET_VALUE_VALUE_FIELDS
    ])
    with pytest.raises(RuntimeError, match="checklistSetValue is missing"):
        command.publication_contract(row)


def test_a_malformed_set_value_type_refuses_to_publish():
    """C. A stringified value is a serialization defect, not a value."""
    row = _mutate_targets(_row(), lambda target: target.update(checklistSetValue="561.26"))
    with pytest.raises(RuntimeError, match="checklistSetValue is missing or not a positive number"):
        command.publication_contract(row)


def test_a_set_value_alias_that_disagrees_refuses_to_publish():
    """C2. The aliases are the fields the compatibility fill used to write."""
    row = _mutate_targets(_row(), lambda target: target.update(checklist_set_value=1.0))
    with pytest.raises(RuntimeError, match="checklist_set_value does not match"):
        command.publication_contract(row)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda target: target.pop("checklistSetValueAsOf"), "checklistSetValueAsOf is missing"),
        (
            lambda target: target.update(checklistSetValueAsOf="2026-07-04"),
            "publication market date",
        ),
    ],
)
def test_set_value_as_of_must_match_the_publication_market_date(mutate, expected):
    """D. A value carrying another date was not built for this publication."""
    row = _mutate_targets(_row(), mutate)
    with pytest.raises(RuntimeError, match=expected):
        command.publication_contract(row)


def test_an_unranked_discovery_target_may_lack_a_set_value_and_still_publish():
    """E. The explicitly encoded exception.

    A newly onboarded set appears as an unranked discovery target before its
    daily set-value history starts - `pitchBlack` did exactly that for the whole
    of July 2026. Refusing to publish the leaderboard over it would make a normal
    onboarding break publication, so it publishes and reports partial coverage.
    """
    row, snapshot, history = _publication_parameters(ranked=1, unranked=1)
    command.validate_publication_payload(row, snapshot, history)
    marker = row["ranking_payload_json"]["meta"]["snapshot"]["setValueContract"]
    assert marker["coverage"] == "partial"
    assert marker["targetCount"] == 2
    assert marker["coveredTargetCount"] == 1


def test_a_complete_publication_carries_the_set_value_capability_marker(monkeypatch):
    row = _row()
    client = _Client(previous=[], existing=[])
    monkeypatch.setattr(command, "build_explore_rankings_snapshot_row", lambda **_kwargs: row)
    command.publish_explore_rip_rankings_snapshot(client, commit=True)
    rpc = next(call for call in client.calls if call[0] == "rpc")
    marker = rpc[2]["p_latest"]["ranking_payload_json"]["meta"]["snapshot"]["setValueContract"]
    assert marker == {
        "version": PUBLIC_SET_VALUE_CONTRACT_VERSION,
        "coverage": "complete",
        "targetCount": 1,
        "coveredTargetCount": 1,
        "asOf": "2026-08-01",
    }
    assert payload_guarantees_canonical_set_value(rpc[2]["p_latest"]["ranking_payload_json"])


def test_a_candidate_missing_set_value_never_reaches_the_publish_rpc(monkeypatch):
    """The guard is on the publication, not merely on a helper.

    The previously valid snapshot stays active because the atomic RPC is never
    invoked at all.
    """
    row = _mutate_targets(_row(), lambda target: [
        target.pop(field, None) for field in SET_VALUE_VALUE_FIELDS
    ])
    client = _Client(previous=[], existing=[])
    monkeypatch.setattr(command, "build_explore_rankings_snapshot_row", lambda **_kwargs: row)
    with pytest.raises(RuntimeError, match="checklistSetValue is missing"):
        command.publish_explore_rip_rankings_snapshot(client, commit=True)
    assert not [call for call in client.calls if call[0] == "rpc"]


def test_publication_preflight_rejects_a_stripped_set_value_marker():
    row, snapshot, history = _publication_parameters(ranked=1, unranked=0)
    row["ranking_payload_json"]["meta"]["snapshot"].pop("setValueContract", None)
    with pytest.raises(RuntimeError, match="set value contract marker"):
        command.validate_publication_payload(row, snapshot, history)
