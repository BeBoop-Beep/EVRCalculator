"""Phase 8.1: the preview must be the write, and the write must hit ONE real row.

The tests here defend two properties:

1. There is no second code path. A preview built by different code from the write
   is not a preview, it is a guess that happens to agree most of the time.

2. The write addresses exactly one existing row, by primary key, with a
   concurrency token. The previous design - ``upsert(on_conflict="set_id")`` -
   passed its tests only because the fake accepted any conflict key. The fake
   here is SCHEMA-AWARE: it refuses conflict targets that do not exist in
   Postgres, which is what the old test suite should have done.
"""

from __future__ import annotations

import ast
import copy
import inspect

import pytest

from backend.desirability.collector_appeal import COLLECTOR_APPEAL_DIAGNOSTICS_KEY
from backend.desirability.collector_appeal_fingerprint import current_fingerprint
from backend.desirability.component_source import (
    COMPONENT_UNIQUE_KEY,
    EXPECTED_COMPOSITE_SCORING_VERSION,
    EXPECTED_HIT_POLICY_VERSION,
    EXPECTED_SCORING_VERSION,
)
from backend.desirability.collector_appeal_rollout import (
    COMPONENT_TABLE,
    PROTECTED_SCORE_COLUMNS,
    WRITABLE_COLUMNS,
    PartialWriteError,
    ReadOnlyClientGuard,
    WriteAttemptedError,
    build_full_source_manifest,
    build_update_plan,
    describe_write_strategy,
    execute_plan,
    load_source_state,
    normalized_payload_hash,
    paged_select_all,
    rip_consumed_coverage,
)

V1 = "pokemon_card_desirability_hit_policy_v1"


# ---------------------------------------------------------------------------
# Schema-aware fakes
# ---------------------------------------------------------------------------

class UniqueConstraintViolation(Exception):
    """What Postgres raises for an on_conflict target that is not a constraint."""


class FakeQuery:
    def __init__(self, rows, recorder):
        self._rows = rows
        self._recorder = recorder

    def select(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        start, end = self._range
        self._recorder.append({"op": "select", "range": (start, end)})
        return type("R", (), {"data": self._rows[start:end + 1]})()


class SchemaAwareTable:
    """A fake that enforces the REAL constraints of the component table.

    Specifically:
      * ``upsert(on_conflict=...)`` raises unless the target is an actual unique
        constraint. ``set_id`` is not one, so the old write path fails here the
        way it would fail in Postgres.
      * ``update().eq(...)`` returns only the rows its predicate matches, so a
        stale ``updated_at`` returns zero rows rather than silently succeeding.
    """

    def __init__(self, rows, recorder):
        self._rows = rows
        self._recorder = recorder
        self._filters = []
        self._payload = None

    def select(self, *args, **kwargs):
        return FakeQuery(self._rows, self._recorder)

    def upsert(self, payload, **kwargs):
        on_conflict = kwargs.get("on_conflict", "")
        target = tuple(part.strip() for part in on_conflict.split(",") if part.strip())
        if target != tuple(COMPONENT_UNIQUE_KEY):
            raise UniqueConstraintViolation(
                f'there is no unique or exclusion constraint matching ON CONFLICT ({on_conflict})'
            )
        self._recorder.append({"op": "upsert", "rows": len(payload)})
        return type("E", (), {"execute": lambda self_: type("R", (), {"data": payload})()})()

    def insert(self, payload, **kwargs):
        self._recorder.append({"op": "insert"})
        return self

    def update(self, payload, **kwargs):
        self._payload = payload
        self._filters = []
        self._recorder.append({"op": "update", "payload_keys": sorted(payload)})
        return self

    def delete(self, **kwargs):
        self._recorder.append({"op": "delete"})
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def execute(self):
        matched = [
            row for row in self._rows
            if all(str(row.get(column)) == str(value) for column, value in self._filters)
        ]
        for row in matched:
            row.update(self._payload or {})
        self._recorder.append({"op": "update_execute", "filters": list(self._filters),
                               "matched": len(matched)})
        return type("R", (), {"data": matched})()


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.recorder = []

    def table(self, name):
        return SchemaAwareTable(self.rows, self.recorder)

    def rpc(self, *args, **kwargs):
        self.recorder.append({"op": "rpc"})
        return self


def _row(set_id, key, score, *, diagnostics=None, built_at="2026-06-14T22:59:34Z",
         hit_policy=EXPECTED_HIT_POLICY_VERSION, row_id=None, updated_at=None):
    return {
        "id": row_id or f"row-{set_id}",
        "set_id": set_id,
        "set_name": key,
        "set_canonical_key": key,
        "scoring_version": EXPECTED_SCORING_VERSION,
        "hit_policy_version": hit_policy,
        "composite_scoring_version": EXPECTED_COMPOSITE_SCORING_VERSION,
        "fan_popularity_snapshot_id": "snap-1",
        "config_fingerprint": f"cfg-{set_id}",
        "set_desirability_score": score,
        "hit_eligible_card_count": 40,
        "scored_hit_eligible_card_count": 40,
        "unique_subject_count": 10,
        "subject_rollups_json": [
            {
                "subject_key": "ref:1",
                "subject_name": "Pikachu",
                "pokemon_reference_id": 1,
                "max_desirability_score": 90.0,
                "rarity_buckets_present": ["premium_chase"],
                "card_count": 2,
            }
        ],
        "diagnostics_json": diagnostics if diagnostics is not None else {"canonical_cards_seen": 100},
        "built_at": built_at,
        "updated_at": updated_at or built_at,
    }


def _fixture_rows():
    return [
        _row("s1", "evolvingSkies", 70.0),
        _row("s2", "swshBlackStarPromos", 0.0),
        _row("s3", "exTrainerKitLatias", 0.0),
    ]


def _state(client=None):
    client = client or FakeClient(_fixture_rows())
    return load_source_state(client), client


def _subjects():
    return {
        "s1": [{
            "subject_key": "ref:1", "subject_name": "Pikachu", "subject_demand": 90.0,
            "appeal_excess": 0.8,
            "cards": [
                {"card_name": "easy", "pull_probability": 0.1},
                {"card_name": "elite", "pull_probability": 0.001},
            ],
        }]
    }


def _approved(plan):
    return {
        "expected_fingerprint": plan["expected_fingerprint"],
        "expected_manifest_hash": plan["source_manifest"]["manifest_hash"],
        "expected_payload_hash": plan["normalized_payload_hash"],
    }


# ---------------------------------------------------------------------------
# The write spy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method", ["insert", "upsert", "update", "delete"])
def test_read_only_guard_blocks_every_mutating_table_method(method):
    guard = ReadOnlyClientGuard(FakeClient(_fixture_rows()))
    with pytest.raises(WriteAttemptedError):
        getattr(guard.table(COMPONENT_TABLE), method)([{"set_id": "s1"}])
    assert guard.write_attempts


def test_read_only_guard_blocks_client_level_rpc():
    guard = ReadOnlyClientGuard(FakeClient(_fixture_rows()))
    with pytest.raises(WriteAttemptedError):
        guard.rpc("anything")


def test_read_only_guard_allows_reads_and_logs_them():
    client = FakeClient(_fixture_rows())
    guard = ReadOnlyClientGuard(client)
    state = load_source_state(guard)
    assert len(state["selected_rows"]) == 3
    assert not guard.write_attempts
    assert any(call["op"] == "select" for call in guard.calls)


def test_loading_and_planning_reach_no_write_method():
    client = FakeClient(_fixture_rows())
    guard = ReadOnlyClientGuard(client)
    plan = build_update_plan(load_source_state(guard))
    execute_plan(plan, guard, commit=False)
    assert not guard.write_attempts
    assert not [call for call in client.recorder if call["op"] in ("upsert", "insert", "update", "delete")]


# ---------------------------------------------------------------------------
# The schema contract the old fake could not see
# ---------------------------------------------------------------------------

def test_the_schema_aware_fake_rejects_the_old_on_conflict_set_id_upsert():
    """The old write path, run against a fake that knows the real constraints.

    This is the test the previous suite could not have failed: its fake accepted
    every conflict key, so ``on_conflict="set_id"`` looked fine right up until
    production.
    """
    client = FakeClient(_fixture_rows())
    with pytest.raises(UniqueConstraintViolation, match="no unique or exclusion constraint"):
        client.table(COMPONENT_TABLE).upsert(
            [{"set_id": "s1", "diagnostics_json": {}}], on_conflict="set_id"
        ).execute()


def test_the_schema_aware_fake_accepts_only_the_real_six_column_key():
    client = FakeClient(_fixture_rows())
    client.table(COMPONENT_TABLE).upsert(
        [{"set_id": "s1"}], on_conflict=",".join(COMPONENT_UNIQUE_KEY)
    ).execute()
    assert [call for call in client.recorder if call["op"] == "upsert"]


def test_the_rollout_module_contains_no_upsert_call_at_all():
    """AST, not text search: the write strategy DOCUMENTS upsert as forbidden,
    and a substring scan cannot tell prose from a call."""
    import backend.desirability.collector_appeal_rollout as module

    tree = ast.parse(inspect.getsource(module))
    upserts = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "upsert"
    ]
    assert not upserts, "the rollout must never upsert this table"


def test_execute_plan_is_the_only_module_function_that_writes():
    import backend.desirability.collector_appeal_rollout as module

    tree = ast.parse(inspect.getsource(module))
    banned = {"upsert", "insert", "delete", "update"}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "execute_plan":
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr in banned):
                # dict.update() on a local is not a database write.
                target = inner.func.value
                is_local_dict = isinstance(target, ast.Name) and target.id in (
                    "row", "identity", "appeal_block", "entry", "bucket"
                )
                assert is_local_dict, f"{node.name}() calls .{inner.func.attr}() on a client"


# ---------------------------------------------------------------------------
# Version-exact source selection through the loader
# ---------------------------------------------------------------------------

def test_load_source_state_ignores_a_newer_wrong_version_row():
    rows = _fixture_rows() + [
        _row("s1", "evolvingSkies", 70.0, hit_policy=V1, row_id="row-s1-v1",
             built_at="2026-07-16T00:00:00Z"),
    ]
    state = load_source_state(FakeClient(rows))
    assert state["selected_rows"]["s1"]["id"] == "row-s1"
    assert state["selected_rows"]["s1"]["hit_policy_version"] == EXPECTED_HIT_POLICY_VERSION


def test_a_set_with_only_an_old_version_row_is_reported_unavailable_and_unplanned():
    rows = [
        _row("s1", "evolvingSkies", 70.0),
        _row("chaos", "chaosRising", 60.0, hit_policy=V1, row_id="row-chaos-v1"),
    ]
    plan = build_update_plan(load_source_state(FakeClient(rows)))

    assert [row["set_id"] for row in plan["rows"]] == ["s1"]
    unavailable = plan["unavailable_sources"][0]
    assert unavailable["set_id"] == "chaos"
    assert unavailable["reason"] == "missing_current_component_source_row"
    assert [v["hit_policy_version"] for v in unavailable["available_versions"]] == [V1]
    assert EXPECTED_HIT_POLICY_VERSION in unavailable["rebuild_command"]
    assert plan["counts"]["exact_version_source_rows_missing"] == 1


def test_an_unavailable_set_is_still_classified_so_the_census_stays_whole():
    rows = [
        _row("s1", "evolvingSkies", 70.0),
        _row("kit", "exTrainerKitLatias", 0.0, hit_policy=V1, row_id="row-kit-v1"),
    ]
    plan = build_update_plan(load_source_state(FakeClient(rows)))
    unavailable = plan["unavailable_sources"][0]
    assert unavailable["booster_supported"] is False
    assert unavailable["product_support_type"] == "unsupported_trainer_kit"


def test_planning_raises_if_a_selected_row_carries_the_wrong_versions():
    """Defence in depth: even if selection were bypassed, certification fails."""
    from backend.desirability import collector_appeal_rollout as module

    state = load_source_state(FakeClient(_fixture_rows()))
    # Smuggle a v1 row past the selector.
    state["selected_rows"]["s1"] = _row("s1", "evolvingSkies", 70.0, hit_policy=V1)
    state["selection"]["selected"] = state["selected_rows"]
    with pytest.raises(AssertionError, match="refusing to certify"):
        module.build_update_plan(state)


# ---------------------------------------------------------------------------
# Source identity in the payload
# ---------------------------------------------------------------------------

def test_every_block_carries_a_source_identity_describing_its_own_row():
    state, _ = _state()
    plan = build_update_plan(state)
    for row in plan["rows"]:
        identity = row["proposed_diagnostics"][COLLECTOR_APPEAL_DIAGNOSTICS_KEY]["source_identity"]
        assert identity["component_row_id"] == f"row-{row['set_id']}"
        assert identity["hit_policy_version"] == EXPECTED_HIT_POLICY_VERSION
        assert identity["scoring_version"] == EXPECTED_SCORING_VERSION
        assert identity["composite_scoring_version"] == EXPECTED_COMPOSITE_SCORING_VERSION
        assert identity["fan_popularity_snapshot_id"] == "snap-1"
        assert identity["config_fingerprint"] == f"cfg-{row['set_id']}"
        assert identity["built_at"] and identity["updated_at"]


def test_source_identity_is_separate_from_the_formula_fingerprint():
    """Two identities, two questions. Neither answers the other's."""
    state, _ = _state()
    plan = build_update_plan(state)
    block = plan["rows"][0]["proposed_diagnostics"][COLLECTOR_APPEAL_DIAGNOSTICS_KEY]
    assert block["fingerprint"] == current_fingerprint()          # the RULES
    assert block["source_identity"]["component_row_id"] == "row-s1"  # the INPUTS
    assert "fingerprint" not in block["source_identity"]


# ---------------------------------------------------------------------------
# The naming collision
# ---------------------------------------------------------------------------

def test_the_block_is_namespaced_and_declares_what_it_is():
    state, _ = _state()
    plan = build_update_plan(state)
    block = plan["rows"][0]["proposed_diagnostics"][COLLECTOR_APPEAL_DIAGNOSTICS_KEY]
    assert COLLECTOR_APPEAL_DIAGNOSTICS_KEY == "collector_appeal_ca7"
    assert block["metric_name"] == "collector_appeal_ca7"
    assert block["product_status"] == "internal_candidate"
    assert block["formula"] == "CA7"


def test_no_payload_introduces_a_generic_collector_appeal_key():
    """The public collector_appeal_score is Pure/Universal Desirability.
    CA7 must not squat on that name."""
    state, _ = _state()
    plan = build_update_plan(state)
    for row in plan["rows"]:
        diagnostics = (row["update_payload"] or {}).get("diagnostics_json", {})
        assert "collector_appeal" not in diagnostics


def test_an_existing_generic_collector_appeal_block_is_left_untouched():
    rows = _fixture_rows()
    rows[0]["diagnostics_json"] = {
        "canonical_cards_seen": 100,
        "collector_appeal": {"value": 42.0, "source": "pure_universal_desirability"},
    }
    plan = build_update_plan(load_source_state(FakeClient(rows)))
    row = next(r for r in plan["rows"] if r["set_id"] == "s1")
    assert row["proposed_diagnostics"]["collector_appeal"] == {
        "value": 42.0, "source": "pure_universal_desirability"
    }
    assert COLLECTOR_APPEAL_DIAGNOSTICS_KEY in row["proposed_diagnostics"]
    changed = [field["field"] for field in row["changed_fields"]]
    assert changed == [f"diagnostics_json.{COLLECTOR_APPEAL_DIAGNOSTICS_KEY}"]


# ---------------------------------------------------------------------------
# One code path
# ---------------------------------------------------------------------------

def test_dry_run_and_commit_target_the_same_rows():
    """THE core property: same plan, same targets; only sending differs."""
    state, client = _state()
    plan = build_update_plan(state)

    dry = execute_plan(plan, client, commit=False)
    wet = execute_plan(plan, client, commit=True, **_approved(plan))
    assert dry["target_set_ids"] == wet["target_set_ids"]
    assert dry["target_row_ids"] == wet["target_row_ids"]
    assert dry["rows_targeted"] == wet["rows_targeted"]
    assert dry["writes_performed"] == 0
    assert wet["writes_performed"] == wet["rows_targeted"]


def test_commit_updates_by_primary_key_never_by_set_id():
    state, client = _state()
    plan = build_update_plan(state)
    execute_plan(plan, client, commit=True, **_approved(plan))

    executed = [call for call in client.recorder if call["op"] == "update_execute"]
    assert len(executed) == 3
    for call in executed:
        columns = [column for column, _value in call["filters"]]
        assert columns == ["id", "updated_at"]
        assert call["matched"] == 1
    assert not [call for call in client.recorder if call["op"] in ("upsert", "insert")]


def test_commit_writes_only_the_diagnostics_column():
    state, client = _state()
    plan = build_update_plan(state)
    execute_plan(plan, client, commit=True, **_approved(plan))
    for call in [c for c in client.recorder if c["op"] == "update"]:
        assert call["payload_keys"] == ["diagnostics_json"]


def test_commit_leaves_every_score_version_and_source_column_untouched():
    rows = _fixture_rows()
    before = copy.deepcopy(rows)
    client = FakeClient(rows)
    plan = build_update_plan(load_source_state(client))
    execute_plan(plan, client, commit=True, **_approved(plan))

    for original, written in zip(before, rows):
        for column in original:
            if column == "diagnostics_json":
                continue
            assert written[column] == original[column], f"{column} changed"


def test_commit_inserts_nothing():
    rows = _fixture_rows()
    client = FakeClient(rows)
    plan = build_update_plan(load_source_state(client))
    execute_plan(plan, client, commit=True, **_approved(plan))
    assert len(client.rows) == 3
    assert plan["counts"]["would_insert"] == 0
    assert not [call for call in client.recorder if call["op"] == "insert"]


# ---------------------------------------------------------------------------
# Optimistic concurrency
# ---------------------------------------------------------------------------

def test_a_stale_updated_at_fails_rather_than_overwriting():
    """The row moved after the preview. Zero rows match; nothing is clobbered."""
    rows = _fixture_rows()
    client = FakeClient(rows)
    plan = build_update_plan(load_source_state(client))

    # Production moves underneath us.
    rows[0]["updated_at"] = "2026-07-20T00:00:00Z"
    rows[0]["diagnostics_json"] = {"canonical_cards_seen": 999}

    with pytest.raises(PartialWriteError) as excinfo:
        execute_plan(plan, client, commit=True, **_approved(plan))

    result = excinfo.value.result
    failure = next(f for f in result["failures"] if f["set_id"] == "s1")
    assert failure["error"] == "stale_or_missing_row"
    assert rows[0]["diagnostics_json"] == {"canonical_cards_seen": 999}  # untouched


def test_a_partial_write_reports_the_exact_ids_that_landed():
    rows = _fixture_rows()
    client = FakeClient(rows)
    plan = build_update_plan(load_source_state(client))
    rows[0]["updated_at"] = "2026-07-20T00:00:00Z"

    with pytest.raises(PartialWriteError) as excinfo:
        execute_plan(plan, client, commit=True, **_approved(plan))

    result = excinfo.value.result
    assert result["updated_row_ids"] == ["row-s2", "row-s3"]
    assert result["writes_performed"] == 2
    assert result["rows_targeted"] == 3
    assert result["partial"] is True
    assert [f["set_id"] for f in result["failures"]] == ["s1"]


def test_a_vanished_row_fails_instead_of_inserting():
    rows = _fixture_rows()
    client = FakeClient(rows)
    plan = build_update_plan(load_source_state(client))
    rows.pop(0)

    with pytest.raises(PartialWriteError) as excinfo:
        execute_plan(plan, client, commit=True, **_approved(plan))
    assert excinfo.value.result["failures"][0]["error"] == "stale_or_missing_row"
    assert len(client.rows) == 2  # nothing re-created


def test_a_non_unique_predicate_fails_rather_than_writing_two_rows():
    """Cannot happen against a primary key - which is why it is checked."""
    rows = _fixture_rows()
    duplicate = copy.deepcopy(rows[0])
    rows.append(duplicate)  # same id, same updated_at
    client = FakeClient(rows)
    plan = build_update_plan(load_source_state(FakeClient(_fixture_rows())))

    with pytest.raises(PartialWriteError) as excinfo:
        execute_plan(plan, client, commit=True, **_approved(plan))
    errors = {f["error"] for f in excinfo.value.result["failures"]}
    assert "non_unique_write_predicate" in errors


def test_every_update_target_has_a_non_null_row_id():
    state, _ = _state()
    plan = build_update_plan(state)
    for row in plan["rows"]:
        if row["would_update"]:
            assert row["update_target"]["id"]
            assert row["update_target"]["expected_updated_at"]


def test_a_target_without_a_row_id_is_refused_at_plan_time():
    from backend.desirability import collector_appeal_rollout as module

    bad = [{
        "set_id": "s1", "update_payload": {"diagnostics_json": {}},
        "update_target": {"id": None},
    }]
    with pytest.raises(AssertionError, match="no source row ID"):
        module._assert_payload_shape(bad)


def test_a_payload_carrying_identity_columns_is_refused_at_plan_time():
    from backend.desirability import collector_appeal_rollout as module

    bad = [{
        "set_id": "s1",
        "update_payload": {"set_id": "s1", "diagnostics_json": {}},
        "update_target": {"id": "row-s1"},
    }]
    with pytest.raises(AssertionError, match="non-writable columns"):
        module._assert_payload_shape(bad)


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------

def test_the_operation_is_idempotent():
    """Run it twice; the second run plans nothing."""
    rows = _fixture_rows()
    client = FakeClient(rows)
    plan = build_update_plan(load_source_state(client))
    execute_plan(plan, client, commit=True, **_approved(plan))

    second = build_update_plan(load_source_state(FakeClient(rows)))
    assert second["counts"]["would_update"] == 0
    assert second["counts"]["fingerprint_current"] == 3
    assert execute_plan(second, FakeClient(rows), commit=False)["rows_targeted"] == 0


# ---------------------------------------------------------------------------
# Commit guards: all THREE approval tokens
# ---------------------------------------------------------------------------

def test_commit_refuses_without_an_expected_fingerprint():
    state, client = _state()
    plan = build_update_plan(state)
    approved = _approved(plan)
    approved.pop("expected_fingerprint")
    with pytest.raises(RuntimeError, match="fingerprint"):
        execute_plan(plan, client, commit=True, **approved)
    assert not [call for call in client.recorder if call["op"] == "update"]


def test_commit_refuses_on_a_fingerprint_mismatch():
    state, client = _state()
    plan = build_update_plan(state)
    with pytest.raises(RuntimeError, match="fingerprint"):
        execute_plan(plan, client, commit=True, **{**_approved(plan), "expected_fingerprint": "0" * 64})


def test_commit_refuses_when_source_data_changed_since_the_preview():
    state, client = _state()
    plan = build_update_plan(state)
    with pytest.raises(RuntimeError, match="source data has changed"):
        execute_plan(plan, client, commit=True, **{**_approved(plan), "expected_manifest_hash": "stale"})


def test_commit_refuses_on_a_payload_hash_mismatch():
    """The manifest can match while the payload changed - so both are pinned."""
    state, client = _state()
    plan = build_update_plan(state)
    with pytest.raises(RuntimeError, match="payload"):
        execute_plan(plan, client, commit=True, **{**_approved(plan), "expected_payload_hash": "0" * 64})


def test_commit_requires_all_three_tokens():
    state, client = _state()
    plan = build_update_plan(state)
    for omitted in ("expected_fingerprint", "expected_manifest_hash", "expected_payload_hash"):
        approved = _approved(plan)
        approved.pop(omitted)
        with pytest.raises(RuntimeError):
            execute_plan(plan, client, commit=True, **approved)
    assert not [call for call in client.recorder if call["op"] == "update_execute"]


# ---------------------------------------------------------------------------
# Score protection
# ---------------------------------------------------------------------------

def test_no_proposed_payload_touches_a_score_column():
    state, _ = _state()
    plan = build_update_plan(state)
    for row in plan["rows"]:
        payload = row["update_payload"] or {}
        assert set(payload).issubset(set(WRITABLE_COLUMNS))
        for column in PROTECTED_SCORE_COLUMNS:
            assert column not in payload


def test_proposed_score_always_equals_the_current_stored_score():
    state, _ = _state()
    plan = build_update_plan(state)
    for row in plan["rows"]:
        assert row["current_stored_score"] == row["proposed_score"]
    assert plan["counts"]["score_changing_updates"] == 0


def test_plan_raises_rather_than_report_a_score_change():
    from backend.desirability import collector_appeal_rollout as module

    bad = [{"set_id": "s1", "current_stored_score": 1.0, "proposed_score": 2.0, "update_payload": {}}]
    with pytest.raises(AssertionError, match="stored score"):
        module._assert_no_score_changes(bad)

    bad_column = [{
        "set_id": "s1", "current_stored_score": 1.0, "proposed_score": 1.0,
        "update_payload": {"set_desirability_score": 5.0},
    }]
    with pytest.raises(AssertionError, match="protected score column"):
        module._assert_no_score_changes(bad_column)


# ---------------------------------------------------------------------------
# Fingerprint integration
# ---------------------------------------------------------------------------

def test_every_proposed_diagnostics_carries_the_current_fingerprint():
    state, _ = _state()
    plan = build_update_plan(state)
    for row in plan["rows"]:
        block = row["proposed_diagnostics"][COLLECTOR_APPEAL_DIAGNOSTICS_KEY]
        assert block["fingerprint"] == current_fingerprint()
        assert block["lambda"] == 0.50
        assert block["formula"] == "CA7"


def test_rows_without_a_stored_fingerprint_are_reported_missing_and_updated():
    state, _ = _state()
    plan = build_update_plan(state)
    assert plan["counts"]["fingerprint_missing"] == 3
    assert plan["counts"]["would_update"] == 3


def test_a_stale_fingerprint_is_surfaced_and_explained():
    rows = _fixture_rows()
    rows[0]["diagnostics_json"] = {
        "canonical_cards_seen": 100,
        COLLECTOR_APPEAL_DIAGNOSTICS_KEY: {"fingerprint": "0" * 64, "formula": "CA7", "lambda": 0.5},
    }
    plan = build_update_plan(load_source_state(FakeClient(rows)))
    stale = next(row for row in plan["rows"] if row["set_id"] == "s1")
    assert stale["fingerprint_status"] == "stale"
    assert stale["would_update"] is True
    reason = next(f["reason"] for f in stale["changed_fields"]
                  if f["field"].endswith(COLLECTOR_APPEAL_DIAGNOSTICS_KEY))
    assert "different formula fingerprint" in reason


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_two_plans_from_the_same_source_state_are_identical():
    state, _ = _state()
    first = build_update_plan(state)
    second = build_update_plan(state)
    assert [row["update_payload"] for row in first["rows"]] == [row["update_payload"] for row in second["rows"]]
    assert first["counts"] == second["counts"]
    assert first["normalized_payload_hash"] == second["normalized_payload_hash"]


def test_plan_rows_are_deterministically_sorted():
    forward = build_update_plan(load_source_state(FakeClient(_fixture_rows())))
    reversed_rows = list(reversed(_fixture_rows()))
    backward = build_update_plan(load_source_state(FakeClient(reversed_rows)))
    assert [row["set_id"] for row in forward["rows"]] == [row["set_id"] for row in backward["rows"]]
    assert forward["normalized_payload_hash"] == backward["normalized_payload_hash"]


def test_the_payload_hash_covers_the_target_not_just_the_payload():
    """Two plans writing identical diagnostics to different rows are different."""
    state, _ = _state()
    plan = build_update_plan(state)
    baseline = normalized_payload_hash(plan)

    moved = copy.deepcopy(plan)
    moved["rows"][0]["update_target"]["id"] = "some-other-row"
    assert normalized_payload_hash(moved) != baseline


def test_the_payload_hash_moves_when_the_concurrency_token_moves():
    state, _ = _state()
    plan = build_update_plan(state)
    baseline = normalized_payload_hash(plan)

    moved = copy.deepcopy(plan)
    moved["rows"][0]["update_target"]["expected_updated_at"] = "2026-07-20T00:00:00Z"
    assert normalized_payload_hash(moved) != baseline


# ---------------------------------------------------------------------------
# Full source manifest
# ---------------------------------------------------------------------------

def test_the_manifest_covers_every_input_class():
    state, _ = _state()
    manifest = build_full_source_manifest(state, _subjects())
    assert set(manifest["parts"]) == {
        "component_rows", "pull_model", "card_inputs", "simulation_cohort", "policies"
    }
    assert manifest["manifest_hash"]


def test_the_manifest_moves_when_a_subject_rollup_changes():
    """The old manifest hashed set_id + built_at + score only, so this exact
    change - which moves every computed D - left the approval token valid."""
    baseline = build_full_source_manifest(_state()[0])

    rows = _fixture_rows()
    rows[0]["subject_rollups_json"][0]["max_desirability_score"] = 10.0
    moved = build_full_source_manifest(load_source_state(FakeClient(rows)))
    assert moved["manifest_hash"] != baseline["manifest_hash"]


def test_the_manifest_moves_when_diagnostics_change():
    baseline = build_full_source_manifest(_state()[0])
    rows = _fixture_rows()
    rows[0]["diagnostics_json"] = {"canonical_cards_seen": 101}
    moved = build_full_source_manifest(load_source_state(FakeClient(rows)))
    assert moved["manifest_hash"] != baseline["manifest_hash"]


def test_the_manifest_moves_when_the_pull_model_changes():
    state = load_source_state(FakeClient(_fixture_rows()),
                             pull_model_loader=lambda c: {"s1": {"rare": {"probability": 0.1, "slot_group": "a"}}})
    other = load_source_state(FakeClient(_fixture_rows()),
                              pull_model_loader=lambda c: {"s1": {"rare": {"probability": 0.2, "slot_group": "a"}}})
    assert (build_full_source_manifest(state)["manifest_hash"]
            != build_full_source_manifest(other)["manifest_hash"])


def test_the_manifest_moves_when_the_card_inputs_change():
    state, _ = _state()
    baseline = build_full_source_manifest(state, _subjects())
    moved_subjects = copy.deepcopy(_subjects())
    moved_subjects["s1"][0]["cards"][0]["pull_probability"] = 0.5
    assert build_full_source_manifest(state, moved_subjects)["manifest_hash"] != baseline["manifest_hash"]


def test_the_manifest_moves_when_the_simulation_cohort_changes():
    state = load_source_state(FakeClient(_fixture_rows()), simulation_loader=lambda c: {"s1": {}})
    other = load_source_state(FakeClient(_fixture_rows()), simulation_loader=lambda c: {"s1": {}, "s2": {}})
    assert (build_full_source_manifest(state)["manifest_hash"]
            != build_full_source_manifest(other)["manifest_hash"])


def test_the_manifest_is_stable_for_identical_state():
    state, _ = _state()
    assert (build_full_source_manifest(state, _subjects())["manifest_hash"]
            == build_full_source_manifest(state, _subjects())["manifest_hash"])


def test_the_manifest_ignores_row_ordering():
    forward = load_source_state(FakeClient(_fixture_rows()))
    backward = load_source_state(FakeClient(list(reversed(_fixture_rows()))))
    assert (build_full_source_manifest(forward)["manifest_hash"]
            == build_full_source_manifest(backward)["manifest_hash"])


# ---------------------------------------------------------------------------
# RIP coverage reporting
# ---------------------------------------------------------------------------

def test_rip_coverage_splits_the_cohort_into_available_and_unavailable():
    state = load_source_state(
        FakeClient(_fixture_rows()), simulation_loader=lambda c: {"s1": {}, "s2": {}}
    )
    plan = build_update_plan(state, subject_builder=lambda sid: _subjects().get(sid))
    coverage = rip_consumed_coverage(plan)

    assert coverage["rip_consumed_total"] == 2
    assert [entry["set_id"] for entry in coverage["available"]] == ["s1"]
    assert [entry["set_id"] for entry in coverage["unavailable"]] == ["s2"]
    assert coverage["unavailable"][0]["reason"] == "unsupported_product_type"


def test_rip_coverage_counts_a_missing_source_row_as_unavailable():
    rows = [
        _row("s1", "evolvingSkies", 70.0),
        _row("chaos", "chaosRising", 60.0, hit_policy=V1, row_id="row-chaos-v1"),
    ]
    state = load_source_state(FakeClient(rows), simulation_loader=lambda c: {"s1": {}, "chaos": {}})
    plan = build_update_plan(state, subject_builder=lambda sid: _subjects().get(sid))
    coverage = rip_consumed_coverage(plan)

    unavailable = next(e for e in coverage["unavailable"] if e["set_id"] == "chaos")
    assert unavailable["reason"] == "missing_current_component_source_row"
    assert plan["counts"]["rip_consumed_collector_appeal_unavailable"] == 1
    assert plan["counts"]["rip_consumed_collector_appeal_available"] == 1
    assert plan["counts"]["rip_consumed_total"] == 2


def test_counts_report_rip_consumed_totals_separately_from_universal_coverage():
    state = load_source_state(FakeClient(_fixture_rows()), simulation_loader=lambda c: {"s1": {}, "s2": {}})
    plan = build_update_plan(state, subject_builder=lambda sid: _subjects().get(sid))
    counts = plan["counts"]
    assert counts["rip_consumed_total"] == 2
    assert counts["rip_consumed_collector_appeal_available"] == 1
    assert counts["rip_consumed_collector_appeal_unavailable"] == 1


# ---------------------------------------------------------------------------
# Write strategy description
# ---------------------------------------------------------------------------

def test_the_write_strategy_is_a_primary_key_update_with_concurrency():
    strategy = describe_write_strategy()
    assert strategy["method"] == "update"
    assert strategy["rows_per_statement"] == 1
    assert strategy["writable_columns"] == ["diagnostics_json"]
    assert "id = <source_row_id>" in strategy["predicate"]
    assert "updated_at" in strategy["predicate"]
    assert "FORBIDDEN" in strategy["upsert"]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def test_pagination_reads_every_page_and_proves_no_truncation():
    rows = [_row(f"s{i}", "evolvingSkies", 1.0) for i in range(250)]
    result = paged_select_all(FakeQuery(rows, []), page_size=100)
    assert len(result["rows"]) == 250
    assert [page["returned"] for page in result["pagination"]["pages"]] == [100, 100, 50]
    assert result["pagination"]["final_page_partial"] is True
    assert result["pagination"]["truncation_possible"] is False


def test_a_511_row_table_is_not_truncated_by_the_default_page_size():
    rows = [_row(f"s{i}", "evolvingSkies", 1.0) for i in range(511)]
    result = paged_select_all(FakeQuery(rows, []), page_size=1000)
    assert result["pagination"]["total_rows"] == 511
    assert result["pagination"]["final_page_partial"] is True


# ---------------------------------------------------------------------------
# Classification carried into the plan
# ---------------------------------------------------------------------------

def test_plan_classifies_supported_and_unsupported_products():
    state, _ = _state()
    plan = build_update_plan(state)
    by_id = {row["set_id"]: row for row in plan["rows"]}
    assert by_id["s1"]["booster_supported"] is True
    assert by_id["s2"]["product_support_type"] == "unsupported_promo_product"
    assert by_id["s3"]["product_support_type"] == "unsupported_trainer_kit"
    assert plan["counts"]["booster_supported"] == 1
    assert plan["counts"]["unsupported"] == 2


def test_unsupported_products_get_collector_appeal_unavailable_with_a_reason():
    state, _ = _state()
    plan = build_update_plan(state)
    promo = next(row for row in plan["rows"] if row["set_id"] == "s2")
    assert promo["collector_appeal_available"] is False
    assert promo["collector_appeal_value"] is None
    assert promo["collector_appeal_unavailable_reason"] == "unsupported_product_type"


def test_collector_appeal_is_none_not_zero_when_dual_path_is_unavailable():
    state, _ = _state()
    plan = build_update_plan(state)
    supported = next(row for row in plan["rows"] if row["set_id"] == "s1")
    assert supported["collector_appeal_value"] is None
    assert supported["collector_appeal_unavailable_reason"] == "dual_path_depth_unavailable_no_pull_model"


def test_a_pull_modeled_set_with_no_subjects_is_not_reported_as_unmodeled():
    """"No pack model" and "a pack model that matched nothing" are different
    failures with different fixes. Lost Origin is the production case: it HAS a
    pull model, and reporting it as unmodeled would send someone to rebuild data
    that already exists."""
    state = load_source_state(
        FakeClient(_fixture_rows()),
        pull_model_loader=lambda c: {"s1": {"rare": {"probability": 0.1, "slot_group": "a"}}},
    )
    plan = build_update_plan(state, subject_builder=lambda sid: None)
    row = next(r for r in plan["rows"] if r["set_id"] == "s1")
    assert row["collector_appeal_unavailable_reason"] == "dual_path_depth_unavailable_no_modeled_subject"

    unmodeled = next(r for r in plan["rows"] if r["set_id"] == "s2")
    assert unmodeled["collector_appeal_unavailable_reason"] != "dual_path_depth_unavailable_no_modeled_subject"


def test_collector_appeal_is_computed_when_dual_path_is_available():
    state, _ = _state()
    plan = build_update_plan(state, subject_builder=lambda sid: _subjects().get(sid))
    row = next(r for r in plan["rows"] if r["set_id"] == "s1")
    assert row["collector_appeal_available"] is True
    block = row["proposed_diagnostics"][COLLECTOR_APPEAL_DIAGNOSTICS_KEY]
    d = block["inputs"]["roster_desirability_d"] / 100.0
    assert row["collector_appeal_value"] == pytest.approx(d + 0.5 * 1.0 * (1 - d), abs=1e-6)
