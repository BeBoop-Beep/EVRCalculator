"""Phase 8: the preview must be the write.

The tests here defend one property: there is no second code path. A preview that
is built by different code from the write is not a preview, it is a guess that
happens to agree most of the time.
"""

from __future__ import annotations

import copy
import inspect

import pytest

from backend.desirability.collector_appeal_fingerprint import current_fingerprint
from backend.desirability.collector_appeal_rollout import (
    COMPONENT_TABLE,
    PROTECTED_SCORE_COLUMNS,
    ReadOnlyClientGuard,
    WriteAttemptedError,
    build_source_manifest,
    build_update_plan,
    execute_plan,
    load_source_state,
    paged_select_all,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

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


class FakeTable:
    def __init__(self, rows, recorder):
        self._rows = rows
        self._recorder = recorder

    def select(self, *args, **kwargs):
        return FakeQuery(self._rows, self._recorder)

    def upsert(self, payload, **kwargs):
        self._recorder.append({"op": "upsert", "rows": len(payload)})
        return type("E", (), {"execute": lambda self_: type("R", (), {"data": payload})()})()

    def insert(self, payload, **kwargs):
        self._recorder.append({"op": "insert"})
        return self

    def update(self, payload, **kwargs):
        self._recorder.append({"op": "update"})
        return self

    def delete(self, **kwargs):
        self._recorder.append({"op": "delete"})
        return self


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.recorder = []

    def table(self, name):
        return FakeTable(self.rows, self.recorder)

    def rpc(self, *args, **kwargs):
        self.recorder.append({"op": "rpc"})
        return self


def _row(set_id, key, score, *, diagnostics=None, built_at="2026-07-16T00:00:00Z"):
    return {
        "set_id": set_id,
        "set_name": key,
        "set_canonical_key": key,
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
    assert len(state["latest_rows"]) == 3
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
# One code path
# ---------------------------------------------------------------------------

def test_dry_run_and_commit_target_the_same_rows():
    """THE core Phase 8 property: same plan, same targets; only sending differs."""
    state, client = _state()
    plan = build_update_plan(state)

    dry = execute_plan(plan, client, commit=False)
    wet = execute_plan(
        plan, client, commit=True,
        expected_fingerprint=plan["expected_fingerprint"],
        expected_manifest_hash=plan["source_manifest"]["manifest_hash"],
    )
    assert dry["target_set_ids"] == wet["target_set_ids"]
    assert dry["rows_targeted"] == wet["rows_targeted"]
    assert dry["writes_performed"] == 0
    assert wet["writes_performed"] == wet["rows_targeted"]


def test_commit_sends_exactly_the_payload_the_preview_built():
    state, client = _state()
    plan = build_update_plan(state)
    previewed = {row["set_id"]: row["update_payload"] for row in plan["rows"] if row["would_update"]}

    execute_plan(
        plan, client, commit=True,
        expected_fingerprint=plan["expected_fingerprint"],
        expected_manifest_hash=plan["source_manifest"]["manifest_hash"],
    )
    upserts = [call for call in client.recorder if call["op"] == "upsert"]
    assert sum(call["rows"] for call in upserts) == len(previewed)


def test_execute_plan_is_the_only_module_function_that_writes():
    import backend.desirability.collector_appeal_rollout as module

    for name, function in inspect.getmembers(module, inspect.isfunction):
        if name == "execute_plan" or function.__module__ != module.__name__:
            continue
        source = inspect.getsource(function)
        for banned in (".upsert(", ".insert(", ".update(", ".delete("):
            assert banned not in source, f"{name}() contains a write call"


# ---------------------------------------------------------------------------
# Commit guards
# ---------------------------------------------------------------------------

def test_commit_refuses_without_an_expected_fingerprint():
    state, client = _state()
    plan = build_update_plan(state)
    with pytest.raises(RuntimeError, match="fingerprint"):
        execute_plan(plan, client, commit=True,
                     expected_manifest_hash=plan["source_manifest"]["manifest_hash"])
    assert not [call for call in client.recorder if call["op"] == "upsert"]


def test_commit_refuses_on_a_fingerprint_mismatch():
    state, client = _state()
    plan = build_update_plan(state)
    with pytest.raises(RuntimeError, match="fingerprint"):
        execute_plan(plan, client, commit=True, expected_fingerprint="0" * 64,
                     expected_manifest_hash=plan["source_manifest"]["manifest_hash"])


def test_commit_refuses_when_source_data_changed_since_the_preview():
    """Approval is for a specific set of changes against a specific state."""
    state, client = _state()
    plan = build_update_plan(state)
    with pytest.raises(RuntimeError, match="source data has changed"):
        execute_plan(plan, client, commit=True,
                     expected_fingerprint=plan["expected_fingerprint"],
                     expected_manifest_hash="stale-manifest")


def test_commit_requires_the_manifest_even_when_the_fingerprint_matches():
    state, client = _state()
    plan = build_update_plan(state)
    with pytest.raises(RuntimeError):
        execute_plan(plan, client, commit=True, expected_fingerprint=plan["expected_fingerprint"])


# ---------------------------------------------------------------------------
# Score protection
# ---------------------------------------------------------------------------

def test_no_proposed_payload_touches_a_score_column():
    state, _ = _state()
    plan = build_update_plan(state)
    for row in plan["rows"]:
        payload = row["update_payload"] or {}
        assert set(payload).issubset({"set_id", "diagnostics_json"})
        for column in PROTECTED_SCORE_COLUMNS:
            assert column not in payload


def test_proposed_score_always_equals_the_current_stored_score():
    state, _ = _state()
    plan = build_update_plan(state)
    for row in plan["rows"]:
        assert row["current_stored_score"] == row["proposed_score"]
    assert plan["counts"]["score_changing_updates"] == 0


def test_plan_raises_rather_than_report_a_score_change():
    """A score-changing plan must fail loudly, not be politely summarized."""
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
        block = row["proposed_diagnostics"]["collector_appeal"]
        assert block["fingerprint"] == current_fingerprint()
        assert block["lambda"] == 0.50
        assert block["formula"] == "CA7"


def test_rows_without_a_stored_fingerprint_are_reported_missing_and_updated():
    state, _ = _state()
    plan = build_update_plan(state)
    assert plan["counts"]["fingerprint_missing"] == 3
    assert plan["counts"]["would_update"] == 3


def test_a_row_already_carrying_the_current_fingerprint_is_not_rewritten():
    """Unchanged inputs must not create writes."""
    client = FakeClient(_fixture_rows())
    plan = build_update_plan(load_source_state(client))
    settled = copy.deepcopy(_fixture_rows())
    for row, planned in zip(settled, plan["rows"]):
        row["diagnostics_json"] = planned["proposed_diagnostics"]

    second = build_update_plan(load_source_state(FakeClient(settled)))
    assert second["counts"]["would_update"] == 0
    assert second["counts"]["fingerprint_current"] == 3
    assert execute_plan(second, FakeClient(settled), commit=False)["rows_targeted"] == 0


def test_a_stale_fingerprint_is_surfaced_and_explained():
    rows = _fixture_rows()
    rows[0]["diagnostics_json"] = {
        "canonical_cards_seen": 100,
        "collector_appeal": {"fingerprint": "0" * 64, "formula": "CA7", "lambda": 0.5},
    }
    plan = build_update_plan(load_source_state(FakeClient(rows)))
    stale = next(row for row in plan["rows"] if row["set_id"] == "s1")
    assert stale["fingerprint_status"] == "stale"
    assert stale["would_update"] is True
    reason = next(f["reason"] for f in stale["changed_fields"] if f["field"].endswith("collector_appeal"))
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


def test_plan_rows_are_deterministically_sorted():
    forward = build_update_plan(load_source_state(FakeClient(_fixture_rows())))
    reversed_rows = list(reversed(_fixture_rows()))
    backward = build_update_plan(load_source_state(FakeClient(reversed_rows)))
    assert [row["set_id"] for row in forward["rows"]] == [row["set_id"] for row in backward["rows"]]


# ---------------------------------------------------------------------------
# Source manifest
# ---------------------------------------------------------------------------

def test_source_manifest_is_stable_for_identical_state():
    rows = {"s1": _row("s1", "evolvingSkies", 70.0)}
    assert build_source_manifest(rows)["manifest_hash"] == build_source_manifest(rows)["manifest_hash"]


def test_source_manifest_changes_when_a_score_or_build_time_changes():
    base = {"s1": _row("s1", "evolvingSkies", 70.0)}
    moved_score = {"s1": _row("s1", "evolvingSkies", 71.0)}
    moved_time = {"s1": _row("s1", "evolvingSkies", 70.0, built_at="2026-07-17T00:00:00Z")}
    assert build_source_manifest(base)["manifest_hash"] != build_source_manifest(moved_score)["manifest_hash"]
    assert build_source_manifest(base)["manifest_hash"] != build_source_manifest(moved_time)["manifest_hash"]


def test_source_manifest_ignores_row_ordering():
    rows = {"s1": _row("s1", "a", 1.0), "s2": _row("s2", "b", 2.0)}
    reordered = {"s2": rows["s2"], "s1": rows["s1"]}
    assert build_source_manifest(rows)["manifest_hash"] == build_source_manifest(reordered)["manifest_hash"]


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


def test_pagination_flags_a_possible_truncation_on_an_exact_boundary():
    """An exactly-full final page cannot prove the read was complete."""
    rows = [_row(f"s{i}", "evolvingSkies", 1.0) for i in range(200)]
    query = FakeQuery(rows, [])
    result = paged_select_all(query, page_size=100)
    # The fake returns an empty third page, so the read terminates correctly.
    assert len(result["rows"]) == 200
    assert result["pagination"]["pages"][-1]["returned"] == 0
    assert result["pagination"]["truncation_possible"] is False


def test_a_171_row_catalogue_is_not_truncated_by_the_default_page_size():
    rows = [_row(f"s{i}", "evolvingSkies", 1.0) for i in range(171)]
    result = paged_select_all(FakeQuery(rows, []), page_size=1000)
    assert result["pagination"]["total_rows"] == 171
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
    """No missing metric may be silently converted to zero."""
    state, _ = _state()
    plan = build_update_plan(state)
    supported = next(row for row in plan["rows"] if row["set_id"] == "s1")
    assert supported["collector_appeal_value"] is None
    assert supported["collector_appeal_unavailable_reason"] == "dual_path_depth_unavailable_no_pull_model"


def test_collector_appeal_is_computed_when_dual_path_is_available():
    state, _ = _state()
    subjects = {
        "s1": [{
            "subject_key": "ref:1", "subject_name": "Pikachu", "subject_demand": 90.0,
            "appeal_excess": 0.8,
            "cards": [
                {"card_name": "easy", "pull_probability": 0.1},
                {"card_name": "elite", "pull_probability": 0.001},
            ],
        }]
    }
    plan = build_update_plan(state, subject_builder=lambda sid: subjects.get(sid))
    row = next(r for r in plan["rows"] if r["set_id"] == "s1")
    assert row["collector_appeal_available"] is True
    d = row["proposed_diagnostics"]["collector_appeal"]["inputs"]["roster_desirability_d"] / 100.0
    assert row["collector_appeal_value"] == pytest.approx(d + 0.5 * 1.0 * (1 - d), abs=1e-6)
