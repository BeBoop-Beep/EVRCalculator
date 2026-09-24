from backend.scripts import repair_missing_market_set_value_history as repair


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        return _Result(self.rows)


class _Client:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _name):
        return _Query(self.rows)


def test_read_present_scopes_only_accepts_positive_priced_rows(monkeypatch):
    client = _Client([
        {"set_id": "a", "value_scope": "standard", "set_value": 10, "priced_card_count": 5},
        {"set_id": "a", "value_scope": "top10", "set_value": 4, "priced_card_count": 2},
        {"set_id": "b", "value_scope": "standard", "set_value": 0, "priced_card_count": 5},
        {"set_id": "b", "value_scope": "top10", "set_value": 3, "priced_card_count": 0},
    ])
    monkeypatch.setattr(
        repair,
        "run_supabase_with_transient_retry",
        lambda operation, **_kwargs: operation(client, 1),
    )
    present = repair._read_present_scopes(
        client, market_date="2026-09-22", set_ids=["a", "b"]
    )
    assert present["a"] == {"standard", "top10"}
    assert present["b"] == set()


def test_dry_run_reports_missing_without_refreshing(monkeypatch):
    calls = []
    monkeypatch.setattr(
        repair,
        "missing_market_root_set_ids",
        lambda *_a, **_k: ["b"],
    )
    monkeypatch.setattr(
        repair,
        "_refresh_one",
        lambda *_a, **_k: calls.append(True) or 1,
    )
    report = repair.repair_missing_market_set_values(
        object(),
        market_date="2026-09-22",
        commit=False,
        set_ids=["a", "b"],
    )
    assert report["missing_before_count"] == 1
    assert report["missing_after_count"] == 1
    assert report["ok"] is True
    assert calls == []


def test_commit_rechecks_and_retries_only_remaining_sets(monkeypatch):
    states = iter([
        ["b", "c"],  # before
        ["c"],       # after pass 1
        [],          # after pass 2
        [],          # final report read
    ])
    monkeypatch.setattr(
        repair,
        "missing_market_root_set_ids",
        lambda *_a, **_k: next(states),
    )
    calls = []
    monkeypatch.setattr(
        repair,
        "_refresh_one",
        lambda set_id, market_date: calls.append((set_id, market_date)) or 2,
    )
    monkeypatch.setattr(repair.time, "sleep", lambda *_a, **_k: None)

    report = repair.repair_missing_market_set_values(
        object(),
        market_date="2026-09-22",
        commit=True,
        max_passes=3,
        set_ids=["a", "b", "c"],
    )
    assert calls == [
        ("b", "2026-09-22"),
        ("c", "2026-09-22"),
        ("c", "2026-09-22"),
    ]
    assert report["missing_after_count"] == 0
    assert report["passes_run"] == 2
    assert report["ok"] is True


def test_commit_fails_closed_when_coverage_still_missing(monkeypatch):
    monkeypatch.setattr(
        repair,
        "missing_market_root_set_ids",
        lambda *_a, **_k: ["b"],
    )
    monkeypatch.setattr(repair, "_refresh_one", lambda *_a, **_k: 0)
    monkeypatch.setattr(repair.time, "sleep", lambda *_a, **_k: None)

    report = repair.repair_missing_market_set_values(
        object(),
        market_date="2026-09-22",
        commit=True,
        max_passes=2,
        set_ids=["a", "b"],
    )
    assert report["missing_after_count"] == 1
    assert report["ok"] is False
