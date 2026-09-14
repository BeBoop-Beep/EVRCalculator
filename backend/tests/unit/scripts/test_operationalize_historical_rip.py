from datetime import date, datetime, timezone

from backend.scripts import operationalize_historical_rip as subject


class _Result:
    def __init__(self, data): self.data = data


class _Rpc:
    def __init__(self, value): self.value = value
    def execute(self): return _Result(self.value)


class _Client:
    def __init__(self, inserted=0): self.inserted = inserted; self.calls = []
    def rpc(self, name, payload):
        self.calls.append((name, payload)); return _Rpc(self.inserted)


def _plan(all_fresh=True):
    return {"freshness":{"allFresh":all_fresh,"sources":[{"key":"artist_12m","due":not all_fresh}]},
            "rowsPlanned":128,"scoredRows":22,"unavailableRows":106,
            "providerCallsPlanned":0,"rowsToAppend":128,"modelRunId":"old-model",
            "sourceAuthority":{"pokemonTrends":"p","trainer12m":"t12","trainer5y":"t5",
                               "playability":"play","artist12m":"a12","artist5y":"a5"}}


def test_dry_run_has_zero_mutation_and_zero_provider_calls(monkeypatch):
    monkeypatch.setattr(subject, "build_plan", lambda *_a, **_k: _plan())
    client = _Client()
    result = subject.execute(client, as_of=date(2026,9,11),
                             now=datetime.now(timezone.utc), commit=False)
    assert result["status"] == "VALIDATED_DRY_RUN"
    assert result["mutationsPerformed"] == result["providerCallsPlanned"] == 0
    assert client.calls == []


def test_stale_dry_run_plans_only_due_source_without_provider_call(monkeypatch):
    monkeypatch.setattr(subject, "build_plan", lambda *_a, **_k: _plan(False))
    client = _Client()
    result = subject.execute(client, as_of=date(2026,9,18),
                             now=datetime.now(timezone.utc), commit=False)
    assert result["status"] == "COLLECTOR_SOURCE_REFRESH_PLANNED"
    assert result["dueSources"] == ["artist_12m"] and client.calls == []


def test_commit_uses_idempotent_database_append(monkeypatch):
    monkeypatch.setattr(subject, "build_plan", lambda *_a, **_k: _plan())
    client = _Client(inserted=0)
    result = subject.execute(client, as_of=date(2026,9,11),
                             now=datetime.now(timezone.utc), commit=True)
    assert result["status"] == "ALREADY_PRESENT" and result["mutationsPerformed"] == 0
    assert client.calls[0][0] == "append_current_collector_v7_history"


def _hooks(refresh=None, build=None, persist=None, pages=None):
    return subject.RefreshHooks(
        refresh or (lambda *_a: "new-a12"),
        build or (lambda *_a: {"manifest":{"formulaFingerprint":subject.FROZEN_FORMULA_FINGERPRINT,
                                             "analysis":{"cardArtistStatusCounts":{"SCORED":1}}},
                                      "sets":[{"set_id":"s","collector_appeal":51}]}),
        persist or (lambda *_a: ("new-model",{"passed":True},True)),
        pages or (lambda *_a: {"status":"validated","generationId":"generation"}),
    )


def test_one_stale_source_rebuilds_with_fresh_ids_preserved(monkeypatch):
    monkeypatch.setattr(subject,"build_plan",lambda *_a,**_k:_plan(False))
    monkeypatch.setattr(subject,"validate_source_run",lambda *_a,**_k:{"usable_for_model":True})
    paged_results=iter(([{"set_id":"s","score_status":"scored","collector_appeal_score":50}],[]))
    monkeypatch.setattr(subject,"_paged",lambda _factory:next(paged_results))
    captured={}
    hooks=_hooks(build=lambda _c,a:(captured.update(a) or {"manifest":{"formulaFingerprint":subject.FROZEN_FORMULA_FINGERPRINT,"analysis":{}},"cards":[],"sets":[{"set_id":"s","collector_appeal":51}]}))
    client=_Client(inserted=128)
    result=subject.execute(client,as_of=date(2026,9,18),now=datetime.now(timezone.utc),commit=True,hooks=hooks)
    assert result["status"]=="COLLECTOR_HISTORY_APPENDED"
    assert captured["artist12m"]=="new-a12" and captured["trainer5y"]=="t5"
    assert any(name=="promote_pokemon_collector_v7_with_set_page_generation" for name,_ in client.calls)


def test_refresh_or_model_failure_never_promotes(monkeypatch):
    monkeypatch.setattr(subject,"build_plan",lambda *_a,**_k:_plan(False))
    client=_Client()
    hooks=_hooks(refresh=lambda *_a: (_ for _ in ()).throw(RuntimeError("provider failed")))
    result=subject.execute(client,as_of=date(2026,9,18),now=datetime.now(timezone.utc),commit=True,hooks=hooks)
    assert result["status"]=="COLLECTOR_SOURCE_REFRESH_BLOCKED"
    assert not any(name=="promote_pokemon_collector_v7_with_set_page_generation" for name,_ in client.calls)


def test_formula_drift_blocks_before_persistence_or_promotion(monkeypatch):
    monkeypatch.setattr(subject,"build_plan",lambda *_a,**_k:_plan(False))
    monkeypatch.setattr(subject,"validate_source_run",lambda *_a,**_k:{})
    hooks=_hooks(build=lambda *_a:{"manifest":{"formulaFingerprint":"drift"},"sets":[]})
    client=_Client(); result=subject.execute(client,as_of=date(2026,9,18),now=datetime.now(timezone.utc),commit=True,hooks=hooks)
    assert "V7_FROZEN_FORMULA_DRIFT_BLOCKER" in result["error"]
    assert client.calls==[]
