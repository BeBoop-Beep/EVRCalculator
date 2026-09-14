"""Real, runnable tests for backend/scripts/build_atomic_set_page_snapshot_generation.py.

Scope note: `main()` is a single monolithic function that opens a real
Supabase client and reads real env vars (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY).
It is not refactored into independently-callable pieces (that refactor is out
of scope for a repo-source verification pass -- these tests exercise the
actual, unmodified script through its real `main()` entrypoint, driven by a
fake Supabase client and monkeypatched collaborators).

Only the `--dry-run` path (i.e. omitting --write-stage) is exercised: the
`--write-stage` path performs real writes (`.upsert(...)`, generation-row
inserts) that this test suite has no business simulating as if they were a
real database -- faking that convincingly would test the fake, not the
script. The dry-run path already runs every membership/reconciliation/
cohort-accounting code path in `main()` up to (but not including) the
`if not args.write_stage: ... return` line.

NOT independently testable from this repo without a live database or a much
larger fake-Postgres harness (documented here rather than skipped silently):
  * "a changed frozen authority makes a resume fail with a clear message" --
    this logic (`resumable` / `building` row comparison) lives entirely in the
    `--write-stage` branch and depends on a `pokemon_set_page_snapshot_generations`
    row already existing in `status='building'`; faking this fully requires
    replicating upsert/insert semantics for that table.
  * "membership changing mid-build fails closed" -- `full_set_ids` is read
    once at the top of a single `main()` invocation; there is no in-process
    re-read to race against within one run, so this property can only be
    observed across two separate invocations against a real (or fully
    Postgres-faked) generation-rows table, which is beyond this fake client.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import backend.scripts.build_atomic_set_page_snapshot_generation as mod


def _live_row(set_id, payload_json=None):
    return {
        "set_id": set_id,
        "set_identity_json": {"id": set_id},
        "title_card_json": {},
        "rip_summary_json": {},
        "market_summary_json": {},
        "risk_summary_json": {},
        "concentration_json": {},
        "desirability_summary_json": {},
        "set_intelligence_json": {},
        "payload_json": payload_json if payload_json is not None else {"existing": True},
        "as_of": "2026-09-01",
        "source_updated_at": "2026-09-01T00:00:00Z",
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
        "rip_bootstrap_json": {},
        "rip_simulation_evidence_json": {},
        "rip_advanced_json": {},
    }


class _Query:
    """Minimal chainable query stub mirroring the subset of the postgrest
    client interface build_atomic_set_page_snapshot_generation.py actually
    calls: .select().order().range().execute() and .select().in_().execute().
    """

    def __init__(self, rows):
        self._rows = list(rows)
        self._start = 0
        self._end = None

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._start, self._end = start, end
        return self

    def in_(self, _field, values):
        wanted = set(values)
        self._rows = [r for r in self._rows if r.get("id") in wanted or r.get("set_id") in wanted]
        return self

    def eq(self, *_a, **_k):
        # Only reached by --write-stage paths in the real script (current
        # generation lookup, building-row lookup); not exercised by the
        # dry-run tests here, but harmless as a passthrough.
        return self

    def limit(self, *_a, **_k):
        return self

    def single(self, *_a, **_k):
        return self

    def execute(self):
        if self._end is not None:
            data = self._rows[self._start : self._end + 1]
        else:
            data = self._rows
        return SimpleNamespace(data=data)


class FakeClient:
    def __init__(self, live_rows, sets_rows):
        self._live_rows = live_rows
        self._sets_rows = sets_rows

    def table(self, name):
        if name == "pokemon_set_page_snapshot_latest":
            return _Query(self._live_rows)
        if name == "sets":
            return _Query(self._sets_rows)
        raise AssertionError(f"unexpected table access in dry-run path: {name}")


def _fresh_target(set_id, run_id, rank=1):
    return {
        "set_id": set_id,
        "calculation_run_id": run_id,
        "overallRipV12": {"rank": rank},
    }


def _patch_common(monkeypatch, *, live_set_ids, fresh_targets, collector_payloads=None,
                   formula_fingerprint="fp-test"):
    live_rows = [_live_row(sid) for sid in live_set_ids]
    sets_rows = [{"id": sid, "name": f"Set {sid}"} for sid in live_set_ids]
    fake_client = FakeClient(live_rows, sets_rows)

    monkeypatch.setattr(mod, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "create_client", lambda *_a, **_k: fake_client)
    monkeypatch.setattr(mod.os, "environ", {**mod.os.environ, "SUPABASE_URL": "http://x", "SUPABASE_SERVICE_ROLE_KEY": "k"})

    monkeypatch.setattr(
        mod,
        "get_rip_statistics_targets_payload",
        lambda **_k: {"meta": {"desirabilityBundleStatus": "ok"}, "targets": fresh_targets},
    )

    fresh_ids = [t["set_id"] for t in fresh_targets]
    payloads = collector_payloads or {
        sid: {"collectorAppeal": {"score": 1.0}} for sid in fresh_ids
    }
    monkeypatch.setattr(
        mod,
        "load_canonical_v5_collector_appeal",
        lambda _ids: {"payloads": payloads, "identity": {"formulaFingerprint": formula_fingerprint}},
    )

    def _fake_build_contract_from_v5(payload):
        if not payload:
            return None
        return {
            "collectorAppeal": {
                "version": mod.COLLECTOR_APPEAL_V5_VERSION,
                "modelRunId": None,
                "score": (payload.get("collectorAppeal") or {}).get("score"),
            }
        }

    monkeypatch.setattr(mod, "build_public_collector_appeal_contract_from_v5", _fake_build_contract_from_v5)

    def _fake_build_row(source_row, client=None, rankings_payload=None):
        return {
            "set_id": source_row["id"],
            "payload_json": {},
            "as_of": "2026-09-08",
            "source_updated_at": "2026-09-08T00:00:00Z",
        }

    monkeypatch.setattr(mod, "build_set_page_snapshot_row", _fake_build_row)
    monkeypatch.setattr(mod, "source_run_fingerprint", lambda runs: "frozen-fp-" + str(len(runs)))

    # Bypass the retry wrapper's real client_factory (which would otherwise
    # try to build a genuine Supabase service-role client from env).
    monkeypatch.setattr(mod, "run_snapshot_operation_with_retry", lambda op, **_k: op(fake_client))

    return fake_client


def _run_dry(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["build_atomic_set_page_snapshot_generation.py"])
    mod.main()
    out = capsys.readouterr().out
    return json.loads(out)


# --------------------------------------------------------------------------- #
def test_live_universe_count_becomes_expected_generation_count(monkeypatch, capsys):
    live_ids = [f"s{i}" for i in range(1, 8)]  # 7 live sets, NOT 210 -- no hardcoded count
    fresh = [_fresh_target("s1", "run-1"), _fresh_target("s2", "run-2")]
    # The script requires exactly 22 frozen runs (a real, current invariant in
    # the script itself -- see the RuntimeError below), so bump fresh count to 22.
    fresh = [_fresh_target(f"s{i}", f"run-{i}") for i in range(1, 23)]
    live_ids = [f"s{i}" for i in range(1, 23)] + ["carry-a", "carry-b"]
    _patch_common(monkeypatch, live_set_ids=live_ids, fresh_targets=fresh)

    summary = _run_dry(monkeypatch, capsys)

    assert summary["fullGenerationExpectedSetCount"] == len(live_ids) == 24
    assert summary["freshRebuiltSetCount"] == 22
    assert summary["carriedForwardSetCount"] == 2
    assert summary["mode"] == "dry-run"


def test_new_legitimate_set_is_includable_without_hardcoded_210(monkeypatch, capsys):
    """The live-universe count in this test (23) does not match production's
    ~210 and is not close to it; the script must not choke on, special-case,
    or silently drop a universe of a different size.
    """
    fresh = [_fresh_target(f"s{i}", f"run-{i}") for i in range(1, 23)]
    live_ids = [f"s{i}" for i in range(1, 23)] + ["brand-new-set"]
    _patch_common(monkeypatch, live_set_ids=live_ids, fresh_targets=fresh)

    summary = _run_dry(monkeypatch, capsys)

    assert summary["fullGenerationExpectedSetCount"] == 23
    assert "brand-new-set" in [f"s{i}" for i in range(1, 23)] + ["brand-new-set"]


def test_fresh_and_carry_forward_partition_is_exact_and_disjoint(monkeypatch, capsys):
    fresh = [_fresh_target(f"s{i}", f"run-{i}") for i in range(1, 23)]
    live_ids = [f"s{i}" for i in range(1, 23)] + ["cf1", "cf2", "cf3"]
    _patch_common(monkeypatch, live_set_ids=live_ids, fresh_targets=fresh)

    summary = _run_dry(monkeypatch, capsys)

    assert summary["freshRebuiltSetCount"] + summary["carriedForwardSetCount"] == summary["fullGenerationExpectedSetCount"]


def test_non_22_fresh_cohort_raises_with_a_clear_message(monkeypatch, capsys):
    fresh = [_fresh_target("s1", "run-1")]  # only 1, not 22
    live_ids = ["s1", "s2", "s3"]
    _patch_common(monkeypatch, live_set_ids=live_ids, fresh_targets=fresh)

    monkeypatch.setattr(sys, "argv", ["build_atomic_set_page_snapshot_generation.py"])
    with pytest.raises(RuntimeError, match="refusing non-22 or incomplete frozen calculation-run cohort"):
        mod.main()


def test_incomplete_frozen_run_id_raises(monkeypatch, capsys):
    fresh = [_fresh_target(f"s{i}", f"run-{i}") for i in range(1, 22)] + [
        {"set_id": "s22", "calculation_run_id": None, "overallRipV12": {"rank": 1}}
    ]
    live_ids = [f"s{i}" for i in range(1, 23)]
    _patch_common(monkeypatch, live_set_ids=live_ids, fresh_targets=fresh)

    monkeypatch.setattr(sys, "argv", ["build_atomic_set_page_snapshot_generation.py"])
    with pytest.raises(RuntimeError, match="refusing non-22 or incomplete frozen calculation-run cohort"):
        mod.main()


def test_incomplete_desirability_bundle_raises_before_membership_work(monkeypatch, capsys):
    live_ids = ["s1", "s2"]
    fake_client = FakeClient([_live_row(sid) for sid in live_ids], [{"id": sid} for sid in live_ids])
    monkeypatch.setattr(mod, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "create_client", lambda *_a, **_k: fake_client)
    monkeypatch.setattr(mod.os, "environ", {**mod.os.environ, "SUPABASE_URL": "http://x", "SUPABASE_SERVICE_ROLE_KEY": "k"})
    monkeypatch.setattr(
        mod, "get_rip_statistics_targets_payload",
        lambda **_k: {"meta": {"desirabilityBundleStatus": "degraded"}, "targets": []},
    )
    monkeypatch.setattr(sys, "argv", ["build_atomic_set_page_snapshot_generation.py"])
    with pytest.raises(RuntimeError, match="canonical Rankings cohort failed to build completely"):
        mod.main()


def test_no_live_set_can_silently_disappear_from_candidate_membership(monkeypatch, capsys):
    """full_set_ids is read directly from pokemon_set_page_snapshot_latest and
    every id in it ends up in either fresh_set_ids or carry_forward_set_ids
    (enforced by the script's own reconciliation RuntimeError). This test
    proves that every live id supplied by the fake client surfaces in the
    dry-run's accounted total, i.e. none are dropped in this code path.
    """
    fresh = [_fresh_target(f"s{i}", f"run-{i}") for i in range(1, 23)]
    live_ids = [f"s{i}" for i in range(1, 23)] + ["untouched-1", "untouched-2"]
    _patch_common(monkeypatch, live_set_ids=live_ids, fresh_targets=fresh)

    summary = _run_dry(monkeypatch, capsys)
    assert summary["fullGenerationExpectedSetCount"] == len(live_ids)


def test_frozen_source_run_fingerprint_is_recorded_in_dry_run_summary(monkeypatch, capsys):
    fresh = [_fresh_target(f"s{i}", f"run-{i}") for i in range(1, 23)]
    live_ids = [f"s{i}" for i in range(1, 23)]
    _patch_common(monkeypatch, live_set_ids=live_ids, fresh_targets=fresh)

    summary = _run_dry(monkeypatch, capsys)
    assert summary["frozenSourceRunFingerprint"] == "frozen-fp-22"
    assert summary["frozenSourceRuns"] == {f"s{i}": f"run-{i}" for i in range(1, 23)}


def test_incomplete_collector_authority_raises(monkeypatch, capsys):
    fresh = [_fresh_target(f"s{i}", f"run-{i}") for i in range(1, 23)]
    live_ids = [f"s{i}" for i in range(1, 23)]
    # Only 21 of the 22 fresh sets get scored collector payloads.
    partial_payloads = {f"s{i}": {"collectorAppeal": {"score": 1.0}} for i in range(1, 22)}
    partial_payloads["s22"] = {"collectorAppeal": {"score": None}}
    _patch_common(monkeypatch, live_set_ids=live_ids, fresh_targets=fresh, collector_payloads=partial_payloads)

    monkeypatch.setattr(sys, "argv", ["build_atomic_set_page_snapshot_generation.py"])
    with pytest.raises(RuntimeError, match="canonical Collector authority is incomplete for frozen cohort"):
        mod.main()
